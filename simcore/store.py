"""Lapisan data untuk API: query, pagination, feed kotor, forecast.

Bisa dibaca dari CSV (default, tanpa database) atau MySQL (DATA_BACKEND=mysql).
Aturan penting: data dengan waktu setelah "sekarang" disembunyikan, sehingga dataset
terasa hidup (event baru "muncul" seiring waktu). Atur SIM_NOW untuk membekukan waktu.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import uuid
from contextvars import ContextVar

import numpy as np
import pandas as pd

from . import forecast as F

H8 = pd.Timedelta(hours=8)
# diisi middleware dari header X-Sim-Now (hanya untuk key trainer)
SIM_OVERRIDE: ContextVar[str | None] = ContextVar("sim_override", default=None)
TABLES = {
    "gardu_induk": ("gardu_induk.csv", []),
    "bay": ("bay.csv", []),
    "scada_point": ("scada_point.csv", []),
    "kalender": ("kalender.csv", []),
    "gangguan": ("gangguan.csv", ["mulai", "selesai"]),
    "event_soe": ("event_soe.csv.gz", ["ts_event", "ts_received"]),
    "beban_sistem": ("beban_sistem.csv.gz", ["ts"]),
    "telemetry_tm": ("telemetry_tm.csv.gz", ["ts"]),
    "rencana_operasi": ("rencana_operasi.csv.gz", []),
}


class BadRequest(ValueError):
    """Kesalahan input pengguna (diterjemahkan jadi HTTP 400)."""


class NotFound(KeyError):
    """Data tidak ditemukan (HTTP 404)."""


# ------------------------------------------------------------------ waktu
def parse_time(value: str | None, default: pd.Timestamp | None = None) -> pd.Timestamp | None:
    """String waktu -> Timestamp UTC naive. Tanpa zona waktu dianggap WITA."""
    if value is None or value == "":
        return default
    try:
        t = pd.Timestamp(value)
    except Exception as e:  # noqa: BLE001
        raise BadRequest(f"Format waktu tidak dikenali: {value!r}. Contoh: 2026-11-23T06:30 atau 2026-11-23") from e
    if t.tzinfo is not None:
        return t.tz_convert("UTC").tz_localize(None)
    return t - H8


def fmt_ts(s: pd.Series, ms: bool = False) -> pd.Series:
    """Series UTC naive -> string ISO WITA (+08:00)."""
    w = s + H8
    if ms:
        out = w.dt.strftime("%Y-%m-%dT%H:%M:%S.%f").str[:-3] + "+08:00"
    else:
        out = w.dt.strftime("%Y-%m-%dT%H:%M:%S") + "+08:00"
    return out.where(s.notna(), None)


def records(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    clean = df.astype(object).where(pd.notna(df), None)
    out = clean.to_dict("records")
    for r in out:
        for k, v in r.items():
            if isinstance(v, (np.integer,)):
                r[k] = int(v)
            elif isinstance(v, (np.floating,)):
                r[k] = None if math.isnan(v) else float(v)
            elif isinstance(v, (np.bool_,)):
                r[k] = bool(v)
    return out


def paginate(df: pd.DataFrame, page: int, page_size: int, max_size: int = 500) -> dict:
    if page < 1:
        raise BadRequest("page dimulai dari 1")
    if not 1 <= page_size <= max_size:
        raise BadRequest(f"page_size harus 1..{max_size}")
    total = len(df)
    start = (page - 1) * page_size
    chunk = df.iloc[start:start + page_size]
    has_next = start + page_size < total
    return {"data": records(chunk), "page": page, "page_size": page_size, "total": total,
            "next_page": page + 1 if has_next else None}


def _hash(series: pd.Series) -> np.ndarray:
    return (pd.util.hash_pandas_object(series, index=False).to_numpy() % 1000).astype(int)


# ------------------------------------------------------------------ store
class DataStore:
    def __init__(self, frames: dict[str, pd.DataFrame], engine=None):
        self.engine = engine
        self.gi = frames["gardu_induk"]
        self.bay = frames["bay"]
        self.point = frames["scada_point"]
        self.cal = frames["kalender"]
        self.inc = frames["gangguan"].sort_values("mulai").reset_index(drop=True)
        self.ev = frames["event_soe"].sort_values(["ts_event", "event_id"]).reset_index(drop=True)
        self.load = frames["beban_sistem"].sort_values("ts").reset_index(drop=True)
        tele = frames["telemetry_tm"].sort_values(["point_id", "ts"])
        self.tele = {pid: g.reset_index(drop=True) for pid, g in tele.groupby("point_id", sort=False)}
        roh = frames["rencana_operasi"].copy()
        roh["ts"] = pd.to_datetime(roh["tanggal"] + " " + roh["slot_mulai"]) - H8
        self.roh = roh
        self.cal_idx = self.cal.set_index("tanggal")
        lw = self.load.set_index(self.load["ts"] + H8)
        self._load_w = lw["beban_mw"].astype(float)
        self._flag_w = lw["flag"]
        self.reports: list[dict] = []

    # ---- konstruktor
    @classmethod
    def from_csv(cls, data_dir: str) -> "DataStore":
        frames = {}
        for name, (fn, dates) in TABLES.items():
            path = os.path.join(data_dir, fn)
            if not os.path.exists(path):
                raise FileNotFoundError(f"{path} tidak ada. Jalankan: python -m simcore.generate --out {data_dir}")
            frames[name] = pd.read_csv(path, parse_dates=dates or None, keep_default_na=True)
        return cls(frames)

    @classmethod
    def from_mysql(cls, url: str) -> "DataStore":
        from sqlalchemy import create_engine
        engine = create_engine(normalize_mysql_url(url), pool_pre_ping=True)
        frames = {}
        for name, (_, dates) in TABLES.items():
            frames[name] = pd.read_sql_table(name, engine, parse_dates=dates or None)
        return cls(frames, engine=engine)

    @classmethod
    def from_env(cls) -> "DataStore":
        backend = os.getenv("DATA_BACKEND", "csv").lower()
        if backend == "mysql":
            url = os.getenv("DATABASE_URL") or os.getenv("MYSQL_URL")
            if not url:
                raise RuntimeError("DATA_BACKEND=mysql tapi DATABASE_URL/MYSQL_URL kosong")
            return cls.from_mysql(url)
        return cls.from_csv(os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data")))

    # ---- waktu simulasi
    def now(self) -> pd.Timestamp:
        sim = SIM_OVERRIDE.get() or os.getenv("SIM_NOW")
        if sim:
            return parse_time(sim)
        return pd.Timestamp(dt.datetime.now(dt.timezone.utc)).tz_localize(None)

    def window(self, start, end, default_hours=24):
        now = self.now()
        e = parse_time(end, now)
        s = parse_time(start, e - pd.Timedelta(hours=default_hours))
        e = min(e, now)
        if s >= e:
            raise BadRequest("start harus lebih awal dari end (dan tidak di masa depan)")
        return s, e

    # ---- master
    def substations(self):
        return records(self.gi)

    def bays(self, gi_id=None, jenis=None):
        df = self.bay
        if gi_id:
            df = df[df.gi_id == gi_id.upper()]
        if jenis:
            df = df[df.jenis == jenis.upper()]
        return records(df)

    def points(self, gi_id=None, kategori=None, bay_id=None, besaran=None):
        df = self.point
        if gi_id:
            df = df[df.gi_id == gi_id.upper()]
        if kategori:
            df = df[df.kategori == kategori.upper()]
        if bay_id:
            df = df[df.bay_id == bay_id.upper()]
        if besaran:
            df = df[df.besaran == besaran.upper()]
        return records(df)

    # ---- telemetering
    def telemetry(self, point_id, start=None, end=None, page=1, page_size=100):
        pid = point_id.upper()
        if pid not in self.tele:
            known = self.point[self.point.point_id == pid]
            if known.empty:
                raise NotFound(f"point_id {pid} tidak dikenal. Lihat GET /api/v1/points")
            raise NotFound(f"point_id {pid} tidak punya histori. Pilih point dengan ada_histori=true")
        s, e = self.window(start, end)
        df = self.tele[pid]
        df = df[(df.ts >= s) & (df.ts <= e)].copy()
        meta = self.point.set_index("point_id").loc[pid]
        df["ts"] = fmt_ts(df["ts"])
        df["satuan"] = meta.satuan
        return paginate(df[["ts", "point_id", "value", "satuan", "quality"]], page, page_size)

    def telemetry_latest(self, gi_id=None, stale_minutes=30):
        now = self.now()
        rows = []
        for pid, df in self.tele.items():
            if gi_id and not pid.startswith(gi_id.upper() + "."):
                continue
            d = df[df.ts <= now]
            if d.empty:
                continue
            r = d.iloc[-1]
            # nilai beku: cari kapan quality terakhir GOOD
            last_good = d[d.quality == "GOOD"].ts.max()
            age = (now - r.ts).total_seconds() / 60
            stale_since = None if r.quality == "GOOD" else last_good
            rows.append(dict(point_id=pid, ts=r.ts, value=r.value, quality=r.quality,
                             umur_menit=round(age, 1),
                             tidak_update_sejak=stale_since,
                             perlu_dicek=bool(r.quality != "GOOD" or age > stale_minutes)))
        df = pd.DataFrame(rows)
        if df.empty:
            return []
        df["ts"] = fmt_ts(df["ts"])
        df["tidak_update_sejak"] = fmt_ts(pd.to_datetime(df["tidak_update_sejak"]))
        return records(df.sort_values(["perlu_dicek", "point_id"], ascending=[False, True]))

    # ---- event
    def _events(self, start, end, gi_id, bay_id, jenis, prioritas_maks):
        s, e = self.window(start, end)
        df = self.ev[(self.ev.ts_event >= s) & (self.ev.ts_event <= e) & (self.ev.ts_received <= self.now())]
        if gi_id:
            df = df[df.gi_id == gi_id.upper()]
        if bay_id:
            df = df[df.bay_id == bay_id.upper()]
        if jenis:
            wanted = [j.strip().upper() for j in jenis.split(",")]
            df = df[df.jenis.isin(wanted)]
        if prioritas_maks:
            df = df[df.prioritas <= int(prioritas_maks)]
        return df

    def events(self, start=None, end=None, gi_id=None, bay_id=None, jenis=None, prioritas_maks=None,
               page=1, page_size=50):
        df = self._events(start, end, gi_id, bay_id, jenis, prioritas_maks).copy()
        df["ts_event"] = fmt_ts(df["ts_event"], ms=True)
        df["ts_received"] = fmt_ts(df["ts_received"], ms=True)
        return paginate(df, page, page_size)

    def raw_events(self, start=None, end=None, gi_id=None, page=1, page_size=100):
        """Feed mentah: duplikat, format waktu campur, urutan acak."""
        df = self._events(start, end, gi_id, None, None, None).copy()
        k = (df["event_id"].to_numpy() * 2654435761) % 1000
        dup = df[k % 25 == 0]
        df = pd.concat([df, dup]).reset_index(drop=True)
        k = (df["event_id"].to_numpy() * 2654435761) % 1000
        local = k % 10 < 3
        iso_e = (df.ts_event.dt.strftime("%Y-%m-%dT%H:%M:%S.%f").str[:-3] + "Z")
        loc_e = (df.ts_event + H8).dt.strftime("%d/%m/%Y %H:%M:%S")
        iso_r = (df.ts_received.dt.strftime("%Y-%m-%dT%H:%M:%S.%f").str[:-3] + "Z")
        loc_r = (df.ts_received + H8).dt.strftime("%d/%m/%Y %H:%M:%S")
        order_key = df.ts_received + pd.to_timedelta(k % 9, unit="s")
        df["ts_event"] = np.where(local, loc_e, iso_e)
        df["ts_received"] = np.where(local, loc_r, iso_r)
        df = df.assign(_o=order_key.to_numpy()).sort_values("_o").drop(columns="_o")
        return paginate(df, page, page_size)

    def raw_telemetry(self, point_id, start=None, end=None, page=1, page_size=200):
        """Feed telemetering mentah: satuan campur (V/kV, kW/MW), sentinel 9999, null, duplikat."""
        pid = point_id.upper()
        if pid not in self.tele:
            raise NotFound(f"point_id {pid} tidak punya histori")
        s, e = self.window(start, end)
        df = self.tele[pid]
        df = df[(df.ts >= s) & (df.ts <= e)].copy()
        if df.empty:
            return paginate(df, page, page_size)
        k = _hash(df["point_id"] + df["ts"].astype(str))
        df = pd.concat([df, df[k % 40 == 0]]).reset_index(drop=True)
        k = _hash(df["point_id"] + df["ts"].astype(str) + pd.Series(df.index.astype(str)))
        unit = self.point.set_index("point_id").loc[pid, "satuan"]
        df["satuan"] = unit
        val = df["value"].astype(float).to_numpy()
        if unit == "kV":
            m = k % 5 == 0
            val = np.where(m, val * 1000, val)
            df["satuan"] = np.where(m, "V", "kV")
        elif unit == "MW":
            m = k % 7 == 0
            val = np.where(m, val * 1000, val)
            df["satuan"] = np.where(m, "kW", "MW")
        val = np.where(k % 331 == 0, 9999.0, val)
        val = np.where(k % 199 == 0, np.nan, val)
        df["value"] = val
        local = k % 10 < 3
        df["ts"] = np.where(local, (df.ts + H8).dt.strftime("%d/%m/%Y %H:%M:%S"),
                            df.ts.dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
        return paginate(df[["ts", "point_id", "value", "satuan", "quality"]], page, page_size)

    # ---- gangguan
    def _visible_incidents(self):
        now = self.now()
        df = self.inc[self.inc.mulai <= now].copy()
        ongoing = df.selesai > now
        df.loc[ongoing, ["beban_padam_mw", "durasi_menit", "ens_mwh"]] = np.nan
        df["selesai"] = df["selesai"].where(~ongoing)
        df.loc[ongoing, "status_rca"] = "BERLANGSUNG"
        return df

    def incidents(self, start=None, end=None, gi_id=None, bay_id=None, penyebab=None, status_rca=None,
                  q=None, page=1, page_size=50):
        df = self._visible_incidents()
        if start or end:
            s = parse_time(start, pd.Timestamp("2000-01-01"))
            e = parse_time(end, self.now())
            df = df[(df.mulai >= s) & (df.mulai <= e)]
        if gi_id:
            df = df[df.gi_id == gi_id.upper()]
        if bay_id:
            df = df[df.bay_id == bay_id.upper()]
        if penyebab:
            df = df[df.penyebab.isin([p.strip().upper() for p in penyebab.split(",")])]
        if status_rca:
            df = df[df.status_rca == status_rca.upper()]
        if q:
            text = (df.kronologi.fillna("") + " " + df.tindakan.fillna("") + " " + df.rca_ringkas.fillna("")).str.lower()
            for word in q.lower().split():
                df = df[text.loc[df.index].str.contains(word, regex=False)]
        df = df.sort_values("mulai", ascending=False).copy()
        df["mulai"] = fmt_ts(df["mulai"], ms=True)
        df["selesai"] = fmt_ts(df["selesai"], ms=True)
        return paginate(df, page, page_size)

    def incident(self, gangguan_id):
        df = self._visible_incidents()
        row = df[df.gangguan_id == gangguan_id.upper()]
        if row.empty:
            raise NotFound(f"{gangguan_id} tidak ditemukan")
        row = row.copy()
        r = row.iloc[0]
        evs = self.ev[(self.ev.bay_id == r.bay_id) & (self.ev.ts_event >= r.mulai - pd.Timedelta(minutes=10)) &
                      (self.ev.ts_event <= (r.selesai if pd.notna(r.selesai) else self.now()) + pd.Timedelta(minutes=2)) &
                      (self.ev.ts_received <= self.now())].copy()
        evs["ts_event"] = fmt_ts(evs["ts_event"], ms=True)
        evs["ts_received"] = fmt_ts(evs["ts_received"], ms=True)
        row["mulai"] = fmt_ts(row["mulai"], ms=True)
        row["selesai"] = fmt_ts(row["selesai"], ms=True)
        out = records(row)[0]
        out["event_terkait"] = records(evs[["event_id", "ts_event", "jenis", "sinyal", "fasa", "prioritas"]])
        return out

    # ---- beban & rencana
    def load_system(self, start=None, end=None, interval="30m"):
        s, e = self.window(start, end, default_hours=24 * 7)
        df = self.load[(self.load.ts >= s) & (self.load.ts <= e)].copy()
        df["w"] = df.ts + H8
        if interval == "30m":
            df["ts"] = fmt_ts(df["ts"])
            return records(df[["ts", "beban_mw", "suhu_c", "hujan_mm", "jenis_hari", "flag"]])
        if interval == "1h":
            g = df.set_index("w").resample("1h").agg({"beban_mw": "mean", "suhu_c": "mean", "hujan_mm": "sum",
                                                     "flag": lambda x: "NORMAL" if (x == "NORMAL").all() else x[x != "NORMAL"].iloc[0]})
            g = g.reset_index()
            g["ts"] = g["w"].dt.strftime("%Y-%m-%dT%H:%M:%S") + "+08:00"
            g["beban_mw"] = g["beban_mw"].round(1)
            g["suhu_c"] = g["suhu_c"].round(1)
            return records(g[["ts", "beban_mw", "suhu_c", "hujan_mm", "flag"]])
        if interval == "1d":
            rows = []
            for day, g in df.groupby(df.w.dt.date):
                ok = g.dropna(subset=["beban_mw"])
                if ok.empty:
                    continue
                i = ok.beban_mw.idxmax()
                key = str(day)
                rows.append(dict(tanggal=key, beban_puncak_mw=ok.loc[i, "beban_mw"],
                                 waktu_puncak=ok.loc[i, "w"].strftime("%H:%M"),
                                 beban_min_mw=ok.beban_mw.min(), beban_rata_mw=round(ok.beban_mw.mean(), 1),
                                 energi_mwh=round(ok.beban_mw.sum() * 0.5, 1),
                                 jenis_hari=self.cal_idx.loc[key, "jenis_hari"] if key in self.cal_idx.index else None,
                                 keterangan=self.cal_idx.loc[key, "keterangan"] if key in self.cal_idx.index else None,
                                 slot_berflag=int((g.flag != "NORMAL").sum()), slot_lengkap=len(g) == 48))
            return records(pd.DataFrame(rows))
        raise BadRequest("interval harus 30m, 1h, atau 1d")

    def calendar(self, start=None, end=None):
        df = self.cal
        if start:
            df = df[df.tanggal >= start[:10]]
        if end:
            df = df[df.tanggal <= end[:10]]
        return records(df)

    def plan_roh(self, tanggal=None, start=None, end=None):
        now = self.now()
        if tanggal:
            df = self.roh[self.roh.tanggal == tanggal[:10]]
        else:
            s = (start or (now + H8).strftime("%Y-%m-%d"))[:10]
            e = (end or s)[:10]
            df = self.roh[(self.roh.tanggal >= s) & (self.roh.tanggal <= e)]
        if df.empty:
            raise NotFound("Rencana untuk tanggal itu tidak tersedia (data ROH mulai 2024-12-01)")
        # ROH dirilis H-1 jam 10.00 WITA
        visible = pd.to_datetime(df["tanggal"]) - pd.Timedelta(hours=14) - H8 <= now
        df = df[visible]
        if df.empty:
            raise NotFound("ROH tanggal itu belum dirilis (rilis H-1 pukul 10.00 WITA)")
        m = df.merge(self.load[["ts", "beban_mw", "flag"]], on="ts", how="left")
        m.loc[m.ts > now, ["beban_mw", "flag"]] = [np.nan, None]
        m["deviasi_pct"] = ((m.prakiraan_mw - m.beban_mw) / m.beban_mw * 100).round(2)
        m = m.rename(columns={"beban_mw": "realisasi_mw"})
        return records(m[["tanggal", "jam_ke", "slot_mulai", "prakiraan_mw", "realisasi_mw", "deviasi_pct", "flag", "metode"]])

    # ---- forecast
    def _history(self, until_w: pd.Timestamp, weeks: int, exclude_flags: bool):
        lo = until_w - pd.Timedelta(days=max(weeks * 7, 14) + 400)
        s = self._load_w[(self._load_w.index >= lo) & (self._load_w.index < until_w)]
        f = self._flag_w.reindex(s.index)
        clean, n_bad = F.clean_history(s, f, exclude_flags)
        return clean, n_bad

    def forecast(self, method="koefisien", start=None, horizon_slots=48, history_weeks=8, exclude_flags=True):
        now_w = self.now() + H8
        if horizon_slots < 1 or horizon_slots > 336 * 2:
            raise BadRequest("horizon_slots 1..672 (maks 2 minggu)")
        st_w = (parse_time(start) + H8) if start else now_w.ceil("30min")
        st_w = st_w.floor("30min")
        until = min(st_w, now_w.floor("30min"))
        methods = sorted(F.METHODS) if method == "all" else [F.ALIASES.get(method, method)]
        for m in methods:
            if m not in F.METHODS:
                raise BadRequest(f"method harus salah satu: {sorted(F.METHODS)} atau 'all'")
        hist, n_bad = self._history(until, history_weeks, exclude_flags)
        cal = self.cal_idx
        result = {"start": st_w.strftime("%Y-%m-%dT%H:%M:%S") + "+08:00", "horizon_slots": horizon_slots,
                  "data_sampai": until.strftime("%Y-%m-%dT%H:%M:%S") + "+08:00",
                  "slot_histori_diganti": n_bad, "metode": {}}
        if st_w > until + pd.Timedelta(days=14):
            raise BadRequest("start terlalu jauh di depan data yang tersedia (maks 14 hari setelah sekarang)")
        for m in methods:
            # bila start di masa depan, isi celah dengan prakiraan metode yang sama
            h = hist.copy()
            if st_w > until:
                gap = int((st_w - until) / pd.Timedelta(minutes=30))
                bridge = F.run(m, h, cal, until, gap)
                h = pd.concat([h, bridge])
            fc = F.run(m, h, cal, st_w, horizon_slots).round(1)
            peak_ts = fc.idxmax()
            result["metode"][m] = {
                "ringkasan": {"puncak_mw": float(fc.max()), "waktu_puncak": peak_ts.strftime("%Y-%m-%dT%H:%M") + "+08:00",
                              "minimum_mw": float(fc.min()), "energi_mwh": round(float(fc.sum() * 0.5), 1)},
                "prakiraan": [{"ts": t.strftime("%Y-%m-%dT%H:%M:%S") + "+08:00", "prakiraan_mw": float(v)}
                              for t, v in fc.items()],
            }
        return result

    def backtest(self, method="all", start=None, days=7, exclude_flags=True):
        now_w = self.now() + H8
        end_w = (parse_time(start) + H8).normalize() if start else now_w.normalize()
        end_w = min(end_w, now_w.normalize())
        test_start = end_w - pd.Timedelta(days=days)
        methods = sorted(F.METHODS) if method == "all" else [F.ALIASES.get(method, method)]
        hist, n_bad = self._history(test_start, 8, exclude_flags)
        actual = self._load_w[(self._load_w.index >= test_start) & (self._load_w.index < end_w)]
        flags = self._flag_w.reindex(actual.index)
        actual_eval = actual.where(flags == "NORMAL")
        out = {"periode_uji": {"mulai": test_start.strftime("%Y-%m-%d"),
                               "selesai": (end_w - pd.Timedelta(days=1)).strftime("%Y-%m-%d")},
               "catatan": "Slot berflag (pemadaman, UFR, data hilang) tidak ikut dinilai.",
               "slot_histori_diganti": n_bad, "metode": {}}
        for m in methods:
            if m not in F.METHODS:
                raise BadRequest(f"method harus salah satu: {sorted(F.METHODS)} atau 'all'")
            fc = F.run(m, hist, self.cal_idx, test_start, days * 48)
            ev = F.evaluate(actual_eval, fc)
            per_day = []
            for d, g in fc.groupby(fc.index.date):
                a = actual_eval.reindex(g.index)
                per_day.append({"tanggal": str(d), "mape_pct": F._r(F.mape(a, g)),
                                "jenis_hari": self.cal_idx.loc[str(d), "jenis_hari"] if str(d) in self.cal_idx.index else None})
            ev["per_hari"] = per_day
            out["metode"][m] = ev
        valid = {k: v["mape_total_pct"] for k, v in out["metode"].items() if v["mape_total_pct"] is not None}
        out["terbaik"] = min(valid, key=valid.get) if valid else None
        return out

    # ---- laporan
    def add_report(self, group: str, payload: dict) -> dict:
        rid = "LAP-" + uuid.uuid4().hex[:8].upper()
        now = self.now()
        rec = {"report_id": rid, "grup": group, "diterima": (now + H8).strftime("%Y-%m-%dT%H:%M:%S") + "+08:00",
               **payload}
        self.reports.append(rec)
        if self.engine is not None:
            row = pd.DataFrame([{"report_id": rid, "grup": group, "diterima": now,
                                 "judul": payload.get("judul"), "isi": str(payload.get("isi")),
                                 "disetujui_oleh": payload.get("disetujui_oleh"),
                                 "metadata": str(payload.get("metadata"))}])
            row.to_sql("laporan", self.engine, if_exists="append", index=False)
        return rec

    def list_reports(self, group: str | None = None):
        if group:
            return [r for r in self.reports if r["grup"] == group]
        return list(self.reports)


def normalize_mysql_url(url: str) -> str:
    """Railway memberi mysql://...; SQLAlchemy butuh mysql+pymysql://..."""
    if url.startswith("mysql://"):
        return "mysql+pymysql://" + url[len("mysql://"):]
    return url
