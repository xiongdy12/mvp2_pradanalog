"""
tab_kabupaten.py — drill-down kabupaten/kota untuk PradanaLog
==============================================================
Isi tab menyesuaikan peran akun yang masuk:

    pusat     — daftar provinsi, lalu masuk ke salah satunya
    provinsi  — peta seluruh kabupaten/kota di provinsinya
    kabupaten — profil wilayahnya sendiri saja

Pemasangan di pradanalog_map.py:

    from tab_kabupaten import render_tab_kabupaten          # bagian import

    tab_peta, tab_frontier, tab_harga, tab_dampak, tab_siap, tab_kab = st.tabs(
        ["🗺️ Peta Distribusi", "📈 Frontier Kebijakan", "🔮 Prediksi Harga",
         "🎯 Dampak & Roadmap", "🧭 Kesiapan Data", "🏛️ Tinjauan Kabupaten"])

    with tab_kab:
        render_tab_kabupaten(df_to_html)

Berkas pendamping: auth.py, data_kabupaten.py, kab_profil.csv, kab_harga.csv
"""

import pandas as pd
import pydeck as pdk
import streamlit as st

from auth import PERAN, batasi, bilah_sesi, gerbang_login
from data_kabupaten import (KOM, DataKabupatenTidakSah, muat, ringkas_status)

try:
    import altair as alt
    HAS_ALT = True
except Exception:
    HAS_ALT = False

LABEL = {"beras": "Beras", "jagung": "Jagung", "bawang": "Bawang Merah",
         "cabai_besar": "Cabai Besar", "cabai_rawit": "Cabai Rawit",
         "kentang": "Kentang"}
LABEL2KEY = {v: k for k, v in LABEL.items()}


def _tema(chart):
    return (chart.configure(background="transparent")
            .configure_view(strokeWidth=0)
            .configure_axis(labelColor="#C7D3D5", titleColor="#C7D3D5",
                            gridColor="rgba(255,255,255,0.08)",
                            domainColor="rgba(255,255,255,0.15)")
            .configure_legend(labelColor="#C7D3D5", titleColor="#C7D3D5"))


def _warna(nilai, batas):
    """Merah untuk defisit, hijau untuk surplus, pekat mengikuti besarnya."""
    if batas <= 0:
        return [120, 124, 130, 120]
    t = max(min(nilai / batas, 1.0), -1.0)
    if t > 0.02:
        return [46, 204, 113, 70 + int(150 * t)]
    if t < -0.02:
        return [231, 76, 60, 70 + int(150 * -t)]
    return [120, 124, 130, 110]


def _sidik_berkas() -> tuple:
    """
    Sidik jari isi folder data: nama, ukuran, dan waktu ubah tiap berkas.

    Dipakai sebagai kunci cache. Tanpa ini, @st.cache_data pada fungsi tanpa
    argumen menyimpan hasil selamanya — mengganti kab_profil.csv dengan data
    terverifikasi tidak akan terlihat sampai aplikasi dimatikan, dan spanduk
    tetap mengumumkan data contoh padahal berkasnya sudah berganti.
    """
    from pathlib import Path
    sidik = []
    for nama in ("kab_profil.csv", "kab_harga.csv", "kab_rute.csv"):
        p = Path(__file__).parent / nama
        sidik.append((nama, p.stat().st_mtime_ns, p.stat().st_size) if p.exists()
                     else (nama, 0, 0))
    return tuple(sidik)


@st.cache_data(show_spinner="Memuat data kabupaten...")
def _muat_cached(sidik):
    return muat()


def _muat():
    return _muat_cached(_sidik_berkas())


