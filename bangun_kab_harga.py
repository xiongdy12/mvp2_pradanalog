"""
bangun_kab_harga.py — membentuk kab_harga.csv asli dari hasil penarikan
========================================================================
Membaca enam berkas jatim_<komoditas>_setahun.csv, meringkas harga tingkat
pasar menjadi harga tingkat kabupaten/kota per hari, lalu menulis ulang
kab_harga.csv dengan skema yang persis sama seperti versi contoh sehingga
tab_kabupaten.py tidak perlu disentuh.

Dua kosakata harus cocok dan keduanya diperiksa sebelum menulis:
  - nama kabupaten/kota   -> disamakan dengan kab_profil.csv
  - nama komoditas        -> disamakan dengan kab_harga.csv yang lama

Penggabungan yang gagal menghasilkan tabel kosong tanpa pesan galat, jadi
skrip ini menolak menulis bila ada nama yang tidak berpasangan.

Pakai:
    python bangun_kab_harga.py            uji coba, tidak menulis apa pun
    python bangun_kab_harga.py --tulis    menulis setelah keluaran uji coba benar
"""

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
TULIS = "--tulis" in sys.argv
SUMBER = "SISKAPERBAPO"
STATUS = "terverifikasi"


def normal(s: str) -> str:
    """Buang gelar wilayah dan tanda baca agar nama bisa dibandingkan."""
    s = str(s).lower().strip()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\b(kabupaten|kabupaten|kab|kota|kotamadya|adm)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def jenis(s: str) -> str:
    """Kota dan kabupaten bernama sama itu wilayah berbeda (mis. Malang)."""
    t = str(s).lower()
    return "kota" if re.search(r"\bkota\b|^kot[a\.]", t) else "kab"


def kunci(s: str) -> str:
    return f"{jenis(s)}|{normal(s)}"


def padan(sumber: list, tujuan: list) -> tuple:
    """Petakan nama sumber ke nama tujuan. Kembalikan peta dan yang gagal."""
    peta_tujuan = {}
    for t in tujuan:
        peta_tujuan.setdefault(kunci(t), t)
    peta, gagal = {}, []
    for s in sumber:
        t = peta_tujuan.get(kunci(s))
        if t is None:                       # coba tanpa membedakan kota/kab
            calon = [v for k, v in peta_tujuan.items()
                     if k.split("|", 1)[1] == normal(s)]
            t = calon[0] if len(calon) == 1 else None
        if t is None:
            gagal.append(s)
        else:
            peta[s] = t
    return peta, gagal


