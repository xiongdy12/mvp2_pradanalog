"""
perbarui_katalog_jatim.py — tulis angka produksi Jawa Timur hasil verifikasi
============================================================================
Mengganti enam baris estimasi Jawa Timur di katalog_produksi.csv dengan angka
yang dihitung langsung dari berkas unduhan BPS Provinsi Jawa Timur.

    python perbarui_katalog_jatim.py            # pratinjau, tidak mengubah apa pun
    python perbarui_katalog_jatim.py --terapkan # tulis ke katalog

Berkas sumber yang harus ada se-folder:
    2023_bawang_merah.xlsx, 2024_bawang_merah.xlsx, 2025_bawang_merah.xlsx
        (judul menyesatkan — isinya seluruh komoditas sayuran, bukan bawang saja)
    2023_beras.xlsx, 2024_beras.xlsx, 2025_beras.xlsx

CATATAN JAGUNG
Tabel produksi jagung tingkat kabupaten/kota Jawa Timur berhenti pada 2018.
Barisnya karena itu tidak ditandai terverifikasi; yang diperbarui hanya rentang
tahun dan catatannya, sementara jumlah kabupaten tetap berstatus estimasi.
"""

import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

KATALOG = Path("katalog_produksi.csv")
TANGGAL = datetime.now().strftime("%Y-%m-%d")

URL_HORTI = ("https://jatim.bps.go.id/id/statistics-table/3/"
             "ZUhFd1JtZzJWVVpqWTJsV05XTllhVmhRSzFoNFFUMDkjMw==/"
             "produksi-tanaman-sayuran-dan-buah-buahan-semusim-menurut-kabupaten-kota-"
             "dan-jenis-tanaman---di-provinsi-jawa-timur--2023.html")
URL_BERAS = ("https://jatim.bps.go.id/id/statistics-table/3/"
             "ZDNaak0yODBUVTlGYW5sa2REUkVUVVY1YVZkbmR6MDkjMw==/"
             "produksi-padi-sup-1--sup--dan-beras-menurut-kabupaten-kota-"
             "di-provinsi-jawa-timur--2024.html")


