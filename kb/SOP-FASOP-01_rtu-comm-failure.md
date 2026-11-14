# SOP-FASOP-01 Penanganan RTU Communication Failure dan Kualitas Data SCADA

> **FIKTIF, UNTUK PELATIHAN.** Bukan SOP resmi PLN.

## 1. Tujuan
Memastikan data SCADA yang dipakai dispatcher dapat dipercaya, dan gangguan komunikasi RTU ditangani dalam waktu yang terukur.

## 2. Definisi
2.1 **RTU_COMM_FAIL**: master station kehilangan komunikasi dengan RTU satu GI. Diakhiri oleh RTU_COMM_OK.
2.2 **Quality flag** pada telemetering:
  - GOOD: nilai valid dan terbaru.
  - OLD: nilai tidak diperbarui (beku), biasanya karena komunikasi putus.
  - INVALID: nilai tidak valid dari sumbernya.
  - SUSPECT: nilai di luar kewajaran, perlu dicek.
  - MANUAL: nilai dimasukkan manual oleh operator.
2.3 **Media komunikasi**: FO (fiber optic), RADIO, PLC (power line carrier). GI dengan media radio lebih rentan gangguan saat hujan lebat (rain fade).

## 3. Dampak ke operasi
3.1 Selama RTU_COMM_FAIL, dispatcher harus menganggap seluruh data GI terkait **tidak real-time**. Konfirmasi kondisi lapangan melalui telepon ke operator GI.
3.2 Laporan dan analisis otomatis wajib menandai atau mengecualikan nilai dengan quality selain GOOD.

## 4. Langkah penanganan
4.1 Cek apakah gangguan terjadi di satu GI atau beberapa GI sekaligus (indikasi masalah di sisi master station atau jaringan inti).
4.2 Bila komunikasi belum pulih dalam **10 menit**, buat tiket ke tim Fasilitas Operasi dengan informasi: GI, media komunikasi, jam mulai, cuaca.
4.3 Bila belum pulih dalam **60 menit**, eskalasi ke Supervisor Fasilitas Operasi dan informasikan ke dispatcher.
4.4 Setelah pulih, verifikasi bahwa nilai telemetering kembali berubah (tidak beku) dan quality kembali GOOD.

## 5. Laporan availability bulanan
5.1 Availability RTU = 1 - (total durasi RTU_COMM_FAIL / total waktu dalam bulan).
5.2 Target availability per RTU: **99,5%** atau lebih.
5.3 RTU di bawah target dua bulan berturut-turut masuk usulan perbaikan media komunikasi (misalnya migrasi radio ke FO).

## 6. Point stale tanpa RTU_COMM_FAIL
Point yang berstatus OLD atau tidak berubah lebih dari 30 menit sementara RTU normal menandakan masalah di transduser, IED, atau mapping database. Buat tiket dengan menyebut point_id.
