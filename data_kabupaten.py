"""
data_kabupaten.py — kontrak data untuk drill-down kabupaten
============================================================
Berkas ini menetapkan bentuk data yang dipakai tab kabupaten, supaya
pembangunan sistem dan verifikasi data bisa berjalan bersamaan. Sistem dibangun
di atas skema; verifikasi mengisi skema. Tidak ada kode yang perlu berubah saat
data contoh ditukar data asli.

TIGA BERKAS

kab_profil.csv       satu baris per kabupaten/kota
    provinsi, kabkota, kode_bps, lat, lon, penduduk,
    beras, jagung, bawang, cabai_besar, cabai_rawit, kentang   (surplus/defisit, ton)
    sumber, tanggal_akses, status_verifikasi

kab_harga.csv        satu baris per kabupaten x komoditas x tanggal
    provinsi, kabkota, komoditas, tanggal, harga,
    sumber, status_verifikasi

kab_rute.csv         hasil optimasi, satu baris per rute (boleh kosong di awal)
    provinsi, asal, tujuan, komoditas, volume_ton, biaya_rp

Nilai surplus/defisit memakai perjanjian yang sama dengan aplikasi provinsi:
positif berarti surplus, negatif berarti defisit.

DATA CONTOH
`buat_contoh()` menghasilkan angka acak yang bisa diulang, dan menandai setiap
barisnya `status_verifikasi = contoh`. Validator menolak berkas yang seluruhnya
berstatus contoh bila dijalankan dengan `izinkan_contoh=False`, sehingga angka
karangan tidak mungkin lolos diam-diam ke paper.
"""

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
KOM = ["beras", "jagung", "bawang", "cabai_besar", "cabai_rawit", "kentang"]

KOLOM_PROFIL = ["provinsi", "kabkota", "kode_bps", "lat", "lon", "penduduk"] + KOM + [
    "sumber", "tanggal_akses", "status_verifikasi"]
KOLOM_HARGA = ["provinsi", "kabkota", "komoditas", "tanggal", "harga",
               "sumber", "status_verifikasi"]
KOLOM_RUTE = ["provinsi", "asal", "tujuan", "komoditas", "volume_ton", "biaya_rp"]

STATUS_SAH = {"terverifikasi", "sebagian", "estimasi", "contoh"}

# Titik pusat perkiraan 38 kabupaten/kota Jawa Timur beserta kode BPS.
# Koordinat ini kasar dan hanya untuk menempatkan penanda peta; ganti dengan
# titik resmi dari Ina-Geoportal BIG sebelum dipakai menghitung jarak.
JATIM = [
    ("3501", "Kabupaten Pacitan", -8.20, 111.10), ("3502", "Kabupaten Ponorogo", -7.87, 111.47),
    ("3503", "Kabupaten Trenggalek", -8.05, 111.71), ("3504", "Kabupaten Tulungagung", -8.07, 111.90),
    ("3505", "Kabupaten Blitar", -8.13, 112.17), ("3506", "Kabupaten Kediri", -7.82, 112.06),
    ("3507", "Kabupaten Malang", -8.17, 112.65), ("3508", "Kabupaten Lumajang", -8.13, 113.22),
    ("3509", "Kabupaten Jember", -8.17, 113.70), ("3510", "Kabupaten Banyuwangi", -8.35, 114.20),
    ("3511", "Kabupaten Bondowoso", -7.91, 113.82), ("3512", "Kabupaten Situbondo", -7.71, 114.01),
    ("3513", "Kabupaten Probolinggo", -7.87, 113.30), ("3514", "Kabupaten Pasuruan", -7.72, 112.85),
    ("3515", "Kabupaten Sidoarjo", -7.45, 112.70), ("3516", "Kabupaten Mojokerto", -7.47, 112.47),
    ("3517", "Kabupaten Jombang", -7.55, 112.23), ("3518", "Kabupaten Nganjuk", -7.60, 111.90),
    ("3519", "Kabupaten Madiun", -7.63, 111.65), ("3520", "Kabupaten Magetan", -7.65, 111.35),
    ("3521", "Kabupaten Ngawi", -7.40, 111.45), ("3522", "Kabupaten Bojonegoro", -7.15, 111.88),
    ("3523", "Kabupaten Tuban", -6.90, 112.05), ("3524", "Kabupaten Lamongan", -7.12, 112.42),
    ("3525", "Kabupaten Gresik", -7.16, 112.65), ("3526", "Kabupaten Bangkalan", -7.03, 112.75),
    ("3527", "Kabupaten Sampang", -7.05, 113.25), ("3528", "Kabupaten Pamekasan", -7.05, 113.48),
    ("3529", "Kabupaten Sumenep", -7.00, 113.87), ("3571", "Kota Kediri", -7.82, 112.02),
    ("3572", "Kota Blitar", -8.10, 112.16), ("3573", "Kota Malang", -7.98, 112.63),
    ("3574", "Kota Probolinggo", -7.75, 113.22), ("3575", "Kota Pasuruan", -7.65, 112.91),
    ("3576", "Kota Mojokerto", -7.47, 112.43), ("3577", "Kota Madiun", -7.63, 111.52),
    ("3578", "Kota Surabaya", -7.26, 112.75), ("3579", "Kota Batu", -7.87, 112.53),
]


