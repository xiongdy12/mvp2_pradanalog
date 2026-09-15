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

Berkas pendamping: auth.py, data_kabupaten.py, kab_profil.csv, kab_harga.csv,
kab_rute.csv (dibangun optimasi_kabupaten.py)
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
    for nama in ("kab_profil.csv", "kab_harga.csv", "kab_rute.csv", "kab_batas.geojson"):
        p = Path(__file__).parent / nama
        sidik.append((nama, p.stat().st_mtime_ns, p.stat().st_size) if p.exists()
                     else (nama, 0, 0))
    return tuple(sidik)


@st.cache_data(show_spinner="Memuat data kabupaten...")
def _muat_cached(sidik):
    return muat()


def _muat():
    return _muat_cached(_sidik_berkas())


# ============================================================ rute distribusi
def _batasi_rute(rute, sesi):
    """
    Rute tidak punya kolom kabkota, sehingga batasi() akan mengembalikan tabel
    kosong untuk akun kabupaten. Akun kabupaten melihat rute yang menyentuh
    wilayahnya sendiri, baik sebagai asal maupun tujuan.
    """
    if not len(rute):
        return rute
    if sesi["peran"] == "kabupaten":
        kab = sesi.get("kabkota")
        return rute[(rute.asal == kab) | (rute.tujuan == kab)]
    return batasi(rute, sesi)


def _muat_batas():
    """kab_batas.geojson: batas kabupaten/kota (properti provinsi, kabkota, lat, lon)."""
    import json
    from pathlib import Path
    p = Path(__file__).parent / "kab_batas.geojson"
    if not p.exists():
        return None
    sidik = (p.stat().st_mtime_ns, p.stat().st_size)
    return _muat_batas_cached(str(p), sidik)


@st.cache_data(show_spinner=False)
def _muat_batas_cached(jalur, sidik):
    import json
    with open(jalur, encoding="utf-8") as f:
        return json.load(f)


def _warna_isi(nilai, batas):
    """Skala isi poligon: pekat mengikuti besaran, dengan lantai agar tetap terbaca."""
    if batas <= 0 or abs(nilai) < 1e-9:
        return [95, 100, 108, 150]
    t = min(abs(nilai) / batas, 1.0) ** 0.5
    if nilai > 0:
        return [int(30 + 16 * t), int(110 + 94 * t), int(70 + 43 * t), int(110 + 120 * t)]
    return [int(150 + 81 * t), int(60 + 16 * t), int(55 + 5 * t), int(110 + 120 * t)]


