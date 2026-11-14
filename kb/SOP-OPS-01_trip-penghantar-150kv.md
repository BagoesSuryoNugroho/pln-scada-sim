# SOP-OPS-01 Penanganan Trip PMT Penghantar 150 kV

> **FIKTIF, UNTUK PELATIHAN.** Bukan SOP resmi PLN. Dibuat untuk simulasi RevoU x PLN Makassar.
> Revisi 2 (simulasi), berlaku untuk unit pengatur beban sistem simulasi Sulbagsel.

## 1. Tujuan
Memberi langkah baku bagi dispatcher saat PMT 150 kV pada bay penghantar trip, agar pemulihan cepat, aman, dan terdokumentasi.

## 2. Ruang lingkup
Berlaku untuk seluruh bay penghantar 150 kV di GI simulasi (contoh: LSR-PHT-KRB1, LSR-PHT-KRB2, PTR-PHT-BTM1). Tidak berlaku untuk trafo (lihat SOP-OPS-02) dan penyulang 20 kV (wewenang unit distribusi, lihat SOP-OPS-03 bagian 5).

## 3. Definisi
3.1 **Trip**: PMT membuka otomatis karena perintah relay proteksi.
3.2 **A/R (auto reclose)**: PMT menutup kembali otomatis sekitar 1 detik setelah trip. **A/R berhasil** berarti gangguan bersifat temporer. **A/R gagal (lockout)** berarti relay kembali bekerja setelah reclose.
3.3 **Relay distance Z1**: zona 1, gangguan di dalam sekitar 80% panjang saluran; trip seketika. **Z2**: zona 2, trip dengan tunda waktu.
3.4 **Estimasi lokasi**: jarak gangguan dari GI menurut rekaman relay, dalam km.

## 4. Langkah penanganan
### 4.1 Identifikasi
4.1.1 Baca urutan event SOE: RELAY_PICKUP, RELAY_TRIP, CB_OPEN, lalu AR_SUCCESS atau AR_FAIL.
4.1.2 Catat jam kejadian sampai milidetik, zona relay, fasa yang terganggu, dan estimasi lokasi.
4.1.3 Cek kondisi cuaca di sepanjang jalur. Pada musim hujan (November sampai Maret), gangguan sore hari disertai petir adalah penyebab yang paling sering.

### 4.2 Bila A/R berhasil
4.2.1 Tidak ada manuver yang diperlukan. Pastikan beban dan tegangan kembali normal.
4.2.2 Informasikan ke UPT untuk patroli jalur pada jam kerja berikutnya, fokus pada tower di sekitar estimasi lokasi.
4.2.3 Buat laporan awal sesuai IK-LAP-01 bagian 3.

### 4.3 Bila A/R gagal (lockout)
4.3.1 Pastikan apakah ada beban padam. Bila ada, lakukan manuver pemulihan sesuai SOP-OPS-03.
4.3.2 Dispatcher boleh melakukan **satu kali** percobaan masuk secara remote paling cepat 3 menit setelah lockout, bila tidak ada laporan konduktor putus, kebakaran, atau pekerjaan di jalur.
4.3.3 Bila percobaan masuk berhasil, catat jam normal dan durasi padam.
4.3.4 Bila percobaan masuk trip lagi, **jangan mencoba ulang**. Nyatakan gangguan permanen, minta UPT patroli darurat, dan eskalasi ke Supervisor Operasi.

### 4.4 Gangguan berulang
4.4.1 Bila bay yang sama trip tiga kali atau lebih dalam 30 hari, Supervisor Operasi wajib meminta analisis tren gangguan dan rekomendasi perbaikan (misalnya pemeriksaan arrester, grounding tower, atau isolator).

## 5. Koordinasi
5.1 UPT untuk patroli jalur dan inspeksi tower.
5.2 Tim proteksi untuk analisis rekaman gangguan bila penyebab belum diketahui.
5.3 Unit distribusi bila ada penyulang terdampak.

## 6. Pelaporan
Laporan awal paling lambat 60 menit dan laporan lengkap paling lambat 1x24 jam, mengikuti IK-LAP-01.

## 7. Catatan khusus petir
7.1 Gangguan akibat petir umumnya temporer (A/R berhasil) dan muncul di Z1 satu fasa.
7.2 Temuan patroli yang lazim: flashover isolator dan bertambahnya counter arrester.
7.3 Pola petir yang berulang di jalur yang sama adalah indikasi kebutuhan evaluasi perlindungan petir jalur tersebut.

## 8. Larangan
Asisten AI atau sistem otomatis **tidak boleh** memberi perintah buka/tutup PMT. Semua perintah remote hanya oleh dispatcher berwenang.
