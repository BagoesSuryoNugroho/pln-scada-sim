# SCADA Sim API: data SCADA fiktif untuk pelatihan AI Agent & Automation

Paket ini menyediakan "dapur" untuk training RevoU x PLN Makassar (23–25 Nov 2026):
dataset SCADA fiktif yang deterministik, API dengan Swagger, layanan forecast, dan dokumen SOP fiktif untuk RAG.
Peserta cukup memanggil API dari n8n; tidak ada yang perlu diinstal di laptop mereka.

> Semua nama gardu induk, kejadian, angka, dan dokumen adalah **fiktif**. Jangan unggah data operasional asli.

## Isi folder

| Path | Isi |
|---|---|
| `app/main.py` | API FastAPI (Swagger di `/docs`) |
| `simcore/generate.py` | Generator dataset (seed tetap, ~30 detik) |
| `simcore/forecast.py` | Metode koefisien, seasonal naive, Holt-Winters, MAPE |
| `simcore/store.py` | Query, pagination, feed kotor, aturan "data masa depan disembunyikan" |
| `simcore/seed_mysql.py` | Opsional: muat dataset ke MySQL |
| `data/` | Dataset hasil generate (CSV/CSV.gz) |
| `kb/` | 7 dokumen SOP/IK fiktif untuk vector store (disajikan API di `/api/v1/kb`) |
| `n8n_datatables/` | CSV siap impor ke n8n Data Tables: uji chatbot, contoh kronologi |
| `tests/smoke_test.py` | 40 cek otomatis untuk semua endpoint |
| `KUNCI_TRAINER.md` | Pola yang ditanam, jadwal kejadian "live", kunci jawaban (jangan dibagikan ke peserta) |

## Jalankan di laptop (trainer)

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python tests/smoke_test.py                              # opsional, 40 cek
uvicorn app.main:app --reload
# buka http://localhost:8000/docs, klik Authorize, isi: dev-key
```

Tanpa variabel `API_KEYS`, key default adalah `dev-key`.
Dataset sudah ikut di folder `data/`. Untuk membuat ulang (hasil identik): `python -m simcore.generate --out data`.

## Deploy ke Railway (disarankan, tidak tidur saat idle)

1. Buat repo GitHub privat, push seluruh folder ini.
2. Railway: **New Project**, lalu **Deploy from GitHub repo**, pilih repo tersebut. `railway.json` membuat Railway memakai `Dockerfile` dan health check `/health`.
3. Tab **Variables** pada service: isi `API_KEYS` (lihat `.env.example`). Contoh:
   `grup-a:a7f3...,grup-b:9c21...,grup-c:44de...,grup-d:b0e8...,trainer:t-55aa...`
4. Tab **Settings**, bagian **Networking**: **Generate Domain**. Hasilnya seperti `https://scada-sim-production.up.railway.app`.
5. Buka `https://<domain>/docs`. Bagikan URL ini dan key per grup ke peserta.

Hindari tier gratis yang menidurkan service saat idle; request pertama setelah tidur bisa menunggu sekitar satu menit dan merusak demo.

### Opsional: MySQL sebagai "historian replica"

Mode default membaca CSV, jadi MySQL tidak wajib. Tambahkan bila ingin mendemokan node MySQL di n8n.

1. Di project yang sama: **New**, lalu **Database**, lalu **MySQL**.
2. Dari laptop, isi tabel sekali (pakai URL publik dari variabel service MySQL, biasanya `MYSQL_PUBLIC_URL`):
   ```bash
   DATABASE_URL="mysql://root:...@...proxy.rlwy.net:PORT/railway" python -m simcore.seed_mysql
   ```
