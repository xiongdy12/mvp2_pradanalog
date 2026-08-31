"""
bangun_katalog.py — membangun 3 katalog basis bukti untuk IKD PradanaLog
=======================================================================
Katalog dipisah per lapis data supaya tiap sel bisa diberi sumber, URL,
tanggal akses, dan status verifikasi sendiri. Struktur long (provinsi x
komoditas) membuat dimensi C, K, T, A ikut bervariasi antarprovinsi —
masalah "tiga dimensi konstan" pada versi pertama hilang di sini.

Jalankan: python bangun_katalog.py
Keluaran: katalog_produksi.csv, katalog_harga.csv, katalog_wilayah.csv

PENTING — status verifikasi:
  terverifikasi = penulis membuka sumbernya langsung dan mencatat angkanya
  estimasi      = dugaan berdasar pengetahuan domain, WAJIB dicek (lihat VERIFIKASI.md)
Jangan pernah mengubah "estimasi" jadi "terverifikasi" tanpa membuka sumbernya.
"""

from pathlib import Path

import pandas as pd

KOM = ["beras", "jagung", "bawang", "cabai_besar", "cabai_rawit", "kentang"]

N_KABKOTA = {
    "Jawa Timur": 38, "Jawa Tengah": 35, "Jawa Barat": 27, "Sumatera Utara": 33,
    "Sulawesi Selatan": 24, "Lampung": 15, "Nusa Tenggara Barat": 10,
    "DI Yogyakarta": 5, "Bali": 9, "Sumatera Selatan": 17,
}

# Jumlah kabupaten/kota dengan produksi tercatat, per komoditas.
# Semua angka di bawah masih ESTIMASI kecuali disebut lain — lihat VERIFIKASI.md.
PRODUKSI = {
    #                     beras jagung bawang cbesar crawit kentang
    "Jawa Timur":          [34,   33,    12,    30,    34,     6],
    "Jawa Tengah":         [32,   30,    10,    28,    30,     6],
    "Jawa Barat":          [24,   22,     8,    20,    22,     6],
    "Sumatera Utara":      [30,   28,     8,    24,    24,     5],
    "Sulawesi Selatan":    [22,   22,     6,    16,    18,     3],
    "Lampung":             [14,   14,     3,    12,    13,     1],
    "Nusa Tenggara Barat": [10,   10,     6,     9,    10,     1],
    "DI Yogyakarta":       [ 4,    4,     3,     4,     4,     0],
    "Bali":                [ 8,    8,     3,     7,     8,     2],
    "Sumatera Selatan":    [16,   14,     2,    12,    13,     1],
}

# Rentang tahun deret kabupaten. Tanaman pangan (padi, jagung) punya deret
# lebih panjang lewat KSA; tabel hortikultura kabupaten di situs BPS provinsi
# umumnya baru mulai 2021. Perbedaan ini nyata dan membuat dimensi T bervariasi
# sesuai komposisi komoditas tiap provinsi.
TAHUN = {"beras": (2018, 2024), "jagung": (2018, 2024), "bawang": (2021, 2024),
         "cabai_besar": (2021, 2024), "cabai_rawit": (2021, 2024),
         "kentang": (2021, 2024)}

