"""
hitung_neraca_jatim.py — isi kab_profil.csv dengan neraca pangan sesungguhnya
=============================================================================
Menghitung surplus/defisit lima komoditas untuk 38 kabupaten/kota Jawa Timur:

    S/D = produksi - (penduduk x konsumsi per kapita)

Positif berarti surplus, negatif berarti defisit — perjanjian yang sama dengan
model MOLP pada tingkat provinsi.

    python hitung_neraca_jatim.py            # pratinjau
    python hitung_neraca_jatim.py --terapkan # tulis ke kab_profil.csv

Berkas sumber yang harus ada se-folder:
    2025_bawang_merah.xlsx   (isinya seluruh komoditas sayuran)
    2025_beras.xlsx
    penduduk_jatim.xlsx      (Jumlah Penduduk menurut Kabupaten/Kota, BPS Jatim)
    PradanaLog_Dataset_Konsumsi.xlsx

TIGA ASUMSI YANG HARUS DISEBUT DI METODOLOGI

1. Konsumsi per kapita hanya tersedia pada tingkat NASIONAL. Satu angka yang
   sama diterapkan ke 38 kabupaten, artinya Kota Surabaya dan Kabupaten Pacitan
   diperlakukan memiliki pola konsumsi identik. Ini asumsi terbesar dalam
   perhitungan ini.

2. Konsumsi bawang merah 2025 memakai angka 2024. Nilai 2025 turun 88 persen
   dari 2,85 ke 0,33 kg/kapita/tahun — anomali yang sudah ditandai sendiri pada
   catatan dataset konsumsi. Memakainya akan membuat hampir seluruh kabupaten
   tampak surplus.

3. Konsumsi kentang memakai estimasi Kementerian Pertanian 0,3 kg/kapita/tahun
   karena Susenas tidak menyediakan angka spesifik.

CATATAN SATUAN
Produksi hortikultura BPS dalam KUINTAL, beras dalam TON. Kolom penduduk BPS
berjudul "Jumlah Penduduk (Ribu)" tetapi isinya jiwa penuh — Pacitan tertulis
589.357, bukan 589. Judul kolom tidak dipercaya; besaran nilainya yang diperiksa.
"""

import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

KOM = ["beras", "bawang", "cabai_besar", "cabai_rawit", "kentang"]
TAHUN = 2025
TANGGAL = datetime.now().strftime("%Y-%m-%d")

# kg per kapita per tahun. Sumber: PradanaLog_Dataset_Konsumsi.xlsx,
# lembar Konsumsi_per_Kapita_Nasional.
KONSUMSI = {
    "beras": 78.5089,        # 2025
    "bawang": 2.8536,        # 2024 — 2025 anomali (0,3315)
    "cabai_besar": 0.1870,   # 2025
    "cabai_rawit": 0.1987,   # 2025
    "kentang": 0.3000,       # estimasi Kementan, tetap sepanjang tahun
}
SUMBER_KONSUMSI = {
    "beras": "Susenas 2025", "bawang": "Susenas 2024 (2025 anomali)",
    "cabai_besar": "Susenas 2025", "cabai_rawit": "Susenas 2025",
    "kentang": "estimasi Kementan",
}


