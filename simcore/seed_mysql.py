"""Muat CSV di ./data ke MySQL (opsional; untuk demo node MySQL di n8n).

    DATABASE_URL=mysql://user:pass@host:port/db  python -m simcore.seed_mysql

Railway: isi DATABASE_URL dengan variabel MYSQL_URL dari service MySQL.
"""
from __future__ import annotations

import os
import sys

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.mysql import BIGINT, DATETIME, VARCHAR

from .store import TABLES, normalize_mysql_url

DT3 = DATETIME(fsp=3)
DTYPES = {
    "gardu_induk": {"gi_id": VARCHAR(8)},
    "bay": {"bay_id": VARCHAR(20), "gi_id": VARCHAR(8)},
    "scada_point": {"point_id": VARCHAR(40), "gi_id": VARCHAR(8), "bay_id": VARCHAR(20)},
    "kalender": {"tanggal": VARCHAR(10)},
    "gangguan": {"gangguan_id": VARCHAR(16), "bay_id": VARCHAR(20), "gi_id": VARCHAR(8), "mulai": DT3, "selesai": DT3},
    "event_soe": {"event_id": BIGINT, "bay_id": VARCHAR(20), "gi_id": VARCHAR(8), "point_id": VARCHAR(40),
                  "jenis": VARCHAR(20), "ts_event": DT3, "ts_received": DT3},
    "beban_sistem": {"ts": DATETIME},
    "telemetry_tm": {"point_id": VARCHAR(40), "ts": DATETIME},
    "rencana_operasi": {"tanggal": VARCHAR(10)},
}
INDEXES = [
    "ALTER TABLE gardu_induk ADD PRIMARY KEY (gi_id)",
    "ALTER TABLE bay ADD PRIMARY KEY (bay_id)",
    "ALTER TABLE scada_point ADD PRIMARY KEY (point_id)",
    "ALTER TABLE gangguan ADD PRIMARY KEY (gangguan_id)",
    "ALTER TABLE event_soe ADD PRIMARY KEY (event_id)",
    "CREATE INDEX idx_ev_ts ON event_soe (ts_event)",
    "CREATE INDEX idx_ev_bay ON event_soe (bay_id, ts_event)",
    "CREATE INDEX idx_tele ON telemetry_tm (point_id, ts)",
    "CREATE INDEX idx_beban ON beban_sistem (ts)",
    "CREATE INDEX idx_roh ON rencana_operasi (tanggal(10))",
    """CREATE TABLE IF NOT EXISTS laporan (
         report_id VARCHAR(16) PRIMARY KEY, grup VARCHAR(40), diterima DATETIME,
         judul TEXT, isi LONGTEXT, disetujui_oleh TEXT, metadata TEXT)""",
    """CREATE OR REPLACE VIEW v_event_kritis AS
         SELECT event_id, CONVERT_TZ(ts_event,'+00:00','+08:00') AS ts_event_wita,
                gi_id, bay_id, jenis, sinyal, fasa
         FROM event_soe WHERE prioritas = 1""",
]


def main(data_dir: str = "data"):
    url = os.getenv("DATABASE_URL") or os.getenv("MYSQL_URL")
    if not url:
        sys.exit("Set DATABASE_URL dulu, contoh: mysql://root:pass@host:3306/railway")
    engine = create_engine(normalize_mysql_url(url), pool_pre_ping=True)
    for name, (fn, dates) in TABLES.items():
        df = pd.read_csv(os.path.join(data_dir, fn), parse_dates=dates or None)
        df.to_sql(name, engine, if_exists="replace", index=False, chunksize=5000, method="multi",
                  dtype=DTYPES.get(name))
        print(f"{name:16s} {len(df):>8,d} baris")
    with engine.begin() as c:
        for sql in INDEXES:
            try:
                c.execute(text(sql))
            except Exception as e:  # noqa: BLE001  (indeks sudah ada saat seed ulang)
                print("lewati:", sql.split("\n")[0][:60], "->", str(e).split("\n")[0][:80])
    print("Selesai. Set DATA_BACKEND=mysql pada service API lalu redeploy.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data")