def main() -> int:
    profil = HERE / "kab_profil.csv"
    lama = HERE / "kab_harga.csv"
    if not profil.exists():
        print("kab_profil.csv tidak ada. Jalankan dari folder aplikasi.")
        return 1

    prof = pd.read_csv(profil)
    k_kab_prof = next((c for c in prof.columns
                       if c.strip().lower() in ("kabkota", "kabupaten", "wilayah")), None)
    if k_kab_prof is None:
        print("Kolom kabkota tidak ditemukan di kab_profil.csv:", list(prof.columns))
        return 1
    resmi = sorted(prof[k_kab_prof].dropna().astype(str).unique())
    print(f"kab_profil.csv   : {len(resmi)} kabupaten/kota resmi")

    # Kosakata komoditas dan skema kolom diambil dari berkas lama
    if lama.exists():
        old = pd.read_csv(lama)
        kolom = list(old.columns)
        kos_kom = sorted(old.komoditas.dropna().astype(str).unique())
        print(f"kab_harga.csv    : {len(old):,} baris contoh, komoditas {kos_kom}")
    else:
        kolom = ["provinsi", "kabkota", "komoditas", "tanggal",
                 "harga", "sumber", "status_verifikasi"]
        kos_kom = []
        print("kab_harga.csv    : belum ada, memakai skema baku")

    berkas = sorted(HERE.glob("jatim_*_setahun.csv"))
    if not berkas:
        print("Tidak ada berkas jatim_*_setahun.csv di folder ini.")
        return 1

    bagian, semua_kab, laporan = [], set(), []
    for p in berkas:
        kom_kunci = p.stem.replace("jatim_", "").replace("_setahun", "")
        d = pd.read_csv(p)
        d["harga"] = pd.to_numeric(d.harga, errors="coerce")
        d = d[d.harga.gt(0).fillna(False)]
        if not len(d):
            print(f"  {p.name}: tidak ada harga sah, dilewati")
            continue
        semua_kab |= set(d.kabkota.astype(str).unique())
        # harga kabupaten = median antar pasar, tahan terhadap pencilan
        g = (d.groupby([d.kabkota.astype(str), "tanggal"], as_index=False)
               .agg(harga=("harga", "median"), n_pasar=("harga", "size")))
        g.columns = ["kabkota", "tanggal", "harga", "n_pasar"]
        g["_kom"] = kom_kunci
        bagian.append(g)
        laporan.append((kom_kunci, len(g), g.tanggal.nunique(), g.kabkota.nunique()))

    gab = pd.concat(bagian, ignore_index=True)

    print("\n--- RINGKASAN PER KOMODITAS (tingkat kabupaten) ---")
    for kom, n, hari, kab in laporan:
        print(f"  {kom:14s} {n:7,} baris · {hari} hari · {kab} kab")

    # --- pemadanan nama kabupaten ---
    peta_kab, gagal_kab = padan(sorted(semua_kab), resmi)
    print("\n--- PEMADANAN KABUPATEN ---")
    print(f"cocok  : {len(peta_kab)} dari {len(semua_kab)} nama di data tarikan")
    contoh = [(s, t) for s, t in list(peta_kab.items())[:3] if s != t]
    for s, t in contoh:
        print(f"  '{s}'  ->  '{t}'")
    if gagal_kab:
        print("TIDAK COCOK (data tarikan):")
        for s in gagal_kab:
            print(f"  - {s}")
    tak_terisi = sorted(set(resmi) - set(peta_kab.values()))
    if tak_terisi:
        print("TIDAK TERISI (ada di profil, tak ada di tarikan):")
        for s in tak_terisi:
            print(f"  - {s}")

    # --- pemadanan nama komoditas ---
    kunci_kom = sorted(gab._kom.unique())
    peta_kom, gagal_kom = {}, []
    for k in kunci_kom:
        pel = k.replace("_", " ")
        calon = [v for v in kos_kom
                 if normal(v) == normal(pel) or normal(v).startswith(normal(pel))]
        if len(calon) == 1:
            peta_kom[k] = calon[0]
        elif not kos_kom:
            peta_kom[k] = pel
        else:
            gagal_kom.append((k, calon))
    print("\n--- PEMADANAN KOMODITAS ---")
    for k in kunci_kom:
        print(f"  {k:14s} ->  {peta_kom.get(k, '?')}")
    for k, calon in gagal_kom:
        print(f"  GAGAL {k}: calon {calon}")

    if gagal_kab or gagal_kom:
        print("\nTIDAK MENULIS. Ada nama yang tidak berpasangan; kirimkan daftar di atas.")
        return 1

    gab["kabkota"] = gab.kabkota.map(peta_kab)
    gab["komoditas"] = gab._kom.map(peta_kom)
    gab["provinsi"] = "Jawa Timur"
    gab["sumber"] = SUMBER
    gab["status_verifikasi"] = STATUS

    hasil = gab[[c for c in kolom if c in gab.columns]].copy()
    kurang = [c for c in kolom if c not in hasil.columns]
    if kurang:
        print("\nKolom skema lama yang tidak terbentuk:", kurang)
        return 1
    hasil = hasil.sort_values(["komoditas", "kabkota", "tanggal"]).reset_index(drop=True)

    print("\n--- HASIL ---")
    print(f"baris        : {len(hasil):,}   (contoh lama {len(old):,})"
          if lama.exists() else f"baris        : {len(hasil):,}")
    print(f"kolom        : {list(hasil.columns)}")
    print(f"kabupaten    : {hasil.kabkota.nunique()} dari {len(resmi)}")
    print(f"rentang      : {hasil.tanggal.min()}  s.d.  {hasil.tanggal.max()}")
    print(f"status       : {hasil.status_verifikasi.value_counts().to_dict()}")

    cak = (hasil.groupby(["kabkota", "komoditas"]).tanggal.nunique()
                .groupby("kabkota").min().sort_values())
    print("\nCakupan hari terendah per kabupaten:")
    for nama, n in cak.head(5).items():
        print(f"  {nama:28s} {n} hari")

    if not TULIS:
        print("\nUJI COBA — tidak ada berkas yang ditulis.")
        print("Bila keluaran di atas benar, jalankan:  python bangun_kab_harga.py --tulis")
        return 0

    if lama.exists():
        cad = HERE / f"kab_harga_contoh_{datetime.now():%Y%m%d_%H%M}.csv"
        shutil.copy2(lama, cad)
        print(f"\nSalinan versi contoh: {cad.name}")
    hasil.to_csv(lama, index=False, encoding="utf-8")
    print(f"kab_harga.csv ditulis: {len(hasil):,} baris")
    print("\nMatikan Streamlit sepenuhnya lalu nyalakan ulang.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
