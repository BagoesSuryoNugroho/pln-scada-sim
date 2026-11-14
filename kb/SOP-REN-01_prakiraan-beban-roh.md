# SOP-REN-01 Prakiraan Beban dan Penyusunan ROH dengan Metode Koefisien

> **FIKTIF, UNTUK PELATIHAN.** Bukan SOP resmi PLN. Rumus disederhanakan dan sama dengan yang dipakai API simulasi.

## 1. Tujuan
Menyusun prakiraan beban sistem per 30 menit untuk Rencana Operasi Harian (ROH) dan Mingguan (ROM).

## 2. Jadwal
2.1 **ROH** dirilis setiap hari pukul **10.00 WITA** untuk hari berikutnya (H-1).
2.2 **ROM** dirilis setiap Kamis pukul 14.00 WITA untuk minggu berikutnya (Senin sampai Minggu).

## 3. Data masukan
3.1 Beban sistem realisasi per 30 menit minimal 8 minggu terakhir.
3.2 Kalender: hari kerja, Sabtu, Minggu, libur nasional, cuti bersama, Ramadan, periode mudik.
3.3 **Slot berflag harus dikeluarkan atau diganti** sebelum dipakai sebagai data latih: PEMADAMAN_BERGILIR, PELEPASAN_UFR, DATA_HILANG, ESTIMASI. Pada slot tersebut beban tercatat tidak mencerminkan kebutuhan.

## 4. Metode koefisien
4.1 Prakiraan(slot) = beban puncak mingguan x koefisien harian x koefisien slot.
4.2 **Beban puncak mingguan**: rata-rata puncak dua minggu terakhir (hari normal), disesuaikan dengan tren empat minggu.
4.3 **Koefisien harian**: rasio puncak hari terhadap puncak mingguan, dirata-rata dari empat minggu terakhir untuk jenis hari yang sama.
4.4 **Koefisien slot**: rasio beban slot terhadap puncak harinya, dirata-rata dari hari sejenis.
4.5 Untuk hari libur nasional, cuti bersama, dan Idulfitri, koefisien diambil dari kejadian serupa di histori, bukan dari hari biasa.

## 5. Evaluasi
5.1 Akurasi diukur dengan MAPE (mean absolute percentage error) total dan **MAPE WBP** (17.00 sampai 22.00 WITA).
5.2 Target: MAPE WBP **2,5% atau kurang** pada hari kerja; **4% atau kurang** pada hari libur.
5.3 Deviasi di atas target dijelaskan dalam catatan evaluasi mingguan: penyebab yang lazim adalah cuaca ekstrem, hari libur, gangguan besar, atau pelepasan beban.

## 6. Periode khusus
6.1 **Ramadan**: muncul tonjolan beban saat sahur (sekitar 02.30 sampai 04.30) dan pergeseran pola malam.
6.2 **Idulfitri dan periode mudik**: beban turun signifikan; gunakan koefisien Idulfitri tahun sebelumnya.
6.3 **Natal dan Tahun Baru (Nataru)**: beban siang turun pada 24 Desember sampai 1 Januari; perhatikan kenaikan beban malam 31 Desember.

## 7. Peran AI
7.1 Angka prakiraan dihasilkan oleh model statistik, bukan oleh model bahasa.
7.2 Asisten AI boleh menulis narasi catatan perencanaan, membandingkan metode, dan menandai risiko, dengan **hanya mengutip angka dari keluaran model**.
7.3 Catatan yang dihasilkan AI ditinjau oleh engineer Perencanaan sebelum ROM final.
