# VERIFIKASI.md — Status dan Sisa Tugas Verifikasi Katalog IKD

Diperbarui 20 Agustus 2026.

## Yang sudah dikerjakan

**Keterisian SISKAPERBAPO Jawa Timur — terukur, bukan lagi tebakan.**
Panel 7 hari (22–28 Maret 2023) satu komoditas ditarik dari
<https://siskaperbapo.jatimprov.go.id/harga-komoditas>: 38 kabupaten/kota,
120 pasar, 840 sel.

| Ukuran | Nilai |
|---|---|
| Keterisian tingkat pasar | 0,961 |
| Keterisian tingkat kabupaten | **0,970** |
| Enam hari pertama, tingkat kabupaten | 1,000 |
| Hari terakhir, tingkat kabupaten | 0,789 |
| Kabupaten tanpa data sama sekali | tidak ada |

Estimasi awal 0,55 salah, dan salahnya instruktif. Angka itu saya ambil dari
papan progres di beranda situs yang menampilkan "12 dari 38 kabupaten". Papan
itu mengukur entri **hari berjalan** yang belum selesai, bukan kelengkapan
arsip. Arsipnya nyaris penuh. Pelajarannya: jangan pernah menyimpulkan
kelengkapan data dari indikator progres harian.

Ekor yang belum lengkap tetap punya konsekuensi operasional. Model peramalan
harian harus mundur 1–2 hari dari tanggal terkini, kalau tidak fitur hari
terakhir masuk dalam keadaan bolong.

**Cakupan PIHPS Bank Indonesia — terverifikasi.** 82 kabupaten/kota sampel
inflasi IHK, 2 pasar tradisional per kabupaten/kota, dan daftar komoditasnya
tidak memuat jagung maupun kentang.

**Cakupan SiHati Jawa Tengah — terverifikasi sebagian.** Menu Tabel Harga
Berdasarkan Kabupaten memuat 35 kabupaten/kota (Cilacap sampai Kota Tegal).
Angka keterisiannya belum bisa diambil: SiHati aplikasi JavaScript satu
halaman, isinya tidak muncul tanpa browser.

## Dampak ke keputusan

Jawa Timur kembali ke peringkat 1 dengan IKD 0,813 melawan Jawa Tengah 0,756,
dan bertahan di 100% dari 4.000 kombinasi bobot.

### Koreksi klaim sebelumnya

Sempat ditulis bahwa Jawa Timur "terkunci" karena satu-satunya parameter rapuh
sudah aman. Klaim itu terlalu berani: yang diuji waktu itu hanya satu parameter
dari dua puluh satu yang masih estimasi. Setelah `pindai_kerapuhan()` menyapu
semuanya, dua parameter ternyata masih sanggup memindahkan peringkat 1.

| Parameter | Ambang pembalik | Wajar? |
|---|---|---|
| Keterisian SiHati Jawa Tengah | 1,00 | Tidak. Menuntut kesempurnaan, melebihi Jawa Timur yang terukur 0,97. |
| Jumlah kabupaten berproduksi Jawa Timur | ×0,50 | Tidak. Menuntut estimasi saya meleset dua kali lipat. |

Sembilan belas parameter lain tidak berpengaruh sama sekali. Kesimpulannya:
**Jawa Timur tetap pilihan pilot, dan pembalikannya hanya mungkin di keadaan
yang tidak masuk akal** — tapi itu kalimat yang berbeda dari "terkunci", dan
perbedaannya penting kalau ada juri yang bertanya.

---

## Pembaruan 22 Agustus 2026 — verifikasi sumber Siskaperbapo

Halaman `harga-komoditas` disimpan dan dibaca langsung. Tiga temuan.

### Kentang ternyata dipantau

Dugaan sebelumnya salah. Siskaperbapo memantau 67 komoditas, dan keenam
komoditas PradanaLog ada di dalamnya:

| Komoditas | id | Nama di situs |
|---|---|---|
| beras | 4 | Beras Medium / kg |
| jagung | 25 | Jagung Pipilan Kering / kg |
| bawang | 39 | Bawang Merah / kg |
| cabai_besar | 38 | Cabe Merah Besar / kg |
| cabai_rawit | 50 | Cabe Rawit Merah / kg |
| **kentang** | **45** | **Kentang / kg** |