def _angka(v):
    s = str(v).replace("\xa0", "").replace(" ", "").replace(",", "")
    if s in ("-", "", "nan", "None"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return None


def _bersih(d: pd.DataFrame) -> pd.DataFrame:
    """Buang baris total, kosong, dan catatan kaki tanpa menyentuh nama wilayah."""
    d = d[d.wilayah.notna()].copy()
    d["wilayah"] = d.wilayah.astype(str).str.strip()
    catatan = (d.wilayah.str.contains("<", na=False)
               | d.wilayah.str.lower().str.startswith(
                   ("keterangan", "sumber", "catatan", "metadata", "indikator",
                    "angka tetap", "angka sementara", "jumlah penduduk",
                    "laju pertumbuhan", "kepadatan", "rasio jenis"))
               | d.wilayah.str.match(r"^\d", na=False))
    return d[~(d.wilayah.str.lower().isin(["jawa timur", "nan", ""]) | catatan)].reset_index(drop=True)


def _muat(nama: str) -> pd.DataFrame:
    d = pd.read_excel(nama, engine="openpyxl", header=None)
    kepala = [str(x).strip() for x in d.iloc[0]]
    d = d.iloc[1:].reset_index(drop=True)
    d.columns = kepala
    return _bersih(d.rename(columns={kepala[0]: "wilayah"}))


def _kol(df, kunci):
    for c in df.columns:
        if kunci.lower() in str(c).lower():
            return c
    raise KeyError(f"Kolom '{kunci}' tidak ada di {[str(c)[:35] for c in df.columns]}")


def muat_penduduk() -> pd.Series:
    d = _muat("penduduk_jatim.xlsx")
    kol = _kol(d, "Jumlah Penduduk")
    v = d[kol].map(_angka)
    if v.isna().any():
        raise ValueError("Ada nilai penduduk yang tidak terbaca sebagai angka.")
    # Judul kolom BPS menyebut "Ribu" tetapi isinya jiwa penuh. Satuan ditentukan
    # dari besaran nilainya, bukan dari judulnya.
    if v.median() < 10_000:
        v = v * 1000
        print("  catatan: nilai penduduk dikali 1.000 karena tampak dalam satuan ribu.")

    hasil = pd.Series(v.values, index=d.wilayah)

    # Silang-periksa terhadap kolom persentase. Berkas BPS 2026 memuat galat
    # ketik pada Kota Malang: tertulis 88.682 jiwa sementara persentasenya 2,09
    # yang setara 885.157 jiwa — satu digit hilang. Tanpa pemeriksaan ini,
    # Kota Malang akan tampak surplus beras padahal defisit besar.
    kol_pct = None
    for c in d.columns:
        if "persentase" in str(c).lower():
            kol_pct = c
            break
    if kol_pct is not None:
        pct = d[kol_pct].map(_angka)
        total = float(hasil.sum())
        if pct.notna().all() and pct.sum() > 90:
            tersirat = pct.values / 100.0 * total / (pct.sum() / 100.0)
            rasio = hasil.values / tersirat
            for w, r, nilai, sirat in zip(hasil.index, rasio, hasil.values, tersirat):
                if r < 0.5 or r > 2.0:
                    print(f"  KOREKSI: {w} tertulis {nilai:,.0f} jiwa, sedangkan "
                          f"kolom persentase menyiratkan {sirat:,.0f}. Nilai "
                          f"persentase yang dipakai — periksa berkas BPS.")
                    hasil[w] = round(sirat)
    return hasil


def muat_produksi() -> pd.DataFrame:
    h = _muat(f"{TAHUN}_bawang_merah.xlsx")
    b = _muat(f"{TAHUN}_beras.xlsx")
    if len(h) != 38 or len(b) != 38:
        raise ValueError(f"Jumlah wilayah tidak 38 — hortikultura {len(h)}, beras {len(b)}.")

    # Hortikultura BPS dalam kuintal; 1 ton = 10 kuintal.
    ke_ton = 0.1
    out = pd.DataFrame(index=h.wilayah)
    out["bawang"] = h[_kol(h, "Bawang Merah")].map(_angka).values * ke_ton
    out["cabai_rawit"] = h[_kol(h, "Cabai Rawit")].map(_angka).values * ke_ton
    out["kentang"] = h[_kol(h, "Kentang")].map(_angka).values * ke_ton
    cb = h[_kol(h, "Cabai Besar")].map(_angka).values
    ck = h[_kol(h, "Cabai Keriting")].map(_angka).values
    out["cabai_besar"] = (cb + ck) * ke_ton
    out["beras"] = b.set_index("wilayah")[_kol(b, "Beras")].map(_angka).reindex(out.index).values
    if out.isna().any().any():
        raise ValueError("Ada nilai produksi yang tidak terbaca.")
    return out


def hitung() -> pd.DataFrame:
    prod = muat_produksi()
    pend = muat_penduduk()

    hilang = set(prod.index) ^ set(pend.index)
    if hilang:
        raise ValueError(f"Nama wilayah tidak cocok antara produksi dan penduduk: "
                         f"{sorted(hilang)}")

    d = pd.DataFrame(index=prod.index)
    d["penduduk"] = pend.reindex(prod.index).astype(int)
    for k in KOM:
        konsumsi_ton = d.penduduk * KONSUMSI[k] / 1000.0   # kg -> ton
        d[k] = (prod[k] - konsumsi_ton).round(0).astype(int)
    return d


def ringkas(d: pd.DataFrame):
    print(f"\n{'Komoditas':<14}{'Defisit':>9}{'Surplus':>9}{'Neraca (ton)':>15}")
    for k in KOM:
        print(f"{k:<14}{int((d[k] < 0).sum()):>9}{int((d[k] > 0).sum()):>9}{d[k].sum():>15,.0f}")

    print("\nLima wilayah defisit beras terdalam:")
    for w, v in d.nsmallest(5, "beras").beras.items():
        print(f"  {w:<22}{v:>12,.0f} ton")
    print("\nLima wilayah surplus beras terbesar:")
    for w, v in d.nlargest(5, "beras").beras.items():
        print(f"  {w:<22}{v:>12,.0f} ton")


def main():
    terapkan = "--terapkan" in sys.argv

    wajib = [f"{TAHUN}_bawang_merah.xlsx", f"{TAHUN}_beras.xlsx",
             "penduduk_jatim.xlsx", "PradanaLog_Dataset_Konsumsi.xlsx"]
    kurang = [f for f in wajib if not Path(f).exists()]
    if kurang:
        print("Berkas sumber belum lengkap:", ", ".join(kurang))
        sys.exit(1)

    d = hitung()
    print(f"Neraca pangan {len(d)} kabupaten/kota Jawa Timur, tahun {TAHUN}")
    print(f"Total penduduk: {d.penduduk.sum():,} jiwa")
    ringkas(d)

    if not terapkan:
        print("\nIni baru pratinjau. Jalankan ulang dengan --terapkan untuk menulis "
              "ke kab_profil.csv.")
        return

    if not Path("kab_profil.csv").exists():
        print("kab_profil.csv tidak ada. Jalankan `python data_kabupaten.py` dulu.")
        sys.exit(1)

    cad = Path(f"kab_profil_sebelum_neraca_{datetime.now():%Y%m%d_%H%M%S}.csv")
    shutil.copy("kab_profil.csv", cad)
    print(f"\nCadangan disimpan: {cad.name}")

    prof = pd.read_csv("kab_profil.csv")
    # kab_profil memakai nama lengkap ("Kabupaten Malang"); tabel BPS memakai
    # nama pendek ("Malang"). Pemetaan lewat akhiran nama, bukan urutan baris.
    def cocok(nama_panjang):
        n = nama_panjang.replace("Kabupaten ", "").replace("Kota ", "").strip()
        kota = nama_panjang.startswith("Kota")
        for w in d.index:
            wk = w.startswith("Kota")
            wn = w.replace("Kota ", "").strip()
            if wn.lower() == n.lower() and wk == kota:
                return w
        return None

    tak_cocok = []
    for i, r in prof.iterrows():
        w = cocok(r.kabkota)
        if w is None:
            tak_cocok.append(r.kabkota)
            continue
        prof.loc[i, "penduduk"] = int(d.loc[w, "penduduk"])
        for k in KOM:
            prof.loc[i, k] = int(d.loc[w, k])
        prof.loc[i, "sumber"] = (f"BPS Jatim {TAHUN}: produksi kab/kota, penduduk kab/kota; "
                                 f"konsumsi per kapita nasional Susenas")
        prof.loc[i, "tanggal_akses"] = TANGGAL
        prof.loc[i, "status_verifikasi"] = "terverifikasi"

    if tak_cocok:
        shutil.copy(cad, "kab_profil.csv")
        print("Nama wilayah tidak cocok:", ", ".join(tak_cocok))
        print("Berkas dikembalikan dari cadangan.")
        sys.exit(1)

    # Jagung tidak dapat dihitung: data produksi kab/kota berhenti 2018.
    if "jagung" in prof.columns:
        prof["jagung"] = 0
        print("  catatan: kolom jagung diisi nol — data produksi kab/kota berhenti 2018.")

    prof.to_csv("kab_profil.csv", index=False)

    ulang = pd.read_csv("kab_profil.csv")
    sisa = (ulang.status_verifikasi.astype(str).str.lower() == "contoh").sum()
    if sisa:
        shutil.copy(cad, "kab_profil.csv")
        print(f"Verifikasi gagal: masih ada {sisa} baris berstatus contoh.")
        sys.exit(1)

    print(f"Berhasil. {len(ulang)} baris kab_profil.csv kini terverifikasi.")
    print("Langkah berikutnya: streamlit run pradanalog_map.py — spanduk kuning "
          "pada tab Tinjauan Kabupaten akan hilang.")


if __name__ == "__main__":
    main()