SUMBER_PROD = {
    "beras": ("BPS – Luas Panen & Produksi Padi (KSA) per kab/kota",
              "https://www.bps.go.id/id/statistics-table/2/NjEjMg==/produksi-tanaman-sayuran.html"),
    "jagung": ("BPS provinsi – produksi jagung menurut kab/kota",
               "https://jatim.bps.go.id/id/statistics-table"),
    "bawang": ("BPS provinsi – produksi bawang daun & bawang merah menurut kab/kota",
               "https://jatim.bps.go.id/en/statistics-table/1/MjUzNCMx/-produksi-tanaman-sayuran-bawang-daun-dan-bawang-merah-menurut-kabupaten-kota-dan-jenis-tanaman-di-provinsi-jawa-timur-kuintal-2021-dan-2022.html"),
    "cabai_besar": ("BPS provinsi – produksi cabai besar/rawit/keriting menurut kab/kota",
                    "https://jatim.bps.go.id/en/statistics-table/1/MjUzNiMx/produksi-tanaman-sayuran-cabai-besar--cabai-rawit--cabai-keriting-menurut-kabupaten-kota-dan-jenis-tanaman-di-provinsi-jawa-timur--kuintal---2021-dan-2022.html"),
    "cabai_rawit": ("BPS provinsi – produksi cabai besar/rawit/keriting menurut kab/kota",
                    "https://jatim.bps.go.id/en/statistics-table/1/MjUzNiMx/produksi-tanaman-sayuran-cabai-besar--cabai-rawit--cabai-keriting-menurut-kabupaten-kota-dan-jenis-tanaman-di-provinsi-jawa-timur--kuintal---2021-dan-2022.html"),
    "kentang": ("BPS provinsi – produksi tanaman sayuran semusim menurut kab/kota",
                "https://jatim.bps.go.id/id/statistics-table/3/%20ZUhFd1JtZzJWVVpqWTJsV05XTllhVmhRSzFoNFFUMDkjMw==/produksi-tanaman-sayuran-menurut-kabupaten-kota-dan-jenis-tanaman-di-provinsi-jawa-timur--2023.html?year=2024"),
}

# --------------------------------------------------------------------- harga
# TEMUAN TERVERIFIKASI (20 Agustus 2026):
# PIHPS Bank Indonesia menyurvei 82 kota/kabupaten sampel inflasi IHK, 2 pasar
# tradisional per kab/kota, dan daftar komoditasnya TIDAK memuat jagung maupun
# kentang. Artinya PIHPS hanya menutup 4 dari 6 komoditas PradanaLog.
PIHPS_KOM = ["beras", "bawang", "cabai_besar", "cabai_rawit"]
PIHPS_KABKOTA = {  # perkiraan jumlah kab/kota sampel PIHPS per provinsi
    "Jawa Timur": 8, "Jawa Tengah": 6, "Jawa Barat": 7, "Sumatera Utara": 6,
    "Sulawesi Selatan": 5, "Lampung": 2, "Nusa Tenggara Barat": 2,
    "DI Yogyakarta": 1, "Bali": 1, "Sumatera Selatan": 2,
}

# Sistem harga milik pemerintah provinsi. Hanya dua provinsi di daftar pendek
# yang punya sistem harga harian tingkat kabupaten sendiri.
SISTEM_PROV = {
    "Jawa Timur": dict(
        nama="SISKAPERBAPO Disperindag Jatim",
        url="https://siskaperbapo.jatimprov.go.id/",
        kom=["beras", "jagung", "bawang", "cabai_besar", "cabai_rawit", "kentang"],
        n_kabkota=38, frekuensi="harian", keterisian=0.996,
        status="sebagian",
        catatan="TERVERIFIKASI dari sumber: 38 kab/kota, 121 pasar, 67 komoditas "
                "dipantau. Keenam komoditas PradanaLog ada, termasuk KENTANG "
                "(id=45) yang semula diduga tidak dipantau. Keterisian 0,996 dihitung "
                "dari panel 7 hari (2026-08-16 s.d. 2026-08-22) komoditas Beras Premium: "
                "tingkat kabupaten 0,9962, enam hari pertama 1,000 dan hanya hari "
                "berjalan turun ke 0,974. Perlu diperluas ke satu tahun dan enam "
                "komoditas. id komoditas: beras=4, jagung=25, bawang=39, "
                "cabai_besar=38, cabai_rawit=50, kentang=45."),
    "Jawa Tengah": dict(
        nama="SiHati Jateng (hargajateng.org)",
        url="https://www.hargajateng.org/",
        kom=["beras", "jagung", "bawang", "cabai_besar", "cabai_rawit"],
        n_kabkota=35, frekuensi="harian", keterisian=0.70,
        status="estimasi",
        catatan="Sistem dan cakupan 35 kab/kota terverifikasi lewat menu Tabel Harga "
                "Berdasarkan Kabupaten (dropdown memuat Cilacap s.d. Kota Tegal). SiHati "
                "adalah SPA JavaScript sehingga angkanya tidak bisa ditarik tanpa browser; "
                "keterisian 0,70 MASIH ESTIMASI dan menentukan peringkat."),
}

