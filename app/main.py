"""API SCADA tiruan untuk pelatihan AI Agent & Automation (data FIKTIF).

Jalankan lokal:  uvicorn app.main:app --reload
Swagger UI:      http://localhost:8000/docs
"""
from __future__ import annotations

import os
from typing import Any, Optional

import pandas as pd

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, Security
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from simcore import kb as KB
from simcore.store import SIM_OVERRIDE, BadRequest, DataStore, NotFound

DESCRIPTION = """
API **simulasi** data SCADA untuk pelatihan RevoU x PLN Makassar. Semua nama gardu induk,
kejadian, dan angka adalah **fiktif**.

Arsitektur yang ditiru: SCADA -> historian replica (read-only, DMZ) -> database pelaporan -> **API ini** -> n8n.

**Autentikasi:** kirim header `X-API-Key` (klik tombol *Authorize*). Setiap grup punya key sendiri.

**Waktu:** semua respons memakai WITA (`+08:00`). Parameter `start`/`end` tanpa zona waktu dianggap WITA.
Data setelah "sekarang" tidak ditampilkan, jadi event baru muncul seiring waktu berjalan.

**Pagination:** endpoint daftar mengembalikan `data`, `page`, `page_size`, `total`, `next_page`.
Ulangi request dengan `page=next_page` sampai `next_page` bernilai `null`.
"""

TAGS = [
    {"name": "Master", "description": "Gardu induk, bay, dan daftar point SCADA."},
    {"name": "Telemetering", "description": "Besaran analog per 15 menit (MW, kV, suhu minyak, frekuensi)."},
    {"name": "Event & alarm", "description": "Sequence of events (SOE): trip, PMT, alarm, RTU."},
    {"name": "Gangguan", "description": "Log gangguan yang ditulis dispatcher, untuk RCA dan chatbot."},
    {"name": "Beban & rencana", "description": "Beban sistem per 30 menit, ROH, kalender, prakiraan."},
    {"name": "Laporan", "description": "Tempat menyimpan laporan yang sudah disetujui."},
    {"name": "Dokumen", "description": "Dokumen SOP/IK fiktif (Markdown) untuk di-ingest ke vector store."},
    {"name": "Feed mentah", "description": "Data kotor untuk latihan cleaning: duplikat, format waktu campur, satuan campur."},
]

app = FastAPI(title="SCADA Sim API (fiktif)", version="1.0.0", description=DESCRIPTION, openapi_tags=TAGS)
store = DataStore.from_env()


# ------------------------------------------------------------------ auth
def _load_keys() -> dict[str, str]:
    """API_KEYS="grup-a:KEY1,grup-b:KEY2,trainer:KEY3"  ->  {KEY1: grup-a, ...}

    - Tanda kutip yang ikut tertempel dibuang.
    - Kosong sama sekali -> mode dev (key "dev-key").
    - Terisi tetapi tidak ada satu pun entri "nama:key" yang valid -> gagal start,
      supaya salah format tidak diam-diam jatuh ke key bawaan.
    """
    raw = os.getenv("API_KEYS", "")
    keys: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip().strip("\"'")
        if ":" not in part:
            continue
        name, key = part.split(":", 1)
        name, key = name.strip().strip("\"'"), key.strip().strip("\"'")
        if name and key:
            keys[key] = name
    if raw.strip() and not keys:
        raise RuntimeError("API_KEYS terisi tetapi tidak ada entri berformat nama:key. "
                           "Contoh: grup-1:KEYACAK1,grup-2:KEYACAK2,trainer:KEYACAK3")
    if not keys:
        keys = {"dev-key": "dev"}
    return keys


API_KEYS = _load_keys()
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
TRAINER_GROUPS = {"trainer", "dev"}