# ---------------------------------------------------------------- validasi
class DataKabupatenTidakSah(ValueError):
    pass


def validasi(profil, harga, rute=None, izinkan_contoh=True, ketat=True) -> list:
    m = []

    for nama, df, kolom in [("profil", profil, KOLOM_PROFIL),
                            ("harga", harga, KOLOM_HARGA)]:
        kurang = [c for c in kolom if c not in df.columns]
        if kurang:
            m.append(f"kab_{nama}.csv kehilangan kolom {kurang}")

    if "kabkota" in profil.columns and profil.kabkota.duplicated().any():
        ganda = profil.loc[profil.kabkota.duplicated(), "kabkota"].unique().tolist()
        m.append(f"kab_profil.csv memuat kabupaten ganda: {ganda}")

    for c in ["lat", "lon", "penduduk"] + KOM:
        if c not in profil.columns:
            continue
        nilai = pd.to_numeric(profil[c], errors="coerce")
        if nilai.isna().any():
            m.append(f"kab_profil.csv kolom {c} punya sel kosong atau bukan angka")
    if "lat" in profil.columns:
        lat = pd.to_numeric(profil.lat, errors="coerce")
        lon = pd.to_numeric(profil.lon, errors="coerce")
        if ((lat < -11) | (lat > 6)).any() or ((lon < 95) | (lon > 141)).any():
            m.append("kab_profil.csv memuat koordinat di luar wilayah Indonesia")
    if "penduduk" in profil.columns:
        if (pd.to_numeric(profil.penduduk, errors="coerce") <= 0).any():
            m.append("kab_profil.csv memuat penduduk nol atau negatif")

    if "komoditas" in harga.columns:
        asing = set(harga.komoditas) - set(KOM)
        if asing:
            m.append(f"kab_harga.csv memuat komoditas di luar daftar: {sorted(asing)}")
    if "harga" in harga.columns:
        h = pd.to_numeric(harga.harga, errors="coerce")
        if (h <= 0).any():
            m.append("kab_harga.csv memuat harga nol atau negatif")
    if "kabkota" in harga.columns and "kabkota" in profil.columns:
        yatim = set(harga.kabkota) - set(profil.kabkota)
        if yatim:
            m.append(f"kab_harga.csv memuat kabupaten yang tidak ada di profil: "
                     f"{sorted(yatim)[:5]}")

    for nama, df in [("profil", profil), ("harga", harga)]:
        if "status_verifikasi" not in df.columns:
            continue
        salah = set(df.status_verifikasi.astype(str).str.lower()) - STATUS_SAH
        if salah:
            m.append(f"kab_{nama}.csv memuat status tidak dikenal: {sorted(salah)}")
        if not izinkan_contoh:
            n = (df.status_verifikasi.astype(str).str.lower() == "contoh").sum()
            if n:
                m.append(f"kab_{nama}.csv masih memuat {n} baris berstatus contoh; "
                         "angka karangan tidak boleh masuk hasil akhir")

    if rute is not None and len(rute):
        kurang = [c for c in KOLOM_RUTE if c not in rute.columns]
        if kurang:
            m.append(f"kab_rute.csv kehilangan kolom {kurang}")
        elif "kabkota" in profil.columns:
            luar = (set(rute.asal) | set(rute.tujuan)) - set(profil.kabkota)
            if luar:
                m.append(f"kab_rute.csv menyebut wilayah di luar profil: {sorted(luar)[:5]}")

    if m and ketat:
        raise DataKabupatenTidakSah("Data kabupaten tidak lolos pemeriksaan:\n  - "
                                    + "\n  - ".join(m))
    return m


# ------------------------------------------------------------------- muat
def muat(folder: Path = HERE, validasi_ketat: bool = True):
    profil = pd.read_csv(folder / "kab_profil.csv")
    harga = pd.read_csv(folder / "kab_harga.csv", parse_dates=["tanggal"])
    rute_path = folder / "kab_rute.csv"
    rute = pd.read_csv(rute_path) if rute_path.exists() else pd.DataFrame(columns=KOLOM_RUTE)
    if validasi_ketat:
        validasi(profil, harga, rute)
    return profil, harga, rute


def ringkas_status(*df_list, nama=None) -> dict:
    """
    Berapa bagian data yang masih contoh, dirinci per berkas.

    Rasio gabungan menyesatkan ketika dua berkas berbeda jauh ukurannya:
    kab_profil punya 38 baris, kab_harga puluhan ribu. Setelah profil
    diverifikasi seluruhnya, rasio gabungan tetap menunjukkan hampir 100 persen
    dan spanduk mengumumkan "seluruh data masih contoh" — padahal neraca
    surplus-defisit yang tampil di peta sudah nyata.
    """
    nama = nama or [f"berkas {i+1}" for i in range(len(df_list))]
    total = contoh = 0
    rinci = {}
    for n, df in zip(nama, df_list):
        if df is None or not len(df) or "status_verifikasi" not in df.columns:
            continue
        s = df.status_verifikasi.astype(str).str.lower()
        c = int((s == "contoh").sum())
        rinci[n] = {"baris": len(s), "contoh": c, "rasio": c / len(s)}
        total += len(s)
        contoh += c
    return {"total": total, "contoh": contoh,
            "rasio_contoh": contoh / total if total else 0.0,
            "rinci": rinci}