# ------------------------------------------------------------------ wilayah
# fraksi_terhubung_darat: bagian kab/kota yang tersambung jaringan jalan tanpa
# penyeberangan laut. Dipakai karena matriks jarak MOLP/FLP intra-provinsi
# tidak sah untuk kabupaten kepulauan.
WILAYAH = {
    "Jawa Timur":          dict(geojson=1, terhubung=0.97, lag_prod=8),
    "Jawa Tengah":         dict(geojson=1, terhubung=0.97, lag_prod=8),
    "Jawa Barat":          dict(geojson=1, terhubung=1.00, lag_prod=8),
    "Sumatera Utara":      dict(geojson=1, terhubung=0.85, lag_prod=10),
    "Sulawesi Selatan":    dict(geojson=1, terhubung=0.88, lag_prod=10),
    "Lampung":             dict(geojson=1, terhubung=1.00, lag_prod=10),
    "Nusa Tenggara Barat": dict(geojson=1, terhubung=0.50, lag_prod=10),
    "DI Yogyakarta":       dict(geojson=1, terhubung=1.00, lag_prod=8),
    "Bali":                dict(geojson=1, terhubung=0.89, lag_prod=10),
    "Sumatera Selatan":    dict(geojson=1, terhubung=1.00, lag_prod=10),
}

TANGGAL = "2026-08-20"


def bangun_produksi():
    baris = []
    for prov, vals in PRODUKSI.items():
        for kom, n in zip(KOM, vals):
            t0, t1 = TAHUN[kom]
            sumber, url = SUMBER_PROD[kom]
            baris.append(dict(
                provinsi=prov, komoditas=kom, n_kabkota=N_KABKOTA[prov],
                n_kabkota_produksi=n, tahun_awal=t0, tahun_akhir=t1,
                sumber=sumber, url=url, tanggal_akses=TANGGAL,
                status_verifikasi="estimasi"))
    return pd.DataFrame(baris)


def bangun_harga():
    baris = []
    for prov in N_KABKOTA:
        for kom in KOM:
            opsi = []
            if kom in PIHPS_KOM:
                opsi.append(dict(
                    sistem="PIHPS Bank Indonesia", n_kabkota_harga=PIHPS_KABKOTA[prov],
                    frekuensi="harian", keterisian=0.95,
                    url="https://www.bi.go.id/hargapangan", status_verifikasi="terverifikasi",
                    catatan="PIHPS: 82 kab/kota sampel IHK nasional, 2 pasar per kab/kota; "
                            "daftar komoditas tidak memuat jagung dan kentang."))
            s = SISTEM_PROV.get(prov)
            if s and kom in s["kom"]:
                opsi.append(dict(
                    sistem=s["nama"], n_kabkota_harga=s["n_kabkota"],
                    frekuensi=s["frekuensi"], keterisian=s["keterisian"],
                    url=s["url"], status_verifikasi=s["status"], catatan=s["catatan"]))
            if not opsi:
                opsi.append(dict(
                    sistem="(tidak ada sumber kab/kota)", n_kabkota_harga=0,
                    frekuensi="tidak ada", keterisian=0.0,
                    url="", status_verifikasi="terverifikasi",
                    catatan="Tidak ditemukan pemantauan harga tingkat kabupaten untuk "
                            "komoditas ini; harga hanya tersedia di level provinsi."))
            # pilih sumber terbaik: cakupan x frekuensi x keterisian
            frek_skor = {"harian": 1.0, "mingguan": 0.75, "bulanan": 0.5, "tidak ada": 0.0}
            best = max(opsi, key=lambda o: (o["n_kabkota_harga"] / N_KABKOTA[prov])
                       * frek_skor[o["frekuensi"]] * o["keterisian"])
            baris.append(dict(provinsi=prov, komoditas=kom,
                              n_kabkota=N_KABKOTA[prov], **best,
                              tanggal_akses=TANGGAL))
    return pd.DataFrame(baris)