class SimNowMiddleware:
    """Header X-Sim-Now (mis. 2026-11-24T06:30) membekukan waktu untuk satu request.

    Hanya berlaku bila X-API-Key milik grup trainer, supaya peserta tidak bisa "melihat masa depan".
    """

    def __init__(self, app_):
        self.app = app_

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            sim = headers.get("x-sim-now")
            if sim and API_KEYS.get(headers.get("x-api-key", "")) in TRAINER_GROUPS:
                token = SIM_OVERRIDE.set(sim)
                try:
                    return await self.app(scope, receive, send)
                finally:
                    SIM_OVERRIDE.reset(token)
        return await self.app(scope, receive, send)


app.add_middleware(SimNowMiddleware)


def require_key(key: Optional[str] = Security(api_key_header)) -> str:
    if not key:
        raise HTTPException(status_code=401, detail="Header X-API-Key wajib diisi")
    if key not in API_KEYS:
        raise HTTPException(status_code=403, detail="X-API-Key tidak dikenal")
    return API_KEYS[key]


@app.exception_handler(BadRequest)
async def _bad_request(_: Request, exc: BadRequest):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(NotFound)
async def _not_found(_: Request, exc: NotFound):
    return JSONResponse(status_code=404, content={"detail": str(exc).strip("'\"")})


Start = Query(None, description="Awal rentang. Contoh: 2026-11-23T06:30 (WITA) atau 2026-11-22T22:30:00Z")
End = Query(None, description="Akhir rentang. Default: sekarang")
Page = Query(1, ge=1, description="Nomor halaman, mulai dari 1")


