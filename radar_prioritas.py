"""
radar_prioritas.py — menyinkronkan tampilan indeks prioritas dengan model
=========================================================================
Persamaan (3) pada model PradanaLog:

    pi_jk^t = max(0, P_hat_jk^{t+3} / P_jk^t - 1) . 1[D_jk^t > 0]

Ketika metode peramalan terpilih adalah persistensi, menurut definisi
P_hat^{t+3} = P^t, sehingga pi = max(0, 0) = 0 untuk SELURUH provinsi. Nilainya
bukan kecil melainkan nol identik, dan pengurutan prioritas menjadi tidak
terdefinisi.

Akibatnya terlihat langsung di layar: tabel Radar Provinsi Rawan Lonjakan
menampilkan kolom Perubahan bernilai +0,0% pada setiap baris. Pembaca yang tidak
tahu akan membacanya sebagai "harga stabil di mana-mana", padahal artinya
"tidak ada sinyal proyeksi untuk komoditas ini".

Modul ini menutup jarak antara model dan tampilan dengan satu aturan: indeks
prioritas hanya ditampilkan pada kombinasi komoditas x horizon yang metodenya
lolos ambang MASE. Selebihnya diberi keterangan eksplisit.

Pemasangan — ganti blok radar di pradanalog_map.py (sekitar baris 1241-1253):

    from radar_prioritas import render_radar
    render_radar(pred, kom_h, df_to_html, h=3)
"""

from pathlib import Path

import pandas as pd
import streamlit as st

HERE = Path(__file__).parent
AMBANG_MASE = 0.95

# Nama komoditas di aturan backtest vs di prediksi_harga.csv bisa berbeda ejaan.
SELARAS = {
    "bawang merah": "Bawang Merah", "beras": "Beras",
    "cabai besar": "Cabai Besar", "cabe merah besar": "Cabai Besar",
    "cabai rawit": "Cabai Rawit", "cabe rawit merah": "Cabai Rawit",
    "jagung": "Jagung", "kentang": "Kentang",
}


def _baku(nama) -> str:
    return SELARAS.get(str(nama).strip().lower(), str(nama).strip())


def _sidik(*nama) -> tuple:
    """Sidik jari berkas untuk kunci cache; lihat catatan di tab_kabupaten.py."""
    out = []
    for n in nama:
        f = HERE / n
        out.append((n, f.stat().st_mtime_ns, f.stat().st_size) if f.exists() else (n, 0, 0))
    return tuple(out)


@st.cache_data(show_spinner=False)
def _muat_aturan_cached(sidik, folder):
    return _baca_aturan(folder)


def muat_aturan(folder: str = None) -> pd.DataFrame:
    return _muat_aturan_cached(_sidik("aturan_metode.csv", "metrik_harga_backtest.csv"), folder)


def _baca_aturan(folder: str = None) -> pd.DataFrame:
    """
    Baca aturan metode hasil backtest. Dicoba berurutan:
    aturan_metode.csv, lalu metrik_harga_backtest.csv. Kembalikan DataFrame
    kosong bila keduanya tidak ada — dalam hal itu status sinyal ditentukan
    langsung dari datanya.
    """
    dasar = Path(folder) if folder else HERE

    p = dasar / "aturan_metode.csv"
    if p.exists():
        a = pd.read_csv(p)
        kol = "metode_dipakai" if "metode_dipakai" in a.columns else "metode"
        a = a.rename(columns={kol: "metode_dipakai"})
        a["komoditas"] = a.komoditas.map(_baku)
        return a[["komoditas", "h", "metode_dipakai", "mase"]]

    p = dasar / "metrik_harga_backtest.csv"
    if p.exists():
        r = pd.read_csv(p)
        bukan = r[(r.metode != "naif") & r.mase.notna()]
        if len(bukan):
            idx = bukan.groupby(["komoditas", "h"]).mase.idxmin()
            t = bukan.loc[idx, ["komoditas", "h", "metode", "mase"]].copy()
            t["metode_dipakai"] = t.apply(
                lambda x: x.metode if x.mase < AMBANG_MASE else "naif", axis=1)
            t["komoditas"] = t.komoditas.map(_baku)
            return t[["komoditas", "h", "metode_dipakai", "mase"]]

    return pd.DataFrame(columns=["komoditas", "h", "metode_dipakai", "mase"])


