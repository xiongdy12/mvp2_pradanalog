# PANDUAN.md — Langkah Demi Langkah

Dua jalur berjalan bersamaan. Jalur A memakan waktu Anda sekitar 40 menit lalu
selesai. Jalur B berjalan di latar sambil Anda mengerjakan hal lain.

Kuncinya ada di kontrak data: `kab_profil.csv` dan `kab_harga.csv` sudah punya
bentuk final. Jalur B mengisi bentuk itu dengan angka sungguhan. Tidak ada satu
baris kode pun yang perlu berubah saat data contoh ditukar.

---

# JALUR A — Pasang sistem (40 menit)

## Langkah 1 — Kumpulkan berkas (2 menit)

Salin semua berkas ini ke folder yang sama dengan `pradanalog_map.py`:

```
auth.py              data_kabupaten.py    tab_kabupaten.py
buat_kredensial.py   tab_kesiapan.py      data_readiness.py
bangun_katalog.py    hitung_keterisian.py
uji_ikd.py           uji_sistem.py
katalog_produksi.csv katalog_harga.csv    katalog_wilayah.csv
```

Pastikan pustakanya ada:

```bash
pip install -U streamlit pydeck pandas altair
```

## Langkah 2 — Bangun data contoh (1 menit)

```bash
python data_kabupaten.py
```

Menghasilkan `kab_profil.csv` (38 baris) dan `kab_harga.csv` (41.040 baris),
seluruhnya bertanda `contoh`. Angkanya karangan, bentuknya final.

## Langkah 3 — Buat akun (2 menit)

Untuk latihan dan demonstrasi panggung:

```bash
python buat_kredensial.py contoh
```

Tiga akun tercetak ke layar: `pusat`, `jatim`, `malang`. Untuk akun sungguhan:

```bash
python buat_kredensial.py tambah      # kata sandi diketik tersembunyi
python buat_kredensial.py daftar
```

**Segera** tambahkan ke `.gitignore`:

```
kredensial.json
```

Kata sandi tidak pernah masuk berkas — yang tersimpan hanya hash PBKDF2 beserta
garamnya. Tapi berkas itu tetap tidak boleh masuk repositori publik.

## Langkah 4 — Jalankan uji (2 menit)

```bash
python uji_ikd.py       # 20 uji pipeline indeks kesiapan data
python uji_sistem.py    # 19 uji login dan drill-down
```

Kalau ada yang gagal, berhenti dan perbaiki dulu. Jangan lanjut memasang.

## Langkah 5 — Sambungkan ke pradanalog_map.py (5 menit)

Tiga suntingan.

**a. Bagian impor**, dekat baris 25:

```python
from tab_kesiapan import render_tab_kesiapan
from tab_kabupaten import render_tab_kabupaten
```

**b. Baris 1000**, ganti definisi tab:

```python
tab_peta, tab_frontier, tab_harga, tab_dampak, tab_siap, tab_kab = st.tabs(
    ["🗺️ Peta Distribusi", "📈 Frontier Kebijakan", "🔮 Prediksi Harga",
     "🎯 Dampak & Roadmap", "🧭 Kesiapan Data", "🏛️ Tinjauan Kabupaten"])
```

**c. Paling bawah berkas**, setelah blok `with tab_dampak:`:

```python
with tab_siap:
    render_tab_kesiapan(df_to_html)

with tab_kab:
    render_tab_kabupaten(df_to_html)
```

## Langkah 6 — Jalankan dan coba ketiga peran (10 menit)

```bash
streamlit run pradanalog_map.py
```

Buka tab **Tinjauan Kabupaten**, lalu uji berurutan:

| Masuk sebagai | Yang harus Anda lihat |
|---|---|
| `pusat` / `Demo#Pusat2026` | 38 wilayah, peta penuh |
| `jatim` / `Demo#Jatim2026` | 38 wilayah Jawa Timur |
| `malang` / `Demo#Malang2026` | hanya Kabupaten Malang, tabel disparitas hilang |

Yang wajib Anda periksa sendiri, karena inilah yang akan ditanya juri:

1. Masuk sebagai `malang`, klik unduh CSV. **Berkasnya harus berisi satu baris.**
   Kalau berisi 38, pembatasan lingkupnya bocor.
2. Tekan **Keluar** di sidebar, lalu segarkan halaman. Harus kembali ke borang
   masuk, bukan langsung menampilkan data.
3. Ketik kata sandi salah. Pesannya tidak boleh menyebutkan apakah nama
   penggunanya benar — itu disengaja, supaya nama akun tidak bisa ditebak.

## Langkah 7 — Sadari batas yang ada (5 menit)

Baca bagian batasan di `auth.py`. Ringkasnya, sebutkan sendiri saat presentasi:

- Pembatasan terjadi di lapisan tampilan. Berkas CSV di server tetap utuh, jadi
  siapa pun yang bisa membaca berkasnya melewati pembatasan ini. Produksi butuh
  basis data dengan penyaringan di sisi kueri.
