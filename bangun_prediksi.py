"""
bangun_prediksi.py — membentuk prediksi_harga.csv menurut aturan_metode.csv
============================================================================
prediksi_harga.csv yang sekarang dibangkitkan terpisah dan tidak pernah
membaca aturan_metode.csv. Akibatnya Bawang Merah h=2 tetap memakai naif
padahal aturan menetapkan campuran (MASE 0,896). Modul ini menutup celah itu.

Peramalan memakai _ramal() dari backtest_harga.py, bukan salinannya, sehingga
angka yang ditampilkan di dasbor dijamin berasal dari fungsi yang sama dengan
yang diukur di backtest.

Pita lo/hi dihitung dari galat empiris backtest pada kuantil 15 dan 85 persen,
sesuai keterangan yang sudah tertulis di caption_akurasi().

Pakai:
    python bangun_prediksi.py            uji coba, tidak menulis apa pun
    python bangun_prediksi.py --tulis    menulis setelah keluaran benar
"""

import shutil
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
TULIS = "--tulis" in sys.argv
Q_LO, Q_HI = 0.15, 0.85
AMBANG_MASE = 0.95

try:
    from backtest_harga import _ramal, backtest, ringkas, siapkan
except Exception as e:  # pragma: no cover
    print("Tidak bisa mengimpor backtest_harga.py:", e)
    sys.exit(1)


def cari_panel() -> Path:
    """Panel bulanan provinsi yang dipakai backtest."""
    for nama in ("harga_bulanan_panel.csv", "panel_harga_bulanan.csv"):
        if (HERE / nama).exists():
            return HERE / nama
    calon = [p for p in HERE.glob("*.csv")
             if "panel" in p.name.lower() or "bulanan" in p.name.lower()]
    return calon[0] if len(calon) == 1 else None


def periksa_kosakata(aturan: pd.DataFrame, lama: pd.DataFrame) -> dict:
    """
    Samakan kosakata metode antara aturan (Indonesia) dan berkas prediksi
    (Inggris). Kosakata berkas lama dipertahankan supaya kode tab tidak
    perlu disentuh.
    """
    dari_aturan = sorted(aturan.metode_dipakai.astype(str).unique())
    dari_lama = sorted(lama.metode.astype(str).unique()) if lama is not None else []
    baku = {"naif": "naive", "campuran": "blend",
            "musiman": "seasonal", "hanyut": "drift"}
    peta = {k: v for k, v in baku.items() if v in dari_lama} if dari_lama else \
           {k: k for k in dari_aturan}
    for k in dari_aturan:
        peta.setdefault(k, baku.get(k, k))
    print(f"kosakata aturan  : {dari_aturan}")
    print(f"kosakata prediksi: {dari_lama if dari_lama else '(berkas lama tidak ada)'}")
    print(f"pemetaan dipakai : {peta}")
    return peta


def lacak_kosakata() -> None:
    """
    Cari modul mana yang menyebut nama metode, untuk memastikan tidak ada
    pembanding yang tersandung perbedaan istilah.
    """
    kata = ["campuran", "blend", "naif", "naive"]
    print("\n--- SEBUTAN NAMA METODE DI MODUL ---")
    for p in sorted(HERE.glob("*.py")):
        if p.name in ("bangun_prediksi.py", "intip_prediksi.py"):
            continue
        try:
            teks = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        ada = {k: teks.count(f'"{k}"') + teks.count(f"'{k}'") for k in kata}
        ada = {k: v for k, v in ada.items() if v}
        if ada:
            campur = ("campuran" in ada or "naif" in ada) and \
                     ("blend" in ada or "naive" in ada)
            tanda = "   <-- memakai KEDUA kosakata" if campur else ""
            print(f"  {p.name:28s} {ada}{tanda}")


def pita(hasil: pd.DataFrame, aturan: pd.DataFrame) -> pd.DataFrame:
    """
    Kuantil galat relatif dari titik uji backtest, per komoditas per horizon,
    dihitung pada metode yang benar-benar dipakai.
    """
    h = hasil.copy()
    h["galat_rel"] = (h.ramal - h.benar) / h.benar
    pilih = aturan.set_index(["komoditas", "h"]).metode_dipakai.to_dict()
    baris = []
    for (kom, hz), g in h.groupby(["komoditas", "h"]):
        m = pilih.get((kom, hz), "naif")
        gg = g[g.metode == m]
        gg = gg if len(gg) >= 20 else g[g.metode == "naif"]
        if not len(gg):
            continue
        baris.append({"komoditas": kom, "h": hz,
                      "q_lo": float(gg.galat_rel.quantile(Q_LO)),
                      "q_hi": float(gg.galat_rel.quantile(Q_HI)),
                      "n": len(gg)})
    return pd.DataFrame(baris)


