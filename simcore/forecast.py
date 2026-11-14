"""Metode prakiraan beban yang dipakai endpoint /api/v1/forecast.

Semua fungsi bekerja pada pd.Series beban (MW) ber-index timestamp WITA naive per 30 menit.
Tidak ada dependensi selain numpy & pandas supaya mudah di-deploy.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SLOT = pd.Timedelta(minutes=30)
WEEK = 336  # slot per minggu
WBP_HOURS = (17, 22)  # waktu beban puncak 17.00-22.00


# ---------------------------------------------------------------- utilitas
def clean_history(load: pd.Series, flags: pd.Series | None, exclude_flags: bool = True):
    """Ganti slot berflag (pemadaman, UFR, data hilang) dengan nilai minggu sebelumnya.

    Mengembalikan (series_bersih, jumlah_slot_diganti).
    """
    s = load.astype(float).copy()
    bad = s.isna()
    if exclude_flags and flags is not None:
        bad = bad | flags.reindex(s.index).fillna("NORMAL").ne("NORMAL")
    n_bad = int(bad.sum())
    if n_bad:
        s[bad] = np.nan
        for lag in (WEEK, 2 * WEEK):
            fill = s.shift(lag)
            s = s.fillna(fill)
        s = s.interpolate(limit_direction="both")
    return s, n_bad


def day_kind(day: pd.Timestamp, cal: pd.DataFrame) -> str:
    """Jenis hari untuk koefisien: LEBARAN, LIBUR, CUTI, atau nama hari (0=Senin)."""
    key = day.strftime("%Y-%m-%d")
    if key in cal.index:
        row = cal.loc[key]
        if row["jenis_hari"] == "LIBUR_NAS":
            return "LEBARAN" if "Idulfitri" in str(row["keterangan"]) else "LIBUR"
        if row["jenis_hari"] == "CUTI_BERSAMA":
            return "CUTI"
    return str(day.dayofweek)


def _target_index(start: pd.Timestamp, horizon: int) -> pd.DatetimeIndex:
    return pd.date_range(start, periods=horizon, freq="30min")


# ---------------------------------------------------------------- metode
def seasonal_naive(hist: pd.Series, start: pd.Timestamp, horizon: int) -> pd.Series:
    """Nilai slot yang sama satu minggu sebelumnya (diulang bila horizon > 1 minggu)."""
    idx = _target_index(start, horizon)
    values = []
    known = hist.to_dict()
    for t in idx:
        back = t - pd.Timedelta(days=7)
        while back not in known and back > hist.index[0]:
            back -= pd.Timedelta(days=7)
        v = known.get(back, np.nan)
        known[t] = v
        values.append(v)
    return pd.Series(values, index=idx, name="prakiraan_mw")


def koefisien(hist: pd.Series, cal: pd.DataFrame, start: pd.Timestamp, horizon: int) -> pd.Series:
    """Metode koefisien ala PLN (disederhanakan).

    prakiraan(slot) = beban_puncak_mingguan x koef_harian(jenis_hari) x koef_slot(jenis_hari, slot)
    - beban puncak mingguan: rata-rata puncak 2 minggu terakhir x faktor tren 4 minggu
    - koef harian: puncak hari / puncak minggu itu, dirata-rata 4 minggu terakhir per jenis hari
    - koef slot: beban slot / puncak hari, dirata-rata dari hari sejenis
    Hari libur dan Idulfitri memakai koefisien dari kejadian serupa di histori.
    """
    idx = _target_index(start, horizon)
    hist = hist[hist.index < start]
    daily = hist.resample("D").max().dropna()
    days = daily.index
    kinds = pd.Series([day_kind(d, cal) for d in days], index=days)

    end_day = start.normalize()
    week_peaks = []
    for k in range(4):
        w = daily[(days >= end_day - pd.Timedelta(days=7 * (k + 1))) & (days < end_day - pd.Timedelta(days=7 * k))]
        w = w[kinds.reindex(w.index).str.isdigit()]
        week_peaks.append(w.max() if len(w) else np.nan)
    wp = np.array(week_peaks, dtype=float)
    base_peak = np.nanmean(wp[:2])
    trend = 0.0
    if np.isfinite(wp[0]) and np.isfinite(wp[3]) and wp[3] > 0:
        trend = float(np.clip((wp[0] - wp[3]) / (3 * wp[3]), -0.01, 0.01))

    # koefisien harian & profil slot dari histori
    weekly_max = daily.rolling("7D").max()
    ratio = (daily / weekly_max.shift(1).bfill()).clip(upper=1.05)
    frame = hist.to_frame("mw")
    frame["day"] = frame.index.normalize()
    frame["slot"] = (frame.index.hour * 2 + frame.index.minute // 30)
    frame = frame.join(daily.rename("peak"), on="day")
    frame["rel"] = frame["mw"] / frame["peak"]
    prof = frame.pivot_table(index="day", columns="slot", values="rel")

    def coef_for(kind: str):
        if kind.isdigit():
            pool = [d for d in days[-35:] if kinds[d] == kind]
        else:
            pool = [d for d in days if kinds[d] == kind][-6:]
            if not pool:
                pool = [d for d in days[-35:] if kinds[d] == "6"]  # fallback: Minggu
        pool = [d for d in pool if d in prof.index]
        if not pool:
            pool = list(days[-7:])
        dcoef = float(np.nanmean(ratio.reindex(pool))) if kind.isdigit() else float(
            np.nanmean([daily[d] / daily[(days < d) & (days >= d - pd.Timedelta(days=7))].max() for d in pool]))
        scoef = prof.loc[pool].mean(axis=0)
        return dcoef, scoef

    cache: dict[str, tuple] = {}
    out = []
    for t in idx:
        kind = day_kind(t.normalize(), cal)
        if kind not in cache:
            cache[kind] = coef_for(kind)
        dcoef, scoef = cache[kind]
        weeks_ahead = (t.normalize() - end_day).days / 7.0 + 0.5
        peak = base_peak * (1 + trend * weeks_ahead)
        slot = t.hour * 2 + t.minute // 30
        out.append(peak * dcoef * float(scoef.get(slot, np.nan)))
    return pd.Series(out, index=idx, name="prakiraan_mw")


def holt_winters(hist: pd.Series, start: pd.Timestamp, horizon: int,
                 alpha: float = 0.15, beta: float = 0.002, gamma: float = 0.25) -> pd.Series:
    """Holt-Winters aditif dengan musim mingguan (336 slot). Tidak paham hari libur."""
    y = hist[hist.index < start].to_numpy(dtype=float)[-8 * WEEK:]
    m = WEEK
    if len(y) < 2 * m:
        raise ValueError("Histori minimal 2 minggu untuk holt_winters")
    level = y[:m].mean()
    trend = (y[m:2 * m].mean() - y[:m].mean()) / m
    season = list(y[:m] - level)
    for i in range(len(y)):
        s = season[i % m]
        prev_level = level
        level = alpha * (y[i] - s) + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
        season[i % m] = gamma * (y[i] - level) + (1 - gamma) * s
    n = len(y)
    idx = _target_index(start, horizon)
    vals = [level + (h + 1) * trend + season[(n + h) % m] for h in range(horizon)]
    return pd.Series(vals, index=idx, name="prakiraan_mw")


METHODS = {"koefisien", "seasonal_naive", "holt_winters"}
ALIASES = {"ets": "holt_winters", "hw": "holt_winters", "naive": "seasonal_naive"}


def run(method: str, hist: pd.Series, cal: pd.DataFrame, start: pd.Timestamp, horizon: int) -> pd.Series:
    method = ALIASES.get(method, method)
    if method == "koefisien":
        return koefisien(hist, cal, start, horizon)
    if method == "seasonal_naive":
        return seasonal_naive(hist, start, horizon)
    if method == "holt_winters":
        return holt_winters(hist, start, horizon)
    raise ValueError(f"Metode tidak dikenal: {method}. Pilih: {sorted(METHODS)}")


# ---------------------------------------------------------------- evaluasi
def mape(actual: pd.Series, pred: pd.Series) -> float | None:
    a, p = actual.align(pred, join="inner")
    ok = a.notna() & p.notna() & (a > 0)
    if not ok.any():
        return None
    return float((np.abs(a[ok] - p[ok]) / a[ok]).mean() * 100)


def evaluate(actual: pd.Series, pred: pd.Series) -> dict:
    wbp = pred.index[(pred.index.hour >= WBP_HOURS[0]) & (pred.index.hour < WBP_HOURS[1])]
    a = actual.reindex(pred.index)
    peak_err = None
    if a.notna().any():
        peak_err = float((pred.max() - a.max()) / a.max() * 100)
    return {
        "mape_total_pct": _r(mape(a, pred)),
        "mape_wbp_pct": _r(mape(a.reindex(wbp), pred.reindex(wbp))),
        "error_puncak_pct": _r(peak_err),
        "slot_dibandingkan": int(a.notna().sum()),
    }


def _r(x, nd=2):
    return None if x is None or not np.isfinite(x) else round(float(x), nd)
