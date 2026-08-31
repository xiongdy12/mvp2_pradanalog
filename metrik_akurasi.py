"""
metrik_akurasi.py — menampilkan MAPE bersama lantai dan MASE-nya
=================================================================
MAPE tidak dapat ditafsirkan sendirian. Nilai 1,2 persen pada beras terdengar
sangat baik sampai lantainya dihitung: peramal naif pada data yang sama
mencapai 0,79 persen. Angka yang ditampilkan sebagai akurasi ternyata lebih
buruk daripada tidak melakukan peramalan.

Persoalan kedua bersifat teknis namun berakibat sama: caption lama membaca
metrik_harga.csv dengan jendela Februari–Juni 2026 (lima bulan), sementara
radar prioritas di layar yang sama membaca backtest 24 bulan. Dua angka dari
dua jendela berbeda tampil berdampingan tanpa keterangan.

Modul ini menyatukan keduanya ke satu sumber — metrik_harga_backtest.csv —
dan selalu menampilkan MAPE bersama lantai naif serta MASE-nya.

Pemasangan di pradanalog_map.py, ganti blok baris 1208-1211:

    from metrik_akurasi import caption_akurasi
    caption_akurasi(kom_h, h=3)
"""

from pathlib import Path

import pandas as pd
import streamlit as st

HERE = Path(__file__).parent
AMBANG_MASE = 0.95

SELARAS = {
    "bawang merah": "Bawang Merah", "beras": "Beras",
    "cabai besar": "Cabai Besar", "cabe merah besar": "Cabai Besar",
    "cabai rawit": "Cabai Rawit", "cabe rawit merah": "Cabai Rawit",
    "jagung": "Jagung", "kentang": "Kentang",
}


def _baku(n) -> str:
    return SELARAS.get(str(n).strip().lower(), str(n).strip())


def _sidik(*nama) -> tuple:
    """Sidik jari berkas untuk kunci cache; lihat catatan di tab_kabupaten.py."""
    out = []
    for n in nama:
        f = HERE / n
        out.append((n, f.stat().st_mtime_ns, f.stat().st_size) if f.exists() else (n, 0, 0))
    return tuple(out)


@st.cache_data(show_spinner=False)
def _muat_metrik_cached(sidik, folder):
    return _baca_metrik(folder)


def muat_metrik(folder: str = None) -> pd.DataFrame:
    return _muat_metrik_cached(_sidik("metrik_harga_backtest.csv"), folder)


def _baca_metrik(folder: str = None) -> pd.DataFrame:
    """Baca hasil backtest rolling-origin. Kembalikan kosong bila belum ada."""
    p = (Path(folder) if folder else HERE) / "metrik_harga_backtest.csv"
    if not p.exists():
        return pd.DataFrame()
    r = pd.read_csv(p)
    r["komoditas"] = r.komoditas.map(_baku)
    return r


def ringkas_akurasi(komoditas: str, h: int = 3, metrik: pd.DataFrame = None) -> dict:
    """
    Kembalikan MAPE metode terpilih, MAPE peramal naif, MASE, dan metodenya.

    Metode terpilih ditentukan MASE terkecil di antara metode non-naif; bila
    tidak ada yang lolos ambang, naif yang dipakai dan MAPE yang dilaporkan
    adalah MAPE naif itu sendiri.
    """
    metrik = muat_metrik() if metrik is None else metrik
    if not len(metrik):
        return {}

    sub = metrik[(metrik.komoditas == _baku(komoditas)) & (metrik.h == h)]
    if not len(sub):
        return {}

    baris_naif = sub[sub.metode == "naif"]
    if not len(baris_naif):
        return {}
    mape_naif = float(baris_naif.mape.iloc[0])
    n = int(baris_naif.n.iloc[0]) if "n" in baris_naif.columns else None

    pesaing = sub[(sub.metode != "naif") & sub.mase.notna()]
    pesaing = pesaing[pesaing.mase.astype(float).abs() < float("inf")]
    if len(pesaing):
        terbaik = pesaing.loc[pesaing.mase.idxmin()]
        metode, mase, mape = str(terbaik.metode), float(terbaik.mase), float(terbaik.mape)
    else:
        metode, mase, mape = "naif", 1.0, mape_naif

    dipakai = metode if mase < AMBANG_MASE else "naif"
    # MASE kandidat terbaik disimpan terpisah dari MASE metode yang dipakai.
    # Ketika naif menang, MASE metode yang dipakai memang 1,000 menurut definisi,
    # tetapi angka yang informatif bagi pembaca adalah seberapa jauh pesaing
    # terbaik tertinggal — misalnya 1,346, bukan 1,000.
    mase_kandidat = mase
    if dipakai == "naif":
        mape, mase = mape_naif, 1.0

    return {"komoditas": _baku(komoditas), "h": h, "metode": dipakai,
            "mape": mape, "mape_naif": mape_naif, "mase": mase,
            "n": n, "kandidat_terbaik": metode, "mase_kandidat": mase_kandidat}


def caption_akurasi(komoditas: str, h: int = 3, n_titik_total: int = 33288):
    """
    Tampilkan satu baris keterangan akurasi yang lengkap.

    Selalu menyandingkan tiga angka — MAPE, lantai naif, dan MASE — karena satu
    angka MAPE sendirian tidak memberi tahu apakah model berguna.
    """
    r = ringkas_akurasi(komoditas, h)
    if not r:
        st.caption("Metrik backtest belum tersedia. Jalankan "
                   "`python backtest_harga.py harga_bulanan_panel.csv` untuk "
                   "menghasilkan metrik_harga_backtest.csv.")
        return

    if r["metode"] == "naif":
        putusan = (f"persistensi optimal — pesaing terbaik ({r['kandidat_terbaik']}) "
                   f"tertinggal pada MASE {r['mase_kandidat']:.3f}, di atas ambang "
                   f"{AMBANG_MASE}")
        mase_txt = "MASE **1,000** (acuan)"
    else:
        putusan = f"metode {r['metode']} mengungguli persistensi"
        mase_txt = f"MASE **{r['mase']:.3f}**"

    titik = f" · {r['n']:,} titik uji" if r.get("n") else ""
    st.caption(
        f"Backtest rolling-origin 24 bulan, horizon {h} bulan{titik} — "
        f"MAPE **{r['mape']:.2f}%** · lantai naif **{r['mape_naif']:.2f}%** · "
        f"{mase_txt} — {putusan}. "
        f"MAPE tidak ditafsirkan sendirian karena nilainya bergantung pada "
        f"gejolak komoditas; MASE di bawah 1 menandakan model menambah nilai. "
        f"Pita pada grafik = rentang ketidakpastian empiris (15–85%)."
    )


def tabel_akurasi(komoditas_list=None, h: int = 3, metrik: pd.DataFrame = None) -> pd.DataFrame:
    """Tabel ringkas seluruh komoditas untuk dokumentasi dan lampiran paper."""
    metrik = muat_metrik() if metrik is None else metrik
    if not len(metrik):
        return pd.DataFrame()
    komoditas_list = komoditas_list or sorted(metrik.komoditas.unique())
    baris = []
    for k in komoditas_list:
        r = ringkas_akurasi(k, h, metrik)
        if r:
            baris.append({"Komoditas": r["komoditas"], "Metode": r["metode"],
                          "MAPE (%)": round(r["mape"], 2),
                          "Lantai naif (%)": round(r["mape_naif"], 2),
                          "MASE": round(r["mase"], 3)})
    return pd.DataFrame(baris)