# ------------------------------------------------------------------ umum
@app.get("/health", tags=["Master"], summary="Cek API hidup (tanpa API key; key trainer menampilkan detail tambahan)")
def health(request: Request):
    now = store.now()
    out = {"status": "ok", "waktu_simulasi_wita": (now + pd.Timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%S") + "+08:00",
           "backend": os.getenv("DATA_BACKEND", "csv"), "kunci_dimuat": len(API_KEYS),
           "kunci_bawaan_aktif": "dev-key" in API_KEYS, "catatan": "Data fiktif untuk pelatihan"}
    # Detail hanya untuk key trainer: NAMA database (tanpa host/user/password)
    if API_KEYS.get(request.headers.get("x-api-key", "")) in TRAINER_GROUPS:
        out["database"] = store.db_name
    return out


@app.get("/api/v1/substations", tags=["Master"], summary="Daftar gardu induk")
def substations(grup: str = Depends(require_key)):
    return {"data": store.substations()}


@app.get("/api/v1/bays", tags=["Master"], summary="Daftar bay (penghantar, trafo, penyulang, busbar)")
def bays(gi_id: Optional[str] = Query(None, examples=["LSR"]),
         jenis: Optional[str] = Query(None, description="PENGHANTAR, TRAFO, PENYULANG, BUSBAR"),
         grup: str = Depends(require_key)):
    return {"data": store.bays(gi_id, jenis)}


@app.get("/api/v1/points", tags=["Master"], summary="Daftar point SCADA (tag list)")
def points(gi_id: Optional[str] = None, kategori: Optional[str] = Query(None, description="TM atau TS"),
           bay_id: Optional[str] = None, besaran: Optional[str] = Query(None, description="MW, KV, TEMP_OIL, HZ, A, ..."),
           grup: str = Depends(require_key)):
    return {"data": store.points(gi_id, kategori, bay_id, besaran)}


# ------------------------------------------------------------------ telemetering
@app.get("/api/v1/telemetry", tags=["Telemetering"], summary="Deret waktu satu point (per 15 menit)")
def telemetry(point_id: str = Query(..., examples=["PTR.TRF2.TEMP_OIL"]), start: Optional[str] = Start,
              end: Optional[str] = End, page: int = Page, page_size: int = Query(100, ge=1, le=500),
              grup: str = Depends(require_key)):
    return store.telemetry(point_id, start, end, page, page_size)


@app.get("/api/v1/telemetry/latest", tags=["Telemetering"], summary="Nilai terakhir tiap point + penanda stale")
def telemetry_latest(gi_id: Optional[str] = None, stale_minutes: int = Query(30, ge=5, le=1440),
                     grup: str = Depends(require_key)):
    return {"data": store.telemetry_latest(gi_id, stale_minutes)}


# ------------------------------------------------------------------ event
@app.get("/api/v1/events", tags=["Event & alarm"], summary="Sequence of events (default 24 jam terakhir)")
def events(start: Optional[str] = Start, end: Optional[str] = End, gi_id: Optional[str] = None,
           bay_id: Optional[str] = None,
           jenis: Optional[str] = Query(None, description="Satu atau beberapa, pisahkan koma: RELAY_TRIP,CB_OPEN"),
           prioritas_maks: Optional[int] = Query(None, ge=1, le=3, description="1 = kritis saja; 2 = kritis + penting"),
           page: int = Page, page_size: int = Query(50, ge=1, le=500), grup: str = Depends(require_key)):
    return store.events(start, end, gi_id, bay_id, jenis, prioritas_maks, page, page_size)


# ------------------------------------------------------------------ gangguan
@app.get("/api/v1/incidents", tags=["Gangguan"], summary="Log gangguan (terbaru dulu)")
def incidents(start: Optional[str] = Start, end: Optional[str] = End, gi_id: Optional[str] = None,
              bay_id: Optional[str] = Query(None, examples=["LSR-PHT-KRB1"]),
              penyebab: Optional[str] = Query(None, description="PETIR, POHON, LAYANG2, BINATANG, PERALATAN, PROTEKSI_MALKERJA, EKSTERNAL, BELUM_DIKETAHUI"),
              status_rca: Optional[str] = Query(None, description="OPEN, DRAFT, FINAL, BERLANGSUNG"),
              q: Optional[str] = Query(None, description="Cari kata di kronologi/tindakan/RCA"),
              page: int = Page, page_size: int = Query(50, ge=1, le=200), grup: str = Depends(require_key)):
    return store.incidents(start, end, gi_id, bay_id, penyebab, status_rca, q, page, page_size)


@app.get("/api/v1/incidents/{gangguan_id}", tags=["Gangguan"], summary="Detail gangguan + event SOE terkait")
def incident(gangguan_id: str, grup: str = Depends(require_key)):
    return store.incident(gangguan_id)


# ------------------------------------------------------------------ beban & rencana
@app.get("/api/v1/load/system", tags=["Beban & rencana"], summary="Beban sistem (default 7 hari terakhir)")
def load_system(start: Optional[str] = Start, end: Optional[str] = End,
                interval: str = Query("30m", pattern="^(30m|1h|1d)$"), grup: str = Depends(require_key)):
    return {"data": store.load_system(start, end, interval)}


@app.get("/api/v1/plan/roh", tags=["Beban & rencana"], summary="Rencana operasi harian (prakiraan metode koefisien)")
def plan_roh(tanggal: Optional[str] = Query(None, examples=["2026-11-24"]), start: Optional[str] = None,
             end: Optional[str] = None, grup: str = Depends(require_key)):
    return {"data": store.plan_roh(tanggal, start, end)}


@app.get("/api/v1/calendar", tags=["Beban & rencana"], summary="Kalender: jenis hari, libur, Ramadan, cuaca harian")
def calendar(start: Optional[str] = Query(None, examples=["2026-12-20"]), end: Optional[str] = Query(None, examples=["2027-01-03"]),
             grup: str = Depends(require_key)):
    return {"data": store.calendar(start, end)}


class ForecastIn(BaseModel):
    method: str = Field("koefisien", description="koefisien, seasonal_naive, holt_winters (alias ets), atau all")
    start: Optional[str] = Field(None, description="Awal prakiraan (WITA). Default: slot 30 menit berikutnya")
    horizon_slots: int = Field(48, ge=1, le=672, description="Jumlah slot 30 menit. 48 = 1 hari, 336 = 1 minggu")
    history_weeks: int = Field(8, ge=2, le=52)
    exclude_flags: bool = Field(True, description="Ganti slot pemadaman/UFR/data hilang sebelum menghitung")


class BacktestIn(BaseModel):
    method: str = Field("all", description="koefisien, seasonal_naive, holt_winters, atau all")
    start: Optional[str] = Field(None, description="Hari setelah periode uji. Default: hari ini (uji = 7 hari terakhir)")
    days: int = Field(7, ge=1, le=28)
    exclude_flags: bool = True


@app.post("/api/v1/forecast", tags=["Beban & rencana"], summary="Prakiraan beban sistem")
def forecast(body: ForecastIn = Body(..., examples=[{"method": "all", "horizon_slots": 336}]),
             grup: str = Depends(require_key)):
    return store.forecast(body.method, body.start, body.horizon_slots, body.history_weeks, body.exclude_flags)


@app.post("/api/v1/forecast/backtest", tags=["Beban & rencana"], summary="Uji akurasi metode pada minggu lalu (MAPE total & WBP)")
def backtest(body: BacktestIn = Body(..., examples=[{"method": "all"}]), grup: str = Depends(require_key)):
    return store.backtest(body.method, body.start, body.days, body.exclude_flags)


# ------------------------------------------------------------------ laporan
class ReportIn(BaseModel):
    judul: str = Field(..., examples=["Laporan kejadian harian 24 Nov 2026"])
    isi: Any = Field(..., description="Teks atau JSON laporan")
    disetujui_oleh: Optional[str] = Field(None, examples=["Supervisor Operasi (sim)"])
    metadata: Optional[dict] = None


@app.post("/api/v1/reports", tags=["Laporan"], status_code=201, summary="Simpan laporan yang sudah disetujui")
def add_report(body: ReportIn, grup: str = Depends(require_key)):
    return store.add_report(grup, body.model_dump() if hasattr(body, "model_dump") else body.dict())


@app.get("/api/v1/reports", tags=["Laporan"], summary="Daftar laporan milik grup ini")
def list_reports(semua_grup: bool = False, grup: str = Depends(require_key)):
    return {"data": store.list_reports(None if (semua_grup and grup in ("trainer", "dev")) else grup)}


# ------------------------------------------------------------------ dokumen
@app.get("/api/v1/kb", tags=["Dokumen"], summary="Semua dokumen SOP fiktif beserta isinya (untuk ingest)")
def kb_list(dengan_isi: bool = Query(True, description="false = hanya daftar tanpa isi"), grup: str = Depends(require_key)):
    return {"data": KB.list_docs(dengan_isi)}


@app.get("/api/v1/kb/{doc_id}", tags=["Dokumen"], summary="Satu dokumen, contoh doc_id: SOP-OPS-01")
def kb_get(doc_id: str, grup: str = Depends(require_key)):
    d = KB.get_doc(doc_id)
    if not d:
        raise NotFound(f"{doc_id} tidak ditemukan. Lihat GET /api/v1/kb?dengan_isi=false")
    return d


# ------------------------------------------------------------------ feed mentah
@app.get("/raw/events", tags=["Feed mentah"], summary="Event mentah: duplikat, waktu campur UTC/lokal, urutan acak")
def raw_events(start: Optional[str] = Start, end: Optional[str] = End, gi_id: Optional[str] = None,
               page: int = Page, page_size: int = Query(100, ge=1, le=500), grup: str = Depends(require_key)):
    return store.raw_events(start, end, gi_id, page, page_size)


@app.get("/raw/telemetry", tags=["Feed mentah"], summary="Telemetering mentah: V/kV, kW/MW, 9999, null, duplikat")
def raw_telemetry(point_id: str = Query(..., examples=["LSR.BUS150.KV"]), start: Optional[str] = Start,
                  end: Optional[str] = End, page: int = Page, page_size: int = Query(200, ge=1, le=500),
                  grup: str = Depends(require_key)):
    return store.raw_telemetry(point_id, start, end, page, page_size)
