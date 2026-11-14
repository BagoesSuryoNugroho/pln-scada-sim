"""Smoke test semua route memakai stub FastAPI (sandbox tanpa internet).

Di laptop/Railway dengan FastAPI asli, cukup buka /docs.
"""
import asyncio, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "stubs"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SIM_NOW", "2026-11-24T06:30")
os.environ["API_KEYS"] = "grup-a:key-a,trainer:key-t"
import app.main as M
from fastapi import HTTPException

R = M.app.routes
def call(method, path, **kw):
    fn = R[(method, path)]
    try:
        return fn(**kw)
    except tuple(M.app.handlers) as e:
        h = M.app.handlers[type(e)]
        resp = asyncio.run(h(None, e))
        return {"_status": resp.status_code, **resp.content}

ok = 0
def check(name, cond, info=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + (f"  {info}" if info else ""))
    ok += bool(cond)
    if not cond: sys.exit(1)

# auth
try: M.require_key(None); check("401 tanpa key", False)
except HTTPException as e: check("401 tanpa key", e.status_code == 401)
try: M.require_key("salah"); check("403 key salah", False)
except HTTPException as e: check("403 key salah", e.status_code == 403)
check("key valid -> nama grup", M.require_key("key-a") == "grup-a")

g = "grup-a"
check("health", call("GET", "/health")["status"] == "ok")
check("substations 8", len(call("GET", "/api/v1/substations", grup=g)["data"]) == 8)
check("bays trafo", len(call("GET", "/api/v1/bays", gi_id="PTR", jenis="TRAFO", grup=g)["data"]) == 2)
check("points TM LSR", len(call("GET", "/api/v1/points", gi_id="LSR", kategori="TM", grup=g)["data"]) > 5)
r = call("GET", "/api/v1/events", grup=g, page_size=20)
check("events 24 jam + pagination", r["total"] > 20 and r["next_page"] == 2, f"total={r['total']}")
r2 = call("GET", "/api/v1/events", grup=g, page=r["total"] // 20 + 1, page_size=20)
check("halaman terakhir next_page null", r2["next_page"] is None)
r = call("GET", "/api/v1/events", grup=g, jenis="RELAY_TRIP,CB_OPEN", prioritas_maks=1, page_size=100)
check("filter jenis+prioritas", all(e["prioritas"] == 1 for e in r["data"]) and r["total"] > 0)
r = call("GET", "/api/v1/events", grup=g, start="2026-11-25T00:00")
check("start di masa depan -> 400", r.get("_status") == 400, r.get("detail"))
r = call("GET", "/api/v1/incidents", grup=g, bay_id="LSR-PHT-KRB1", page_size=5)
check("incidents KRB1", r["total"] > 10 and r["data"][0]["mulai"].startswith("2026-11-23"))
gid = r["data"][0]["gangguan_id"]
d = call("GET", "/api/v1/incidents/{gangguan_id}", gangguan_id=gid, grup=g)
check("detail + event terkait", len(d["event_terkait"]) >= 5, f"{gid}: {len(d['event_terkait'])} event")
check("incident 404", call("GET", "/api/v1/incidents/{gangguan_id}", gangguan_id="GGN-1999-0001", grup=g)["_status"] == 404)
r = call("GET", "/api/v1/telemetry", grup=g, point_id="PTR.TRF2.TEMP_OIL", start="2026-11-23T18:00", end="2026-11-23T21:00")
check("telemetry suhu > 85 saat WBP", max(x["value"] for x in r["data"]) > 85)
check("telemetry point tanpa histori 404", call("GET", "/api/v1/telemetry", grup=g, point_id="LSR.TRF1.TAP")["_status"] == 404)
r = call("GET", "/api/v1/telemetry/latest", grup=g, gi_id="LAE")
check("latest LAE", len(r["data"]) >= 2)
r = call("GET", "/api/v1/load/system", grup=g, interval="1d", start="2026-11-17", end="2026-11-24")
check("beban harian (hari terakhir parsial ditandai)", len(r["data"]) == 8 and r["data"][-1]["slot_lengkap"] is False and r["data"][0]["beban_puncak_mw"] > 1500)
check("interval salah 400", call("GET", "/api/v1/load/system", grup=g, interval="2h")["_status"] == 400)
r = call("GET", "/api/v1/plan/roh", grup=g, tanggal="2026-11-23")
check("ROH + realisasi", len(r["data"]) == 48 and r["data"][37]["realisasi_mw"] is not None)
check("ROH belum rilis 404", call("GET", "/api/v1/plan/roh", grup=g, tanggal="2026-11-26")["_status"] == 404)
r = call("GET", "/api/v1/calendar", grup=g, start="2026-12-20", end="2027-01-03")
check("kalender Nataru", any(x["jenis_hari"] == "LIBUR_NAS" for x in r["data"]))
r = call("POST", "/api/v1/forecast", grup=g, body=M.ForecastIn(method="all", horizon_slots=336))
check("forecast 3 metode", len(r["metode"]) == 3 and len(r["metode"]["koefisien"]["prakiraan"]) == 336)
check("forecast metode salah 400", call("POST", "/api/v1/forecast", grup=g, body=M.ForecastIn(method="arima"))["_status"] == 400)
r = call("POST", "/api/v1/forecast/backtest", grup=g, body=M.BacktestIn())
check("backtest", r["terbaik"] in ("koefisien", "seasonal_naive", "holt_winters"), json.dumps({k: v["mape_total_pct"] for k, v in r["metode"].items()}))
rep = call("POST", "/api/v1/reports", grup=g, body=M.ReportIn(judul="Uji", isi={"ringkasan": "ok"}, disetujui_oleh="Spv"))
check("simpan laporan", rep["report_id"].startswith("LAP-") and rep["grup"] == "grup-a")
check("daftar laporan grup", len(call("GET", "/api/v1/reports", grup=g)["data"]) == 1)
check("grup lain tidak lihat", len(call("GET", "/api/v1/reports", grup="grup-b")["data"]) == 0)
r = call("GET", "/raw/events", grup=g, page_size=500)
fmt_local = sum(1 for e in r["data"] if "/" in e["ts_event"])
ids = [e["event_id"] for e in r["data"]]
check("raw events kotor", fmt_local > 0 and len(ids) > len(set(ids)), f"lokal={fmt_local}, duplikat={len(ids)-len(set(ids))}")
r = call("GET", "/raw/telemetry", grup=g, point_id="LSR.BUS150.KV", start="2026-11-22", end="2026-11-24", page_size=500)
units = {x["satuan"] for x in r["data"]}
check("raw telemetry satuan campur", units == {"kV", "V"}, str(units))

r = call("GET", "/api/v1/kb", grup=g, dengan_isi=True)
check("kb: 7 dokumen berisi", len(r["data"]) == 7 and all(d["isi"] for d in r["data"]), ", ".join(d["doc_id"] for d in r["data"]))
check("kb: doc_id & judul", r["data"][0]["doc_id"] == "GLOS-01" and r["data"][0]["judul"].startswith("GLOS-01"))
d = call("GET", "/api/v1/kb/{doc_id}", doc_id="sop-ops-01", grup=g)
check("kb: ambil satu dokumen (tidak peka huruf besar)", "A/R" in d["isi"] and d["doc_id"] == "SOP-OPS-01")
check("kb: tidak ada -> 404", call("GET", "/api/v1/kb/{doc_id}", doc_id="XXX", grup=g)["_status"] == 404)

# middleware X-Sim-Now
import simcore.store as ST
seen = {}
async def inner(scope, receive, send):
    seen["now"] = M.store.now()
mw = M.SimNowMiddleware(inner)
def run_mw(key):
    scope = {"type": "http", "headers": [(b"x-api-key", key.encode()), (b"x-sim-now", b"2026-12-01T08:00")]}
    asyncio.run(mw(scope, None, None)); return seen["now"]
check("X-Sim-Now berlaku untuk trainer", str(run_mw("key-t")) == "2026-12-01 00:00:00")
check("X-Sim-Now diabaikan untuk peserta", str(run_mw("key-a")) == "2026-11-23 22:30:00")
print(f"\n{ok} cek lulus")