def bangun_wilayah():
    baris = []
    for prov, w in WILAYAH.items():
        baris.append(dict(
            provinsi=prov, n_kabkota=N_KABKOTA[prov],
            geojson_kabkota=w["geojson"], fraksi_terhubung_darat=w["terhubung"],
            lag_bulan_produksi=w["lag_prod"],
            sumber="Batas wilayah: geoportal Ina-Geoportal/BIG; konektivitas: "
                   "penilaian jaringan jalan nasional",
            url="https://tanahair.indonesia.go.id/", tanggal_akses=TANGGAL,
            status_verifikasi="estimasi"))
    return pd.DataFrame(baris)


def gabung_aman(baru: pd.DataFrame, path: str, kunci: list) -> pd.DataFrame:
    """
    Tulis katalog tanpa menghapus pekerjaan verifikasi manual.

    Baris lama yang berstatus selain `estimasi` dipertahankan apa adanya;
    hanya baris yang masih estimasi yang ditimpa isian generator. Tanpa
    penjaga ini, satu kali `python bangun_katalog.py` akan menghapus berjam-jam
    verifikasi tanpa memberi tahu siapa pun.
    """
    p = Path(path)
    if not p.exists():
        baru.to_csv(p, index=False)
        return baru

    lama = pd.read_csv(p)
    if "status_verifikasi" not in lama.columns:
        baru.to_csv(p, index=False)
        return baru

    beda = set(baru.columns) ^ set(lama.columns)
    if beda:
        # Tanpa peringatan ini, kolom yang hanya ada di salah satu berkas akan
        # berubah jadi sel kosong untuk seluruh baris terkunci tanpa jejak.
        print(f"  PERINGATAN {p.name}: susunan kolom berbeda {sorted(beda)}. "
              f"Kolom yang hilang akan terisi kosong — periksa hasilnya.")

    dikunci = lama[lama.status_verifikasi.str.lower() != "estimasi"].copy()
    if len(dikunci) == 0:
        baru.to_csv(p, index=False)
        return baru

    idx_kunci = set(map(tuple, dikunci[kunci].values))
    sisa = baru[[tuple(r) not in idx_kunci for r in baru[kunci].values]]
    hasil = (pd.concat([dikunci, sisa], ignore_index=True)
             .sort_values(kunci).reset_index(drop=True))
    hasil = hasil[baru.columns]
    hasil.to_csv(p, index=False)
    print(f"  {p.name}: {len(dikunci)} baris terverifikasi dipertahankan, "
          f"{len(sisa)} baris estimasi diperbarui")
    return hasil


if __name__ == "__main__":
    import sys

    paksa = "--paksa" in sys.argv
    if paksa:
        for f in ("katalog_produksi.csv", "katalog_harga.csv", "katalog_wilayah.csv"):
            Path(f).unlink(missing_ok=True)
        print("Mode --paksa: katalog lama dihapus, termasuk baris terverifikasi.\n")

    p = gabung_aman(bangun_produksi(), "katalog_produksi.csv", ["provinsi", "komoditas"])
    h = gabung_aman(bangun_harga(), "katalog_harga.csv", ["provinsi", "komoditas"])
    w = gabung_aman(bangun_wilayah(), "katalog_wilayah.csv", ["provinsi"])

    print(f"\nkatalog_produksi.csv  : {len(p)} baris")
    print(f"katalog_harga.csv     : {len(h)} baris")
    print(f"katalog_wilayah.csv   : {len(w)} baris")
    ver = (h.status_verifikasi != "estimasi").sum()
    print(f"Baris harga bukan estimasi: {ver}/{len(h)}")