Akibatnya, modul prediksi harga tingkat kabupaten berlaku untuk **enam**
komoditas di Jawa Timur, bukan lima. Keterbatasan "kentang hanya bisa di level
provinsi" tidak lagi berlaku untuk provinsi pilot, meski tetap berlaku di
sembilan provinsi lain yang hanya bergantung PIHPS.

### Keterisian jauh lebih tinggi daripada dugaan pertama

Panel 16–22 Agustus 2026, komoditas Beras Premium, 38 kabupaten/kota, 121 pasar:

| Ukuran | Nilai |
|---|---|
| Tingkat pasar | 0,988 |
| **Tingkat kabupaten** | **0,996** |
| Enam hari pertama | 1,000 |
| Hari berjalan | 0,974 |

Estimasi awal 0,55 meleset jauh. Angka itu diambil dari papan progres beranda
yang mengukur entri hari berjalan, bukan kelengkapan arsip.

### Formulirnya POST, bukan query string

`<form method="post">` dengan `csrf_token` dan satu medan `tanggal_akhir`;
tabel selalu menampilkan tujuh hari yang berakhir pada tanggal itu. URL tidak
bisa dirangkai sendiri. `tarik_siskaperbapo()` sudah ditulis ulang: ambil
halaman untuk mendapat token, lalu POST dalam sesi yang sama. Penguraiannya
diuji langsung pada halaman asli lewat uji 21–23.

### Dampak ke peringkat

| Provinsi | IKD sebelum | IKD sesudah |
|---|---|---|
| Jawa Timur | 0,813 | **0,868** |
| Jawa Tengah | 0,756 | 0,756 |

Yang lebih penting: `pindai_kerapuhan()` kini melaporkan **nol** parameter yang
sanggup memindahkan peringkat 1, turun dari dua. Tidak ada lagi nilai estimasi
di rentang mana pun yang bisa membalikkan pilihan Jawa Timur.


---

## Sisa tugas

### Prioritas 1 — perluas pengukuran Siskaperbapo

Angka 0,996 berasal dari satu komoditas dan satu minggu. Statusnya `sebagian`.
Perluas ke satu tahun dan keenam komoditas. Penarik sudah siap pakai:

```bash
python -c "from hitung_keterisian import tarik_rentang; \
           tarik_rentang('2025-01-01','2025-12-31','beras').to_csv('jatim_beras_2025.csv',index=False)"

python hitung_keterisian.py jatim_beras_2025.csv "Jawa Timur" SISKAPERBAPO
```

Ulangi untuk `jagung`, `bawang`, `cabai_besar`, `cabai_rawit`, `kentang`, lalu
gabungkan sebelum menghitung. Tiap panggilan mengambil satu jendela tujuh hari,
jadi setahun berarti sekitar 53 permintaan per komoditas — beri jeda dan
jalankan sekali saja, simpan hasilnya ke disk.

### Prioritas 2 — jumlah kabupaten berproduksi

Enam puluh baris `katalog_produksi.csv` masih estimasi. Sumber per komoditas
ada di kolom `url` tiap baris.

| Komoditas | Tabel BPS provinsi |
|---|---|
| Beras | Luas Panen dan Produksi Padi menurut Kabupaten/Kota (KSA) |
| Jagung | Produksi Jagung menurut Kabupaten/Kota |
| Bawang merah | Produksi Tanaman Sayuran Bawang Daun dan Bawang Merah menurut Kabupaten/Kota |
| Cabai besar & rawit | Produksi Tanaman Sayuran Cabai Besar, Cabai Rawit, Cabai Keriting menurut Kabupaten/Kota |
| Kentang | Produksi Tanaman Sayuran dan Buah-Buahan Semusim menurut Kabupaten/Kota |

Karena pilot sudah terkunci di Jawa Timur, cukup kerjakan baris Jawa Timur
dulu (6 baris) supaya sistem drill-down bisa jalan. Sembilan provinsi lain
bisa menyusul untuk kelengkapan tabel perbandingan.

