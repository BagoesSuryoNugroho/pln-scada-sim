"""Generator dataset SCADA fiktif (deterministik, seed tetap).

Jalankan:  python -m simcore.generate            -> menulis ke ./data
           python -m simcore.generate --out DIR

Semua timestamp disimpan dalam UTC (kolom *_utc tidak diberi akhiran; dokumentasi di README).
Kalender, cuaca, dan profil beban dihitung dalam WITA lalu dikonversi.
"""
from __future__ import annotations

import argparse
import math
import os
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config as C
from . import forecast as F

H8 = C.WITA_OFFSET


def W(s: str) -> pd.Timestamp:
    """Parse string waktu WITA naive."""
    return pd.Timestamp(s)


# =================================================================== kalender & cuaca
def build_calendar() -> pd.DataFrame:
    days = pd.date_range(C.LOAD_START, C.DATA_END, freq="D", inclusive="left")
    rows = []
    for d in days:
        k = d.strftime("%Y-%m-%d")
        if k in C.LIBUR_NAS:
            jh, ket = "LIBUR_NAS", C.LIBUR_NAS[k]
        elif k in C.CUTI_BERSAMA:
            jh, ket = "CUTI_BERSAMA", "Cuti bersama"
        elif d.dayofweek == 5:
            jh, ket = "SABTU", ""
        elif d.dayofweek == 6:
            jh, ket = "MINGGU", ""
        else:
            jh, ket = "KERJA", ""
        ramadan = any(W(a) <= d <= W(b) for a, b in C.RAMADAN)
        mudik = any(W(a) <= d <= W(b) for a, b in C.MUDIK)
        rows.append(dict(tanggal=k, jenis_hari=jh, keterangan=ket, ramadan=ramadan, periode_mudik=mudik))
    return pd.DataFrame(rows)


SCRIPTED_WEATHER = {  # tanggal -> (hujan, intensitas_mm, petir, angin)
    "2026-11-20": (True, 26.0, True, False),
    "2026-11-23": (True, 31.0, True, True),
    "2026-11-24": (True, 38.0, True, False),
    "2026-11-25": (True, 12.0, False, False),
    "2025-12-09": (False, 0.0, False, False),
    "2026-10-14": (False, 0.0, False, False),
}


def build_weather(rng, cal: pd.DataFrame) -> pd.DataFrame:
    days = pd.to_datetime(cal["tanggal"])
    month = days.dt.month.to_numpy()
    year = days.dt.year.to_numpy()
    n = len(days)
    p_rain = np.select([np.isin(month, [11, 12, 1, 2, 3]), np.isin(month, [4, 5, 6])], [0.62, 0.35], 0.10)
    elnino = (year == 2026) & np.isin(month, [7, 8, 9, 10])
    p_rain = np.where(elnino, 0.04, p_rain)
    rain = rng.random(n) < p_rain
    inten = np.where(rain, rng.gamma(2.0, 9.0, n), 0.0)
    petir = rain & (inten > 14) & (rng.random(n) < 0.75)
    angin = rain & (rng.random(n) < 0.35)
    tmax = (31.5 + np.where(np.isin(month, [9, 10, 11]), 1.0, 0.0) - np.where(rain, 2.3, 0.0)
            + rng.normal(0, 0.8, n) + elnino * 0.8)
    df = pd.DataFrame(dict(tanggal=cal["tanggal"], hujan=rain, hujan_mm=inten.round(1), petir=petir,
                           angin=angin, tmax=tmax.round(1)))
    for k, (r, mm, pt, ag) in SCRIPTED_WEATHER.items():
        i = df.index[df["tanggal"] == k]
        df.loc[i, ["hujan", "hujan_mm", "petir", "angin"]] = [r, mm, pt, ag]
        df.loc[i, "tmax"] = 29.0 if r else 33.2
    return df.set_index("tanggal")


# =================================================================== beban sistem
ANCHORS = [(0, .74), (2, .68), (4, .64), (5, .66), (6, .70), (7, .76), (8, .82), (10, .86), (12, .87),
           (13, .88), (14, .89), (15, .88), (16, .87), (17, .90), (18, .97), (18.5, 1.0), (19, 1.0),
           (19.5, .99), (20, .97), (21, .93), (22, .87), (23, .80), (24, .74)]


