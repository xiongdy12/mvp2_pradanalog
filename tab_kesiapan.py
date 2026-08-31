"""
tab_kesiapan.py — Tab "Kesiapan Data" untuk PradanaLog (v2)
============================================================
Pasang di pradanalog_map.py:

    from tab_kesiapan import render_tab_kesiapan            # bagian import

    tab_peta, tab_frontier, tab_harga, tab_dampak, tab_siap = st.tabs(
        ["🗺️ Peta Distribusi", "📈 Frontier Kebijakan", "🔮 Prediksi Harga",
         "🎯 Dampak & Roadmap", "🧭 Kesiapan Data"])                # ganti baris 1000

    with tab_siap:                                                 # di akhir file
        render_tab_kesiapan(df_to_html)

Berkas pendamping se-folder: katalog_produksi.csv, katalog_harga.csv,
katalog_wilayah.csv, data_readiness.py
"""

import pandas as pd
import streamlit as st

from data_readiness import (BOBOT, GATE_MIN_KOMODITAS, KatalogTidakSah, audit_trail,
                            compute_ikd, load_katalog, pindai_kerapuhan, sensitivity,
                            titik_balik)


@st.cache_data(show_spinner="Memindai kerapuhan parameter...")
def _pindai(prod, harga, wil):
    return pindai_kerapuhan((prod, harga, wil))

try:
    import altair as alt
    HAS_ALT = True
except Exception:
    HAS_ALT = False

LABEL_DIM = {
    "C_cakupan_spasial": "Cakupan spasial",
    "K_kelengkapan_komoditas": "Kelengkapan komoditas",
    "H_granularitas_harga": "Granularitas harga",
    "T_kedalaman_deret": "Kedalaman deret",
    "A_aktualitas": "Aktualitas",
    "G_geospasial_konektivitas": "Geospasial & konektivitas",
}
LABEL_KOM = {"beras": "Beras", "jagung": "Jagung", "bawang": "Bawang Merah",
             "cabai_besar": "Cabai Besar", "cabai_rawit": "Cabai Rawit",
             "kentang": "Kentang"}


def _teks(df, kolom, desimal=3):
    """
    Ubah kolom angka jadi teks sebelum diserahkan ke df_to_html.

    df_to_html milik PradanaLog memakai pct_cols untuk PERUBAHAN: nilai positif
    diwarnai merah karena kenaikan harga itu kabar buruk. Peluang bertahan di
    peringkat 1 sebesar 100% karenanya tampil merah bertanda +100,0% — hasil
    terbaik terlihat seperti peringatan. Fungsi itu juga memangkas angka ke dua
    desimal, padahal selisih IKD antarprovinsi bisa di bawah 0,01. Jadi angka
    diformat di sini, lalu dikirim sebagai teks biasa.
    """
    d = df.copy()
    for c in kolom:
        if c in d.columns:
            d[c] = d[c].map(lambda v: f"{v:.{desimal}f}" if pd.notna(v) else "—")
    return d


def _tema(chart):
    return (chart.configure(background="transparent")
            .configure_view(strokeWidth=0)
            .configure_axis(labelColor="#C7D3D5", titleColor="#C7D3D5",
                            gridColor="rgba(255,255,255,0.08)",
                            domainColor="rgba(255,255,255,0.15)")
            .configure_legend(labelColor="#C7D3D5", titleColor="#C7D3D5"))


def _sapuan_rinci(df_to_html, katalog, prov_uji, sistem_uji):
    with st.expander(f"Sapuan rinci satu parameter — keterisian {sistem_uji}"):
        tb = titik_balik(katalog, provinsi=prov_uji, sistem_key=sistem_uji.split("(")[0].strip())
        pindah = tb[tb.pemenang != tb.pemenang.iloc[0]]
        if HAS_ALT:
            line = alt.Chart(tb).mark_line(color="#3FCF87", point=alt.OverlayMarkDef(
                color="#0E262B", stroke="#3FCF87", strokeWidth=2, size=70)).encode(
                x=alt.X("keterisian:Q", title=f"Keterisian {sistem_uji}"),
                y=alt.Y("IKD_target:Q", title=f"IKD {prov_uji}", scale=alt.Scale(zero=False)),
                tooltip=["keterisian", "pemenang", "IKD_target"])
            lapisan = [line]
            if len(pindah):
                lapisan.append(alt.Chart(pd.DataFrame({"x": [float(pindah.keterisian.iloc[0])]}))
                               .mark_rule(strokeDash=[5, 4], color="#EAC65E", size=2)
                               .encode(x="x:Q"))
            st.altair_chart(_tema(alt.layer(*lapisan).properties(height=260)),
                            use_container_width=True, theme=None)
        tbt = _teks(tb, ["IKD_pemenang", "IKD_target"])
        tbt = _teks(tbt, ["keterisian"], desimal=2)
        tbt = tbt.rename(columns={"keterisian": "Keterisian", "pemenang": "Pemenang",
                                  "IKD_pemenang": "IKD pemenang",
                                  "IKD_target": f"IKD {prov_uji}"})
        st.markdown(df_to_html(tbt, center_cols=("Keterisian", "IKD pemenang",
                                                 f"IKD {prov_uji}")),
                    unsafe_allow_html=True)