Kolom `tahun_awal` dan `tahun_akhir` juga perlu dicek per provinsi. Asumsi
sekarang seragam, dan justru karena seragam itulah dimensi Kedalaman Deret
punya simpangan baku 0,021 — praktis tidak membedakan apa pun.

### Prioritas 3 — pembagian 82 kabupaten sampel PIHPS

Buka <https://www.bi.go.id/hargapangan/TabelHarga/PasarTradisionalKomoditas>,
pilih provinsi, centang "Tampilkan Kab./Kota", hitung entri yang muncul.
Sepuluh provinsi sekitar setengah jam. Ini hanya memperbaiki tabel
perbandingan, tidak mengubah pilot.

### Prioritas 4 — konektivitas darat

`katalog_wilayah.csv`, kolom `fraksi_terhubung_darat`: bagian kabupaten/kota
yang terhubung jaringan jalan tanpa penyeberangan laut. Untuk Jawa Timur nilai
0,97 mencerminkan Kepulauan Kangean dan Masalembu di Sumenep. Pastikan cara
hitungnya sejalan dengan model biaya yang akhirnya Anda pakai di FLP.

### Prioritas 5 — SiHati Jawa Tengah

Sudah tidak menentukan pilot, jadi boleh ditunda. Kalau tetap ingin melengkapi
katalog, buka DevTools > Network di hargajateng.org, cari permintaan XHR yang
mengembalikan JSON, lalu pakai endpoint itu langsung.

---

## Setelah tiap pembaruan

```bash
python uji_ikd.py        # 14 uji; harus lulus semua sebelum angka dipakai
python data_readiness.py
```

`uji_ikd.py` memuat uji asal-usul: angka berstatus bukan-estimasi dihitung ulang
dari data mentahnya dan dibandingkan dengan katalog. Uji ini lahir dari kejadian
nyata — sisa data percobaan sempat menimpa keterisian Jawa Timur jadi 0,123
sementara kolom catatannya tetap menyebut 0,97, indeks tetap jalan, dan angkanya
hampir dilaporkan.

Regenerasi katalog kini aman: `python bangun_katalog.py` mempertahankan baris
berstatus `terverifikasi` dan `sebagian`, hanya menimpa yang masih `estimasi`.
Gunakan `--paksa` hanya kalau memang ingin membuang seluruh hasil verifikasi.

Periksa tiga hal: peringkat 1 dan nilai `P_peringkat1`-nya; simpangan baku tiap
dimensi (di bawah 0,03 berarti dimensi itu tidak membedakan apa pun); dan tabel
titik balik. Laporkan angka yang keluar, bukan angka yang Anda harapkan.

---

## Batasan yang tidak bisa ditutup kode

Beberapa hal berikut sudah dipertimbangkan dan sengaja dibiarkan. Sebutkan
sendiri di paper sebelum juri yang menemukannya.

**Bobot enam dimensi ditetapkan penulis, bukan diturunkan dari data.** Uji
Dirichlet menunjukkan peringkat bertahan di 4.000 kombinasi, dan itu memang
jawaban terhadap keberatan "bobotnya suka-suka". Tapi struktur dimensinya
sendiri — memilih enam sumbu ini dan bukan yang lain — tetap keputusan penulis
yang tidak diuji apa pun.

**Kedalaman deret nyaris tidak membedakan** (simpangan baku 0,021) karena
rentang tahun diasumsikan seragam per komoditas di semua provinsi. Selama
asumsi itu belum diganti angka nyata, dimensi ini hampir tidak bekerja.

**Sepuluh provinsi, bukan tiga puluh delapan.** Daftar pendek dipilih penulis.
Provinsi di luar daftar tidak pernah punya kesempatan menang, dan tidak ada
uji yang bisa menutupi itu — hanya penambahan baris katalog.

**Keterisian 0,970 berasal dari satu komoditas, satu minggu, tahun 2023.**
Statusnya `sebagian`, bukan `terverifikasi`. Angkanya bisa berbeda untuk
komoditas hortikultura yang harganya lebih jarang dilaporkan.

**Fraksi terhubung darat masih penilaian kasar,** bukan hasil hitung jaringan
jalan. Dimensi ini ikut menentukan skor tapi belum berbasis data.