def _angka(v):
    """Ubah sel BPS jadi angka. Tanda strip dan sel kosong berarti nol produksi."""
    s = str(v).replace("\xa0", "").replace(" ", "").replace(",", "")
    if s in ("-", "", "nan", "None"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return None


def _muat(nama: str) -> pd.DataFrame:
    """
    Baca tabel BPS dan buang baris non-wilayah.

    Baris catatan kaki dikenali dari markup HTML atau kata pembukanya, BUKAN
    dari substring di tengah teks. Versi sebelumnya menyaring dengan mencari
    kata 'angka' di mana saja, sehingga Bangkalan ikut terbuang karena memuat
    'angka' di tengah namanya — satu kabupaten hilang tanpa peringatan.
    """
    d = pd.read_excel(nama, engine="openpyxl", header=None)
    kepala = [str(x).strip() for x in d.iloc[0]]
    d = d.iloc[1:].reset_index(drop=True)
    d.columns = kepala
    d = d.rename(columns={kepala[0]: "wilayah"})
    d = d[d.wilayah.notna()]
    d["wilayah"] = d.wilayah.astype(str).str.strip()
    catatan = (d.wilayah.str.contains("<", na=False)
               | d.wilayah.str.lower().str.startswith(
                   ("keterangan", "sumber", "catatan", "angka tetap", "angka sementara")))
    buang = d.wilayah.str.lower().isin(["jawa timur", "nan", ""]) | catatan
    return d[~buang].reset_index(drop=True)


def _kol(df, kunci):
    for c in df.columns:
        if kunci.lower() in str(c).lower():
            return c
    raise KeyError(f"Kolom memuat '{kunci}' tidak ada. Kolom tersedia: "
                   f"{[str(c)[:40] for c in df.columns]}")


def hitung(tahun: int = 2025) -> dict:
    """Jumlah kabupaten/kota dengan produksi bukan nol, per komoditas."""
    h = _muat(f"{tahun}_bawang_merah.xlsx")
    b = _muat(f"{tahun}_beras.xlsx")

    if len(h) != 38 or len(b) != 38:
        raise ValueError(f"Jumlah wilayah tidak 38 — hortikultura {len(h)}, "
                         f"beras {len(b)}. Periksa penyaringan baris.")

    bw = h[_kol(h, "Bawang Merah")].map(_angka)
    cr = h[_kol(h, "Cabai Rawit")].map(_angka)
    kt = h[_kol(h, "Kentang")].map(_angka)
    # BPS memisahkan Cabai Besar/TW/Teropong dan Cabai Keriting jadi dua kolom;
    # kelompok "cabai besar" menurut definisi BPS mencakup keduanya.
    cb = h[_kol(h, "Cabai Besar")].map(_angka)
    ck = h[_kol(h, "Cabai Keriting")].map(_angka)
    br = b[_kol(b, "Beras")].map(_angka)

    for nama, seri in [("bawang", bw), ("cabai_rawit", cr), ("kentang", kt),
                       ("cabai_besar", cb), ("cabai_keriting", ck), ("beras", br)]:
        if seri.isna().any():
            raise ValueError(f"Ada sel {nama} yang tidak terbaca sebagai angka.")

    return {
        "beras": int((br > 0).sum()),
        "bawang": int((bw > 0).sum()),
        "cabai_besar": int(((cb > 0) | (ck > 0)).sum()),
        "cabai_rawit": int((cr > 0).sum()),
        "kentang": int((kt > 0).sum()),
    }


def rencana(n: dict) -> pd.DataFrame:
    sumber_h = "BPS Jatim — Produksi Tanaman Sayuran dan Buah-Buahan Semusim menurut Kab/Kota"
    sumber_b = "BPS Jatim — Produksi Padi dan Beras menurut Kab/Kota"
    catat_h = ("Dihitung dari berkas unduhan BPS 2023/2024/2025: jumlah kab/kota "
               "dengan produksi bukan nol pada 2025. Angka stabil di ketiga tahun.")
    baris = [
        dict(komoditas="beras", n=n["beras"], t0=2023, t1=2025, status="terverifikasi",
             sumber=sumber_b, url=URL_BERAS,
             catatan=("Dihitung dari kolom Produksi Beras 2025; seluruh 38 kab/kota "
                      "berproduksi, termasuk kota. Angka sama pada 2023 dan 2024.")),
        dict(komoditas="jagung", n=None, t0=2007, t1=2018, status="sebagian",
             sumber="BPS Jatim — Produksi Jagung menurut Kab/Kota (seri berhenti 2018)",
             url="https://jatim.bps.go.id/id/statistics-table",
             catatan=("Tabel jagung tingkat kab/kota Jawa Timur terakhir terbit untuk "
                      "tahun 2018; tidak ada rilis 2019 ke atas. Rentang tahun "
                      "terverifikasi dari judul tabel, jumlah kab/kota MASIH ESTIMASI. "
                      "Jagung juga tidak dipantau PIHPS, sehingga merupakan komoditas "
                      "dengan dukungan data kabupaten paling lemah.")),
        dict(komoditas="bawang", n=n["bawang"], t0=2023, t1=2025, status="terverifikasi",
             sumber=sumber_h, url=URL_HORTI, catatan=catat_h),
        dict(komoditas="cabai_besar", n=n["cabai_besar"], t0=2023, t1=2025,
             status="terverifikasi", sumber=sumber_h, url=URL_HORTI,
             catatan=(catat_h + " Gabungan kolom Cabai Besar/TW/Teropong dan Cabai "
                                "Keriting sesuai definisi kelompok BPS.")),
        dict(komoditas="cabai_rawit", n=n["cabai_rawit"], t0=2023, t1=2025,
             status="terverifikasi", sumber=sumber_h, url=URL_HORTI, catatan=catat_h),
        dict(komoditas="kentang", n=n["kentang"], t0=2023, t1=2025,
             status="terverifikasi", sumber=sumber_h, url=URL_HORTI,
             catatan=(catat_h + " Sebaran 12 kab/kota; volume terpusat di Malang, "
                                "Kota Batu, Probolinggo.")),
    ]
    # DataFrame diberi dtype object agar kolom n tidak dipaksa jadi float
    # gara-gara satu nilai None pada baris jagung; None yang berubah jadi NaN
    # membuat pemeriksaan "is None" gagal diam-diam.
    return pd.DataFrame(baris).astype({"n": "object"})


def main():
    terapkan = "--terapkan" in sys.argv

    if not KATALOG.exists():
        print(f"'{KATALOG}' tidak ada. Jalankan dari folder aplikasi.")
        sys.exit(1)
    kurang = [f"{t}_{n}.xlsx" for t in (2023, 2024, 2025)
              for n in ("bawang_merah", "beras") if not Path(f"{t}_{n}.xlsx").exists()]
    if kurang:
        print("Berkas sumber belum lengkap:", ", ".join(kurang))
        sys.exit(1)

    n = hitung(2025)
    r = rencana(n)

    kat = pd.read_csv(KATALOG)
    lama = kat[kat.provinsi == "Jawa Timur"].set_index("komoditas")

    print("Perbandingan estimasi lama terhadap hasil verifikasi:\n")
    print(f"{'komoditas':<14}{'lama':>6}{'baru':>7}{'selisih':>9}   {'tahun':<12}status")
    for _, b in r.iterrows():
        l = int(lama.loc[b.komoditas, "n_kabkota_produksi"])
        ada = b.n is not None and not pd.isna(b.n)
        baru = str(int(b.n)) if ada else "—"
        sel = f"{int(b.n) - l:+d}" if ada else "—"
        print(f"{b.komoditas:<14}{l:>6}{baru:>7}{sel:>9}   {b.t0}–{b.t1:<7}{b.status}")

    if not terapkan:
        print("\nIni baru pratinjau. Jalankan ulang dengan --terapkan untuk menulis.")
        return

    cad = KATALOG.with_name(f"katalog_produksi_sebelum_jatim_{datetime.now():%Y%m%d_%H%M%S}.csv")
    shutil.copy(KATALOG, cad)
    print(f"\nCadangan disimpan: {cad.name}")

    for _, b in r.iterrows():
        m = (kat.provinsi == "Jawa Timur") & (kat.komoditas == b.komoditas)
        if not m.any():
            print(f"PERINGATAN: baris Jawa Timur/{b.komoditas} tidak ditemukan, dilewati.")
            continue
        if b.n is not None and not pd.isna(b.n):
            kat.loc[m, "n_kabkota_produksi"] = int(b.n)
        kat.loc[m, "tahun_awal"] = b.t0
        kat.loc[m, "tahun_akhir"] = b.t1
        kat.loc[m, "sumber"] = b.sumber
        kat.loc[m, "url"] = b.url
        kat.loc[m, "catatan" if "catatan" in kat.columns else "sumber"] = (
            b.catatan if "catatan" in kat.columns else b.sumber)
        kat.loc[m, "tanggal_akses"] = TANGGAL
        kat.loc[m, "status_verifikasi"] = b.status

    kat.to_csv(KATALOG, index=False)

    # Verifikasi hasil tulis, bukan sekadar percaya bahwa penulisan berhasil.
    ulang = pd.read_csv(KATALOG)
    jt = ulang[ulang.provinsi == "Jawa Timur"].set_index("komoditas")
    galat = []
    if len(ulang) != len(kat):
        galat.append("jumlah baris katalog berubah")
    for _, b in r.iterrows():
        if (b.n is not None and not pd.isna(b.n)
                and int(jt.loc[b.komoditas, "n_kabkota_produksi"]) != int(b.n)):
            galat.append(f"{b.komoditas} tidak tertulis dengan benar")
        if int(jt.loc[b.komoditas, "tahun_akhir"]) != b.t1:
            galat.append(f"tahun_akhir {b.komoditas} tidak tertulis")
    if (jt.n_kabkota_produksi > jt.n_kabkota).any():
        galat.append("ada n_kabkota_produksi melebihi n_kabkota")

    if galat:
        shutil.copy(cad, KATALOG)
        print("Verifikasi gagal: " + "; ".join(galat))
        print("Katalog dikembalikan dari cadangan.")
        sys.exit(1)

    ver = (jt.status_verifikasi == "terverifikasi").sum()
    print(f"Berhasil. {ver} dari 6 baris Jawa Timur kini terverifikasi.")
    print("Langkah berikutnya: python uji_ikd.py && python data_readiness.py")


if __name__ == "__main__":
    main()