3. Pada service API, tambahkan `DATA_BACKEND=mysql` dan `DATABASE_URL` yang merujuk ke URL internal MySQL (di Railway bisa memakai referensi variabel, misalnya `${{MySQL.MYSQL_URL}}`). Redeploy.
4. Buat user read-only untuk demo node MySQL di n8n:
   ```sql
   CREATE USER 'peserta_ro'@'%' IDENTIFIED BY 'ganti-password';
   GRANT SELECT ON railway.* TO 'peserta_ro'@'%';
   ```
   Sudah tersedia view `v_event_kritis` (event prioritas 1, waktu WITA) untuk contoh query.

## Variabel lingkungan

| Variabel | Fungsi |
|---|---|
| `API_KEYS` | `nama:key` dipisah koma. Grup bernama `trainer` boleh memakai header `X-Sim-Now`. |
| `SIM_NOW` | Membekukan waktu untuk semua pengguna (WITA), mis. `2026-11-24T06:30`. **Kosongkan saat hari training** supaya data berjalan nyata. |
| `DATA_BACKEND` | `csv` (default) atau `mysql`. |
| `DATABASE_URL` | URL MySQL bila `DATA_BACKEND=mysql`. Format `mysql://` otomatis diubah ke `mysql+pymysql://`. |

## Aturan waktu

- Semua respons memakai WITA (`+08:00`). Input tanpa zona waktu dianggap WITA; input berakhiran `Z` dianggap UTC.
- Data setelah "sekarang" tidak ditampilkan. Dataset berjalan sampai 31 Jan 2027, jadi kejadian baru akan "muncul" selama training dan capstone.
- Gangguan yang sedang berlangsung tampil dengan `status_rca = BERLANGSUNG`, tanpa durasi dan ENS.
- ROH untuk tanggal D baru tersedia mulai D-1 pukul 10.00 WITA.
- Untuk dry-run, trainer bisa mengirim header `X-Sim-Now: 2026-11-24T06:30` bersama key trainer. Peserta tidak terpengaruh.

## Endpoint

| Method & path | Kegunaan | Dipakai di |
|---|---|---|
| `GET /health` | Cek hidup, tanpa key | Hari 2 latihan 1 |
| `GET /api/v1/substations`, `/bays`, `/points` | Master data dan tag list | Hari 2 |
| `GET /api/v1/telemetry?point_id=` | Deret waktu 15 menit (point dengan `ada_histori=true`) | Hari 2, capstone Fasop |
| `GET /api/v1/telemetry/latest?gi_id=` | Nilai terakhir + `perlu_dicek` untuk point stale | Capstone Fasop |
| `GET /api/v1/events` | SOE, default 24 jam terakhir; filter `gi_id`, `bay_id`, `jenis` (koma), `prioritas_maks` | Hari 2 guided build |
| `GET /api/v1/incidents`, `/incidents/{id}` | Log gangguan; `q` untuk cari kata; detail berisi event terkait | Hari 1 tool agent RCA |
| `GET /api/v1/load/system?interval=30m|1h|1d` | Beban sistem; `1d` berisi puncak, jam puncak, energi | Hari 3 |
| `GET /api/v1/plan/roh?tanggal=` | ROH metode koefisien + realisasi + deviasi | Hari 3, capstone Perencanaan |
| `GET /api/v1/calendar` | Jenis hari, libur, Ramadan, hujan/petir harian | Hari 3 catatan perencanaan |
| `POST /api/v1/forecast` | `{"method":"all","horizon_slots":336}` | Hari 3 guided build |
| `POST /api/v1/forecast/backtest` | MAPE total, MAPE WBP, error puncak, per hari, metode terbaik | Hari 3 |
| `GET /api/v1/kb`, `/api/v1/kb/{doc_id}` | 7 dokumen SOP fiktif (Markdown) berikut isinya, untuk workflow ingest | Hari 1 Blok 3 |
| `POST /api/v1/reports`, `GET /api/v1/reports` | Simpan/lihat laporan yang disetujui (per grup) | Hari 2 langkah akhir |
| `GET /raw/events`, `/raw/telemetry` | Feed kotor: duplikat, waktu UTC/lokal campur, V/kV, kW/MW, 9999, null | Hari 2 Blok 3 |