def _deck_kabupaten(batas, profil, rel, kom, kom_label, sorot, lingkup_kab=None):
    """
    Peta berbatas wilayah, mengikuti gaya Peta Distribusi provinsi: poligon
    diwarnai neraca komoditas, klik satu wilayah untuk memunculkan busur
    kirim/terimanya. Tanpa pilihan, tidak ada busur yang digambar.
    """
    import copy
    nilai = profil.set_index("kabkota")[kom].to_dict()
    maks = max((abs(v) for v in nilai.values()), default=1.0) or 1.0
    geo = copy.deepcopy(batas)
    pos = {}
    for ft in geo["features"]:
        pr = ft["properties"]
        k = pr["kabkota"]
        pos[k] = (pr["lon"], pr["lat"])
        if k in nilai:
            v = nilai[k]
            status = "Surplus" if v > 0 else ("Defisit" if v < 0 else "Seimbang")
            pr["fill_color"] = _warna_isi(v, maks)
            pr["judul"] = k
            pr["isi"] = f"{kom_label}: {status} {abs(v):,.0f} ton<br/><i>klik untuk rute</i>"
        else:
            # Di luar lingkup akun: bentuk wilayah tetap tampil, neracanya tidak.
            pr["fill_color"] = [70, 76, 84, 90]
            pr["judul"] = k
            pr["isi"] = "di luar lingkup akun"

    layers = [pdk.Layer(
        "GeoJsonLayer", data=geo, id="kab-layer", pickable=True, stroked=True,
        filled=True, auto_highlight=True, get_fill_color="properties.fill_color",
        get_line_color=[210, 220, 225, 120], line_width_min_pixels=0.8,
        highlight_color=[255, 255, 255, 70])]

    if sorot:
        ft = next((f for f in geo["features"] if f["properties"]["kabkota"] == sorot), None)
        if ft:
            fc = {"type": "FeatureCollection", "features": [ft]}
            layers.append(pdk.Layer("GeoJsonLayer", data=fc, id="kab-glow-luar",
                                    stroked=True, filled=False, pickable=False,
                                    get_line_color=[255, 215, 0, 90], line_width_min_pixels=7))
            layers.append(pdk.Layer("GeoJsonLayer", data=fc, id="kab-glow-dalam",
                                    stroked=True, filled=False, pickable=False,
                                    get_line_color=[255, 240, 150], line_width_min_pixels=2))

    if sorot and len(rel):
        d = rel.copy()
        d["asal_lon"] = d.asal.map(lambda k: pos.get(k, (None, None))[0])
        d["asal_lat"] = d.asal.map(lambda k: pos.get(k, (None, None))[1])
        d["tuj_lon"] = d.tujuan.map(lambda k: pos.get(k, (None, None))[0])
        d["tuj_lat"] = d.tujuan.map(lambda k: pos.get(k, (None, None))[1])
        d = d.dropna(subset=["asal_lon", "tuj_lon"])
        vmax = max(float(d.volume_ton.max()), 1.0)
        d["width"] = (d.volume_ton / vmax) ** 0.5
        d["judul"] = d.asal + " → " + d.tujuan
        d["isi"] = d.apply(lambda r: f"{r.volume_ton:,.0f} ton · Rp {r.biaya_rp:,.1f} jt · "
                                     f"{r.jarak_km:,.0f} km", axis=1)
        layers.append(pdk.Layer(
            "ArcLayer", data=d, id="kab-busur",
            get_source_position=["asal_lon", "asal_lat"],
            get_target_position=["tuj_lon", "tuj_lat"],
            get_source_color=[80, 230, 150, 235], get_target_color=[245, 90, 75, 245],
            get_width="width", width_units="pixels", width_scale=8,
            width_min_pixels=2.5, width_max_pixels=9, get_height=0.5,
            pickable=True, auto_highlight=True))
        mitra = [k for k in set(d.asal) | set(d.tujuan) if k != sorot]
        titik = pd.DataFrame([{"lon": pos[k][0], "lat": pos[k][1],
                               "warna": [245, 90, 75] if k in set(d.tujuan) else [80, 230, 150],
                               "judul": k, "isi": "mitra rute"} for k in mitra])
        titik = pd.concat([titik, pd.DataFrame([{
            "lon": pos[sorot][0], "lat": pos[sorot][1], "warna": [255, 225, 120],
            "judul": sorot, "isi": "wilayah dipilih"}])], ignore_index=True)
        layers.append(pdk.Layer(
            "ScatterplotLayer", data=titik, id="kab-titik", get_position=["lon", "lat"],
            get_fill_color="warna", get_radius=2500, radius_min_pixels=4,
            radius_max_pixels=8, stroked=True, get_line_color=[255, 255, 255],
            line_width_min_pixels=1, pickable=False))

    return pdk.Deck(
        layers=layers, map_provider="carto", map_style="dark",
        initial_view_state=pdk.ViewState(latitude=-7.62, longitude=112.75,
                                         zoom=7.15, pitch=0),
        tooltip={"html": "<b>{judul}</b><br/>{isi}",
                 "style": {"backgroundColor": "#15181d", "color": "white",
                           "border": "1px solid #444", "borderRadius": "6px"}})


def _tabel_rute(df, kolom_wilayah, judul, df_to_html):
    d = (df[[kolom_wilayah, "volume_ton", "jarak_km", "biaya_rp"]]
         .sort_values("volume_ton", ascending=False)
         .rename(columns={kolom_wilayah: judul, "volume_ton": "Ton",
                          "jarak_km": "Jarak (km)", "biaya_rp": "Biaya (jt)"}))
    d["Ton"] = d["Ton"].map(lambda v: f"{v:,.0f}")
    d["Jarak (km)"] = d["Jarak (km)"].map(lambda v: f"{v:,.0f}")
    d["Biaya (jt)"] = d["Biaya (jt)"].map(lambda v: f"{v:,.1f}")
    return df_to_html(d, right_cols=("Ton", "Jarak (km)", "Biaya (jt)"))