def render_tab_kesiapan(df_to_html):
    st.markdown("#### Kesiapan Data: Dasar Kuantitatif Pemilihan Provinsi Pilot")
    st.caption("Enam dimensi kesiapan dinilai dari katalog per provinsi per komoditas, "
               "lalu peringkatnya diuji terhadap 4.000 kombinasi bobot acak. Setiap "
               "angka di katalog menyimpan sumber, URL, dan tanggal aksesnya.")

    try:
        katalog = load_katalog()
    except FileNotFoundError:
        st.error("Katalog belum ada. Jalankan `python bangun_katalog.py` lebih dulu.")
        return
    except KatalogTidakSah as e:
        st.error("Katalog tidak lolos pemeriksaan, jadi indeks tidak dihitung. "
                 "Memberi skor di atas data cacat lebih berbahaya daripada tidak "
                 "memberi skor sama sekali.")
        st.code(str(e))
        return

    prod, harga, wil = katalog
    skor = compute_ikd(katalog)
    sens = sensitivity(katalog)
    audit = audit_trail(katalog)

    juara, runner = skor.iloc[0], skor.iloc[1]
    p1 = float(sens.loc[sens.provinsi == juara.provinsi, "P_peringkat1"].iloc[0])

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Peringkat 1 saat ini", juara.provinsi)
    m2.metric("Indeks Kesiapan Data", f"{juara.IKD:.3f}",
              delta=f"+{juara.IKD - runner.IKD:.3f} vs {runner.provinsi}")
    m3.metric("Bertahan di uji bobot", f"{p1*100:.0f}%",
              help="Proporsi dari 4.000 kombinasi bobot Dirichlet yang tetap "
                   "menempatkan provinsi ini di puncak.")
    m4.metric("Katalog terverifikasi", f"{audit['rasio']*100:.0f}%",
              help="Baris estimasi bernilai 0, sebagian 0,5, terverifikasi 1.")

    st.divider()
    kiri, kanan = st.columns([1.15, 1])

    with kiri:
        st.markdown("##### Kontribusi tiap dimensi terhadap skor akhir")
        dims = list(BOBOT)
        long = skor.melt(id_vars="provinsi", value_vars=dims,
                         var_name="dimensi", value_name="nilai")
        long["kontribusi"] = long.apply(lambda r: r.nilai * BOBOT[r.dimensi], axis=1)
        gugur = set(skor.loc[skor.layak_pilot == "Tidak", "provinsi"])
        long.loc[long.provinsi.isin(gugur), "kontribusi"] = 0.0
        long["Dimensi"] = long.dimensi.map(LABEL_DIM)
        urut = skor.provinsi.tolist()

        if HAS_ALT:
            bar = alt.Chart(long).mark_bar().encode(
                y=alt.Y("provinsi:N", sort=urut, title=None),
                x=alt.X("kontribusi:Q", title="Kontribusi terbobot ke IKD", stack="zero"),
                color=alt.Color("Dimensi:N", scale=alt.Scale(
                    range=["#2FA36B", "#3FCF87", "#7FD9B0", "#E0C15A", "#EAD79A", "#9FB6BC"])),
                tooltip=["provinsi", "Dimensi", alt.Tooltip("nilai:Q", format=".2f"),
                         alt.Tooltip("kontribusi:Q", format=".3f")],
            ).properties(height=26 * len(skor) + 40)
            st.altair_chart(_tema(bar), use_container_width=True, theme=None)
        else:
            st.bar_chart(skor.set_index("provinsi")["IKD"])
        st.caption("Segmen granularitas harga paling lebar sebarannya. Di situlah "
                   "provinsi saling menjauh, dan di situ pula modul prediksi harga "
                   "hidup atau mati.")

    with kanan:
        st.markdown("##### Uji sensitivitas bobot")
        ss = sens.copy()
        ss["P_peringkat1"] = ss.P_peringkat1 * 100
        ss = _teks(ss, ["IKD_dasar", "IKD_p05", "IKD_p95"])
        ss = _teks(ss, ["P_peringkat1"], desimal=1)
        ss["P_peringkat1"] = ss.P_peringkat1 + "%"
        ss = ss.rename(columns={"provinsi": "Provinsi", "IKD_dasar": "IKD",
                                "IKD_p05": "p05", "IKD_p95": "p95",
                                "P_peringkat1": "P(#1)",
                                "peringkat_terburuk": "Peringkat terburuk"})
        st.markdown(df_to_html(ss, center_cols=("IKD", "p05", "p95", "P(#1)",
                                                "Peringkat terburuk")),
                    unsafe_allow_html=True)
        st.caption("p05–p95 adalah rentang skor ketika bobot digeser acak. Kolom "
                   "terakhir menunjukkan posisi terburuk yang pernah dicapai provinsi "
                   "itu di seluruh simulasi.")

    # ------------------------------------------------ peta panas per komoditas
    st.divider()
    st.markdown("##### Di mana datanya putus? Ketersediaan harga per komoditas")
    h = harga.copy()
    frek = {"harian": 1.0, "mingguan": 0.75, "bulanan": 0.5, "tidak ada": 0.0}
    h["skor"] = ((h.n_kabkota_harga / h.n_kabkota).clip(0, 1)
                 * h.frekuensi.str.lower().map(frek).fillna(0) * h.keterisian)
    h["Komoditas"] = h.komoditas.map(LABEL_KOM)
    if HAS_ALT:
        hm = alt.Chart(h).mark_rect(stroke="#0E262B", strokeWidth=1).encode(
            x=alt.X("Komoditas:N", sort=list(LABEL_KOM.values()), title=None),
            y=alt.Y("provinsi:N", sort=skor.provinsi.tolist(), title=None),
            color=alt.Color("skor:Q", title="Skor harga",
                            scale=alt.Scale(domain=[0, 1], range=["#16292E", "#2ECC71"])),
            tooltip=["provinsi", "Komoditas", "sistem",
                     alt.Tooltip("n_kabkota_harga:Q", title="Kab/kota dipantau"),
                     alt.Tooltip("skor:Q", format=".2f")],
        ).properties(height=28 * h.provinsi.nunique() + 30)
        st.altair_chart(_tema(hm), use_container_width=True, theme=None)
    else:
        st.dataframe(h.pivot_table(index="provinsi", columns="Komoditas", values="skor"))
    # Peringatan disusun dari data, bukan ditulis tetap. Versi sebelumnya
    # menyatakan tidak ada harga kentang di provinsi mana pun; setelah katalog
    # Siskaperbapo diverifikasi, kalimat itu jadi salah untuk Jawa Timur.
    kosong = h[h.skor == 0].groupby("Komoditas").provinsi.nunique()
    n_prov = h.provinsi.nunique()
    tak_terpantau = [k for k, v in kosong.items() if v == n_prov]
    sebagian = [f"{k} ({n_prov - v} dari {n_prov} provinsi)"
                for k, v in kosong.items() if 0 < v < n_prov]

    pesan = ["**Temuan yang membentuk desain sistem:** PIHPS Bank Indonesia menyurvei "
             "82 kabupaten/kota sampel inflasi dan daftar komoditasnya tidak memuat "
             "jagung maupun kentang."]
    if tak_terpantau:
        pesan.append(f"Tidak ada satu pun sumber harga tingkat kabupaten untuk "
                     f"{', '.join(tak_terpantau)} di seluruh provinsi yang dinilai.")
    if sebagian:
        pesan.append(f"Tersedia hanya di sebagian wilayah: {'; '.join(sebagian)}.")
    pesan.append("Provinsi yang punya sistem harga daerah sendiri menutup kekurangan "
                 "PIHPS — itulah yang memisahkan peringkat teratas dari sisanya.")
    st.warning(" ".join(pesan))

    # ------------------------------------------------------------ kerapuhan
    st.divider()
    st.markdown("##### Seberapa rapuh kesimpulan ini?")
    st.caption("Setiap parameter yang masih berstatus estimasi digeser ke seluruh "
               "rentang yang masuk akal. Yang ditampilkan: parameter mana yang sanggup "
               "memindahkan peringkat 1, dan pada nilai berapa.")
    pk = _pindai(prod, harga, wil)
    rapuh = pk[pk.bisa_membalik]

    k1, k2 = st.columns([1, 1.3])
    k1.metric("Parameter estimasi diuji", f"{len(pk)}")
    k1.metric("Sanggup membalikkan hasil", f"{len(rapuh)}",
              delta=f"{len(pk) - len(rapuh)} aman", delta_color="normal")

    if len(rapuh):
        tr = rapuh[["lapis", "ruang", "parameter", "ambang", "pemenang_lain"]].rename(
            columns={"lapis": "Lapis", "ruang": "Ruang", "parameter": "Parameter",
                     "ambang": "Ambang", "pemenang_lain": "Pemenang lain"})
        k2.markdown(df_to_html(tr, center_cols=("Ambang",)), unsafe_allow_html=True)
        st.info("Baca kolom Ambang sebagai uji kewajaran, bukan sekadar peringatan. "
                "Ambang yang menuntut keadaan mustahil — misalnya keterisian sempurna "
                "1,00 atau estimasi yang meleset separuh — berarti kesimpulan tetap "
                "aman. Ambang yang jatuh di rentang wajar berarti parameter itu harus "
                "diverifikasi sebelum hasilnya dipakai.")
    else:
        st.success("Tidak ada parameter estimasi yang sanggup memindahkan peringkat 1 "
                   "di seluruh rentang yang diuji.")

    # Parameter yang disapu rinci dipilih dari hasil pemindaian, bukan ditulis
    # tetap. Kalau suatu saat Jawa Tengah sudah diverifikasi atau katalog berubah,
    # bagian ini ikut berpindah sendiri ke parameter yang paling menentukan.
    kandidat = pk[(pk.lapis == "harga") & pk.bisa_membalik]
    if not len(kandidat):
        kandidat = pk[pk.lapis == "harga"]
    if len(kandidat):
        prov_uji, sistem_uji = [x.strip() for x in kandidat.iloc[0].ruang.split("/", 1)]
    else:
        prov_uji, sistem_uji = None, None

    if prov_uji:
        _sapuan_rinci(df_to_html, katalog, prov_uji, sistem_uji)


    # -------------------------------------------------------------- rincian
    st.divider()
    st.markdown("##### Rincian dimensi per provinsi")
    tab = skor[["peringkat", "provinsi", "n_komoditas"] + list(BOBOT)
               + ["IKD", "layak_pilot"]].copy()
    tab = tab.rename(columns={**LABEL_DIM, "peringkat": "#", "provinsi": "Provinsi",
                              "n_komoditas": "Komoditas tersedia",
                              "layak_pilot": "Lolos syarat"})
    num = list(LABEL_DIM.values()) + ["IKD"]
    tab = _teks(tab, num)
    st.markdown(df_to_html(tab, center_cols=tuple(num) + ("Komoditas tersedia",)),
                unsafe_allow_html=True)

    sd = skor[list(BOBOT)].std()
    lemah = [LABEL_DIM[k] for k in BOBOT if sd[k] < 0.03]
    bobot_txt = " · ".join(f"{LABEL_DIM[k]} {v:.0%}" for k, v in BOBOT.items())
    st.caption(f"Bobot dasar — {bobot_txt}. Syarat gugur: minimal "
               f"{GATE_MIN_KOMODITAS} dari 6 komoditas tercatat di ≥3 kabupaten.")
    if lemah:
        st.caption("Dimensi dengan daya pembeda rendah (simpangan baku < 0,03): "
                   + ", ".join(lemah) + ". Perlu indikator tambahan atau bobotnya diturunkan.")

    # ---------------------------------------------------------------- audit
    st.divider()
    r = audit["rinci"]
    pesan = (f"**Jejak audit katalog** — produksi {r['produksi']['rasio']*100:.0f}% "
             f"({r['produksi']['baris']} baris) · harga {r['harga']['rasio']*100:.0f}% "
             f"({r['harga']['baris']} baris) · wilayah {r['wilayah']['rasio']*100:.0f}% "
             f"({r['wilayah']['baris']} baris). Baris berstatus estimasi tidak dihitung "
             "sebagai verifikasi. Daftar tugas verifikasi ada di VERIFIKASI.md.")
    (st.success if audit["rasio"] >= 0.8 else st.warning)(pesan)

    c1, c2, c3 = st.columns(3)
    for kol, (nama, df) in zip((c1, c2, c3),
                               [("produksi", prod), ("harga", harga), ("wilayah", wil)]):
        kol.download_button(f"⬇️  katalog_{nama}.csv",
                            df.to_csv(index=False).encode("utf-8"),
                            file_name=f"katalog_{nama}.csv", mime="text/csv",
                            type="secondary", use_container_width=True)


if __name__ == "__main__":
    st.set_page_config(page_title="Kesiapan Data", layout="wide")

    def _fallback(df, **kw):
        return df.to_html(index=False, escape=False)

    render_tab_kesiapan(_fallback)