def status_sinyal(pred: pd.DataFrame, komoditas: str, h: int = 3,
                  aturan: pd.DataFrame = None) -> dict:
    """
    Tentukan apakah indeks prioritas membawa informasi untuk kombinasi ini.

    Dua lapis pemeriksaan. Lapis pertama memakai aturan hasil backtest bila
    tersedia. Lapis kedua memeriksa datanya langsung: bila seluruh proyeksi
    sama dengan harga kini, pi bernilai nol identik apa pun kata aturan.
    Lapis kedua dipertahankan supaya tampilan tetap benar meskipun berkas
    aturan hilang atau tertinggal versi lama.
    """
    aturan = muat_aturan() if aturan is None else aturan
    kom = _baku(komoditas)

    metode = mase = None
    if len(aturan):
        cocok = aturan[(aturan.komoditas == kom) & (aturan.h == h)]
        if len(cocok):
            metode = str(cocok.metode_dipakai.iloc[0])
            mase = float(cocok.mase.iloc[0])

    sub = pred[(pred.komoditas.map(_baku) == kom) & (pred.h == h)]
    datar = False
    if len(sub) and {"harga_prediksi", "harga_kini"} <= set(sub.columns):
        selisih = (sub.harga_prediksi - sub.harga_kini).abs()
        datar = bool((selisih < 1e-9).all())

    aturan_naif = metode is not None and metode.lower().startswith("na")

    # Tiga sebab berbeda yang sama-sama membuat pi bernilai nol. Membedakannya
    # penting karena tindak lanjutnya berbeda: yang pertama tidak perlu
    # diapa-apakan, yang kedua menandakan berkas prediksi tertinggal versi.
    if datar and aturan_naif:
        return {"ada_sinyal": False, "sebab": "aturan_naif", "metode": metode,
                "mase": mase,
                "alasan": "backtest memilih persistensi dan proyeksi memang "
                          "identik dengan harga kini"}

    if datar and not aturan_naif:
        # Aturan menyatakan ensemble unggul, tetapi berkas prediksi masih berisi
        # hasil persistensi. Artinya prediksi_harga.csv belum dibangkitkan ulang
        # memakai aturan hasil backtest terbaru.
        return {"ada_sinyal": False, "sebab": "prediksi_kedaluwarsa",
                "metode": metode, "mase": mase,
                "alasan": "proyeksi identik dengan harga kini padahal aturan "
                          "backtest menetapkan metode selain persistensi"}

    if aturan_naif:
        return {"ada_sinyal": True, "sebab": "aturan_naif_data_bervariasi",
                "metode": metode, "mase": mase,
                "alasan": "proyeksi bervariasi meskipun aturan memilih persistensi"}

    return {"ada_sinyal": True, "sebab": "normal", "metode": metode,
            "mase": mase, "alasan": ""}