def _panel_ringkas(rk, profil, kom, kom_label, df_to_html):
    dfc = float(-profil.loc[profil[kom] < 0, kom].sum())
    ton, biaya = float(rk.volume_ton.sum()), float(rk.biaya_rp.sum())
    a, b = st.columns(2)
    a.metric("Rute distribusi", f"{len(rk)}")
    b.metric("Pemenuhan defisit", f"{ton / dfc * 100:.0f}%" if dfc else "–")
    c, d = st.columns(2)
    c.metric("Total kirim", f"{ton:,.0f} t")
    d.metric("Biaya logistik", f"Rp {biaya:,.0f} jt",
             delta=f"Rp {biaya * 1e6 / ton:,.0f}/ton" if ton else None, delta_color="off")

    t1, t2 = st.tabs(["🚚 Rute terbesar", "📉 Defisit terdalam"])
    with t1:
        top = rk.nlargest(min(10, len(rk)), "volume_ton").assign(
            Rute=lambda x: x.asal.str.replace("Kabupaten ", "Kab. ") + " → "
            + x.tujuan.str.replace("Kabupaten ", "Kab. "))
        st.markdown(_tabel_rute(top, "Rute", "Rute", df_to_html), unsafe_allow_html=True)
    with t2:
        terima = rk.groupby("tujuan").volume_ton.sum()
        defisit = profil[profil[kom] < 0].nsmallest(min(8, int((profil[kom] < 0).sum())), kom)
        tb = pd.DataFrame({
            "Wilayah": defisit.kabkota,
            "Defisit (t)": defisit[kom].abs().map(lambda v: f"{v:,.0f}"),
            "Diterima (t)": defisit.kabkota.map(terima).fillna(0).map(lambda v: f"{v:,.0f}"),
        })
        st.markdown(df_to_html(tb, right_cols=("Defisit (t)", "Diterima (t)")),
                    unsafe_allow_html=True)
    st.caption("Klik satu wilayah di peta untuk memunculkan rute kirim dan terimanya.")


