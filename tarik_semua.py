"""
tarik_semua.py — menarik seluruh komoditas sisanya dari SISKAPERBAPO
=====================================================================
Memakai tarik_rentang() dari hitung_keterisian.py yang sudah terbukti jalan
pada kentang dan beras.

Aman diulang. Komoditas yang berkasnya sudah ada dan lengkap akan dilewati,
jadi kalau koneksi putus di tengah jalan cukup jalankan ulang perintah yang
sama — yang sudah selesai tidak ditarik dua kali.

Pakai:
    python tarik_semua.py                  seluruh komoditas yang belum ada
    python tarik_semua.py bawang kentang   hanya komoditas tertentu
    python tarik_semua.py --daftar         lihat kunci komoditas yang dikenali
"""

import sys
import time
from pathlib import Path

import pandas as pd

AWAL, AKHIR = "2025-08-01", "2026-08-22"
HERE = Path(__file__).parent

# Kunci yang dipakai tarik_rentang(). Dipakai bila modul tidak
# mengekspos daftarnya sendiri.
CADANGAN = ["beras", "jagung", "bawang", "cabai_besar", "cabai_rawit", "kentang"]


def berkas(kom: str) -> Path:
    return HERE / f"jatim_{kom}_setahun.csv"


def daftar_komoditas() -> list:
    """Ambil daftar kunci dari modul penarik bila ada, kalau tidak pakai cadangan."""
    try:
        import hitung_keterisian as hk
    except Exception:
        return CADANGAN
    for nama in ("KOMODITAS", "PETA_KOMODITAS", "KOM", "ID_KOMODITAS"):
        obj = getattr(hk, nama, None)
        if isinstance(obj, dict) and obj:
            return list(obj.keys())
        if isinstance(obj, (list, tuple)) and obj:
            return list(obj)
    return CADANGAN


def ringkas(p: Path) -> str:
    """Satu baris ringkasan mutu berkas yang baru ditarik."""
    try:
        d = pd.read_csv(p)
        d["harga"] = pd.to_numeric(d.harga, errors="coerce")
        ada = d.harga.gt(0).fillna(False)
        kunci = d.kabkota.astype(str) + "|" + d.pasar.astype(str)
        piv = (d[ada].assign(_k=kunci[ada])
               .pivot_table(index="tanggal", columns="_k", values="harga", aggfunc="mean")
               .sort_index())
        sah = (piv.notna() & piv.shift().notna()).iloc[1:]
        laju = (piv.diff().iloc[1:].ne(0) & sah).values.sum() / max(sah.values.sum(), 1)
        return (f"{len(d):,} baris · {d.tanggal.nunique()} hari · "
                f"{d.kabkota.nunique()} kab · keterisian {ada.mean():.4f} · "
                f"laju {laju:.4f}")
    except Exception as e:
        return f"tidak terbaca ({e})"


def lengkap(p: Path) -> bool:
    """Berkas dianggap selesai bila harinya mendekati rentang yang diminta."""
    if not p.exists():
        return False
    try:
        n = pd.read_csv(p, usecols=["tanggal"]).tanggal.nunique()
        return n > 350
    except Exception:
        return False


def main() -> int:
    arg = [a for a in sys.argv[1:] if not a.startswith("--")]
    semua = daftar_komoditas()

    if "--daftar" in sys.argv:
        print("Kunci komoditas yang dikenali:")
        for k in semua:
            tanda = "sudah ada" if lengkap(berkas(k)) else "belum"
            print(f"  {k:14s} {tanda}")
        return 0

    try:
        from hitung_keterisian import tarik_rentang
    except Exception as e:
        print("Tidak bisa mengimpor tarik_rentang dari hitung_keterisian.py:", e)
        print("Jalankan skrip ini dari folder aplikasi.")
        return 1

    target = arg or semua
    tidak_dikenal = [k for k in target if k not in semua]
    if tidak_dikenal:
        print("Kunci tidak dikenali:", tidak_dikenal)
        print("Yang dikenali:", semua)
        return 1

    antre = [k for k in target if not lengkap(berkas(k))]
    lewat = [k for k in target if k not in antre]

    for k in lewat:
        print(f"[LEWAT ] {k:14s} {ringkas(berkas(k))}")
    if not antre:
        print("\nSemua komoditas sudah tertarik.")
    else:
        print(f"\nAkan menarik {len(antre)} komoditas: {', '.join(antre)}")
        print(f"Rentang {AWAL} s.d. {AKHIR}, sekitar 53 permintaan per komoditas.")
        print("Bisa ditinggal. Kalau putus di tengah, jalankan ulang perintah yang sama.\n")

    for k in antre:
        p = berkas(k)
        mulai = time.time()
        print(f"[TARIK ] {k} ...", flush=True)
        try:
            d = tarik_rentang(AWAL, AKHIR, k)
        except Exception as e:
            print(f"[GAGAL ] {k:14s} {type(e).__name__}: {e}")
            print("          Komoditas lain tetap dilanjutkan.")
            continue
        if d is None or not len(d):
            print(f"[KOSONG] {k:14s} tidak ada baris yang kembali")
            continue
        d.to_csv(p, index=False)
        print(f"[SIMPAN] {k:14s} {ringkas(p)}  ({time.time()-mulai:.0f} detik)")

    # Skema kab_harga.csv yang lama diperlukan untuk membentuk versi aslinya.
    lama = HERE / "kab_harga.csv"
    print("\n--- SKEMA kab_harga.csv YANG SEKARANG ---")
    if lama.exists():
        d = pd.read_csv(lama)
        print("baris:", f"{len(d):,}")
        print("kolom:", list(d.columns))
        print(d.head(3).to_string(index=False))
        for c in d.columns:
            if d[c].dtype == object and d[c].nunique() <= 12:
                print(f"nilai {c}: {sorted(d[c].dropna().unique().tolist())}")
    else:
        print("kab_harga.csv tidak ada di folder ini.")

    print("\nSalin seluruh keluaran di atas dan kirimkan.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