def render_radar(pred: pd.DataFrame, komoditas: str, df_to_html, h: int = 3,
                 n_tampil: int = 8, aturan: pd.DataFrame = None):
    """
    Tampilkan radar prioritas, atau keterangan bila tidak ada sinyal.

    Parameter `aturan` disediakan agar pemanggil dapat menyuntikkan aturan
    tertentu; tanpa itu fungsi selalu membaca ulang dari disk dan pengujian
    terhadap keadaan buatan menjadi mustahil.
    """
    st.markdown(f"##### 🚨 Radar Provinsi Rawan Lonjakan (proyeksi {h} bulan)")

    s = status_sinyal(pred, komoditas, h, aturan)
    sub = pred[(pred.komoditas.map(_baku) == _baku(komoditas)) & (pred.h == h)].copy()

    if not len(sub):
        st.info(f"Belum ada proyeksi {h} bulan untuk {komoditas}.")
        return

    if not s["ada_sinyal"]:
        # Menampilkan tabel berisi +0,0% akan terbaca sebagai "harga stabil
        # di mana-mana", padahal artinya "tidak ada sinyal proyeksi".
        if s.get("sebab") == "prediksi_kedaluwarsa":
            pesan = (f"**Berkas proyeksi untuk {komoditas} belum diperbarui.** "
                     f"Backtest menetapkan metode {s['metode']} sebagai yang terbaik "
                     f"pada horizon {h} bulan")
            if s["mase"] is not None:
                pesan += f" dengan MASE {s['mase']:.3f}"
            pesan += (", namun isi prediksi_harga.csv masih identik dengan harga kini "
                      "— ciri keluaran persistensi. Berkas proyeksi karenanya belum "
                      "dibangkitkan ulang memakai aturan hasil backtest, sehingga "
                      "indeks prioritas π bernilai nol dan tidak dapat dipakai.")
            st.warning(pesan)
            st.caption("Perbaikan: bangkitkan ulang prediksi_harga.csv memakai aturan "
                       "pada aturan_metode.csv, lalu muat ulang halaman. Sampai itu "
                       "dilakukan, prioritas alokasi memakai objektif disparitas Z₂.")
            return

        pesan = (f"**Indeks prioritas tidak tersedia untuk {komoditas} pada horizon "
                 f"{h} bulan.** Backtest menetapkan persistensi sebagai metode "
                 f"terbaik, sehingga proyeksi sama dengan harga kini dan indeks "
                 f"prioritas π bernilai nol untuk seluruh provinsi menurut definisi "
                 f"— bukan karena harga diperkirakan stabil.")
        if s["mase"] is not None:
            pesan += (f" Alternatif terbaik mencapai MASE {s['mase']:.3f}; "
                      f"ambang penggunaan model adalah {AMBANG_MASE}.")
        st.info(pesan)
        st.caption("Prioritas alokasi untuk komoditas ini memakai disparitas harga "
                   "berjalan (objektif Z₂), bukan proyeksi kenaikan. Radar aktif pada "
                   "komoditas yang peramalannya terbukti mengungguli persistensi.")
        return

    sub["perubahan_pct"] = (sub.harga_prediksi / sub.harga_kini - 1) * 100
    naik = sub[sub.perubahan_pct > 0]

    # Dua keadaan yang sama-sama menghasilkan pi = 0 tetapi maknanya berlawanan:
    #   (a) metode persistensi  -> proyeksi tidak diketahui, ditangani di atas
    #   (b) seluruh proyeksi turun -> proyeksi diketahui dan menyatakan tidak ada
    #       risiko lonjakan
    # Keadaan (b) membawa informasi dan tidak boleh dibuang. Urutan provinsi
    # menurut penurunan terkecil tetap berguna sebagai daftar pantau, karena
    # merekalah yang paling dekat berbalik arah.
    turun_semua = not len(naik)
    top = sub.sort_values("perubahan_pct", ascending=False).head(n_tampil)

    if turun_semua:
        st.success(
            f"**Tidak ada provinsi yang diproyeksikan mengalami kenaikan harga "
            f"{komoditas} dalam {h} bulan.** Seluruh πⱼₖ bernilai nol karena "
            f"proyeksi menurun, bukan karena sinyal tidak tersedia — berbeda dengan "
            f"komoditas yang memakai persistensi. Alokasi dini tidak diperlukan; "
            f"daftar di bawah adalah provinsi dengan penurunan terkecil, yaitu yang "
            f"paling dekat berbalik arah bila terjadi guncangan pasok.")
    tt = top[["provinsi", "harga_kini", "harga_prediksi", "perubahan_pct"]].rename(
        columns={"provinsi": "Provinsi", "harga_kini": "Harga Kini (Rp)",
                 "harga_prediksi": f"Proyeksi +{h} bln (Rp)",
                 "perubahan_pct": "Perubahan (%)"})
    tt["Perubahan (%)"] = tt["Perubahan (%)"].round(1)
    st.markdown(df_to_html(tt, center_cols=("Harga Kini (Rp)", f"Proyeksi +{h} bln (Rp)",
                                            "Perubahan (%)"),
                           pct_cols=("Perubahan (%)",)), unsafe_allow_html=True)

    ket = (f"π = max(0, P̂⁽ᵗ⁺{h}⁾/Pᵗ − 1) pada provinsi defisit. "
           f"{len(naik)} dari {len(sub)} provinsi menunjukkan proyeksi kenaikan.")
    if turun_semua:
        ket = (f"Peringkat menurut proyeksi perubahan; seluruhnya negatif sehingga "
               f"π = 0 di semua provinsi. Prioritas MOLP untuk {komoditas} pada "
               f"periode ini ditentukan objektif disparitas Z₂, bukan indeks prioritas.")
    if s["mase"] is not None:
        ket += f" Metode {s['metode']}, MASE {s['mase']:.3f} terhadap persistensi."
    if s["mase"] is not None and not turun_semua:
        pass
    st.caption(ket + ("" if turun_semua
                      else " Kandidat prioritas alokasi MOLP dan operasi pasar dini."))
