# Panduan Deploy PradanaLog ke Server Kampus

Dokumen ini untuk memasang dasbor PradanaLog di server Institut Teknologi Del
agar dapat diakses TPID, Bapanas, dan pihak lain melalui domain kampus.

Ringkasan pembagian beban:

| Kebutuhan | Tempat |
|---|---|
| Menyajikan dasbor ke pengguna (24 jam) | Server web biasa, 2–4 core, RAM 4–8 GB |
| Melatih model, backtest besar, optimasi 514 kabupaten/kota | Server GPU B200, sebagai job terjadwal |

Dasbor ini berjalan sepenuhnya di CPU. GPU B200 **tidak terpakai** untuk
menyajikan halaman, jadi jangan dijadikan web server.

---

## 1. Yang perlu diminta ke tim TI / pengelola HPC

Sampaikan empat hal berikut:

1. **Satu VM atau LXC** dengan Ubuntu Server 22.04/24.04, 2–4 vCPU, RAM 4–8 GB,
   disk 20 GB. Tidak perlu GPU.
2. **Layanan boleh menyala terus** (bukan job antrean seperti SLURM).
3. **Subdomain**, misalnya `pradanalog.del.ac.id`, diarahkan ke IP VM tersebut.
4. **Port 80 dan 443 terbuka** dari internet, atau lewat reverse proxy kampus.

Bila kampus hanya mengizinkan akses dari dalam jaringan, dasbor tetap bisa
dipakai untuk demo internal. Untuk audiensi dengan Bank Indonesia atau Bapanas,
akses publik diperlukan.

---

## 2. Prasyarat di server

```bash
sudo apt update && sudo apt install -y git nginx
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER      # keluar lalu masuk lagi setelah ini
```