Format daftar: `{"data": [...], "page": 1, "page_size": 50, "total": 137, "next_page": 2}`.

## Skrip operasi (folder `scripts/`)

| Skrip | Fungsi |
|---|---|
| `scripts/rotate_keys.sh` | Membuat key acak baru (grup-1..4 + trainer), menyimpannya di `.secrets/` (izin 600, masuk `.gitignore`), mengubah `API_KEYS` di Railway lewat stdin, lalu memverifikasi (key baru diterima, `dev-key` dan key lama ditolak) |
| `scripts/update_code.sh` | Menyalin versi kode terbaru ke repo lokal (tanpa menghapus apa pun), menjalankan smoke test, commit, lalu deploy (`push`, `up`, atau `none`) |

Pakai `bash scripts/<nama>.sh --help` untuk daftar opsi. Keduanya mendukung `--dry-run`.
Kedua skrip selalu memakai `--service pln-scada-sim` secara eksplisit karena `railway link` bisa saja tertaut ke service MySQL.

## Konfigurasi di n8n

**Credential.** Buat credential *Header Auth*: Name `X-API-Key`, Value key grup. Share ke anggota grup. Di node HTTP Request pilih Authentication *Generic Credential Type*, lalu *Header Auth*.

**Pagination di node HTTP Request.** Options, lalu Pagination:
- Mode: *Update a Parameter in Each Request*
- Parameter: Type *Query*, Name `page`, Value `{{ $response.body.next_page }}`
- Pagination Complete When: *Other*, Complete Expression `{{ $response.body.next_page === null }}`

Lanjutkan dengan node *Split Out* pada field `data`.

**Import cURL.** Di Swagger klik *Try it out*, lalu *Execute*, salin perintah cURL, dan tempel ke node HTTP Request lewat *Import cURL*.

**Tool untuk AI Agent.** Pakai *HTTP Request Tool* dengan parameter dari AI, contoh query `bay_id`:
`{{ $fromAI('bay_id', 'kode bay, contoh LSR-PHT-KRB1', 'string') }}`. Tulis deskripsi tool yang jelas: kapan dipakai, contoh input.

**Knowledge base.** Muat isi folder `kb/` ke Simple Vector Store (memory key `kb_sop_v1`). Simple Vector Store tidak persisten, jadi jalankan ulang workflow ingest setiap pagi sebelum kelas.

**Timezone.** Set timezone instance n8n ke `Asia/Makassar`.

## Uji

```bash
python tests/smoke_test.py
```
Test memakai stub FastAPI sehingga bisa jalan tanpa internet. Di lingkungan dengan FastAPI asli, uji akhir cukup lewat `/docs`.

## Data dictionary singkat

| Tabel | Baris | Catatan |
|---|---|---|
| `gardu_induk` | 8 | kode tiga huruf, media komunikasi FO/RADIO/PLC |
| `bay` | 42 | penghantar, trafo, penyulang, busbar |
| `scada_point` | 181 | TM dan TS; `ada_histori` menandai point dengan telemetering |
| `telemetry_tm` | ±406 rb | per 15 menit, 1 Nov 2026 – 31 Jan 2027, quality GOOD/OLD/INVALID |
| `event_soe` | ±2,9 rb | Jan 2025 – Jan 2027, presisi ms, `ts_received` > `ts_event` |
| `gangguan` | ±100 | kronologi gaya dispatcher, kategori baku, status RCA |
| `beban_sistem` | ±39 rb | per 30 menit, Nov 2024 – Jan 2027, `flag` NORMAL/PEMADAMAN_BERGILIR/PELEPASAN_UFR/DATA_HILANG/ESTIMASI |
| `rencana_operasi` | ±38 rb | ROH harian metode koefisien sejak Des 2024 |
| `kalender` | 822 | libur nasional (perkiraan), cuti bersama, Ramadan, mudik, cuaca harian |

Waktu di CSV disimpan dalam **UTC**; API mengonversi ke WITA.
