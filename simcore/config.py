"""Konstanta bersama: rentang waktu, master data, kalender."""
import datetime as dt

SEED = 20261123
WITA_OFFSET = dt.timedelta(hours=8)

LOAD_START = "2024-11-01"      # beban sistem per 30 menit (WITA)
DATA_END = "2027-02-01"        # eksklusif; data "masa depan" disembunyikan API sampai waktunya tiba
EVENT_START = "2025-01-01"     # event SOE & log gangguan
TELEMETRY_START = "2026-11-01" # telemetering per 15 menit

# (gi_id, nama, level_kv, media_kom, rtu_tipe)
GARDU_INDUK = [
    ("LSR", "GI Losari (sim)", 150, "FO", "RTU-X200 (fiktif)"),
    ("KRB", "GI Karebosi (sim)", 150, "FO", "RTU-X200 (fiktif)"),
    ("SMB", "GI Somba Opu (sim)", 150, "FO", "GW-SAS-61850 (fiktif)"),
    ("PTR", "GI Paotere (sim)", 150, "FO", "RTU-X200 (fiktif)"),
    ("LAE", "GI Lae-Lae (sim)", 150, "RADIO", "RTU-M10 (fiktif)"),
    ("SML", "GI Samalona (sim)", 150, "RADIO", "RTU-M10 (fiktif)"),
    ("BTM", "GI Bantimurung (sim)", 150, "PLC", "RTU-X200 (fiktif)"),
    ("MLN", "GI Malino (sim)", 150, "RADIO", "RTU-M10 (fiktif)"),
]
GI_NAMA = {g[0]: g[1] for g in GARDU_INDUK}

# penghantar: (gi_asal, gi_tujuan, sirkit)
PENGHANTAR = [
    ("LSR", "KRB", 1), ("LSR", "KRB", 2), ("LSR", "SMB", 1), ("KRB", "PTR", 1),
    ("SMB", "MLN", 1), ("PTR", "BTM", 1), ("BTM", "MLN", 1), ("LAE", "LSR", 1),
    ("SML", "SMB", 1),
]
# trafo: gi -> [(nomor, kapasitas_mva)]
TRAFO = {
    "LSR": [(1, 60), (2, 60)], "KRB": [(1, 60), (2, 60)], "SMB": [(1, 60), (2, 60)],
    "PTR": [(1, 60), (2, 60)], "LAE": [(1, 30)], "SML": [(1, 30)],
    "BTM": [(1, 60)], "MLN": [(1, 30)],
}
PENYULANG = {
    "LSR": ["01", "02"], "KRB": ["03", "04"], "SMB": ["06", "07"], "PTR": ["03", "05"],
    "LAE": ["01"], "SML": ["01"], "BTM": ["02"], "MLN": ["01", "02"],
}

PENYEBAB = ["PETIR", "POHON", "LAYANG2", "BINATANG", "PERALATAN",
            "PROTEKSI_MALKERJA", "EKSTERNAL", "BELUM_DIKETAHUI"]

# Kalender libur nasional & cuti bersama (perkiraan, cukup untuk simulasi)
LIBUR_NAS = {
    "2024-11-27": "Pilkada serentak", "2024-12-25": "Natal",
    "2025-01-01": "Tahun Baru Masehi", "2025-01-27": "Isra Mikraj", "2025-01-29": "Tahun Baru Imlek",
    "2025-03-29": "Nyepi", "2025-03-31": "Idulfitri 1446 H", "2025-04-01": "Idulfitri 1446 H",
    "2025-04-18": "Wafat Isa Almasih", "2025-05-01": "Hari Buruh", "2025-05-12": "Waisak",
    "2025-05-29": "Kenaikan Isa Almasih", "2025-06-01": "Hari Lahir Pancasila", "2025-06-06": "Iduladha",
    "2025-06-27": "Tahun Baru Islam", "2025-08-17": "HUT RI", "2025-09-05": "Maulid Nabi",
    "2025-12-25": "Natal",
    "2026-01-01": "Tahun Baru Masehi", "2026-01-16": "Isra Mikraj", "2026-02-17": "Tahun Baru Imlek",
    "2026-03-19": "Nyepi", "2026-03-20": "Idulfitri 1447 H", "2026-03-21": "Idulfitri 1447 H",
    "2026-04-03": "Wafat Isa Almasih", "2026-05-01": "Hari Buruh", "2026-05-14": "Kenaikan Isa Almasih",
    "2026-05-27": "Iduladha", "2026-05-31": "Waisak", "2026-06-01": "Hari Lahir Pancasila",
    "2026-06-16": "Tahun Baru Islam", "2026-08-17": "HUT RI", "2026-08-25": "Maulid Nabi",
    "2026-12-25": "Natal", "2027-01-01": "Tahun Baru Masehi",
}
CUTI_BERSAMA = ["2024-12-26", "2025-03-28", "2025-04-02", "2025-04-03", "2025-04-04", "2025-04-07",
                "2025-12-26", "2026-03-18", "2026-03-23", "2026-03-24", "2026-12-24"]
RAMADAN = [("2025-03-01", "2025-03-30"), ("2026-02-18", "2026-03-19")]
MUDIK = [("2025-03-26", "2025-04-08"), ("2026-03-14", "2026-03-28")]

# Pemadaman bergilir & pelepasan beban (beban tercatat < kebutuhan)
PEMADAMAN_BERGILIR = [  # (mulai WITA, selesai WITA, MW dilepas)
    ("2026-08-31 10:00", "2026-08-31 12:00", 110), ("2026-08-31 14:00", "2026-08-31 16:00", 115),
    ("2026-08-31 18:00", "2026-08-31 20:00", 125), ("2026-09-01 18:00", "2026-09-01 20:00", 85),
]
UFR_EVENT = ("2026-09-14 19:12", "2026-09-14 19:52", 46)
