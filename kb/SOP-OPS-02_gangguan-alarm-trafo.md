# SOP-OPS-02 Penanganan Gangguan dan Alarm Trafo Daya 150/20 kV

> **FIKTIF, UNTUK PELATIHAN.** Bukan SOP resmi PLN.

## 1. Tujuan
Menjaga umur trafo dan keamanan pasokan saat muncul alarm suhu, alarm pendingin, atau trip proteksi trafo.

## 2. Ruang lingkup
Seluruh trafo daya 150/20 kV di GI simulasi (contoh: PTR-TRF-2 kapasitas 60 MVA, SML-TRF-1 kapasitas 30 MVA).

## 3. Alarm suhu dan pendingin
3.1 **Ambang suhu minyak atas**: alarm OIL TEMP HI pada **85 °C**, trip OIL TEMP TRIP pada **95 °C**.
3.2 Saat OIL TEMP HI muncul:
  3.2.1 Cek pembebanan trafo. Pembebanan dihitung sebagai MW dibagi (MVA x 0,9).
  3.2.2 Bila pembebanan di atas **90%** pada waktu beban puncak (17.00 sampai 22.00 WITA), lakukan mutasi beban penyulang ke trafo lain di GI yang sama bila memungkinkan.
  3.2.3 Pantau tren suhu setiap 15 menit sampai alarm hilang.
3.3 **Bila alarm suhu muncul pada pembebanan atau suhu lingkungan yang tidak tinggi** (misalnya saat hujan atau di luar WBP), curigai masalah sistem pendingin. Cek alarm **FAN ONAF FAIL** dan minta tim pemeliharaan memeriksa kipas dan pompa pendingin.
3.4 Alarm OIL TEMP HI yang hidup-mati berulang dalam hitungan detik adalah **chattering**. Catat sebagai satu kejadian alarm, bukan puluhan kejadian, dan laporkan ke Fasilitas Operasi untuk pemeriksaan kontak atau setting histeresis.

## 4. Trip proteksi trafo
4.1 **OIL TEMP TRIP**: trafo boleh dimasukkan kembali setelah suhu turun di bawah 75 °C dan penyebab panas berlebih teridentifikasi.
4.2 **Differential trip dan/atau Buchholz trip**: indikasi gangguan internal. Trafo **tidak boleh** dimasukkan kembali sebelum pengujian (DGA minyak, tahanan isolasi, rasio belitan) dan persetujuan Manager Operasi Sistem.
4.3 Pulihkan beban melalui manuver ke trafo lain atau trafo mobile sesuai SOP-OPS-03.

## 5. Tindak lanjut wajib
5.1 Trafo yang mengalami alarm OIL TEMP HI lebih dari 10 hari dalam satu bulan masuk daftar evaluasi pembebanan bulanan tim Perencanaan.
5.2 Rekomendasi yang lazim: pembatasan beban saat WBP, mutasi penyulang, perbaikan pendingin, atau usulan penambahan trafo.

## 6. Pelaporan
Trip trafo dilaporkan sesuai IK-LAP-01. Alarm suhu tanpa trip dicatat di laporan harian bagian "perlu perhatian".