def build_load(rng, cal: pd.DataFrame, wx: pd.DataFrame) -> pd.DataFrame:
    idx = pd.date_range(C.LOAD_START, C.DATA_END, freq="30min", inclusive="left")
    hour = (idx.hour + idx.minute / 60).to_numpy()
    ax, ay = zip(*ANCHORS)
    shape = np.interp(hour, ax, ay)
    dkey = idx.strftime("%Y-%m-%d")
    calx = cal.set_index("tanggal").reindex(dkey)
    jh = calx["jenis_hari"].to_numpy()
    ket = calx["keterangan"].fillna("").to_numpy()
    ramadan = calx["ramadan"].to_numpy(dtype=bool)
    mudik = calx["periode_mudik"].to_numpy(dtype=bool)
    wxx = wx.reindex(dkey)
    day_h = (hour >= 7) & (hour < 17)
    eve_h = (hour >= 17) & (hour < 23)

    f = np.ones(len(idx))
    f = np.where((jh == "SABTU") & day_h, f * 0.95, f)
    f = np.where((jh == "SABTU") & eve_h, f * 0.985, f)
    f = np.where((jh == "MINGGU") & day_h, f * 0.90, f)
    f = np.where((jh == "MINGGU") & ~day_h, f * 0.965, f)
    hol = jh == "LIBUR_NAS"
    f = np.where(hol & day_h, f * 0.86, f)
    f = np.where(hol & ~day_h, f * 0.94, f)
    f = np.where((jh == "CUTI_BERSAMA") & day_h, f * 0.92, f)
    leb = np.char.find(ket.astype(str), "Idulfitri") >= 0
    f = np.where(leb, f * 0.82, f)
    f = np.where(mudik & ~leb, f * 0.93, f)
    # Ramadan: tonjolan sahur, puncak bergeser
    f = np.where(ramadan & (hour >= 2.5) & (hour < 4.5), f * 1.07, f)
    f = np.where(ramadan & (hour >= 18) & (hour < 19), f * 0.97, f)
    f = np.where(ramadan & (hour >= 20) & (hour < 22), f * 1.03, f)
    # Nataru
    md = idx.strftime("%m-%d")
    nataru = np.isin(md, ["12-24", "12-26", "12-27", "12-28", "12-29", "12-30", "12-31"])
    f = np.where(nataru & day_h, f * 0.95, f)
    f = np.where((md == "12-31") & (hour >= 21), f * 1.04, f)

    # suhu per slot
    tmax = wxx["tmax"].to_numpy(dtype=float)
    tmin = 24.6
    tshape = np.clip(np.sin((hour - 6) / 14 * math.pi), 0, None)
    temp = tmin + (tmax - tmin) * tshape
    rain = wxx["hujan"].to_numpy(dtype=bool)
    aft = (hour >= 14) & (hour < 19)
    temp = np.where(rain & aft, temp - 2.5, temp)
    hujan_slot = np.where(rain & (hour >= 13) & (hour < 19), wxx["hujan_mm"].to_numpy(dtype=float) / 12, 0.0)

    years = (idx - W(C.LOAD_START)).days.to_numpy() / 365.25
    month = idx.month.to_numpy()
    peak = 1552 * 1.055 ** years
    peak = peak * np.select([np.isin(month, [9, 10, 11]), np.isin(month, [1, 2])], [1.005, 0.98], 1.0)
    temp_eff = np.where((hour >= 9) & (hour < 22), 0.008 * np.clip(temp - 28, 0, None), 0.0)

    # noise AR(1)
    z = rng.normal(0, 1, len(idx))
    e = np.zeros(len(idx))
    phi, sd = 0.9, 0.012
    for i in range(1, len(idx)):
        e[i] = phi * e[i - 1] + math.sqrt(1 - phi ** 2) * sd * z[i]
    demand = peak * shape * f * (1 + temp_eff) * (1 + e)

    df = pd.DataFrame(dict(ts=idx, kebutuhan_mw=demand, suhu_c=temp, hujan_mm=hujan_slot,
                           jenis_hari=jh, flag="NORMAL"))
    df["beban_mw"] = df["kebutuhan_mw"]
    for a, b, mw in C.PEMADAMAN_BERGILIR:
        m = (df.ts >= W(a)) & (df.ts < W(b))
        df.loc[m, "beban_mw"] -= mw
        df.loc[m, "flag"] = "PEMADAMAN_BERGILIR"
    a, b, mw = C.UFR_EVENT
    m = (df.ts >= W(a).floor("30min")) & (df.ts < W(b))
    df.loc[m, "beban_mw"] -= mw
    df.loc[m, "flag"] = "PELEPASAN_UFR"
    # data hilang & estimasi (di luar periode training)
    for start, hrs, kind in [("2025-02-11 09:00", 4, "DATA_HILANG"), ("2025-07-22 13:30", 3, "DATA_HILANG"),
                             ("2026-01-28 02:00", 6, "DATA_HILANG"), ("2026-06-09 10:00", 3, "ESTIMASI"),
                             ("2026-10-06 15:00", 4, "DATA_HILANG"), ("2025-10-17 20:00", 2, "ESTIMASI")]:
        m = (df.ts >= W(start)) & (df.ts < W(start) + pd.Timedelta(hours=hrs))
        if kind == "DATA_HILANG":
            df.loc[m, "beban_mw"] = np.nan
        else:
            df.loc[m, "beban_mw"] = df.loc[m, "beban_mw"].mean()
        df.loc[m, "flag"] = kind
    df["beban_mw"] = df["beban_mw"].round(1)
    df["kebutuhan_mw"] = df["kebutuhan_mw"].round(1)
    df["suhu_c"] = df["suhu_c"].round(1)
    df["hujan_mm"] = df["hujan_mm"].round(1)
    df["subsistem"] = "SULBAGSEL"
    return df


# =================================================================== master data
def build_master():
    gi = pd.DataFrame(C.GARDU_INDUK, columns=["gi_id", "nama", "level_kv", "media_kom", "rtu_tipe"])
    gi["subsistem"] = "SULBAGSEL"
    bays, points = [], []

    def add_point(pid, gi_id, bay_id, kategori, besaran, satuan, ba, bb, desk, hist):
        points.append(dict(point_id=pid, gi_id=gi_id, bay_id=bay_id, kategori=kategori, besaran=besaran,
                           satuan=satuan, batas_atas=ba, batas_bawah=bb, deskripsi=desk, ada_histori=hist))

    for a, b, n in C.PENGHANTAR:
        bid = f"{a}-PHT-{b}{n}"
        code = f"PHT_{b}{n}"
        bays.append(dict(bay_id=bid, gi_id=a, jenis="PENGHANTAR", tujuan=C.GI_NAMA[b], kapasitas_mva=None,
                         tegangan_kv=150))
        add_point(f"{a}.{code}.MW", a, bid, "TM", "MW", "MW", 180, -180, f"Daya aktif penghantar ke {C.GI_NAMA[b]} #{n}", True)
        add_point(f"{a}.{code}.MVAR", a, bid, "TM", "MVAR", "MVAR", 90, -90, "Daya reaktif", False)
        add_point(f"{a}.{code}.A", a, bid, "TM", "A", "A", 800, 0, "Arus", False)
        add_point(f"{a}.{code}.CB", a, bid, "TS", "CB_STATUS", "", None, None, "Status PMT 150 kV", False)
        add_point(f"{a}.{code}.PROT", a, bid, "TS", "PROTEKSI", "", None, None, "Sinyal relay distance & A/R", False)
    for g, lst in C.TRAFO.items():
        for k, mva in lst:
            bid = f"{g}-TRF-{k}"
            code = f"TRF{k}"
            bays.append(dict(bay_id=bid, gi_id=g, jenis="TRAFO", tujuan="20 kV", kapasitas_mva=mva, tegangan_kv=150))
            mw_max = round(mva * 0.9, 1)
            add_point(f"{g}.{code}.MW", g, bid, "TM", "MW", "MW", mw_max, 0, f"Beban trafo {k} ({mva} MVA)", True)
            add_point(f"{g}.{code}.MVAR", g, bid, "TM", "MVAR", "MVAR", mva * 0.5, -10, "Daya reaktif trafo", False)
            add_point(f"{g}.{code}.TAP", g, bid, "TM", "TAP", "", 17, 1, "Posisi tap OLTC", False)
            add_point(f"{g}.{code}.TEMP_OIL", g, bid, "TM", "TEMP_OIL", "degC", 85, 0, "Suhu minyak atas (alarm 85, trip 95)", True)
            add_point(f"{g}.{code}.CB", g, bid, "TS", "CB_STATUS", "", None, None, "Status PMT trafo", False)
            add_point(f"{g}.{code}.PROT", g, bid, "TS", "PROTEKSI", "", None, None, "Differential, Buchholz, suhu", False)
    hist_pyl = {"SMB-PYL-07", "MLN-PYL-02", "KRB-PYL-04", "PTR-PYL-05"}
    for g, lst in C.PENYULANG.items():
        for nn in lst:
            bid = f"{g}-PYL-{nn}"
            code = f"PYL{nn}"
            bays.append(dict(bay_id=bid, gi_id=g, jenis="PENYULANG", tujuan="JTM 20 kV", kapasitas_mva=None, tegangan_kv=20))
            add_point(f"{g}.{code}.A", g, bid, "TM", "A", "A", 400, 0, "Arus penyulang", bid in hist_pyl)
            add_point(f"{g}.{code}.CB", g, bid, "TS", "CB_STATUS", "", None, None, "Status PMT 20 kV", False)
            add_point(f"{g}.{code}.PROT", g, bid, "TS", "PROTEKSI", "", None, None, "Sinyal OCR/GFR/UFR", False)
    for g in gi.gi_id:
        bays.append(dict(bay_id=f"{g}-BUS-150", gi_id=g, jenis="BUSBAR", tujuan="", kapasitas_mva=None, tegangan_kv=150))
        add_point(f"{g}.BUS150.KV", g, f"{g}-BUS-150", "TM", "KV", "kV", 157.5, 142.5, "Tegangan busbar 150 kV", True)
        add_point(f"{g}.RTU.COMM", g, None, "TS", "RTU_COMM", "", None, None, "Status komunikasi RTU ke master station", False)
        add_point(f"{g}.GI.ALARM", g, None, "TS", "ALARM_UMUM", "", None, None, "Alarm umum GI (SF6, DC, charger)", False)
    add_point("LSR.SYS.HZ", "LSR", "LSR-BUS-150", "TM", "HZ", "Hz", 50.5, 49.5, "Frekuensi sistem (diukur di GI Losari)", True)
    return gi, pd.DataFrame(bays), pd.DataFrame(points)