def main() -> int:
    aturan_p = HERE / "aturan_metode.csv"
    lama_p = HERE / "prediksi_harga.csv"
    if not aturan_p.exists():
        print("aturan_metode.csv tidak ada. Jalankan backtest_harga.py dulu.")
        return 1

    aturan = pd.read_csv(aturan_p)
    lama = pd.read_csv(lama_p) if lama_p.exists() else None
    print(f"aturan_metode.csv : {len(aturan)} baris, "
          f"{aturan.komoditas.nunique()} komoditas x {aturan.h.nunique()} horizon")

    panel_p = cari_panel()
    if panel_p is None:
        print("Panel bulanan tidak ketemu. Sebutkan namanya:")
        for p in sorted(HERE.glob("*.csv")):
            print("   ", p.name)
        return 1
    print(f"panel             : {panel_p.name}")

    panel = pd.read_csv(panel_p)
    d, kunci, kom, wkt, hrg = siapkan(panel)
    print(f"                    {len(d):,} baris · {d[kom].nunique()} komoditas · "
          f"{d[kunci[0]].nunique() if len(kunci) > 1 else 1} wilayah")
    print(f"                    {d[wkt].min():%Y-%m} s.d. {d[wkt].max():%Y-%m}")

    peta_metode = periksa_kosakata(aturan, lama)
    lacak_kosakata()

    print("\n--- BACKTEST ULANG UNTUK PITA KETIDAKPASTIAN ---")
    hasil = backtest(panel)
    r = ringkas(hasil)
    print(f"titik uji         : {len(hasil):,}")

    # Aturan di berkas harus cocok dengan backtest saat ini; kalau tidak,
    # berkas aturan sudah usang dan diprediksi dengan metode yang salah.
    bukan_naif = r[r.metode != "naif"]
    idx = bukan_naif.groupby(["komoditas", "h"]).mase.idxmin()
    kini = bukan_naif.loc[idx, ["komoditas", "h", "metode", "mase"]].copy()
    kini["metode_kini"] = np.where(kini.mase < AMBANG_MASE, kini.metode, "naif")
    cek = aturan.merge(kini[["komoditas", "h", "metode_kini"]],
                       on=["komoditas", "h"], how="left")
    beda = cek[cek.metode_dipakai != cek.metode_kini]
    if len(beda):
        print("PERINGATAN — aturan_metode.csv berbeda dari backtest saat ini:")
        print(beda[["komoditas", "h", "metode_dipakai", "metode_kini"]].to_string(index=False))
        print("Jalankan ulang backtest_harga.py sebelum melanjutkan.")
        return 1
    print("aturan cocok dengan backtest saat ini.")

    q = pita(hasil, aturan)

    # --- pembangkitan ramalan dari ujung deret ---
    pilih = aturan.set_index(["komoditas", "h"]).metode_dipakai.to_dict()
    qmap = q.set_index(["komoditas", "h"])[["q_lo", "q_hi"]].to_dict("index")
    grp_wilayah = kunci[0] if len(kunci) > 1 else None

    # Jangkar: bulan terakhir yang ada di panel. Deret yang berhenti sebelum
    # jangkar tidak boleh diramal — ujungnya sudah basi, dan meramal h bulan
    # dari titik lama menghasilkan "prediksi" untuk bulan yang sudah lewat.
    jangkar = pd.Timestamp(d[wkt].max())
    print(f"\njangkar bulan     : {jangkar:%Y-%m} (bulan terakhir di panel)")

    baris, lewat, basi = [], [], []
    for kunci_nilai, g in d.groupby(kunci):
        komoditas = kunci_nilai[-1] if isinstance(kunci_nilai, tuple) else kunci_nilai
        wilayah = (kunci_nilai[0] if isinstance(kunci_nilai, tuple) and len(kunci_nilai) > 1
                   else "(semua)")
        seri = g.set_index(wkt)[hrg].sort_index()
        seri = seri[~seri.index.duplicated(keep="last")]
        if len(seri) < 14:
            lewat.append((wilayah, komoditas, len(seri)))
            continue
        if seri.index[-1] < jangkar:
            tertinggal = ((jangkar.year - seri.index[-1].year) * 12
                          + jangkar.month - seri.index[-1].month)
            basi.append((wilayah, komoditas, seri.index[-1].strftime("%Y-%m"), tertinggal))
            continue
        kini_nilai = float(seri.iloc[-1])
        for h in sorted(aturan.h.unique()):
            metode = pilih.get((komoditas, h))
            if metode is None:
                continue
            ramalan = _ramal(seri, h)
            nilai = ramalan.get(metode, np.nan)
            if nilai is None or (isinstance(nilai, float) and np.isnan(nilai)):
                metode, nilai = "naif", ramalan["naif"]
            kv = qmap.get((komoditas, h), {"q_lo": -0.05, "q_hi": 0.05})
            bulan = (seri.index[-1] + pd.DateOffset(months=h)).strftime("%Y-%m")
            baris.append({
                "provinsi": wilayah, "komoditas": komoditas, "bulan": bulan, "h": h,
                "harga_prediksi": round(float(nilai)),
                "lo": round(float(nilai) * (1 - kv["q_hi"])),
                "hi": round(float(nilai) * (1 - kv["q_lo"])),
                "harga_kini": round(kini_nilai),
                "metode": peta_metode.get(metode, metode),
            })
    hasil_df = pd.DataFrame(baris)

    if lewat:
        print(f"\nDeret terlalu pendek, dilewati: {len(lewat)} pasangan")
        for w, k, n in lewat[:5]:
            print(f"  {w} · {k} · {n} bulan")

    if basi:
        print(f"\nDeret basi, dilewati: {len(basi)} pasangan "
              f"(berhenti sebelum {jangkar:%Y-%m})")
        for w, k, akhir, n in sorted(basi, key=lambda x: -x[3])[:10]:
            print(f"  {w} · {k} · berhenti {akhir} · tertinggal {n} bulan")
        print("  Daftar ini layak masuk dokumen sebagai keterbatasan cakupan data.")

    bulan_hasil = sorted(hasil_df.bulan.unique())
    if len(bulan_hasil) != len(set(hasil_df.h.unique())):
        print(f"\nPERINGATAN — bulan hasil tidak seragam: {bulan_hasil}")
        print("Seharusnya tepat satu bulan per horizon. Jangan menulis.")
        return 1

    print("\n--- HASIL ---")
    print(f"baris        : {len(hasil_df):,}"
          + (f"   (lama {len(lama):,})" if lama is not None else ""))
    print(f"kolom        : {list(hasil_df.columns)}")
    print(f"wilayah      : {hasil_df.provinsi.nunique()} · "
          f"komoditas {hasil_df.komoditas.nunique()} · bulan "
          f"{sorted(hasil_df.bulan.unique())}")
    print("\nMetode terpakai per komoditas dan horizon:")
    tab = (hasil_df.groupby(["komoditas", "h"]).metode
           .agg(lambda s: s.value_counts().to_dict()).reset_index())
    print(tab.to_string(index=False))

    if lama is not None:
        gab = hasil_df.merge(lama[["provinsi", "komoditas", "h", "metode"]],
                             on=["provinsi", "komoditas", "h"],
                             how="inner", suffixes=("_baru", "_lama"))
        ubah = gab[gab.metode_baru != gab.metode_lama]
        print(f"\nBaris yang metodenya berubah: {len(ubah):,} dari {len(gab):,}")
        if len(ubah):
            print(ubah.groupby(["komoditas", "h", "metode_lama", "metode_baru"])
                  .size().rename("baris").reset_index().to_string(index=False))

    print("\nLebar pita relatif (q15..q85 galat backtest):")
    print(q.assign(lebar=lambda x: (x.q_hi - x.q_lo).round(3))
          [["komoditas", "h", "lebar", "n"]].to_string(index=False))

    if not TULIS:
        print("\nUJI COBA — tidak ada berkas yang ditulis.")
        print("Bila benar, jalankan:  python bangun_prediksi.py --tulis")
        return 0

    if lama_p.exists():
        cad = HERE / f"prediksi_harga_lama_{datetime.now():%Y%m%d_%H%M}.csv"
        shutil.copy2(lama_p, cad)
        print(f"\nSalinan versi lama: {cad.name}")
    hasil_df.to_csv(lama_p, index=False, encoding="utf-8")
    print(f"prediksi_harga.csv ditulis: {len(hasil_df):,} baris")
    print("\nMatikan Streamlit sepenuhnya lalu nyalakan ulang.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
