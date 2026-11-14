# IK-LAP-01 Instruksi Kerja Format dan Tenggat Laporan Gangguan

> **FIKTIF, UNTUK PELATIHAN.** Bukan instruksi kerja resmi PLN.

## 1. Tujuan
Menyeragamkan isi dan waktu penyampaian laporan gangguan.

## 2. Jenis laporan
2.1 **Laporan awal (flash report)**: singkat, segera setelah kejadian.
2.2 **Laporan lengkap**: setelah pemulihan dan data terkumpul.
2.3 **Laporan kejadian harian**: rekap seluruh kejadian 24 jam sebelumnya, dikirim setiap hari pukul **06.30 WITA**.

## 3. Tenggat dan penyetuju
| Laporan | Tenggat | Disetujui oleh |
|---|---|---|
| Laporan awal | paling lambat 60 menit setelah kejadian | Supervisor Operasi (shift) |
| Laporan lengkap | paling lambat 1x24 jam | Manager Operasi Sistem |
| Laporan harian | setiap hari 06.30 WITA | Supervisor Operasi (shift malam) |

## 4. Isi wajib laporan lengkap
4.1 Nomor gangguan (format GGN-TAHUN-NOMOR).
4.2 GI dan bay terganggu.
4.3 Jam mulai dan jam normal (WITA).
4.4 Relay yang bekerja dan status A/R.
4.5 Beban padam (MW), durasi (menit), dan ENS (MWh). **ENS = beban padam x durasi dalam jam.**
4.6 Kronologi berdasarkan urutan event SOE.
4.7 Kategori penyebab (bagian 5) dan dasar penentuannya.
4.8 Tindakan yang sudah dan akan dilakukan.
4.9 Status RCA.

## 5. Kategori penyebab baku
PETIR, POHON, LAYANG2, BINATANG, PERALATAN, PROTEKSI_MALKERJA, EKSTERNAL, BELUM_DIKETAHUI.
Bila bukti belum cukup, gunakan BELUM_DIKETAHUI. Jangan menebak kategori.

## 6. Status RCA
6.1 **OPEN**: analisis belum dimulai atau bukti belum cukup.
6.2 **DRAFT**: hipotesis sudah ada, menunggu verifikasi lapangan atau pengujian.
6.3 **FINAL**: penyebab terverifikasi dan tindak lanjut ditetapkan.

## 7. Isi laporan kejadian harian
7.1 Ringkasan eksekutif paling banyak tiga kalimat.
7.2 Tabel kejadian: bay, jam, relay, beban padam, durasi, kategori usulan.
7.3 Bagian "perlu perhatian": alarm berulang, RTU comm fail, gangguan berulang di bay yang sama.
7.4 Alarm chattering dihitung sebagai satu kejadian dengan keterangan jumlah pengulangan.

## 8. Penggunaan AI
Draf laporan boleh disusun oleh asisten AI. Angka dihitung oleh sistem, bukan oleh AI. Draf wajib disetujui penyetuju sesuai bagian 3 sebelum dikirim.
