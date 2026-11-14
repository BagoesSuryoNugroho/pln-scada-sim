# Kunci trainer (jangan dibagikan ke peserta)

## Kejadian "live" selama minggu training

API memakai jam nyata. Kejadian berikut akan muncul tepat waktunya di endpoint, jadi bisa dijadikan momen demo.

| Waktu (WITA) | Kejadian | ID | Momen kelas |
|---|---|---|---|
| Jum 20 Nov 15.42 | LSR-PHT-KRB1 trip DIST Z1 fasa R, A/R berhasil, petir | GGN-2026-0049 | Contoh JSON di Swagger dan blueprint |
| Sab 21 Nov 10.14 | Alarm **FAN ONAF FAIL** trafo 2 Paotere (sampai 26 Nov 11.30) | event 502377 | Akar masalah alarm suhu berulang |
| 21–26 Nov | PTR-TRF-2 OIL TEMP HI tiap hari dari siang sampai ±23.00, padahal hujan | – | Pertanyaan uji chatbot no. 8 |
| Min 22 Nov 18.26 | OIL TEMP HI **chattering** 43 event dalam ±90 detik | – | Contoh alarm flood |
| Sen 23 Nov 11.45 | OIL TEMP HI **chattering** 37 event dalam ±90 detik | – | Masuk jendela laporan Hari 2; bahan snippet alarm flood |
| Sen 23 Nov 13.12 | MLN-PYL-02 trip GFR, A/R gagal, pohon, padam 5,8 MW 41 menit | GGN-2026-0050 | Hari 1 sesudah ISHOMA: "barusan ada gangguan" |
| Sen 23 Nov 15.31 | RTU LAE communication fail 69 menit (hujan lebat, link radio) | – | Telemetering LAE berstatus OLD |
| Sen 23 Nov 16.05 | LSR-PHT-KRB1 trip DIST Z1 fasa S, **A/R gagal**, petir, padam 22,6 MW 18 menit | GGN-2026-0051 | Terjadi saat Blok 4b Hari 1: tanyakan ke chatbot RCA |
| Sel 24 Nov 06.30 | Jendela laporan harian (23 Nov 06.30 – 24 Nov 06.30): 2 gangguan, 1 RTU fail, alarm flood | – | Schedule Trigger Hari 2 |
| Sel 24 Nov 14.48 | SMB-PYL-07 trip OCR, A/R gagal, binatang (ular), padam 3,9 MW 27 menit | GGN-2026-0052 | Muncul "live" saat Blok 5a Hari 2 |

Gangguan acak lain disembunyikan selama 19–25 Nov supaya demo bisa ditebak. Setelah 25 Nov kejadian acak musim hujan berlanjut sampai 31 Jan 2027.

## Pola yang ditanam (untuk RCA, chatbot, capstone)

1. **Petir di LSR-PHT-KRB1.** 25 gangguan, 23 di antaranya petir, hampir semua sore hari (14.00–18.00) di musim hujan, DIST Z1, sebagian besar A/R berhasil. SOP-OPS-01 §4.4 mewajibkan analisis tren bila trip tiga kali dalam 30 hari.
2. **Layang-layang di SMB-PYL-07.** 17 kejadian, hanya Juli–Oktober, siang hari, OCR/GFR. Pola musim kemarau.
3. **Pohon di MLN-PYL-02 dan BTM-PYL-02.** Saat hujan angin, durasi padam panjang.
4. **Trafo 2 Paotere makin panas.** Episode alarm OIL TEMP HI (chattering dihitung satu): 3 kali di 2025, 131 kali di 2026. November 2026 ada 21 hari beralarm, sehingga memicu SOP-OPS-02 §5.1 (lebih dari 10 hari per bulan). Trip 9 Des 2025 (GGN-2025-0041, 38 MW, 95 menit, kipas ONAF rusak). Kasus kipas lagi pada 21–26 Nov 2026. Bahan capstone Perencanaan (evaluasi pembebanan).
5. **RTU radio rentan hujan.** RTU comm fail paling banyak di LAE, SML, MLN (radio), lalu BTM (PLC). GI dengan FO hampir tidak pernah. Availability bulan basah bisa di bawah target 99,5%. Bahan capstone Fasop.
6. **Proteksi salah kerja.** GGN-2026-0040 (KRB-PYL-04, 14 Okt 2026), GFR trip tanpa arus gangguan, status RCA **OPEN**. Chatbot harus bilang bukti belum cukup. Pembanding FINAL: GGN-2025-0021 (cold load pickup).
7. **Gangguan besar lainnya.** GGN-2026-0025 SML-TRF-1 differential + Buchholz, ENS 79,2 MWh (terbesar). GGN-2026-0033/34/35 UFR tahap 1 pada 14 Sep 2026. GGN-2025-0027 crane proyek.
8. **Frekuensi vs dampak.** Sampai 15 Nov 2026: penyebab terbanyak PETIR (27 kejadian), tetapi ENS terbesar dari PERALATAN (149 MWh dari 3 kejadian). Pertanyaan bagus untuk diskusi prioritas.

## Pola di beban sistem (Hari 3)

- Puncak harian sekitar 1.600–1.800 MW, jam puncak 18.00–19.30. Maret 2026 maksimum 1.718 MW.
- Idulfitri 2026 (20 Mar): puncak sekitar 1.305 MW, kira-kira 24% di bawah hari kerja biasa.
- Pemadaman bergilir 31 Agt dan 1 Sep 2026 (flag `PEMADAMAN_BERGILIR`), UFR 14 Sep 2026 (`PELEPASAN_UFR`), beberapa jendela `DATA_HILANG`/`ESTIMASI`.
- Akurasi ROH (metode koefisien) secara keseluruhan sekitar 1,8% MAPE; hari libur sekitar 3,6%.
- Hasil backtest yang menarik untuk diskusi:
  - Minggu Natal 2025 (`start=2025-12-29`): pada 25 Des, koefisien meleset 1,6%, Holt-Winters dan seasonal naive sekitar 10,6%.
  - Minggu Lebaran 2026 (`start=2026-03-27`): koefisien 5,2% (di atas target 4%), dua metode lain 11–12%.
  - Pesan: model generik tidak paham kalender; metode yang dipakai PLN sudah menangani hari libur.

## Kunci uji chatbot

Lihat `n8n_datatables/uji_chatbot.csv`. Pertanyaan 10–12 harus ditolak dengan sopan. Pertanyaan 7–9 hanya bisa dijawab lengkap bila agent memanggil tool API, bukan hanya vector store.

## Checklist dry-run dengan `X-Sim-Now` (key trainer)

- `2026-11-23T16:30`: chatbot menemukan GGN-2026-0051 sebagai gangguan terbaru dan statusnya OPEN.
- `2026-11-24T06:30`: `GET /api/v1/events` berisi 56 event; laporan harian memuat 2 gangguan + RTU LAE + alarm flood.
- `2026-11-25T09:30`: `POST /api/v1/forecast` `{"method":"all","horizon_slots":336}` dan backtest minggu 18–24 Nov.