def code_of(bay_id: str) -> str:
    g, j, rest = bay_id.split("-", 2)
    return {"PHT": f"PHT_{rest}", "TRF": f"TRF{rest}", "PYL": f"PYL{rest}"}[j]


# =================================================================== gangguan & SOE
@dataclass
class Book:
    incidents: list = field(default_factory=list)
    events: list = field(default_factory=list)
    outages: list = field(default_factory=list)   # (bay_id, mulai, selesai) WITA, untuk telemetry
    rtu_fail: list = field(default_factory=list)  # (gi_id, mulai, selesai)


def hhmm(t: pd.Timestamp) -> str:
    return t.strftime("%H.%M")


def fmt_mw(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


class Builder:
    def __init__(self, rng, load: pd.DataFrame, wx: pd.DataFrame, bays: pd.DataFrame):
        self.rng = rng
        self.load = load.set_index("ts")["kebutuhan_mw"]
        self.load.index = self.load.index.as_unit("ns")
        self.wx = wx
        self.bays = bays.set_index("bay_id")
        self.b = Book()

    # ---- util
    def sysload(self, t):
        return float(self.load.asof(pd.Timestamp(t).as_unit("ns")))

    def cuaca(self, t):
        w = self.wx.loc[t.strftime("%Y-%m-%d")]
        if w.hujan and w.petir:
            return "hujan disertai petir"
        if w.hujan and w.angin:
            return "hujan angin"
        if w.hujan:
            return "hujan"
        return "cerah" if self.rng.random() < .7 else "berawan"

    def ev(self, t, bay_id, suffix, jenis, sinyal, prio, fasa=None, gi=None):
        gi = gi or (bay_id.split("-")[0] if bay_id else None)
        pid = f"{gi}.{code_of(bay_id)}.{suffix}" if bay_id and "-" in bay_id and bay_id.split("-")[1] in ("PHT", "TRF", "PYL") else f"{gi}.{suffix}"
        radio = gi in ("LAE", "SML", "MLN")
        delay = self.rng.uniform(1.0, 6.0) if radio else self.rng.uniform(0.3, 2.5)
        self.b.events.append(dict(ts_event=t, ts_received=t + pd.Timedelta(seconds=delay), gi_id=gi,
                                  bay_id=bay_id, point_id=pid, jenis=jenis, sinyal=sinyal, fasa=fasa,
                                  prioritas=prio, quality="GOOD"))

    def ms(self, x):
        return pd.Timedelta(milliseconds=float(x))

    def add_incident(self, **kw):
        self.b.incidents.append(kw)
        if kw.get("beban_padam_mw", 0) > 0 or kw.get("_outage"):
            self.b.outages.append((kw["bay_id"], kw["mulai"], kw["selesai"]))

    # ---- penghantar
    def pht_trip(self, bay_id, t0, penyebab, ar_ok, zona="Z1", fasa=None, scripted=None):
        r = self.rng
        bay = self.bays.loc[bay_id]
        asal = bay_id.split("-")[0]
        tujuan = bay.tujuan
        fasa = fasa or r.choice(["R", "S", "T"])
        sig = f"DIST {zona}"
        self.ev(t0, bay_id, "PROT", "RELAY_PICKUP", f"{sig} PICKUP", 2, fasa)
        t_trip = t0 + self.ms(r.uniform(15, 25))
        self.ev(t_trip, bay_id, "PROT", "RELAY_TRIP", f"{sig} TRIP", 1, fasa)
        self.ev(t_trip + self.ms(r.uniform(35, 50)), bay_id, "CB", "CB_OPEN", "PMT 150 kV OPEN", 1)
        t_ar = t0 + self.ms(r.uniform(980, 1060))
        self.ev(t_ar, bay_id, "CB", "CB_CLOSE", "PMT 150 kV CLOSE (A/R)", 2)
        km = round(r.uniform(2, 28), 1)
        cu = (scripted or {}).get("cuaca") or self.cuaca(t0)
        if ar_ok:
            self.ev(t_ar + self.ms(r.uniform(20, 40)), bay_id, "PROT", "AR_SUCCESS", "AUTO RECLOSE OK", 2)
            selesai, padam, dur = t_ar, 0.0, 0.0
            krono = (f"Pkl {hhmm(t0)} WITA PMT 150 kV bay penghantar arah {tujuan} di {C.GI_NAMA[asal]} trip. "
                     f"Relay distance {zona} fasa {fasa} kerja, A/R berhasil dalam ±1 detik. Estimasi lokasi relay "
                     f"{fmt_mw(km)} km dari GI. Cuaca {cu} di sekitar jalur. Tidak ada beban padam.")
        else:
            self.ev(t_ar + self.ms(r.uniform(70, 95)), bay_id, "PROT", "RELAY_TRIP", f"{sig} TRIP", 1, fasa)
            self.ev(t_ar + self.ms(r.uniform(110, 140)), bay_id, "CB", "CB_OPEN", "PMT 150 kV OPEN", 1)
            self.ev(t_ar + self.ms(r.uniform(150, 180)), bay_id, "PROT", "AR_FAIL", "AUTO RECLOSE LOCKOUT", 1)
            dur = (scripted or {}).get("dur") or float(r.integers(12, 46))
            padam = (scripted or {}).get("padam") or round(self.sysload(t0) * r.uniform(0.007, 0.02), 1)
            selesai = t0 + pd.Timedelta(minutes=dur)
            self.ev(selesai, bay_id, "CB", "CB_CLOSE", "PMT 150 kV CLOSE (REMOTE)", 2)
            krono = (f"Pkl {hhmm(t0)} WITA PMT 150 kV bay penghantar arah {tujuan} di {C.GI_NAMA[asal]} trip. "
                     f"Relay distance {zona} fasa {fasa} kerja, A/R gagal (lockout). Estimasi lokasi relay "
                     f"{fmt_mw(km)} km dari GI. Atas perintah dispatcher PMT dicoba masuk pkl {hhmm(selesai)} dan berhasil. "
                     f"Beban padam {fmt_mw(padam)} MW selama {int(dur)} menit karena sebagian beban belum termanuver. Cuaca {cu}.")
        tindakan = {
            "PETIR": "Patroli jalur SUTT oleh UPT; cek counter arrester dan isolator di sekitar titik estimasi lokasi; laporan patroli ke dispatcher.",
            "BELUM_DIKETAHUI": "Patroli jalur SUTT; unduh rekaman gangguan relay untuk analisis tim proteksi.",
            "EKSTERNAL": "Koordinasi dengan pihak proyek; pemasangan rambu jarak aman ROW; patroli khusus.",
        }[penyebab]
        temuan = {
            "PETIR": r.choice([f"flashover pada isolator tower T.{r.integers(10, 80)}",
                               f"counter arrester tower T.{r.integers(10, 80)} bertambah satu",
                               "tidak ditemukan kerusakan fisik, gangguan temporer"]),
            "BELUM_DIKETAHUI": "patroli tidak menemukan titik gangguan; rekaman relay menunjukkan gangguan satu fasa ke tanah singkat",
            "EKSTERNAL": "lengan crane proyek terlalu dekat dengan konduktor fasa",
        }[penyebab]
        self.add_incident(mulai=t0, selesai=selesai, gi_id=asal, bay_id=bay_id,
                          relay_kerja=f"{sig} TRIP + {'AR SUCCESS' if ar_ok else 'AR FAIL'}",
                          penyebab=penyebab, beban_padam_mw=padam, durasi_menit=round(dur, 1),
                          ens_mwh=round(padam * dur / 60, 2), cuaca=cu, kronologi=krono, tindakan=tindakan,
                          temuan=temuan, scripted=bool(scripted))

    # ---- penyulang
    def pyl_trip(self, bay_id, t0, penyebab, relay, ar_ok, dur=None, padam=None, extra=None, cu=None, scripted=False):
        r = self.rng
        g = bay_id.split("-")[0]
        fasa = "RST" if relay == "OCR" else r.choice(["R", "S", "T"])
        if relay == "UFR":
            fasa = None
        sig = {"OCR": "OCR TRIP", "GFR": "GFR TRIP", "UFR": "UFR STAGE 1"}[relay]
        if relay != "UFR":
            self.ev(t0, bay_id, "PROT", "RELAY_PICKUP", sig.replace("TRIP", "PICKUP"), 2, fasa)
        t_trip = t0 + self.ms(r.uniform(40, 300) if relay != "UFR" else 0)
        self.ev(t_trip, bay_id, "PROT", "RELAY_TRIP", sig, 1, fasa)
        self.ev(t_trip + self.ms(r.uniform(50, 80)), bay_id, "CB", "CB_OPEN", "PMT 20 kV OPEN", 1)
        if relay != "UFR":
            t_ar = t_trip + self.ms(r.uniform(2900, 3200))
            self.ev(t_ar, bay_id, "CB", "CB_CLOSE", "PMT 20 kV CLOSE (A/R)", 2)
            if ar_ok:
                self.ev(t_ar + self.ms(30), bay_id, "PROT", "AR_SUCCESS", "AUTO RECLOSE OK", 2)
            else:
                self.ev(t_ar + self.ms(r.uniform(150, 400)), bay_id, "PROT", "RELAY_TRIP", sig, 1, fasa)
                self.ev(t_ar + self.ms(r.uniform(450, 500)), bay_id, "CB", "CB_OPEN", "PMT 20 kV OPEN", 1)
                self.ev(t_ar + self.ms(520), bay_id, "PROT", "AR_FAIL", "AUTO RECLOSE LOCKOUT", 1)
        if ar_ok:
            dur, padam, selesai = 0.0, 0.0, t0 + pd.Timedelta(seconds=4)
        else:
            dur = dur or float(r.integers(10, 60))
            padam = padam or round(self.sysload(t0) * r.uniform(0.0025, 0.0045), 1)
            selesai = t0 + pd.Timedelta(minutes=dur)
            self.ev(selesai, bay_id, "CB", "CB_CLOSE", "PMT 20 kV CLOSE (REMOTE)", 2)
        cu = cu or self.cuaca(t0)
        lokasi = r.choice(["Jl. Andi Tonro (sim)", "Kel. Bontoa (sim)", "Jl. Poros Pendidikan (sim)",
                           "Perum Griya Asri (sim)", "Jl. Nelayan (sim)", "Kel. Tamarunang (sim)", "seksi 2 setelah LBS-07"])
        ar_txt = ", A/R berhasil" if ar_ok else ", A/R gagal"
        cerita = {
            "LAYANG2": f"Petugas yantek menemukan layang-layang dengan benang gelasan tersangkut di JTM {lokasi}.",
            "POHON": f"Ditemukan ranting pohon menyentuh JTM saat {cu} di {lokasi}; dilakukan rabas pohon.",
            "BINATANG": r.choice(["Ditemukan bangkai ular di kubikel outgoing.", "Ditemukan bekas tikus di terminasi kabel kubikel.",
                                  f"Ditemukan burung terkena konduktor di tiang dekat {lokasi}."]),
            "PROTEKSI_MALKERJA": "", "EKSTERNAL": "", "PERALATAN": "", "BELUM_DIKETAHUI": "Patroli tidak menemukan penyebab.",
        }[penyebab]
        if extra:
            cerita = extra
        normal = f" Beban padam {fmt_mw(padam)} MW, normal pkl {hhmm(selesai)} ({int(dur)} menit)." if not ar_ok else " Tidak ada beban padam berkelanjutan."
        krono = f"Pkl {hhmm(t0)} WITA PMT 20 kV penyulang {bay_id} di {C.GI_NAMA[g]} trip, relay {sig.replace(' TRIP','')} kerja{ar_txt if relay != 'UFR' else ''}. {cerita}{normal}"
        tindakan = {
            "LAYANG2": "Pembersihan JTM; sosialisasi bahaya layang-layang ke warga sekitar; usulan patroli rutin musim kemarau.",
            "POHON": "Rabas pohon sepanjang seksi terdampak; usulan jadwal rabas sebelum musim hujan.",
            "BINATANG": "Pembersihan kubikel; pemasangan penutup terminasi dan anti-binatang.",
            "PROTEKSI_MALKERJA": "Pengujian relay dan pengecekan setting GFR serta wiring CT oleh tim proteksi.",
            "EKSTERNAL": "Koordinasi dengan pengatur sistem; evaluasi skema UFR.",
            "PERALATAN": "Penggantian peralatan rusak; uji tahanan isolasi sebelum normalisasi.",
            "BELUM_DIKETAHUI": "Patroli ulang siang hari; pemantauan penyulang.",
        }[penyebab]
        self.add_incident(mulai=t0, selesai=selesai, gi_id=g, bay_id=bay_id,
                          relay_kerja=f"{sig} + {'AR SUCCESS' if ar_ok else ('AR FAIL' if relay != 'UFR' else 'TANPA A/R')}",
                          penyebab=penyebab, beban_padam_mw=padam, durasi_menit=round(dur, 1),
                          ens_mwh=round(padam * dur / 60, 2), cuaca=cu, kronologi=krono, tindakan=tindakan,
                          temuan=cerita or "-", scripted=scripted)

    # ---- trafo
    def trf_trip(self, bay_id, t0, kind, dur, padam, krono, tindakan, temuan, cu="cerah"):
        r = self.rng
        if kind == "OIL":
            self.ev(t0, bay_id, "PROT", "RELAY_TRIP", "OIL TEMP TRIP", 1)
        else:
            self.ev(t0 - pd.Timedelta(minutes=7), bay_id, "PROT", "ALARM_ON", "BUCHHOLZ ALARM", 2)
            self.ev(t0, bay_id, "PROT", "RELAY_TRIP", "DIFF TRIP", 1, "RST")
            self.ev(t0 + self.ms(12), bay_id, "PROT", "RELAY_TRIP", "BUCHHOLZ TRIP", 1)
        self.ev(t0 + self.ms(r.uniform(40, 60)), bay_id, "CB", "CB_OPEN", "PMT 150 kV TRAFO OPEN", 1)
        self.ev(t0 + self.ms(r.uniform(60, 90)), bay_id, "CB", "CB_OPEN", "PMT 20 kV INCOMING OPEN", 1)
        selesai = t0 + pd.Timedelta(minutes=dur)
        self.ev(selesai, bay_id, "CB", "CB_CLOSE", "PMT 150 kV TRAFO CLOSE", 2)
        self.ev(selesai + pd.Timedelta(seconds=40), bay_id, "CB", "CB_CLOSE", "PMT 20 kV INCOMING CLOSE", 2)
        self.add_incident(mulai=t0, selesai=selesai, gi_id=bay_id.split("-")[0], bay_id=bay_id,
                          relay_kerja="OIL TEMP TRIP" if kind == "OIL" else "BUCHHOLZ ALARM + DIFF TRIP + BUCHHOLZ TRIP",
                          penyebab="PERALATAN", beban_padam_mw=padam, durasi_menit=float(dur),
                          ens_mwh=round(padam * dur / 60, 2), cuaca=cu, kronologi=krono, tindakan=tindakan,
                          temuan=temuan, scripted=True)

    # ---- non-gangguan
    def rtu_fail(self, g, t0, dur_min):
        t1 = t0 + pd.Timedelta(minutes=dur_min)
        self.ev(t0, None, "RTU.COMM", "RTU_COMM_FAIL", "RTU COMMUNICATION FAIL", 2, gi=g)
        self.ev(t1, None, "RTU.COMM", "RTU_COMM_OK", "RTU COMMUNICATION NORMAL", 2, gi=g)
        self.b.rtu_fail.append((g, t0, t1))

    def maintenance(self, bay_id, t0, hours):
        lvl = "20 kV" if "-PYL-" in bay_id else "150 kV"
        self.ev(t0, bay_id, "CB", "CB_OPEN", f"PMT {lvl} OPEN (PEMELIHARAAN)", 3)
        self.ev(t0 + pd.Timedelta(hours=hours), bay_id, "CB", "CB_CLOSE", f"PMT {lvl} CLOSE (PEMELIHARAAN)", 3)

    def misc_alarm(self, g, t0, sig, minutes):
        self.ev(t0, None, "GI.ALARM", "ALARM_ON", sig, 2, gi=g)
        self.ev(t0 + pd.Timedelta(minutes=minutes), None, "GI.ALARM", "ALARM_OFF", sig, 3, gi=g)

    def oil_alarm(self, bay_id, t_on, t_off, flood):
        r = self.rng
        self.ev(t_on, bay_id, "PROT", "ALARM_ON", "OIL TEMP HI", 2)
        if flood:
            t = t_on
            n = int(r.integers(30, 45))
            for i in range(n):
                t = t + pd.Timedelta(seconds=float(r.uniform(1.2, 2.8)))
                self.ev(t, bay_id, "PROT", "ALARM_OFF" if i % 2 == 0 else "ALARM_ON", "OIL TEMP HI", 3 if i % 2 == 0 else 2)
            if n % 2 == 1:  # pastikan akhir flood dalam keadaan ON
                self.ev(t + pd.Timedelta(seconds=2), bay_id, "PROT", "ALARM_ON", "OIL TEMP HI", 2)
        self.ev(t_off, bay_id, "PROT", "ALARM_OFF", "OIL TEMP HI", 3)


# =================================================================== suhu minyak trafo
TRAFO_SHARE = {"LSR-TRF-1": .0215, "LSR-TRF-2": .0205, "KRB-TRF-1": .0222, "KRB-TRF-2": .0190,
               "SMB-TRF-1": .0210, "SMB-TRF-2": .0200, "PTR-TRF-1": .0185, "PTR-TRF-2": .0296,
               "LAE-TRF-1": .0092, "SML-TRF-1": .0088, "BTM-TRF-1": .0195, "MLN-TRF-1": .0090}


def oil_temp(load_mw: np.ndarray, ambient: np.ndarray, mva: float, share: float, steps_per_tau: float):
    loading = load_mw * share / (mva * 0.9)
    target = ambient + 68 * np.clip(loading, 0, None) ** 1.6
    k = 1 - math.exp(-1 / steps_per_tau)
    out = np.empty_like(target)
    out[0] = target[0]
    for i in range(1, len(target)):
        out[i] = out[i - 1] + (target[i] - out[i - 1]) * k
    return out, loading


# =================================================================== orkestrasi
def build_events(rng, load: pd.DataFrame, wx: pd.DataFrame, bays: pd.DataFrame) -> Book:
    B = Builder(rng, load, wx, bays)
    days = pd.date_range(C.EVENT_START, C.DATA_END, freq="D", inclusive="left")
    quiet = (W("2026-11-19"), W("2026-11-25"))  # minggu training: hanya kejadian berskenario
    pht_all = [f"{a}-PHT-{b}{n}" for a, b, n in C.PENGHANTAR]
    pyl_all = [f"{g}-PYL-{nn}" for g, l in C.PENYULANG.items() for nn in l]
    bays_all = list(bays.bay_id[bays.jenis.isin(["PENGHANTAR", "TRAFO", "PENYULANG"])])

    def at(d, h0, h1):
        return d + pd.Timedelta(hours=float(rng.uniform(h0, h1))) + pd.Timedelta(milliseconds=int(rng.integers(0, 999)))

    for d in days:
        k = d.strftime("%Y-%m-%d")
        w = wx.loc[k]
        in_quiet = quiet[0] <= d <= quiet[1]
        m = d.month
        if not in_quiet:
            if w.hujan and w.petir:
                for p in pht_all:
                    prob = 0.22 if p == "LSR-PHT-KRB1" else 0.018
                    if rng.random() < prob:
                        B.pht_trip(p, at(d, 13.5, 18.5), "PETIR", ar_ok=rng.random() < 0.8,
                                   zona="Z1" if rng.random() < .85 else "Z2")
            if (not w.hujan) and m in (7, 8, 9, 10):
                for p, prob in (("SMB-PYL-07", 0.065), ("PTR-PYL-05", 0.02)):
                    if rng.random() < prob:
                        B.pyl_trip(p, at(d, 11, 17.5), "LAYANG2", "OCR" if rng.random() < .6 else "GFR",
                                   ar_ok=rng.random() < .35)
            if w.hujan and w.angin:
                for p, prob in (("MLN-PYL-02", 0.06), ("BTM-PYL-02", 0.03)):
                    if rng.random() < prob:
                        B.pyl_trip(p, at(d, 13, 20), "POHON", "GFR", ar_ok=rng.random() < .2,
                                   dur=float(rng.integers(30, 120)))
            if rng.random() < 6 / 365:
                B.pyl_trip(str(rng.choice(pyl_all)), at(d, 0, 24), "BINATANG", "OCR", ar_ok=False,
                           dur=float(rng.integers(30, 90)))
            if rng.random() < 4 / 365:
                B.pht_trip(str(rng.choice(pht_all)), at(d, 0, 24), "BELUM_DIKETAHUI", ar_ok=True)
        # RTU comm fail
        for g in ("LAE", "SML", "MLN", "BTM"):
            p = 0.35 if g != "BTM" else 0.10
            if w.hujan and w.hujan_mm > 12 and rng.random() < p and not (in_quiet and k != "2026-11-24"):
                B.rtu_fail(g, at(d, 13, 19).floor("s"), int(rng.integers(10, 120)))
        if rng.random() < 0.004:
            B.rtu_fail(str(rng.choice(["LSR", "KRB", "SMB", "PTR"])), at(d, 0, 24).floor("s"), int(rng.integers(5, 40)))
        if d.dayofweek == 6 and rng.random() < 0.45 and not in_quiet:
            B.maintenance(str(rng.choice(bays_all)), at(d, 8, 9).floor("min"), float(rng.integers(3, 6)))
        if rng.random() < 0.04:
            sig = str(rng.choice(["SF6 LOW PRESSURE", "DC SUPPLY FAIL", "CHARGER FAIL"]))
            B.misc_alarm(str(rng.choice([g[0] for g in C.GARDU_INDUK])), at(d, 0, 24).floor("s"), sig, int(rng.integers(10, 240)))

    # ---------------- kejadian berskenario
    B.pht_trip("PTR-PHT-BTM1", W("2025-08-12 10:37:41.205"), "EKSTERNAL", ar_ok=False, zona="Z1", fasa="T",
               scripted={"dur": 52, "padam": 17.8, "cuaca": "cerah"})
    B.pyl_trip("BTM-PYL-02", W("2025-06-19 06:12:03.511"), "PROTEKSI_MALKERJA", "OCR", ar_ok=False, dur=14, padam=3.2,
               extra="Trip terjadi saat penormalan setelah padam panjang (cold load pickup); arus inrush melebihi setting OCR instan.",
               cu="cerah", scripted=True)
    B.pyl_trip("LAE-PYL-01", W("2026-04-22 21:44:19.090"), "PERALATAN", "OCR", ar_ok=False, dur=126, padam=4.6,
               extra="Ditemukan CT fasa S di kubikel outgoing meledak; kubikel diisolasi dan CT diganti.", scripted=True)
    B.pyl_trip("KRB-PYL-04", W("2026-10-14 10:21:36.732"), "PROTEKSI_MALKERJA", "GFR", ar_ok=False, dur=22, padam=4.1,
               extra=("Rekaman relay tidak menunjukkan arus gangguan tanah yang berarti; patroli tidak menemukan titik gangguan. "
                      "Dugaan sementara setting GFR terlalu sensitif atau wiring CT bermasalah. Menunggu pengujian relay."),
               cu="cerah", scripted=True)
    for p, sec in (("SMB-PYL-06", 0.0), ("KRB-PYL-03", 0.16), ("PTR-PYL-03", 0.31)):
        B.pyl_trip(p, W("2026-09-14 19:12:05.400") + pd.Timedelta(seconds=sec), "EKSTERNAL", "UFR", ar_ok=False,
                   dur=40, padam={"SMB-PYL-06": 16.2, "KRB-PYL-03": 14.9, "PTR-PYL-03": 15.1}[p],
                   extra="Frekuensi sistem turun ke 49,38 Hz akibat gangguan unit pembangkit di luar area simulasi; UFR tahap 1 melepas penyulang sesuai skema.",
                   cu="cerah", scripted=True)
    B.ev(W("2026-09-14 19:12:04.950"), None, "GI.ALARM", "ALARM_ON", "FREKUENSI RENDAH 49.38 HZ", 1, gi="LSR")
    B.ev(W("2026-09-14 19:14:30.000"), None, "GI.ALARM", "ALARM_OFF", "FREKUENSI RENDAH 49.38 HZ", 3, gi="LSR")
    B.trf_trip("PTR-TRF-2", W("2025-12-09 19:05:12.640"), "OIL", 95, 38.0,
               ("Sejak pkl 18.40 WITA alarm OIL TEMP HI trafo 2 GI Paotere (sim) muncul berulang pada pembebanan ±97%. "
                "Pkl 19.05 trafo trip oleh proteksi suhu minyak. Beban 38,0 MW padam; 22 MW dimanuver ke trafo 1 pkl 19.48, "
                "sisanya normal setelah trafo 2 masuk kembali pkl 20.40 usai pendinginan dan pemeriksaan."),
               "Pembatasan beban trafo 2 maksimal 90% saat WBP; usulan mutasi beban penyulang ke trafo 1; pemeriksaan sistem pendingin (kipas ONAF).",
               "Dua kipas pendingin ONAF tidak beroperasi; pembebanan WBP mendekati 100% kapasitas", cu="cerah")
    B.trf_trip("SML-TRF-1", W("2026-07-02 03:18:44.110"), "DIFF", 270, 17.6,
               ("Pkl 03.11 WITA alarm Buchholz trafo 1 GI Samalona (sim). Pkl 03.18 trafo trip oleh relay differential dan Buchholz. "
                "Seluruh beban GI 17,6 MW padam. Trafo dinyatakan tidak boleh dimasukkan sebelum pengujian. Beban dipulihkan pkl 07.48 "
                "melalui trafo mobile."),
               "Trafo diisolasi; uji DGA minyak dan tahanan isolasi; pengoperasian trafo mobile; usulan penggantian trafo.",
               "Hasil DGA menunjukkan gas asetilen tinggi, indikasi busur api internal pada belitan", cu="cerah")
    # demo minggu training
    B.pht_trip("LSR-PHT-KRB1", W("2026-11-20 15:42:07.318"), "PETIR", ar_ok=True, zona="Z1", fasa="R",
               scripted={"cuaca": "hujan disertai petir"})
    B.pyl_trip("MLN-PYL-02", W("2026-11-23 13:12:48.004"), "POHON", "GFR", ar_ok=False, dur=41, padam=5.8,
               cu="hujan angin", scripted=True)
    B.pht_trip("LSR-PHT-KRB1", W("2026-11-23 16:05:22.871"), "PETIR", ar_ok=False, zona="Z1", fasa="S",
               scripted={"dur": 18, "padam": 22.6, "cuaca": "hujan disertai petir"})
    B.pyl_trip("SMB-PYL-07", W("2026-11-24 14:48:10.552"), "BINATANG", "OCR", ar_ok=False, dur=27, padam=3.9,
               extra="Ditemukan bangkai ular di kubikel outgoing.", cu="hujan", scripted=True)
    B.rtu_fail("LAE", W("2026-11-23 15:31:09"), 69)

    # ---------------- alarm suhu minyak dari model termal
    lf = load.set_index("ts")
    lf = lf[lf.index >= W(C.EVENT_START)]
    temp, loading = oil_temp(lf["kebutuhan_mw"].to_numpy(), lf["suhu_c"].to_numpy(), 60, TRAFO_SHARE["PTR-TRF-2"], 3)
    on = False
    t_on = None
    times = lf.index
    tele_start = W(C.TELEMETRY_START)
    for i in range(1, len(temp)):
        if times[i] >= tele_start:
            break
        if not on and temp[i] >= 85 and temp[i - 1] < 85:
            on = True
            t_on = times[i] + pd.Timedelta(seconds=float(rng.uniform(0, 1700)))
        elif on and temp[i] <= 82:
            on = False
            t_off = times[i] + pd.Timedelta(seconds=float(rng.uniform(0, 1700)))
            if quiet[0] <= t_on <= quiet[1] + pd.Timedelta(days=1):
                continue
            if W("2025-12-09") <= t_on < W("2025-12-10"):
                continue
            B.oil_alarm("PTR-TRF-2", t_on, t_off, flood=rng.random() < 0.22)
    # kipas pendingin trafo 2 Paotere mati 21-26 Nov 2026 (cerita RCA minggu training)
    B.ev(FAN_FAIL[0], "PTR-TRF-2", "PROT", "ALARM_ON", "FAN ONAF FAIL", 2)
    B.ev(FAN_FAIL[1], "PTR-TRF-2", "PROT", "ALARM_OFF", "FAN ONAF FAIL", 3)
    B.oil_alarm("PTR-TRF-2", W("2025-12-09 18:40:22"), W("2025-12-09 19:05:12.600"), flood=True)
    return B


FAN_FAIL = (W("2026-11-21 10:14:37"), W("2026-11-26 11:30:02"))


def oil_alarms_from_telemetry(B: "Builder", tele: pd.DataFrame, rng):
    """Alarm OIL TEMP HI di jendela telemetering diturunkan dari telemetering itu sendiri (konsisten)."""
    s = tele[tele.point_id == "PTR.TRF2.TEMP_OIL"].set_index("ts")["value"]
    s.index = s.index + H8
    on, t_on, first_nov23 = False, None, True
    for t, v in s.items():
        if not on and v >= 85:
            on, t_on = True, t + pd.Timedelta(seconds=float(rng.uniform(5, 800)))
        elif on and v <= 82:
            on = False
            t_off = t + pd.Timedelta(seconds=float(rng.uniform(5, 800)))
            forced = first_nov23 and t_on.strftime("%Y-%m-%d") == "2026-11-23"
            if forced:
                first_nov23 = False
            B.oil_alarm("PTR-TRF-2", t_on, t_off, flood=forced or rng.random() < 0.22)


def finalize_incidents(book: Book) -> pd.DataFrame:
    df = pd.DataFrame(book.incidents).sort_values("mulai").reset_index(drop=True)
    df["tahun"] = df["mulai"].dt.year
    df["no"] = df.groupby("tahun").cumcount() + 1
    df["gangguan_id"] = df.apply(lambda r: f"GGN-{r.tahun}-{r.no:04d}", axis=1)
    cutoff = W("2026-11-01")
    df["status_rca"] = np.where(df["mulai"] < cutoff, "FINAL", "DRAFT")
    df.loc[df["penyebab"] == "PROTEKSI_MALKERJA", "status_rca"] = np.where(
        df.loc[df["penyebab"] == "PROTEKSI_MALKERJA", "mulai"] > W("2026-01-01"), "OPEN", "FINAL")
    df.loc[(df["mulai"] >= W("2026-11-20")), "status_rca"] = "OPEN"
    df["rca_ringkas"] = np.where(df["status_rca"] == "FINAL",
                                 "Penyebab " + df["penyebab"].str.lower().str.replace("_", " ") + ": " + df["temuan"],
                                 "")
    cols = ["gangguan_id", "mulai", "selesai", "gi_id", "bay_id", "relay_kerja", "penyebab", "beban_padam_mw",
            "durasi_menit", "ens_mwh", "cuaca", "kronologi", "tindakan", "rca_ringkas", "status_rca"]
    out = df[cols].copy()
    out["mulai"] = out["mulai"] - H8
    out["selesai"] = out["selesai"] - H8
    return out


def finalize_events(book: Book) -> pd.DataFrame:
    ev = pd.DataFrame(book.events)
    ev = ev.sort_values(["ts_event", "jenis"]).reset_index(drop=True)
    ev.insert(0, "event_id", np.arange(500001, 500001 + len(ev)))
    ev["ts_event"] = ev["ts_event"] - H8
    ev["ts_received"] = ev["ts_received"] - H8
    return ev


# =================================================================== telemetering
def build_telemetry(rng, load: pd.DataFrame, points: pd.DataFrame, bays: pd.DataFrame, book: Book) -> pd.DataFrame:
    idx = pd.date_range(C.TELEMETRY_START, C.DATA_END, freq="15min", inclusive="left")
    lf = load.set_index("ts")
    sysmw = lf["beban_mw"].astype(float).interpolate().reindex(lf.index.union(idx)).interpolate().reindex(idx).to_numpy()
    amb = lf["suhu_c"].reindex(lf.index.union(idx)).interpolate().reindex(idx).to_numpy()
    n = len(idx)

    def ar(sd, phi=0.85):
        z = rng.normal(0, 1, n)
        e = np.zeros(n)
        for i in range(1, n):
            e[i] = phi * e[i - 1] + math.sqrt(1 - phi ** 2) * sd * z[i]
        return e

    outage = {}
    for bay_id, t0, t1 in book.outages:
        if t1 < idx[0]:
            continue
        m = (idx >= t0.floor("15min")) & (idx <= t1)
        outage[bay_id] = outage.get(bay_id, np.zeros(n, bool)) | m
    frames = []
    hp = points[points.ada_histori]
    pht_share = dict(zip([f"{a}-PHT-{b}{k}" for a, b, k in C.PENGHANTAR],
                         [.045, .041, .030, .028, .019, .022, .015, .012, .011]))
    for _, p in hp.iterrows():
        bay = p.bay_id
        if p.besaran == "MW" and "-TRF-" in bay:
            v = sysmw * TRAFO_SHARE[bay] * (1 + ar(0.02))
        elif p.besaran == "TEMP_OIL":
            mva = float(bays.set_index("bay_id").loc[bay, "kapasitas_mva"])
            amb_x = amb.copy()
            if bay == "PTR-TRF-2":  # kipas mati -> pendinginan buruk
                m_fan = (idx >= FAN_FAIL[0]) & (idx <= FAN_FAIL[1])
                amb_x = amb_x + np.where(m_fan, 7.5, 0.0)
            v, _ = oil_temp(sysmw, amb_x, mva, TRAFO_SHARE[bay], 6)
            v = v + ar(0.3)
        elif p.besaran == "MW" and "-PHT-" in bay:
            v = sysmw * pht_share[bay] * (1 + ar(0.03))
        elif p.besaran == "KV":
            v = 151.4 - 4.2 * (sysmw / 1800) + ar(0.25)
        elif p.besaran == "HZ":
            v = 50 + ar(0.018, 0.6)
        elif p.besaran == "A":
            mw = sysmw * 0.0042 * (1 + ar(0.04))
            v = mw * 1000 / (math.sqrt(3) * 20 * 0.9)
        else:
            continue
        v = np.array(v, dtype=float)
        if bay in outage and p.besaran in ("MW", "A"):
            v[outage[bay]] = 0.0
        q = np.array(["GOOD"] * n, dtype=object)
        for g, t0, t1 in book.rtu_fail:
            if g != p.gi_id or t1 < idx[0]:
                continue
            m = (idx >= t0) & (idx <= t1)
            if m.any():
                first = np.argmax(m)
                v[m] = v[max(first - 1, 0)]
                q[m] = "OLD"
        bad = rng.random(n) < 0.0005
        v[bad] = 0.0
        q[bad] = "INVALID"
        nd = 2 if p.besaran in ("HZ",) else 1
        frames.append(pd.DataFrame(dict(ts=idx - H8, point_id=p.point_id, value=np.round(v, nd + 1), quality=q)))
    return pd.concat(frames, ignore_index=True)


# =================================================================== ROH (metode koefisien)
def build_roh(load: pd.DataFrame, cal: pd.DataFrame) -> pd.DataFrame:
    s = load.set_index("ts")
    clean, _ = F.clean_history(s["beban_mw"], s["flag"], True)
    calx = cal.set_index("tanggal")
    out = []
    days = pd.date_range("2024-12-01", C.DATA_END, freq="D", inclusive="left")
    for d in days:
        hist = clean[(clean.index >= d - pd.Timedelta(days=400)) & (clean.index < d - pd.Timedelta(days=1))]
        fc = F.koefisien(hist, calx, d, 48)
        out.append(pd.DataFrame(dict(tanggal=d.strftime("%Y-%m-%d"), jam_ke=np.arange(1, 49),
                                     slot_mulai=fc.index.strftime("%H:%M"), prakiraan_mw=fc.round(1).to_numpy(),
                                     metode="KOEFISIEN")))
    return pd.concat(out, ignore_index=True)


# =================================================================== main
def main(out_dir: str = "data"):
    os.makedirs(out_dir, exist_ok=True)
    rng = np.random.default_rng(C.SEED)
    cal = build_calendar()
    wx = build_weather(rng, cal)
    load = build_load(rng, cal, wx)
    gi, bays, points = build_master()
    builder = build_events(rng, load, wx, bays)
    book = builder.b
    tele = build_telemetry(rng, load, points, bays, book)
    oil_alarms_from_telemetry(builder, tele, rng)
    inc = finalize_incidents(book)
    ev = finalize_events(book)
    roh = build_roh(load, cal)

    load_out = load.copy()
    load_out["ts"] = load_out["ts"] - H8
    load_out = load_out[["ts", "subsistem", "beban_mw", "suhu_c", "hujan_mm", "jenis_hari", "flag"]]
    cal_out = cal.merge(wx.reset_index()[["tanggal", "hujan", "hujan_mm", "petir"]], on="tanggal", how="left")
    cal_out = cal_out.rename(columns={"hujan_mm": "hujan_harian_mm"})

    gi.to_csv(f"{out_dir}/gardu_induk.csv", index=False)
    bays.to_csv(f"{out_dir}/bay.csv", index=False)
    points.to_csv(f"{out_dir}/scada_point.csv", index=False)
    cal_out.to_csv(f"{out_dir}/kalender.csv", index=False)
    inc.to_csv(f"{out_dir}/gangguan.csv", index=False, date_format="%Y-%m-%d %H:%M:%S.%f")
    ev.to_csv(f"{out_dir}/event_soe.csv.gz", index=False, date_format="%Y-%m-%d %H:%M:%S.%f")
    load_out.to_csv(f"{out_dir}/beban_sistem.csv.gz", index=False, date_format="%Y-%m-%d %H:%M:%S")
    tele.to_csv(f"{out_dir}/telemetry_tm.csv.gz", index=False, date_format="%Y-%m-%d %H:%M:%S")
    roh.to_csv(f"{out_dir}/rencana_operasi.csv.gz", index=False)
    print(f"gardu_induk {len(gi)}, bay {len(bays)}, point {len(points)}, gangguan {len(inc)}, "
          f"event {len(ev)}, beban {len(load_out)}, telemetry {len(tele)}, roh {len(roh)}")
    return dict(cal=cal, wx=wx, load=load, inc=inc, ev=ev, tele=tele, roh=roh)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data")
    main(ap.parse_args().out)