# ------------------------------------------------------------- data contoh
def buat_contoh(provinsi="Jawa Timur", hari=180, seed=42):
    """
    Hasilkan data berbentuk benar dengan angka karangan, semuanya bertanda
    `contoh`. Tujuannya agar tab bisa dibangun dan diuji hari ini, bukan
    menunggu verifikasi selesai.

    Angka disusun agar polanya masuk akal — Surabaya defisit karena kota besar,
    Malang dan Batu satu-satunya penghasil kentang, Nganjuk dan Probolinggo
    kuat di bawang merah — supaya tampilan peta terlihat wajar saat diuji.
    Tetap saja karangan.
    """
    rng = np.random.default_rng(seed)
    baris = []
    sentra_bawang = {"Kabupaten Nganjuk", "Kabupaten Probolinggo", "Kabupaten Sampang"}
    sentra_kentang = {"Kabupaten Malang", "Kota Batu", "Kabupaten Probolinggo",
                      "Kabupaten Lumajang", "Kabupaten Bondowoso"}
    lumbung = {"Kabupaten Ngawi", "Kabupaten Bojonegoro", "Kabupaten Lamongan",
               "Kabupaten Jember", "Kabupaten Banyuwangi"}

    for kode, nama, lat, lon in JATIM:
        kota = nama.startswith("Kota")
        penduduk = int(rng.integers(90_000, 340_000) if kota
                       else rng.integers(600_000, 2_600_000))
        skala = penduduk / 1_000_000
        nilai = {}
        nilai["beras"] = int(rng.normal(90_000 if nama in lumbung else 12_000, 20_000)
                             - (140_000 * skala if kota else 0))
        nilai["jagung"] = int(rng.normal(60_000 if nama in lumbung else 9_000, 18_000)
                              - (40_000 * skala if kota else 0))
        nilai["bawang"] = int(rng.normal(28_000 if nama in sentra_bawang else -900, 3_000))
        nilai["cabai_besar"] = int(rng.normal(3_500 if not kota else -2_200, 1_800))
        nilai["cabai_rawit"] = int(rng.normal(5_200 if not kota else -2_800, 2_200))
        nilai["kentang"] = int(rng.normal(9_000, 2_500) if nama in sentra_kentang
                               else rng.normal(-450, 200))
        baris.append(dict(provinsi=provinsi, kabkota=nama, kode_bps=kode,
                          lat=lat, lon=lon, penduduk=penduduk, **nilai,
                          sumber="dibangkitkan buat_contoh()",
                          tanggal_akses=pd.Timestamp.today().strftime("%Y-%m-%d"),
                          status_verifikasi="contoh"))
    profil = pd.DataFrame(baris)[KOLOM_PROFIL]

    dasar = {"beras": 13_000, "jagung": 6_200, "bawang": 34_000,
             "cabai_besar": 42_000, "cabai_rawit": 51_000, "kentang": 17_000}
    tanggal = pd.date_range(end=pd.Timestamp.today().normalize(), periods=hari, freq="D")
    t = np.arange(hari)
    hb = []
    for nama in profil.kabkota:
        geser = rng.normal(1.0, 0.06)
        for kom, h0 in dasar.items():
            musim = 1 + 0.10 * np.sin(2 * np.pi * t / 90 + rng.uniform(0, 6.28))
            derau = rng.normal(0, 0.02, hari).cumsum() * 0.35
            seri = h0 * geser * musim * (1 + derau)
            hb.append(pd.DataFrame({"provinsi": provinsi, "kabkota": nama,
                                    "komoditas": kom, "tanggal": tanggal,
                                    "harga": seri.round(-1).astype(int),
                                    "sumber": "dibangkitkan buat_contoh()",
                                    "status_verifikasi": "contoh"}))
    harga = pd.concat(hb, ignore_index=True)[KOLOM_HARGA]
    harga.loc[harga.harga < 500, "harga"] = 500
    return profil, harga


if __name__ == "__main__":
    profil, harga = buat_contoh()
    profil.to_csv(HERE / "kab_profil.csv", index=False)
    harga.to_csv(HERE / "kab_harga.csv", index=False)
    validasi(profil, harga)
    r = ringkas_status(profil, harga)
    print(f"kab_profil.csv : {len(profil)} baris")
    print(f"kab_harga.csv  : {len(harga):,} baris")
    print(f"\nSeluruh {r['contoh']:,} baris berstatus 'contoh'. Tab akan menampilkan "
          "spanduk peringatan sampai statusnya diganti data hasil verifikasi.")