def render_tab_kabupaten(df_to_html):
    sesi = gerbang_login("Tinjauan Kabupaten/Kota — silakan masuk")
    if not sesi:
        return
    bilah_sesi(sesi)

    try:
        profil, harga, rute = _muat()
    except FileNotFoundError:
        st.error("Data kabupaten belum ada. Jalankan `python data_kabupaten.py` "
                 "untuk membuat data contoh, atau letakkan kab_profil.csv dan "
                 "kab_harga.csv di folder aplikasi.")
        return
    except DataKabupatenTidakSah as e:
        st.error("Data kabupaten tidak lolos pemeriksaan, jadi tidak ditampilkan.")
        st.code(str(e))
        return

    # Pembatasan lingkup dilakukan sekali di sini, sebelum apa pun ditampilkan.
    profil = batasi(profil, sesi)
    harga = batasi(harga, sesi)
    rute = batasi(rute, sesi) if len(rute) else rute

    if not len(profil):
        st.warning(f"Tidak ada data untuk lingkup akun ini "
                   f"({sesi.get('kabkota') or sesi.get('provinsi')}). "
                   "Periksa penulisan nama wilayah di kredensial dan di kab_profil.csv.")
        return

    status = ringkas_status(profil, harga, nama=["neraca", "harga"])
    r = status.get("rinci", {})
    neraca_contoh = r.get("neraca", {}).get("rasio", 0) > 0
    harga_contoh = r.get("harga", {}).get("rasio", 0) > 0

    # Dirinci per berkas: rasio gabungan didominasi kab_harga yang barisnya
    # ribuan, sehingga profil yang sudah terverifikasi ikut tertutup.
    if neraca_contoh and harga_contoh:
        st.warning("**Seluruh data pada tab ini masih berstatus contoh** — angka "
                   "dibangkitkan komputer, bukan hasil pengukuran. Bentuk dan alur "
                   "sistem sudah final; angkanya menunggu verifikasi. Jangan tangkap "
                   "layar bagian ini untuk paper.")
    elif neraca_contoh:
        st.warning("**Neraca surplus–defisit masih berstatus contoh.** Deret harga "
                   "sudah terverifikasi, tetapi angka produksi dan konsumsi belum.")
    elif harga_contoh:
        st.info("**Neraca surplus–defisit sudah terverifikasi** dari data BPS "
                "(produksi kabupaten, penduduk kabupaten, konsumsi per kapita "
                "Susenas) — peta dan tabel di bawah menampilkan angka sesungguhnya. "
                "Yang masih berstatus contoh hanya deret harga harian, sehingga "
                "grafik pergerakan harga belum dapat dikutip.")

    st.markdown(f"#### Tinjauan Kabupaten/Kota — {PERAN.get(sesi['peran'], '')}")
    lingkup = sesi.get("kabkota") or sesi.get("provinsi") or "Seluruh Indonesia"
    st.caption(f"Lingkup akses: {lingkup} · {len(profil)} wilayah")

    kom_label = st.selectbox("Komoditas", [LABEL[k] for k in KOM], index=0)
    kom = LABEL2KEY[kom_label]

    # ---------------------------------------------------------------- metrik
    nilai = profil[kom]
    defisit = profil[nilai < 0]
    surplus = profil[nilai > 0]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Wilayah defisit", f"{len(defisit)}", delta=f"dari {len(profil)}",
              delta_color="off")
    m2.metric("Total defisit", f"{abs(nilai[nilai < 0].sum()):,.0f} ton")
    m3.metric("Total surplus", f"{nilai[nilai > 0].sum():,.0f} ton")
    neraca = nilai.sum()
    m4.metric("Neraca wilayah", f"{neraca:,.0f} ton",
              delta="surplus" if neraca > 0 else "defisit",
              delta_color="normal" if neraca > 0 else "inverse")

    # ------------------------------------------------------------------ peta
    st.divider()
    kiri, kanan = st.columns([1.3, 1])
    with kiri:
        st.markdown(f"##### Sebaran surplus dan defisit {kom_label}")
        batas = float(nilai.abs().max()) or 1.0
        titik = profil.copy()
        titik["warna"] = titik[kom].map(lambda v: _warna(v, batas))
        titik["radius"] = titik[kom].abs().pow(0.5) * 60 + 2500
        titik["label"] = titik[kom].map(lambda v: f"{v:,.0f} ton")

        st.pydeck_chart(pdk.Deck(
            map_style=None,
            initial_view_state=pdk.ViewState(
                latitude=float(titik.lat.mean()), longitude=float(titik.lon.mean()),
                zoom=6.4 if len(titik) > 1 else 9, pitch=0),
            layers=[pdk.Layer("ScatterplotLayer", data=titik,
                              get_position="[lon, lat]", get_fill_color="warna",
                              get_radius="radius", pickable=True, opacity=0.85,
                              stroked=True, get_line_color=[255, 255, 255, 60],
                              line_width_min_pixels=1)],
            tooltip={"html": "<b>{kabkota}</b><br/>" + kom_label + ": {label}",
                     "style": {"backgroundColor": "#123840", "color": "#EDF4F1"}}))
        st.caption("Lingkaran merah menandai defisit, hijau surplus; luasnya "
                   "sebanding dengan besarnya. Titik pusat wilayah masih perkiraan "
                   "kasar — ganti dengan batas resmi BIG sebelum dipakai menghitung "
                   "jarak distribusi.")

    with kanan:
        st.markdown("##### Wilayah defisit terdalam")
        if len(defisit):
            tabel = (defisit.nsmallest(min(8, len(defisit)), kom)[["kabkota", kom, "penduduk"]]
                     .rename(columns={"kabkota": "Wilayah", kom: "Neraca (ton)",
                                      "penduduk": "Penduduk"}))
            tabel["Neraca (ton)"] = tabel["Neraca (ton)"].map(lambda v: f"{v:,.0f}")
            tabel["Penduduk"] = tabel["Penduduk"].map(lambda v: f"{v:,.0f}")
            st.markdown(df_to_html(tabel, right_cols=("Neraca (ton)", "Penduduk")),
                        unsafe_allow_html=True)
            st.caption("Urutan ini adalah calon prioritas alokasi. Gabungkan dengan "
                       "tren harga di bawah sebelum memutuskan operasi pasar.")
        else:
            st.info(f"Tidak ada wilayah defisit {kom_label} pada lingkup ini.")

    # ------------------------------------------------------------------ harga
    st.divider()
    st.markdown(f"##### Pergerakan harga {kom_label}")
    hk = harga[harga.komoditas == kom].copy()
    if not len(hk):
        st.info("Belum ada deret harga untuk komoditas ini.")
        return

    pilihan = sorted(hk.kabkota.unique())
    bawaan = pilihan[:3] if len(pilihan) > 3 else pilihan
    dipilih = st.multiselect("Bandingkan wilayah", pilihan, default=bawaan,
                             max_selections=6)
    if not dipilih:
        st.caption("Pilih minimal satu wilayah untuk menampilkan grafik.")
        return

    hp = hk[hk.kabkota.isin(dipilih)]
    if HAS_ALT:
        garis = alt.Chart(hp).mark_line(strokeWidth=2).encode(
            x=alt.X("tanggal:T", title=None),
            y=alt.Y("harga:Q", title="Harga (Rp/kg)", scale=alt.Scale(zero=False)),
            color=alt.Color("kabkota:N", title="Wilayah", scale=alt.Scale(
                range=["#3FCF87", "#E0C15A", "#5BC8E8", "#E8895B", "#B48BE0", "#9FB6BC"])),
            tooltip=["kabkota", "tanggal", alt.Tooltip("harga:Q", format=",.0f")])
        st.altair_chart(_tema(garis.properties(height=320)),
                        use_container_width=True, theme=None)
    else:
        st.line_chart(hp.pivot_table(index="tanggal", columns="kabkota", values="harga"))

    # ------------------------------------------------- disparitas antarwilayah
    akhir = hk[hk.tanggal == hk.tanggal.max()]
    if len(akhir) > 1:
        termurah, termahal = akhir.nsmallest(1, "harga"), akhir.nlargest(1, "harga")
        selisih = float(termahal.harga.iloc[0] - termurah.harga.iloc[0])
        rasio = selisih / float(termurah.harga.iloc[0]) * 100
        d1, d2, d3 = st.columns(3)
        d1.metric("Termurah", f"Rp {termurah.harga.iloc[0]:,.0f}",
                  delta=termurah.kabkota.iloc[0], delta_color="off")
        d2.metric("Termahal", f"Rp {termahal.harga.iloc[0]:,.0f}",
                  delta=termahal.kabkota.iloc[0], delta_color="off")
        d3.metric("Disparitas", f"{rasio:.1f}%", delta=f"Rp {selisih:,.0f}",
                  delta_color="off")
        st.caption("Disparitas harga antarwilayah dalam satu provinsi menandakan "
                   "hambatan distribusi, bukan kelangkaan produksi. Bandingkan dengan "
                   "peta di atas: kalau wilayah termahal ternyata bertetangga dengan "
                   "wilayah surplus, persoalannya ada di logistik.")

    # -------------------------------------------------------------- unduhan
    st.divider()
    u1, u2 = st.columns(2)

    # Nama berkas mengikuti cakupan data, bukan lingkup akses akun. Akun pusat
    # berlingkup seluruh Indonesia sedangkan datanya baru satu provinsi;
    # menamainya "Seluruh_Indonesia" menjanjikan isi yang tidak ada di dalamnya.
    if len(profil) == 1 and "kabkota" in profil.columns:
        cakupan = str(profil["kabkota"].iloc[0])
    elif "provinsi" in profil.columns and profil["provinsi"].nunique() == 1:
        cakupan = str(profil["provinsi"].iloc[0])
    elif "provinsi" in profil.columns and profil["provinsi"].nunique() > 1:
        cakupan = f"{profil['provinsi'].nunique()} provinsi"
    else:
        cakupan = "Jawa Timur"
    slug = cakupan.replace(" ", "_").replace("/", "_").replace("\\", "_")
    tanggal = pd.Timestamp.today().strftime("%Y-%m-%d")

    def _csv_berketerangan(d, judul):
        """CSV dengan tiga baris keterangan sumber di kepalanya."""
        kepala = (f"# PradanaLog - {judul} - {cakupan}, {len(profil)} wilayah\n"
                  f"# sumber: BPS Jawa Timur (neraca) dan SISKAPERBAPO (harga)\n"
                  f"# diunduh: {tanggal}\n")
        return (kepala + d.to_csv(index=False)).encode("utf-8")

    u1.download_button("\u2b07\ufe0f  Profil wilayah (CSV)",
                       _csv_berketerangan(profil, "profil wilayah"),
                       file_name=f"profil_{slug}.csv",
                       mime="text/csv", use_container_width=True)
    u2.download_button(f"\u2b07\ufe0f  Deret harga {kom_label} (CSV)",
                       _csv_berketerangan(hk, f"deret harga {kom_label}"),
                       file_name=f"harga_{kom}_{slug}.csv",
                       mime="text/csv", use_container_width=True)
    st.caption(f"Berkas memuat {len(profil)} wilayah dalam lingkup akun ini "
               f"({lingkup}). Tiga baris pertama berisi keterangan sumber; "
               f"baca dengan comment='#' bila diolah kembali dengan pandas.")