- Belum ada pembatasan percobaan masuk, rotasi sesi, maupun jejak audit.
- PBKDF2 stdlib dipakai agar tidak menambah dependensi; produksi sebaiknya
  bcrypt atau argon2.

Juri yang paham keamanan akan menanyakan ini. Menyebutnya lebih dulu mengubah
kelemahan jadi tanda Anda tahu apa yang Anda bangun.

## Langkah 8 — Untuk penyebaran ke Streamlit Community Cloud

Jangan unggah `kredensial.json`. Salin isinya ke **Settings > Secrets** dengan
kunci `pradanalog_pengguna`:

```toml
pradanalog_pengguna = '''
{ "pusat": { "garam": "...", "hash": "...", "iterasi": 240000, "peran": "pusat" } }
'''
```

`auth.py` membaca `st.secrets` lebih dulu, berkas lokal hanya sebagai cadangan.

---

# JALUR B — Verifikasi data (paralel)

## B1 — Temukan pola URL Siskaperbapo (10 menit, kerjakan hari ini)

Ini yang membuka semua langkah berikutnya.

1. Buka <https://siskaperbapo.jatimprov.go.id/harga-komoditas>
2. Tekan F12, pilih tab **Network**
3. Ganti pilihan komoditas dan rentang tanggal di halaman
4. Perhatikan permintaan yang muncul; salin URL lengkapnya
5. Tempel ke `POLA_URL` di dalam `tarik_siskaperbapo()` pada
   `hitung_keterisian.py`

Kalau ternyata datanya datang lewat permintaan JSON, lebih baik lagi — pakai
endpoint itu langsung, lebih stabil daripada mengurai HTML.

Catat sekalian: **apakah kentang termasuk komoditas yang dipantau?** Katalog
sekarang mengasumsikan tidak. Kalau ternyata ya, modul prediksi harga Anda bisa
mencakup keenam komoditas, bukan lima.

## B2 — Tarik dan hitung (jalan di latar)

```bash
python -c "from hitung_keterisian import tarik_siskaperbapo as t; \
           t('2025-01-01','2025-12-31',komoditas_id=1).to_csv('jatim_2025.csv',index=False)"

python hitung_keterisian.py jatim_2025.csv "Jawa Timur" SISKAPERBAPO
python uji_ikd.py && python data_readiness.py
```

Perintah kedua menulis hasilnya langsung ke `katalog_harga.csv` dan mengubah
statusnya jadi `terverifikasi`.

## B3 — Enam baris produksi Jawa Timur (20 menit)

Buka tabel BPS Jawa Timur, hitung kabupaten/kota dengan produksi bukan nol,
lalu sunting `katalog_produksi.csv` — hanya enam baris Jawa Timur.

| Komoditas | Tabel |
|---|---|
| Beras | Luas Panen dan Produksi Padi menurut Kabupaten/Kota (KSA) |
| Jagung | Produksi Jagung menurut Kabupaten/Kota |
| Bawang merah | Produksi Tanaman Sayuran Bawang Daun dan Bawang Merah menurut Kabupaten/Kota |
| Cabai besar & rawit | Produksi Tanaman Sayuran Cabai Besar, Cabai Rawit, Cabai Keriting menurut Kabupaten/Kota |
| Kentang | Produksi Tanaman Sayuran dan Buah-Buahan Semusim menurut Kabupaten/Kota |

Isi juga `tahun_awal` dan `tahun_akhir` sesuai yang benar-benar tersedia, lalu
ubah `status_verifikasi` jadi `terverifikasi`.

Menjalankan `python bangun_katalog.py` setelah ini **tidak akan** menghapus
pekerjaan Anda — baris bukan-estimasi dipertahankan.

## B4 — Tukar data contoh dengan data sungguhan

Angka yang sama dari B3 dipakai untuk mengisi `kab_profil.csv`. Kolom
surplus/defisit diisi produksi dikurangi konsumsi, dengan konsumsi = penduduk
kabupaten dikali konsumsi per kapita Susenas provinsi.

Ganti `status_verifikasi` dari `contoh` jadi `terverifikasi` baris per baris.
Spanduk peringatan kuning di tab akan menyusut sendiri seiring Anda mengisi, dan
hilang saat tidak ada lagi baris `contoh`.

Untuk `kab_harga.csv`, data dari B2 tinggal dibentuk ulang ke kolom
`provinsi, kabkota, komoditas, tanggal, harga, sumber, status_verifikasi`.

---

## Urutan yang saya sarankan hari ini

1. Jalur A Langkah 1–6 — sistem hidup dengan data contoh (40 menit)
2. Jalur B1 — temukan pola URL (10 menit)
3. Jalankan penarikan B2, biarkan berjalan
4. Kerjakan B3 sambil menunggu

Akhir hari Anda punya sistem yang berfungsi penuh dan sebagian data sudah
terverifikasi. Yang tersisa hanya menukar isi berkas.

## Aturan yang tidak boleh dilanggar

Jangan pernah menangkap layar tab kabupaten untuk paper atau presentasi selama
spanduk kuning masih muncul. Angka di baliknya karangan komputer. Spanduk itu
sengaja dibuat mencolok supaya Anda tidak lupa.