def _panel_wilayah(rk, profil, sorot, kom, kom_label, df_to_html):
    keluar, masuk = rk[rk.asal == sorot], rk[rk.tujuan == sorot]
    baris = profil[profil.kabkota == sorot]
    nilai = float(baris[kom].iloc[0]) if len(baris) else 0.0
    st.markdown(f"##### {sorot}")
    a, b = st.columns(2)
    a.metric(kom_label, f"{nilai:,.0f} t",
             delta="Surplus" if nilai > 0 else ("Defisit" if nilai < 0 else "Seimbang"),
             delta_color="normal" if nilai > 0 else ("inverse" if nilai < 0 else "off"))
    b.metric("Biaya rute", f"Rp {keluar.biaya_rp.sum() + masuk.biaya_rp.sum():,.1f} jt")
    c, d = st.columns(2)
    c.metric("Kirim", f"{keluar.volume_ton.sum():,.0f} t")
    d.metric("Terima", f"{masuk.volume_ton.sum():,.0f} t")

    if nilai < 0:
        terp = masuk.volume_ton.sum() / -nilai * 100
        asal_utama = masuk.nlargest(1, "volume_ton").asal.iloc[0] if len(masuk) else "–"
        st.info(f"**{sorot}** defisit {-nilai:,.0f} t {kom_label}; solusi mengirim "
                f"{masuk.volume_ton.sum():,.0f} t ({terp:.0f}% kebutuhan) dari "
                f"{len(masuk)} wilayah, terbesar dari **{asal_utama}**.")
    elif nilai > 0 and len(keluar):
        st.info(f"**{sorot}** surplus {nilai:,.0f} t; {keluar.volume_ton.sum() / nilai * 100:.0f}% "
                f"dialirkan ke {len(keluar)} wilayah defisit. Sisanya dapat diposisikan "
                "sebagai cadangan penyangga atau pasokan antarprovinsi.")
    elif nilai > 0:
        st.info(f"**{sorot}** surplus namun tidak dipilih sebagai pemasok pada solusi ini: "
                "wilayah surplus lain lebih dekat atau lebih murah ke titik defisit.")

    t1, t2 = st.tabs(["📤 Kirim", "📥 Terima"])
    with t1:
        if len(keluar):
            st.markdown(_tabel_rute(keluar, "tujuan", "Tujuan", df_to_html), unsafe_allow_html=True)
        else:
            st.caption("Tidak ada rute keluar.")
    with t2:
        if len(masuk):
            st.markdown(_tabel_rute(masuk, "asal", "Asal", df_to_html), unsafe_allow_html=True)
        else:
            st.caption("Tidak ada rute masuk.")


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
    ada_rute = set(rute.komoditas) if len(rute) else set()
    rute = _batasi_rute(rute, sesi)

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

    # ------------------------------------------------- peta + rute distribusi
    st.divider()
    batas = _muat_batas()
    if batas is None:
        st.error("kab_batas.geojson tidak ditemukan, peta batas wilayah tidak dapat digambar.")
        return
    rk = rute[rute.komoditas == kom] if len(rute) else rute

    KOSONG = "— klik wilayah di peta —"
    if sesi["peran"] == "kabupaten":
        sorot = sesi.get("kabkota")
    else:
        # Klik peta disimpan dulu, lalu dipasang ke kotak pilihan sebelum kotak
        # itu dibuat ulang — Streamlit melarang mengubah nilai widget setelah
        # widget dirender pada putaran yang sama.
        if st.session_state.get("kab_pending"):
            st.session_state["kab_pick"] = st.session_state.pop("kab_pending")
        opsi = [KOSONG] + sorted(profil.kabkota)
        if st.session_state.get("kab_pick") not in opsi:
            st.session_state["kab_pick"] = KOSONG
        sorot = st.selectbox("Pilih kabupaten/kota (atau klik di peta)", opsi, key="kab_pick")
        sorot = None if sorot in (None, KOSONG) else sorot
    rel = rk[(rk.asal == sorot) | (rk.tujuan == sorot)] if (sorot and len(rk)) else rk.iloc[0:0]

    kiri, kanan = st.columns([1.75, 1] if sorot else [1.9, 1], gap="small")
    with kiri:
        st.markdown(f"##### Distribusi {kom_label} antarkabupaten/kota")
        deck = _deck_kabupaten(batas, profil, rel, kom, kom_label, sorot)
        diklik = None
        try:
            ev = st.pydeck_chart(deck, use_container_width=True, height=520,
                                 on_select="rerun", selection_mode="single-object",
                                 key="kab_map")
            objs = (ev.selection.get("objects", {})
                    if ev is not None and getattr(ev, "selection", None) else {})
            item = (objs or {}).get("kab-layer") or []
            if item:
                o = item[0]
                diklik = o.get("kabkota") or o.get("properties", {}).get("kabkota")
        except TypeError:
            st.pydeck_chart(deck, use_container_width=True)
        if sesi["peran"] != "kabupaten":
            sebelum = st.session_state.get("kab_last_sel", "__awal__")
            if diklik != sebelum:
                st.session_state["kab_last_sel"] = diklik
                if diklik and diklik in set(profil.kabkota) and diklik != sorot:
                    st.session_state["kab_pending"] = diklik
                    st.rerun()
        st.markdown(
            f"**Legenda ({kom_label}):** <span style='color:#2ecc71'>hijau</span>=surplus · "
            "<span style='color:#e74c3c'>merah</span>=defisit · pekat=besar · "
            "busur hijau→merah=arah aliran · <span style='color:#ffd700'>garis emas</span>"
            "=wilayah dipilih.", unsafe_allow_html=True)

    with kanan:
        if not len(rk):
            if kom in ada_rute:
                st.info(f"**{sorot}** tidak terlibat rute {kom_label} pada solusi ini.")
            elif not ada_rute:
                st.info("Rute kabupaten belum dibangun. Jalankan "
                        "`python optimasi_kabupaten.py` untuk membuat kab_rute.csv.")
            else:
                st.info(f"Tidak ada rute {kom_label}: tidak ada pasangan wilayah "
                        "surplus dan defisit pada komoditas ini.")
        elif sorot is None:
            with st.container(border=True):
                _panel_ringkas(rk, profil, kom, kom_label, df_to_html)
        else:
            with st.container(border=True):
                _panel_wilayah(rk, profil, sorot, kom, kom_label, df_to_html)

    if len(rk):
        st.caption("**Batas model:** jarak garis lurus antartitik pusat poligon wilayah "
                   "(belum jarak jalan); tarif per ton-km mewarisi fungsi biaya lapisan "
                   "nasional yang masih asumtif; surplus yang dialokasikan ke provinsi lain "
                   "belum dikurangkan. Biaya dibaca sebagai perbandingan antar-rute, bukan "
                   "anggaran. Batas wilayah: skema RBI Badan Informasi Geospasial, "
                   "disederhanakan untuk tampilan.")

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