Bila tim TI **tidak mengizinkan Docker**, lewati Docker dan ikuti
[jalur B](#4b-jalur-tanpa-docker-systemd).

---

## 3. Ambil kode

```bash
sudo mkdir -p /opt/pradanalog && sudo chown $USER /opt/pradanalog
git clone https://github.com/xiongdy12/mvp2_pradanalog.git /opt/pradanalog/app
cd /opt/pradanalog/app
```

---

## 4. Membuat akun pengguna

`kredensial.json` sengaja **tidak** ikut di Git, karena berisi hash kata sandi.
Berkas itu dibuat langsung di server:

```bash
echo {} > kredensial.json
python3 buat_kredensial.py tambah
```

> Berkas harus berisi `{}`, bukan kosong. `touch kredensial.json` menghasilkan
> berkas berukuran nol, dan itu ditolak sebagai JSON yang tidak sah.

Bila Python 3.12 belum ada di server, jalankan lewat container setelah citra
dibangun (langkah 4A):

```bash
docker run --rm -it --user $(id -u):$(id -g) -v "$PWD":/app -w /app \
    pradanalog:latest python buat_kredensial.py tambah
```

Isian yang diminta: nama pengguna, kata sandi, peran (`pusat` / `provinsi` /
`kabupaten`), lalu provinsi dan kabupaten bila perannya menuntut itu.

Untuk demo cepat ke juri atau tamu audiensi:

```bash
python3 buat_kredensial.py contoh    # 3 akun demo
python3 buat_kredensial.py daftar    # lihat akun yang ada
```

> Akun demo memakai kata sandi yang mudah ditebak. Hapus sebelum dasbor
> dibuka ke publik: `python3 buat_kredensial.py hapus <nama_pengguna>`

---

## 4A. Jalur Docker (disarankan)

> Pastikan langkah 4 sudah dijalankan lebih dulu. Bila `kredensial.json` belum
> ada, Docker akan membuatkan **folder** kosong bernama sama dan semua login
> akan gagal. Periksa dengan `ls -la kredensial.json`; hasilnya harus berawalan
> `-rw`, bukan `d`.

```bash
cd /opt/pradanalog/app
docker compose up -d --build
```

Pembangunan pertama memakan 3–8 menit. Setelah selesai, periksa:

```bash
docker compose ps                  # STATUS harus healthy
curl -s localhost:8501/_stcore/health   # harus menjawab: ok
docker compose logs -f             # Ctrl+C untuk keluar dari log
```

Catatan teknis: `Dockerfile` memakai **Python 3.12**, bukan 3.11, karena
`numpy==2.5.0` pada `requirements.txt` hanya tersedia untuk Python 3.12 ke atas.

---

## 4B. Jalur tanpa Docker (systemd)

```bash
sudo apt install -y python3.12 python3.12-venv
sudo useradd --system --create-home --home-dir /opt/pradanalog pradana
sudo chown -R pradana:pradana /opt/pradanalog

sudo -u pradana python3.12 -m venv /opt/pradanalog/venv
sudo -u pradana /opt/pradanalog/venv/bin/pip install -r /opt/pradanalog/app/requirements.txt

sudo cp /opt/pradanalog/app/deploy/pradanalog.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pradanalog
sudo systemctl status pradanalog
```

Bila Ubuntu yang terpasang belum menyediakan Python 3.12:

```bash
sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt update
sudo apt install -y python3.12 python3.12-venv
```

---

## 4C. Jalur tanpa hak sudo (Docker + Caddy)

Dipakai bila akun Bapak anggota grup `docker` tetapi tidak punya sudo, sehingga
Nginx dan certbot tidak bisa dipasang ke sistem. Caddy dijalankan sebagai
container dan mengurus sertifikat HTTPS sendiri. Ini jalur yang dipakai pada
pemasangan di `itdelb200b`.

```bash
cd ~
git clone https://github.com/xiongdy12/mvp2_pradanalog.git pradanalog
cd pradanalog

# Angka uid/gid dipakai docker-compose.tanpa-sudo.yml agar container
# berjalan sebagai pemilik berkas, bukan uid 10001 bawaan citra.
printf 'HOST_UID=%s\nHOST_GID=%s\n' $(id -u) $(id -g) > .env

docker build -t pradanalog:latest .
echo {} > kredensial.json
docker run --rm -it --user $(id -u):$(id -g) -v "$PWD":/app -w /app \
    pradanalog:latest python buat_kredensial.py tambah

nano deploy/Caddyfile        # isi nama domain, atau aktifkan blok :80
docker compose -f docker-compose.tanpa-sudo.yml up -d --build
docker compose -f docker-compose.tanpa-sudo.yml ps
curl -s localhost/_stcore/health
```

Periksa lebih dulu bahwa port 80 dan 443 belum dipakai layanan lain:

```bash
ss -tln | grep -E ':80 |:443 |:8501 '
```

Perintah itu tidak boleh menampilkan apa pun.

Selama domain belum siap, pakai blok `:80` di dalam `deploy/Caddyfile`, karena
Caddy tidak dapat mengambil sertifikat untuk domain yang belum mengarah ke
server ini.

---

## 5. Nginx dan HTTPS

```bash
sudo cp /opt/pradanalog/app/deploy/nginx-pradanalog.conf \
        /etc/nginx/sites-available/pradanalog
sudo nano /etc/nginx/sites-available/pradanalog    # ganti nama domain
sudo ln -s /etc/nginx/sites-available/pradanalog /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Pasang sertifikat HTTPS gratis:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d pradanalog.del.ac.id
```

Certbot memperbarui sertifikat otomatis setiap 90 hari.

> Dua baris `proxy_set_header Upgrade` dan `Connection "upgrade"` di berkas
> Nginx wajib ada. Tanpa keduanya, dasbor tampil lalu membeku pada tulisan
> "Connecting..." karena Streamlit memakai WebSocket.

---

## 6. Memperbarui versi

Setiap kali ada perubahan yang sudah di-push ke GitHub:

```bash
cd /opt/pradanalog/app
git pull
python3 uji_sistem.py              # harus: Lulus 41 · Gagal 0
docker compose up -d --build       # jalur Docker
# atau
sudo systemctl restart pradanalog  # jalur systemd
```

Jalankan `uji_sistem.py` **sebelum** memuat ulang layanan. Bila ada yang gagal,
jangan lanjutkan; versi lama tetap melayani pengguna.

---

## 7. Menyegarkan data dan hasil hitungan

Berkas hasil hitungan berikut dibaca dasbor apa adanya, jadi dasbor tidak
menjalankan solver saat halaman dibuka:

| Berkas | Dibangun oleh |
|---|---|
| `kab_rute.csv` | `python3 optimasi_kabupaten.py` |
| `prediksi_harga.csv` | `python3 bangun_prediksi.py` |
| `kab_harga.csv` | `python3 bangun_kab_harga.py` |

Untuk pembaruan harga mingguan, pasang cron:

```bash
crontab -e
```

Tambahkan baris berikut (setiap Senin pukul 02.00 WIB):

```
0 2 * * 1 cd /opt/pradanalog/app && /usr/bin/python3 bangun_kab_harga.py && /usr/bin/python3 optimasi_kabupaten.py && /usr/bin/docker compose restart pradanalog
```

---

## 8. Peran server B200

Server GPU dipakai untuk pekerjaan yang benar-benar butuh GPU, dan hasilnya
dikirim ke server dasbor sebagai berkas:

1. Latih ulang model peramalan, backtest rolling-origin, atau optimasi MOLP
   skala nasional di B200, dijadwalkan lewat SLURM.
2. Salin keluarannya ke server dasbor, misalnya:
   ```bash
   scp prediksi_harga.csv pradana@pradanalog.del.ac.id:/opt/pradanalog/app/
   ```
3. Muat ulang layanan dasbor.

Pola ini menjaga dasbor tetap ringan dan membuat klaim pemakaian B200 pada
proposal tetap jujur: GPU dipakai untuk komputasi, bukan untuk menyajikan web.

---

## 9. Pemecahan masalah

| Gejala | Penyebab dan penanganan |
|---|---|
| Halaman membeku di "Connecting..." | Dua baris `Upgrade`/`Connection` hilang dari konfigurasi Nginx |
| `502 Bad Gateway` | Container atau layanan mati. Cek `docker compose ps` atau `systemctl status pradanalog` |
| Peta kabupaten kosong | `kab_batas.geojson` tidak ikut tersalin. Cek dengan `ls -la kab_batas.geojson` |
| Semua akun ditolak | `kredensial.json` belum dibuat di server; jalankan `buat_kredensial.py tambah` |
| Galat `numpy` saat pasang | Python masih 3.11. Wajib 3.12 ke atas |
| `PermissionError: '/app/kredensial.json'` | Container berjalan sebagai uid lain. Buat `.env` berisi HOST_UID/HOST_GID seperti pada langkah 4C, lalu jalankan ulang |
| `kredensial.json bukan JSON yang sah` | Berkas kosong. Isi dengan `echo {} > kredensial.json` lalu buat ulang akunnya |
| Tampilan masih versi lama | Peramban menyimpan versi lama; tekan Ctrl+F5 |

Log lengkap:

```bash
docker compose logs --tail 100     # jalur Docker
sudo journalctl -u pradanalog -n 100 --no-pager   # jalur systemd
```

---

## 10. Sebelum dibuka ke publik

- [ ] Akun demo dihapus, kata sandi asli diberikan langsung ke masing-masing instansi
- [ ] HTTPS aktif, akses `http://` dialihkan otomatis ke `https://`
- [ ] `python3 uji_sistem.py` lulus 41/41 di server
- [ ] Cadangan `kredensial.json` disimpan terpisah, di luar Git
- [ ] Tim TI mengetahui layanan ini berjalan dan siapa penanggung jawabnya
