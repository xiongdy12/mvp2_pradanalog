"""
PradanaLog — Platform Distribusi Pangan (3 TAB)
================================================
Tab 1  Peta Distribusi   : choropleth interaktif + panah MOLP + profil provinsi
Tab 2  Frontier Kebijakan: trade-off pemenuhan defisit (delta) vs biaya logistik
Tab 3  Dampak & Roadmap  : metrik dampak, rekomendasi kebijakan otomatis, roadmap

File pendamping (se-folder):
  indonesia_provinces.geojson
  rute_molp.csv           (opsional; fallback ke contoh)
  profil_provinsi.csv     (opsional; fallback ke contoh)
  frontier_delta.csv      (opsional; fallback ke contoh)

Jalankan:  pip install -U streamlit pydeck pandas altair
           # untuk fitur UNGGAH DATA (pipeline live): pip install pulp scikit-learn openpyxl
           streamlit run pradanalog_map.py
"""

import json
from io import StringIO
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st
from tab_kesiapan import render_tab_kesiapan
from tab_kabupaten import render_tab_kabupaten
from radar_prioritas import render_radar
from metrik_akurasi import caption_akurasi

try:
    import altair as alt
    HAS_ALT = True
except Exception:
    HAS_ALT = False

st.set_page_config(page_title="PradanaLog — Platform Distribusi Pangan",
                   page_icon="🌾", layout="wide")
st.markdown("""
<style>
/* ---------- Background & tipografi global ---------- */
.stApp{
  background:
    radial-gradient(1100px 620px at 12% -8%, #17454C 0%, rgba(23,69,76,0) 55%),
    radial-gradient(900px 500px at 100% 0%, #12403A 0%, rgba(18,64,58,0) 50%),
    linear-gradient(180deg, #0E262B 0%, #0A1D21 100%);
  background-attachment: fixed;
}
.block-container{padding-top:1.1rem; padding-bottom:2rem; max-width:1500px;}
h1,h2,h3,h4,h5{letter-spacing:-.2px;}

/* ---------- Hero header ---------- */
.pl-hero{
  background:linear-gradient(120deg,#10333A 0%,#1A574B 58%,#20674E 100%);
  border:1px solid rgba(255,255,255,.10);
  border-radius:18px; padding:20px 26px; margin:2px 0 14px 0;
  box-shadow:0 14px 40px rgba(0,0,0,.42), inset 0 1px 0 rgba(255,255,255,.06);
  position:relative; overflow:hidden;
}
.pl-hero:after{content:"";position:absolute;right:-60px;top:-60px;width:220px;height:220px;
  background:radial-gradient(circle,rgba(224,193,90,.16),transparent 70%);}
.pl-wordmark{font-size:2.0rem;font-weight:800;letter-spacing:-.6px;line-height:1;
  background:linear-gradient(90deg,#8CE6AE 0%,#E7C862 100%);
  -webkit-background-clip:text;background-clip:text;color:transparent;}
.pl-pill{background:rgba(224,193,90,.14);color:#F0D384;border:1px solid rgba(224,193,90,.42);
  padding:4px 12px;border-radius:999px;font-size:.72rem;font-weight:600;letter-spacing:.3px;
  text-transform:uppercase;}
.pl-tag{color:#B7D6CB;font-size:.95rem;margin-top:7px;}
.pl-tag b{color:#E9F4EE;}

/* ---------- Tabs ---------- */
.stTabs [data-baseweb="tab-list"]{gap:4px;border-bottom:1px solid rgba(255,255,255,.10);}
.stTabs [data-baseweb="tab"]{font-size:1.02rem;font-weight:600;padding:9px 16px;color:#9FB6BC;}
.stTabs [data-baseweb="tab"]:hover{color:#E9F4EE;}
.stTabs [aria-selected="true"]{color:#F0D384 !important;}
.stTabs [data-baseweb="tab-highlight"]{background:linear-gradient(90deg,#2FA36B,#E0C15A) !important;height:3px;}

/* ---------- Kartu (st.container border) ---------- */
[data-testid="stVerticalBlockBorderWrapper"]{
  background:linear-gradient(180deg, rgba(255,255,255,.045), rgba(255,255,255,.02));
  border:1px solid rgba(255,255,255,.10) !important; border-radius:16px !important;
  box-shadow:0 8px 26px rgba(0,0,0,.30); backdrop-filter: blur(3px);
}

/* ---------- Metrics ---------- */
[data-testid="stMetricValue"]{font-size:1.3rem;line-height:1.1;}
[data-testid="stMetricLabel"]{font-size:0.78rem;color:#9FB6BC;}
[data-testid="stMetricDelta"]{font-size:0.72rem;}

/* ---------- Tombol ---------- */
.stButton>button, .stDownloadButton>button{
  border-radius:11px;font-weight:700;border:0;color:#06231A;
  background:linear-gradient(90deg,#39C07E,#2CA9A0);
  box-shadow:0 6px 18px rgba(47,163,107,.28);transition:transform .05s ease,filter .2s ease;}
.stButton>button:hover, .stDownloadButton>button:hover{filter:brightness(1.07);}
.stButton>button:active{transform:translateY(1px);}
.stButton>button[kind="secondary"]{background:rgba(255,255,255,.06);color:#E6EDEE;
  border:1px solid rgba(255,255,255,.14);box-shadow:none;}

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#123037 0%,#0C2126 100%);
  border-right:1px solid rgba(255,255,255,.07);}
[data-testid="stSidebar"] h2{color:#EAF4EF;}
[data-testid="stFileUploaderDropzone"]{
  background:rgba(255,255,255,.035);border:1px dashed rgba(140,230,174,.35);border-radius:12px;}
/* Tombol "Upload/Browse" pada file uploader */
[data-testid="stFileUploaderDropzone"] button,
[data-testid="stFileUploader"] button{
  background:linear-gradient(90deg,#39C07E,#2CA9A0) !important;
  color:#06231A !important;border:0 !important;font-weight:700 !important;
  border-radius:9px !important;box-shadow:0 4px 12px rgba(47,163,107,.30) !important;}
[data-testid="stFileUploaderDropzone"] button *,
[data-testid="stFileUploader"] button *{color:#06231A !important;}
[data-testid="stFileUploaderDropzone"] button:hover{filter:brightness(1.07);}

/* ---------- Selectbox / slider ---------- */
[data-baseweb="select"]>div{background:rgba(255,255,255,.06);border-radius:10px;
  border-color:rgba(255,255,255,.14);}
[data-baseweb="select"] div,
[data-baseweb="select"] span,
[data-baseweb="select"] input{color:#EDF4F1 !important;}
[data-baseweb="select"] svg{fill:#AEC6CC !important;}
/* Menu dropdown yang terbuka */
[data-baseweb="popover"] ul,[data-baseweb="popover"] [role="listbox"]{
  background:#123840 !important;border:1px solid rgba(255,255,255,.12) !important;}
[data-baseweb="popover"] li,[data-baseweb="popover"] [role="option"]{color:#EDF4F1 !important;}
[data-baseweb="popover"] li:hover,[data-baseweb="popover"] [role="option"]:hover{
  background:rgba(47,163,107,.20) !important;}

/* ---------- Peta pydeck: sudut membulat + glow ---------- */
[data-testid="stDeckGlJsonChart"], iframe[title="st.pydeck_chart"]{
  border-radius:16px;overflow:hidden;
  box-shadow:0 12px 34px rgba(0,0,0,.45);border:1px solid rgba(255,255,255,.09);}

/* ---------- Alerts (info/success) lebih kalem ---------- */
[data-testid="stAlert"]{border-radius:12px;}

/* ---------- Dataframe ---------- */
[data-testid="stDataFrame"]{border-radius:12px;overflow:hidden;border:1px solid rgba(255,255,255,.08);}

/* ---------- Header atas transparan (hilangkan strip putih) ---------- */
[data-testid="stHeader"]{background:transparent !important;}
[data-testid="stDecoration"]{background:linear-gradient(90deg,#2FA36B,#E0C15A) !important;}
[data-testid="stToolbar"] *{color:#CBD9D7 !important;}
.block-container{padding-top:2.4rem !important;}

/* ---------- Kontras teks tinggi (independen dari tema) ---------- */
h1,h2,h3,h4,h5,h6{color:#F2F7F5 !important;}
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] strong{color:#E3ECEA !important;}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] *{color:#A6BBBF !important;}
[data-testid="stMetricValue"]{color:#F4F8F6 !important;}
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] *{color:#9FB6BC !important;}
[data-testid="stMetricDelta"] *{color:#8FD9B0 !important;}
[data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] *{color:#CBD9D7 !important;}
/* div/span markdown tanpa warna inline -> terang (warna inline hijau/merah tetap menang) */
[data-testid="stMarkdownContainer"] div,
[data-testid="stMarkdownContainer"] span{color:#E3ECEA;}
/* Sidebar teks jelas */
[data-testid="stSidebar"] p, [data-testid="stSidebar"] label,
[data-testid="stSidebar"] li, [data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] *{color:#EAF3F0 !important;}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] *{color:#C2D4D1 !important;}
/* Instruksi & label file uploader lebih terang */
[data-testid="stFileUploaderDropzoneInstructions"],
[data-testid="stFileUploaderDropzoneInstructions"] *{color:#D2E0DD !important;}
[data-testid="stFileUploaderDropzoneInstructions"] small{color:#A6BBBF !important;}

/* Alert: panel gelap kontras tinggi (ramah buta warna) */
[data-testid="stAlert"]{
  background:rgba(255,255,255,.05) !important;
  border:1px solid rgba(255,255,255,.12) !important;
  border-left:4px solid #37C08A !important; border-radius:12px !important;}
[data-testid="stAlert"] *{color:#EDF4F1 !important;}

/* Tabel HTML kustom (pengganti dataframe putih) */
.pl-table{width:100%;border-collapse:collapse;font-size:.9rem;border-radius:12px;overflow:hidden;
  border:1px solid rgba(255,255,255,.10);margin-top:4px;}
.pl-table th{background:rgba(47,163,107,.18);color:#EFF6F3;font-weight:700;text-align:left;
  padding:9px 13px;border-bottom:1px solid rgba(255,255,255,.10);}
.pl-table td{padding:8px 13px;color:#E3ECEA;border-bottom:1px solid rgba(255,255,255,.06);}
.pl-table tr:nth-child(even) td{background:rgba(255,255,255,.03);}
.pl-table tr:hover td{background:rgba(47,163,107,.12);}
</style>
""", unsafe_allow_html=True)

HERE = Path(__file__).parent
GEOJSON_PATH = HERE / "indonesia_provinces.geojson"
PLACEHOLDER = "— Pilih provinsi —"

PROVINSI = {
    "Aceh": (4.69, 96.74), "Sumatera Utara": (2.11, 99.53),
    "Sumatera Barat": (-0.74, 100.22), "Riau": (0.29, 101.71),
    "Jambi": (-1.61, 103.61), "Sumatera Selatan": (-3.32, 103.91),
    "Bengkulu": (-3.80, 102.27), "Lampung": (-4.55, 105.41),
    "Kepulauan Bangka Belitung": (-2.74, 106.44), "Kepulauan Riau": (3.92, 108.14),
    "DKI Jakarta": (-6.21, 106.85), "Jawa Barat": (-6.91, 107.61),
    "Jawa Tengah": (-7.15, 110.14), "DI Yogyakarta": (-7.87, 110.43),
    "Jawa Timur": (-7.54, 112.24), "Banten": (-6.40, 106.07),
    "Bali": (-8.34, 115.09), "Nusa Tenggara Barat": (-8.65, 117.36),
    "Nusa Tenggara Timur": (-8.66, 121.08), "Kalimantan Barat": (-0.26, 111.48),
    "Kalimantan Tengah": (-1.68, 113.38), "Kalimantan Selatan": (-3.09, 115.28),
    "Kalimantan Timur": (0.53, 116.32), "Kalimantan Utara": (3.07, 116.04),
    "Sulawesi Utara": (0.62, 123.97), "Gorontalo": (0.54, 123.06),
    "Sulawesi Tengah": (-1.43, 121.45), "Sulawesi Barat": (-2.84, 119.23),
    "Sulawesi Selatan": (-3.66, 119.97), "Sulawesi Tenggara": (-4.15, 122.17),
    "Maluku": (-3.24, 130.15), "Maluku Utara": (1.57, 127.81),
    "Papua Barat": (-1.34, 133.17), "Papua": (-4.27, 138.08),
}
# Kawasan Timur Indonesia (untuk analisis dampak)
KTI = {"Bali", "Nusa Tenggara Barat", "Nusa Tenggara Timur", "Kalimantan Barat",
       "Kalimantan Tengah", "Kalimantan Selatan", "Kalimantan Timur", "Kalimantan Utara",
       "Sulawesi Utara", "Gorontalo", "Sulawesi Tengah", "Sulawesi Barat",
       "Sulawesi Selatan", "Sulawesi Tenggara", "Maluku", "Maluku Utara",
       "Papua Barat", "Papua"}

KOMODITAS = ["beras", "jagung", "bawang", "cabai_besar", "cabai_rawit", "kentang"]
LABEL = {"beras": "Beras", "jagung": "Jagung", "bawang": "Bawang Merah",
         "cabai_besar": "Cabai Besar", "cabai_rawit": "Cabai Rawit", "kentang": "Kentang"}
LABEL2KEY = {v: k for k, v in LABEL.items()}
CLUSTER_WARNA = {
    "Defisit Kritis": [231, 76, 60], "Defisit Moderat": [230, 126, 34],
    "Surplus Moderat": [241, 196, 15], "Surplus Tinggi": [46, 204, 113],
}

PROFIL_CSV = """provinsi,cluster,beras,jagung,bawang,cabai_besar,cabai_rawit,kentang
Jawa Tengah,Surplus Tinggi,2100,1500,350,40,30,45
Jawa Timur,Surplus Tinggi,2400,4200,180,35,50,15
Jawa Barat,Surplus Tinggi,800,200,60,45,40,40
Sumatera Selatan,Surplus Moderat,900,300,-20,5,8,-3
Lampung,Surplus Moderat,600,800,-15,3,6,-2
Sulawesi Selatan,Surplus Moderat,1200,500,-10,4,5,-4
Sumatera Utara,Surplus Moderat,400,250,30,8,6,20
Sumatera Barat,Surplus Moderat,300,150,15,10,12,8
Aceh,Defisit Moderat,150,40,8,5,6,3
Riau,Defisit Moderat,-200,-30,-12,-3,-4,-5
Jambi,Defisit Moderat,-50,-20,-8,2,3,-3
Bengkulu,Defisit Moderat,-30,10,-5,4,5,-2
Kalimantan Barat,Defisit Moderat,-120,-40,-10,-4,-3,-6
Kalimantan Selatan,Defisit Moderat,80,-25,-9,-2,-3,-4
Sulawesi Tengah,Defisit Moderat,-40,20,-6,2,4,-3
Bali,Defisit Moderat,-60,-15,8,3,18,-2
Nusa Tenggara Barat,Defisit Moderat,-30,40,25,2,4,-3
DKI Jakarta,Defisit Kritis,-900,-120,-80,-15,-20,-25
Banten,Defisit Kritis,-150,-40,-30,-8,-10,-12
DI Yogyakarta,Defisit Kritis,-40,-15,-12,-3,-4,-5
Kepulauan Riau,Defisit Kritis,-120,-25,-15,-5,-6,-7
Kepulauan Bangka Belitung,Defisit Kritis,-70,-18,-10,-4,-5,-6
Kalimantan Tengah,Defisit Kritis,-90,-30,-12,-4,-4,-6
Kalimantan Timur,Defisit Kritis,-160,-50,-20,-7,-8,-10
Kalimantan Utara,Defisit Kritis,-50,-15,-8,-3,-3,-4
Sulawesi Utara,Defisit Kritis,-40,30,-10,-2,5,-5
Gorontalo,Defisit Kritis,-20,60,-6,-2,-2,-3
Sulawesi Barat,Defisit Kritis,-25,15,-5,-2,-2,-3
Sulawesi Tenggara,Defisit Kritis,-35,25,-8,-3,-3,-4
Maluku,Defisit Kritis,-80,-20,-12,-4,-4,-6
Maluku Utara,Defisit Kritis,-60,-15,-10,-3,-3,-5
Papua Barat,Defisit Kritis,-100,-18,-9,-3,-3,-4
Papua,Defisit Kritis,-278,-11,-14,5,10,1
Nusa Tenggara Timur,Defisit Kritis,-150,80,-12,-3,-3,-6
"""

FRONTIER_CSV = """komoditas,delta_pct,biaya_juta
Beras,50,751338
Beras,60,926298
Beras,70,1102781
Beras,80,1283366
Beras,90,1469476
Beras,100,1665428
Bawang Merah,50,72220
Bawang Merah,60,86730
Bawang Merah,70,103326
Bawang Merah,80,120274
Bawang Merah,90,137251
Bawang Merah,100,154253
Kentang,50,11067
Kentang,60,13544
Kentang,70,16022
Kentang,80,18623
Kentang,90,21433
Kentang,100,24249
"""


@st.cache_data
def load_profil():
    real = HERE / "profil_provinsi.csv"
    if real.exists():
        return pd.read_csv(real).set_index("provinsi")
    return pd.read_csv(StringIO(PROFIL_CSV)).set_index("provinsi")


@st.cache_data
def load_routes():
    real = HERE / "rute_molp.csv"
    if real.exists():
        df = pd.read_csv(real)[["komoditas", "asal", "tujuan", "volume_ton", "biaya_rp"]].copy()
    else:
        df = pd.DataFrame([
            ("Beras", "Jawa Barat", "DKI Jakarta", 400000, 60000),
            ("Beras", "Lampung", "DKI Jakarta", 270000, 55000),
            ("Beras", "Sulawesi Selatan", "Papua", 95000, 310000),
            ("Jagung", "Jawa Timur", "DKI Jakarta", 30000, 40000),
            ("Bawang Merah", "Jawa Tengah", "DKI Jakarta", 40000, 35000),
            ("Kentang", "Jawa Tengah", "Sumatera Utara", 8000, 70000),
        ], columns=["komoditas", "asal", "tujuan", "volume_ton", "biaya_rp"])
    for c, a, fn in [("asal_lat", "asal", lambda p: PROVINSI[p][0]),
                     ("asal_lon", "asal", lambda p: PROVINSI[p][1]),
                     ("tuj_lat", "tujuan", lambda p: PROVINSI[p][0]),
                     ("tuj_lon", "tujuan", lambda p: PROVINSI[p][1])]:
        df[c] = df[a].map(fn)
    return df


def add_coords(df):
    df = df[["komoditas", "asal", "tujuan", "volume_ton", "biaya_rp"]].copy()
    df["asal_lat"] = df["asal"].map(lambda p: PROVINSI.get(p, (0, 0))[0])
    df["asal_lon"] = df["asal"].map(lambda p: PROVINSI.get(p, (0, 0))[1])
    df["tuj_lat"] = df["tujuan"].map(lambda p: PROVINSI.get(p, (0, 0))[0])
    df["tuj_lon"] = df["tujuan"].map(lambda p: PROVINSI.get(p, (0, 0))[1])
    return df


@st.cache_data
def load_frontier():
    real = HERE / "frontier_delta.csv"
    if real.exists():
        return pd.read_csv(real)
    return pd.read_csv(StringIO(FRONTIER_CSV))


@st.cache_data
def load_geojson():
    with open(GEOJSON_PATH, encoding="utf-8") as f:
        return json.load(f)


# ==================================================================
#  PIPELINE LIVE — unggah 3 Excel -> cleaning -> K-Means -> MOLP -> frontier
# ==================================================================
def _haversine(lat1, lon1, lat2, lon2):
    import numpy as np
    R = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = (np.sin(np.radians(lat2 - lat1) / 2) ** 2
         + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2)
    return 2 * R * np.arcsin(np.sqrt(a))


def _bpp(lon):
    return max(500.0, 800.0 + 15.0 * (lon - 95.0))


def _read_xlsx(f, sheet):
    import io
    if isinstance(f, (bytes, bytearray)):
        f = io.BytesIO(f)
    try:
        f.seek(0)
        return pd.read_excel(f, sheet_name=sheet, skiprows=1)
    except Exception:
        f.seek(0)
        return pd.read_excel(f, sheet_name=0, skiprows=1)


def _solve_molp(data_idx, sur, dfc, hrg, havg, S, D, delta, theta=0.4,
                wb=0.4, wd=0.4, wj=0.2):
    import pulp
    from pulp import LpProblem, LpVariable, LpMinimize, lpSum, value, LpStatus
    jr, bk = {}, {}
    for i in S:
        for j in D:
            if i == j:
                continue
            d = _haversine(data_idx[i][0], data_idx[i][1], data_idx[j][0], data_idx[j][1])
            jr[(i, j)] = d
            bk[(i, j)] = (_bpp(data_idx[i][1]) + _bpp(data_idx[j][1])) / 2 * d
    if not bk:
        return None
    mb = max(bk.values()); mj = max(jr.values())
    md = max(abs(hrg.get(j, havg) - havg) for j in D) or 1
    prob = LpProblem("molp", LpMinimize)
    x = {(i, j): LpVariable(f"x_{i}_{j}".replace(" ", "_"), lowBound=0)
         for i in S for j in D if i != j}
    prob += (wb * lpSum(x[k] * bk[k] / mb for k in x)
             + wd * lpSum(x[k] * abs(hrg.get(k[1], havg) - havg) / md for k in x)
             + wj * lpSum(x[k] * jr[k] / mj for k in x))
    for i in S:
        prob += lpSum(x[(i, j)] for j in D if (i, j) in x) <= sur[i]
    for j in D:
        prob += lpSum(x[(i, j)] for i in S if (i, j) in x) >= delta * dfc[j]
    for i in S:
        for j in D:
            if (i, j) in x:
                prob += x[(i, j)] <= theta * sur[i]
    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    if LpStatus[prob.status] != "Optimal":
        return None
    rows = []
    for (i, j), var in x.items():
        v = value(var)
        if v and v > 0.1:
            rows.append({"asal": i, "tujuan": j, "volume_ton": round(v, 1),
                         "biaya_rp": round(v * bk[(i, j)] / 1e6, 2)})
    return rows


@st.cache_data(show_spinner=False)
def run_pipeline(prod_bytes, kons_bytes, ihk_bytes):
    """Return (routes_df, profil_df, frontier_df) dari 3 Excel BPS."""
    import numpy as np
    from sklearn.preprocessing import MinMaxScaler
    from sklearn.cluster import KMeans

    dp = _read_xlsx(prod_bytes, "Dataset_Produksi").iloc[:, :4]
    dp.columns = ["tahun", "provinsi", "komoditas", "produksi_ton"]
    dk = _read_xlsx(kons_bytes, "Dataset_Konsumsi").iloc[:, :6]
    dk.columns = ["tahun", "provinsi", "komoditas", "penduduk_jiwa",
                  "konsumsi_per_kapita", "konsumsi_total_ton"]
    di = _read_xlsx(ihk_bytes, "Dataset_IHK_Provinsi").iloc[:, :6]
    di.columns = ["tahun", "bulan", "nama_bulan", "provinsi", "ihk_mmt", "ihk_makanan"]

    for df in (dp, dk, di):
        df["tahun"] = pd.to_numeric(df["tahun"], errors="coerce").astype("Int64")
        df["provinsi"] = df["provinsi"].astype(str).str.strip()
    dp["produksi_ton"] = pd.to_numeric(dp["produksi_ton"], errors="coerce").fillna(0)
    dk["konsumsi_total_ton"] = pd.to_numeric(dk["konsumsi_total_ton"], errors="coerce").fillna(0)
    di["ihk_makanan"] = pd.to_numeric(di["ihk_makanan"], errors="coerce")

    merge = pd.merge(dp[["tahun", "provinsi", "komoditas", "produksi_ton"]],
                     dk[["tahun", "provinsi", "komoditas", "konsumsi_total_ton"]],
                     on=["tahun", "provinsi", "komoditas"], how="outer").fillna(0)
    merge["surplus_defisit_ton"] = merge["produksi_ton"] - merge["konsumsi_total_ton"]
    ihk_th = di.groupby(["tahun", "provinsi"]).agg(
        ihk_makanan_avg=("ihk_makanan", "mean")).reset_index()
    master = pd.merge(merge, ihk_th, on=["tahun", "provinsi"], how="left")

    years = [int(y) for y in master["tahun"].dropna().unique()]
    thn = 2024 if 2024 in years else int(max(years))
    cur = master[master["tahun"] == thn].copy()

    # K-Means cluster
    agg = cur.groupby("provinsi").agg(
        sd_mean=("surplus_defisit_ton", "mean"), prod=("produksi_ton", "sum"),
        kons=("konsumsi_total_ton", "sum"), ihk=("ihk_makanan_avg", "mean")).reset_index()
    Xc = MinMaxScaler().fit_transform(agg[["sd_mean", "prod", "kons", "ihk"]].fillna(0))
    km = KMeans(n_clusters=4, random_state=42, n_init=10)
    agg["cl"] = km.fit_predict(Xc)
    order = agg.groupby("cl")["sd_mean"].mean().sort_values()
    lab = {order.index[0]: "Defisit Kritis", order.index[1]: "Defisit Moderat",
           order.index[2]: "Surplus Moderat", order.index[3]: "Surplus Tinggi"}
    agg["cluster"] = agg["cl"].map(lab)
    cluster_map = dict(zip(agg["provinsi"], agg["cluster"]))

    KEY = {"Beras": "beras", "Jagung": "jagung", "Bawang Merah": "bawang",
           "Cabai Besar": "cabai_besar", "Cabai Rawit": "cabai_rawit", "Kentang": "kentang"}
    koms = [k for k in KEY if k in cur["komoditas"].unique()]

    # siapkan per-komoditas surplus/defisit/harga
    def prep(kom):
        d = cur[cur["komoditas"] == kom].set_index("provinsi")
        idx = {p: (PROVINSI[p][0], PROVINSI[p][1]) for p in d.index if p in PROVINSI}
        sur = {p: max(0, d.loc[p, "surplus_defisit_ton"]) for p in idx}
        dfc = {p: max(0, -d.loc[p, "surplus_defisit_ton"]) for p in idx}
        hrg = d["ihk_makanan_avg"].reindex(idx.keys())
        hrg = hrg.fillna(hrg.mean()).to_dict()
        havg = np.nanmean(list(hrg.values())) if hrg else 0
        S = [p for p in idx if sur[p] > 10]; Dd = [p for p in idx if dfc[p] > 10]
        return idx, sur, dfc, hrg, havg, S, Dd

    # routes (delta 0.8)
    all_routes = []
    for kom in koms:
        idx, sur, dfc, hrg, havg, S, Dd = prep(kom)
        if not S or not Dd:
            continue
        rows = _solve_molp(idx, sur, dfc, hrg, havg, S, Dd, 0.8)
        if rows:
            for r in rows:
                r["komoditas"] = kom
            all_routes.extend(rows)
    routes = add_coords(pd.DataFrame(all_routes)) if all_routes else add_coords(
        pd.DataFrame(columns=["komoditas", "asal", "tujuan", "volume_ton", "biaya_rp"]))

    # profil (ribu ton) + cluster
    piv = cur.pivot_table(index="provinsi", columns="komoditas",
                          values="surplus_defisit_ton", aggfunc="sum").fillna(0)
    piv = (piv / 1000).round(0).astype(int).rename(columns=KEY)
    for c in ["beras", "jagung", "bawang", "cabai_besar", "cabai_rawit", "kentang"]:
        if c not in piv.columns:
            piv[c] = 0
    piv["cluster"] = piv.index.map(cluster_map).fillna("Defisit Kritis")
    profil = piv[["cluster", "beras", "jagung", "bawang",
                  "cabai_besar", "cabai_rawit", "kentang"]]

    # frontier (delta sweep)
    fr = []
    for kom in koms:
        idx, sur, dfc, hrg, havg, S, Dd = prep(kom)
        if not S or not Dd:
            continue
        for delta in [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
            rows = _solve_molp(idx, sur, dfc, hrg, havg, S, Dd, delta)
            if rows:
                fr.append({"komoditas": kom, "delta_pct": int(delta * 100),
                           "biaya_juta": round(sum(r["biaya_rp"] for r in rows), 1)})
    frontier = pd.DataFrame(fr)
    return routes, profil, frontier


# ==================================================================
#  LAPORAN PDF — profil + rute + rekomendasi per provinsi (1 file)
# ==================================================================
def _rekom_pdf(prov, r, masuk, keluar):
    KOM = ["beras", "jagung", "bawang", "cabai_besar", "cabai_rawit", "kentang"]
    LAB = {"beras": "Beras", "jagung": "Jagung", "bawang": "Bawang Merah",
           "cabai_besar": "Cabai Besar", "cabai_rawit": "Cabai Rawit", "kentang": "Kentang"}
    vals = {LAB[k]: int(r[k]) for k in KOM}
    defi = {k: v for k, v in vals.items() if v < 0}
    surp = {k: v for k, v in vals.items() if v > 0}
    if "Defisit" in r["cluster"]:
        worst = min(defi, key=defi.get) if defi else "-"
        pemasok = ", ".join(masuk.sort_values("volume_ton", ascending=False)["asal"].head(2)) \
            if len(masuk) else "belum ada rute MOLP"
        prio = "TINGGI" if r["cluster"] == "Defisit Kritis" else "SEDANG"
        return (f"<b>Peran: PENERIMA (defisit) &middot; Prioritas {prio}.</b> "
                f"Defisit terbesar pada <b>{worst}</b> ({defi.get(worst, 0):,} rb ton). "
                f"Rekomendasi pasokan dari <b>{pemasok}</b>. Perkuat stok menjelang "
                f"Ramadan/Lebaran dan musim paceklik untuk menekan lonjakan harga.")
    best = max(surp, key=surp.get) if surp else "-"
    tujuan = ", ".join(keluar.sort_values("volume_ton", ascending=False)["tujuan"].head(2)) \
        if len(keluar) else "belum dialokasikan"
    return (f"<b>Peran: PEMASOK (hub surplus).</b> Surplus terbesar pada <b>{best}</b> "
            f"({surp.get(best, 0):,} rb ton). Salurkan ke <b>{tujuan}</b> untuk menekan "
            f"disparitas harga antarwilayah.")


@st.cache_data(show_spinner=False)
def build_pdf(routes, profil):
    import io
    from datetime import datetime
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, PageBreak, KeepTogether)
    from reportlab.graphics.shapes import Drawing, Rect, Line

    DARK = colors.HexColor("#12343B"); GREEN = colors.HexColor("#2C7A4B")
    RED = colors.HexColor("#C0392B"); GOLD = colors.HexColor("#B8860B")
    INK = colors.HexColor("#1E2A2E"); MUT = colors.HexColor("#5C6B70")
    LIGHT = colors.HexColor("#EEF3F1"); LINE = colors.HexColor("#DDE3E1")
    CLC = {"Defisit Kritis": colors.HexColor("#E74C3C"), "Defisit Moderat": colors.HexColor("#E67E22"),
           "Surplus Moderat": colors.HexColor("#C9A227"), "Surplus Tinggi": colors.HexColor("#2ECC71")}
    KOM = ["beras", "jagung", "bawang", "cabai_besar", "cabai_rawit", "kentang"]
    LAB = {"beras": "Beras", "jagung": "Jagung", "bawang": "Bawang Merah",
           "cabai_besar": "Cabai Besar", "cabai_rawit": "Cabai Rawit", "kentang": "Kentang"}
    KTIp = {"Bali", "Nusa Tenggara Barat", "Nusa Tenggara Timur", "Kalimantan Barat",
            "Kalimantan Tengah", "Kalimantan Selatan", "Kalimantan Timur", "Kalimantan Utara",
            "Sulawesi Utara", "Gorontalo", "Sulawesi Tengah", "Sulawesi Barat", "Sulawesi Selatan",
            "Sulawesi Tenggara", "Maluku", "Maluku Utara", "Papua Barat", "Papua"}

    ss = getSampleStyleSheet()
    def P(txt, size=8.5, color=INK, bold=False, lead=12, align=0):
        return Paragraph(txt, ParagraphStyle(
            "x", parent=ss["Normal"], fontName="Helvetica-Bold" if bold else "Helvetica",
            fontSize=size, textColor=color, leading=lead, alignment=align))

    def fnum(x):
        return f"{x:,.0f}"

    def bar(val, vmax, w=34 * mm, h=5 * mm):
        d = Drawing(w, h)
        d.add(Line(w / 2, 0, w / 2, h, strokeColor=colors.HexColor("#CFCFCF"), strokeWidth=0.5))
        if vmax > 0 and val != 0:
            frac = max(-1, min(1, val / vmax)); ln = abs(frac) * (w / 2 - 1)
            if val > 0:
                d.add(Rect(w / 2, 1, ln, h - 2, fillColor=GREEN, strokeColor=None))
            else:
                d.add(Rect(w / 2 - ln, 1, ln, h - 2, fillColor=RED, strokeColor=None))
        return d

    # ---- precompute poligon mini-peta dari geojson (vektor, ringan) ----
    def _rings(geom):
        out = []
        polys = ([geom["coordinates"]] if geom["type"] == "Polygon"
                 else geom["coordinates"] if geom["type"] == "MultiPolygon" else [])
        for poly in polys:
            if poly:
                out.append(poly[0])
        return out

    feat_rings = {}
    _lon, _lat = [], []
    try:
        gj = load_geojson()
        for ft in gj["features"]:
            nm = ft["properties"]["provinsi"]
            rings = sorted(_rings(ft["geometry"]), key=len, reverse=True)[:3]
            keep = []
            for ring in rings:
                if len(ring) < 5:
                    continue
                step = max(1, len(ring) // 26)
                rr = ring[::step]
                keep.append(rr)
                for lon, lat in rr:
                    _lon.append(lon); _lat.append(lat)
            if keep:
                feat_rings[nm] = keep
    except Exception:
        feat_rings = {}

    if feat_rings:
        lon0, lon1 = min(_lon), max(_lon); lat0, lat1 = min(_lat), max(_lat)
        MAP_W = 60 * mm
        MAP_H = MAP_W * (lat1 - lat0) / (lon1 - lon0)
        feat_norm = {n: [[((lo - lon0) / (lon1 - lon0), (la - lat0) / (lat1 - lat0))
                          for lo, la in r] for r in rings] for n, rings in feat_rings.items()}
    else:
        MAP_W = MAP_H = 0

    def minimap(hl):
        from reportlab.graphics.shapes import Drawing, Polygon
        d = Drawing(MAP_W, MAP_H)
        hl_color = CLC.get(profil.loc[hl, "cluster"], GOLD) if hl in profil.index else GOLD
        for name, rings in feat_norm.items():
            if name == hl:
                continue
            for r in rings:
                pts = [c for nx, ny in r for c in (nx * MAP_W, ny * MAP_H)]
                d.add(Polygon(points=pts, fillColor=colors.HexColor("#D7DEDC"),
                              strokeColor=colors.white, strokeWidth=0.3))
        for r in feat_norm.get(hl, []):
            pts = [c for nx, ny in r for c in (nx * MAP_W, ny * MAP_H)]
            d.add(Polygon(points=pts, fillColor=hl_color,
                          strokeColor=colors.HexColor("#243539"), strokeWidth=0.8))
        return d

    story = []
    # ---------- COVER / NASIONAL ----------
    head = Table([[P("PradanaLog", 20, colors.white, bold=True, lead=25)],
                  [P("Laporan Kebijakan Optimasi Distribusi Pangan Nasional", 11, colors.whitesmoke, lead=15)],
                  [P("Dihasilkan otomatis oleh platform &middot; " +
                     datetime.now().strftime("%d %B %Y"), 8, colors.HexColor("#AEC6CC"), lead=11)]],
                 colWidths=[176 * mm])
    head.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), DARK),
        ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (0, 0), 16), ("BOTTOMPADDING", (0, 2), (0, 2), 14),
        ("TOPPADDING", (0, 1), (0, 2), 2), ("BOTTOMPADDING", (0, 0), (0, 1), 2)]))
    story += [head, Spacer(1, 8)]

    tot_rute = len(routes); tot_vol = routes["volume_ton"].sum()
    prov_l = routes["tujuan"].nunique()
    kti_vol = routes[routes["tujuan"].isin(KTIp)]["volume_ton"].sum()

    def kpi(v, lbl, c=DARK):
        return Table([[P(v, 15, c, bold=True)], [P(lbl, 7.5, MUT)]], colWidths=[42 * mm])
    kpis = Table([[kpi(f"{tot_rute}", "Total rute MOLP"),
                   kpi(f"{tot_vol/1e6:.2f} jt t", "Volume terdistribusi"),
                   kpi(f"{prov_l}", "Provinsi terlayani"),
                   kpi(f"{kti_vol/1e3:,.0f} rb t", "Volume ke KTI", GOLD)]], colWidths=[44 * mm] * 4)
    kpis.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), LIGHT), ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.white), ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("LEFTPADDING", (0, 0), (-1, -1), 10)]))
    story += [kpis, Spacer(1, 10)]

    # cluster distribusi
    cl_counts = profil["cluster"].value_counts().to_dict()
    chips = []
    for cl in ["Defisit Kritis", "Defisit Moderat", "Surplus Moderat", "Surplus Tinggi"]:
        chips.append(Table([[P(str(cl_counts.get(cl, 0)), 14, colors.white, bold=True)],
                            [P(cl, 7, colors.white)]], colWidths=[43 * mm]))
        chips[-1].setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CLC[cl]),
            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 9)]))
    clrow = Table([chips], colWidths=[44 * mm] * 4)
    clrow.setStyle(TableStyle([("INNERGRID", (0, 0), (-1, -1), 2, colors.white)]))
    story += [P("Distribusi Klaster Ketahanan Pangan (34 Provinsi)", 10, DARK, bold=True), Spacer(1, 4),
              clrow, Spacer(1, 10)]

    # rekomendasi nasional
    net = profil[KOM].sum(axis=1).sort_values()
    top3 = " &middot; ".join(net.head(3).index)
    rec = (f"1. <b>Prioritaskan wilayah defisit kritis:</b> {top3} — alokasikan lebih awal "
           "sebelum lonjakan harga menjelang Ramadan/Lebaran.<br/>"
           "2. <b>Subsidi logistik tepat sasaran ke Kawasan Timur Indonesia.</b> Rute lintas pulau "
           "ke Papua/Maluku/NTT paling mahal per ton — jadikan tanggung jawab fiskal negara.<br/>"
           "3. <b>Integrasi ke GNPIP &amp; rapat TPID.</b> Output rute dapat langsung dipakai sebagai "
           "dasar keputusan distribusi antarprovinsi.<br/>"
           "4. <b>Perkuat backbone efisien Jawa&harr;Jawa &amp; Sumatera&harr;Sumatera</b> sebagai "
           "penyeimbang biaya distribusi nasional.")
    recbox = Table([[P(rec, 8.5, INK, lead=13)]], colWidths=[176 * mm])
    recbox.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FBF6E9")),
        ("BOX", (0, 0), (-1, -1), 0.5, GOLD), ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    story += [P("Rekomendasi Kebijakan Nasional", 10, DARK, bold=True), Spacer(1, 4),
              recbox, PageBreak()]

    # ---------- PER PROVINSI ----------
    order_cl = {"Defisit Kritis": 0, "Defisit Moderat": 1, "Surplus Moderat": 2, "Surplus Tinggi": 3}
    prof2 = profil.copy()
    prof2["_net"] = prof2[KOM].sum(axis=1)
    prof2["_o"] = prof2["cluster"].map(order_cl).fillna(9)
    prov_sorted = prof2.sort_values(["_o", "_net"]).index.tolist()

    story += [P("Tinjauan Per Provinsi", 13, DARK, bold=True),
              P("Diurutkan berdasarkan prioritas: defisit kritis lebih dulu.", 8, MUT), Spacer(1, 6)]

    for prov in prov_sorted:
        r = profil.loc[prov]
        vmax = max(abs(int(r[k])) for k in KOM) or 1
        cluster = r["cluster"]
        # header + mini-peta
        chip = Table([[P(cluster, 7.5, colors.white, bold=True, align=1)]], colWidths=[40 * mm])
        chip.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CLC.get(cluster, MUT)),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        left = Table([[P(prov, 13, DARK, bold=True)], [chip]], colWidths=[108 * mm])
        left.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (0, 0), 2), ("BOTTOMPADDING", (0, 0), (0, 0), 5),
            ("TOPPADDING", (0, 1), (0, 1), 0)]))
        if MAP_W:
            mm_cell = Table([[minimap(prov)]], colWidths=[64 * mm])
            mm_cell.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F6F8F7")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
            hdr = Table([[left, mm_cell]], colWidths=[110 * mm, 66 * mm])
        else:
            hdr = Table([[left]], colWidths=[176 * mm])
        hdr.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEBELOW", (0, 0), (-1, -1), 1, DARK), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))

        # profil komoditas
        prows = [[P("Komoditas", 7.5, colors.white, bold=True), P("Nilai (rb ton)", 7.5, colors.white, bold=True),
                  P("Neraca", 7.5, colors.white, bold=True), P("Status", 7.5, colors.white, bold=True)]]
        for k in KOM:
            v = int(r[k]); status = "Surplus" if v > 0 else ("Defisit" if v < 0 else "Seimbang")
            sc = GREEN if v > 0 else (RED if v < 0 else MUT)
            prows.append([P(LAB[k], 8), P(f"{v:,}", 8, sc, bold=True), bar(v, vmax),
                          P(status, 8, sc)])
        pt = Table(prows, colWidths=[40 * mm, 30 * mm, 40 * mm, 26 * mm])
        pt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), DARK),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F8F7")]),
            ("BOX", (0, 0), (-1, -1), 0.5, LINE), ("LINEBELOW", (0, 0), (-1, 0), 0.5, LINE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LEFTPADDING", (0, 0), (-1, -1), 6)]))

        # rute keluar / masuk
        keluar = routes[routes["asal"] == prov]
        masuk = routes[routes["tujuan"] == prov]

        def rute_tbl(df, kolom, judul):
            rows = [[P(judul, 7.5, colors.white, bold=True), P("Kom.", 7.5, colors.white, bold=True),
                     P("Ton", 7.5, colors.white, bold=True)]]
            d = df.sort_values("volume_ton", ascending=False).head(5)
            if len(d) == 0:
                rows.append([P("—", 8), P("—", 8), P("—", 8)])
            for _, x in d.iterrows():
                rows.append([P(x[kolom], 7.5), P(x["komoditas"][:4] + ".", 7.5),
                             P(fnum(x["volume_ton"]), 7.5)])
            extra = len(df) - 5
            if extra > 0:
                rows.append([P(f"+{extra} rute lainnya", 7, MUT), P("", 7), P("", 7)])
            t = Table(rows, colWidths=[46 * mm, 18 * mm, 22 * mm])
            hc = GREEN if "Memasok" in judul else RED
            t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), hc),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F8F7")]),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 5)]))
            return t

        routes_row = Table([[rute_tbl(keluar, "tujuan", "Memasok ke"),
                             rute_tbl(masuk, "asal", "Menerima dari")]],
                           colWidths=[88 * mm, 88 * mm])
        routes_row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), 6),
            ("LEFTPADDING", (0, 1), (0, 1), 0)]))

        # rekomendasi
        rtext = _rekom_pdf(prov, r, masuk, keluar)
        rbox = Table([[P(rtext, 8.5, INK, lead=12)]], colWidths=[176 * mm])
        rbox.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), LIGHT),
            ("LINEBEFORE", (0, 0), (0, -1), 3, CLC.get(cluster, GOLD)),
            ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))

        block = KeepTogether([hdr, Spacer(1, 4), pt, Spacer(1, 4), routes_row,
                              Spacer(1, 4), rbox, Spacer(1, 12)])
        story.append(block)

    # footer
    def _foot(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7); canvas.setFillColor(MUT)
        canvas.drawString(18 * mm, 10 * mm, "PradanaLog · Laporan Kebijakan Distribusi Pangan")
        canvas.drawRightString(192 * mm, 10 * mm, f"Halaman {doc.page}")
        canvas.setStrokeColor(LINE); canvas.line(18 * mm, 13 * mm, 192 * mm, 13 * mm)
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=17 * mm, rightMargin=17 * mm,
                            topMargin=15 * mm, bottomMargin=18 * mm,
                            title="Laporan Kebijakan PradanaLog")
    doc.build(story, onFirstPage=_foot, onLaterPages=_foot)
    return buf.getvalue()


# ---------------- Sidebar: sumber data ----------------
with st.sidebar:
    st.header("⚙️ Sumber Data")
    st.caption("Unggah 3 file Excel BPS untuk memperbarui model & seluruh tampilan otomatis.")
    up_prod = st.file_uploader("1. Dataset Produksi (.xlsx)", type=["xlsx"], key="up_prod")
    up_kons = st.file_uploader("2. Dataset Konsumsi (.xlsx)", type=["xlsx"], key="up_kons")
    up_ihk = st.file_uploader("3. Dataset IHK (.xlsx)", type=["xlsx"], key="up_ihk")
    if st.button("🔄 Proses & Perbarui Model", type="primary", use_container_width=True):
        if up_prod and up_kons and up_ihk:
            try:
                with st.spinner("Menjalankan pipeline: cleaning \u2192 K-Means \u2192 MOLP \u2192 frontier..."):
                    res = run_pipeline(up_prod.getvalue(), up_kons.getvalue(), up_ihk.getvalue())
                st.session_state["live"] = res
                # reset tampilan ke kondisi awal: Beras, tanpa provinsi terpilih
                st.session_state["kom_map"] = "Beras"
                st.session_state["prov_pick"] = PLACEHOLDER
                st.session_state.pop("prov_map", None)
                st.session_state.pop("last_map_sel", None)
                st.session_state["just_updated"] = True
                st.rerun()
            except ImportError:
                st.error("Butuh library tambahan. Jalankan: pip install pulp scikit-learn openpyxl")
            except Exception as e:
                st.error(f"Gagal memproses data: {e}")
        else:
            st.warning("Unggah ketiga file Excel terlebih dahulu.")
    if "live" in st.session_state:
        if st.session_state.pop("just_updated", False):
            st.success("Model diperbarui! Tampilan direset ke Beras.")
        rr, pp, ff = st.session_state["live"]
        n_kritis = int((pp["cluster"] == "Defisit Kritis").sum())
        st.success("Sumber aktif: **DATA UNGGAHAN**")
        st.caption(f"{len(rr)} rute \u00b7 {pp.shape[0]} provinsi \u00b7 {n_kritis} defisit kritis")
        if st.button("Kembali ke data bawaan", use_container_width=True):
            del st.session_state["live"]
            st.session_state["kom_map"] = "Beras"
            st.session_state["prov_pick"] = PLACEHOLDER
            st.session_state.pop("prov_map", None)
            st.session_state.pop("last_map_sel", None)
            st.rerun()
    else:
        st.caption("Sumber aktif: **data bawaan (BPS terlampir)**")

# ---------------- Pilih sumber data ----------------
if "live" in st.session_state:
    routes, profil, frontier = st.session_state["live"]
else:
    profil = load_profil()
    routes = load_routes()
    frontier = load_frontier()

if not GEOJSON_PATH.exists():
    st.error("File 'indonesia_provinces.geojson' tidak ditemukan. Letakkan se-folder dengan script.")
    st.stop()
geo = load_geojson()


def warna_nilai(val, vmax):
    if vmax <= 0:
        return [80, 84, 92, 120]
    t = max(min(val / vmax, 1.0), -1.0)
    if t > 0.02:
        return [46, 204, 113, 90 + int(150 * t)]
    if t < -0.02:
        return [231, 76, 60, 90 + int(150 * -t)]
    return [120, 124, 130, 110]


def df_to_html(df, right_cols=(), color_cols=(), center_cols=(), pct_cols=()):
    import html as _html
    def _th(c):
        al = "center" if c in center_cols else ("right" if c in right_cols else "left")
        return f"<th style='text-align:{al};'>{_html.escape(str(c))}</th>"
    head = "".join(_th(c) for c in df.columns)
    body = ""
    for _, row in df.iterrows():
        cells = ""
        for c in df.columns:
            v = row[c]
            style = ""
            if c in center_cols:
                style += "text-align:center;"
            elif c in right_cols:
                style += "text-align:right;"
            if c in pct_cols and isinstance(v, (int, float)) and not isinstance(v, bool):
                col = "#F0857A" if v > 0.05 else ("#5FD39A" if v < -0.05 else "#AEBFC2")
                style += f"color:{col};font-weight:700;"
                txt = f"{v:+.1f}%"
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                txt = f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"
                if c in color_cols:
                    col = "#5FD39A" if v > 0 else ("#F0857A" if v < 0 else "#AEBFC2")
                    style += f"color:{col};font-weight:600;"
            else:
                txt = _html.escape(str(v))
            cells += f"<td style='{style}'>{txt}</td>"
        body += f"<tr>{cells}</tr>"
    return (f"<table class='pl-table'><thead><tr>{head}</tr></thead>"
            f"<tbody>{body}</tbody></table>")


def build_deck(active_prov, komoditas_label, rute_kom, zoom):
    base = pdk.Layer(
        "GeoJsonLayer", data=geo, id="prov-layer",
        pickable=True, stroked=True, filled=True, auto_highlight=True,
        get_fill_color="properties.fill_color",
        get_line_color=[130, 140, 155, 110], line_width_min_pixels=0.5,
        highlight_color=[255, 255, 255, 90])
    layers = [base]
    if active_prov:
        feat = next((ft for ft in geo["features"]
                     if ft["properties"]["provinsi"] == active_prov), None)
        if feat:
            fc = {"type": "FeatureCollection", "features": [feat]}
            layers.append(pdk.Layer("GeoJsonLayer", data=fc, id="glow-out", pickable=False,
                                    stroked=True, filled=False,
                                    get_line_color=[255, 215, 0, 90], line_width_min_pixels=7))
            layers.append(pdk.Layer("GeoJsonLayer", data=fc, id="glow-in", pickable=False,
                                    stroked=True, filled=False,
                                    get_line_color=[255, 240, 150], line_width_min_pixels=2))
        rel = rute_kom[(rute_kom["asal"] == active_prov) | (rute_kom["tujuan"] == active_prov)]
        if len(rel):
            vmax = max(rel["volume_ton"].max(), 1)
            d = rel.assign(width=((rel["volume_ton"] / vmax) ** 0.5))
            layers.append(pdk.Layer(
                "ArcLayer", data=d,
                get_source_position=["asal_lon", "asal_lat"],
                get_target_position=["tuj_lon", "tuj_lat"],
                get_source_color=[80, 230, 150, 230], get_target_color=[245, 90, 75, 240],
                get_width="width", width_units="pixels", width_scale=8,
                width_min_pixels=2.5, width_max_pixels=8, get_height=0.5, pickable=False))
            pts = []
            for _, row in rel.iterrows():
                other = row["tujuan"] if row["asal"] == active_prov else row["asal"]
                is_t = row["asal"] == active_prov
                pts.append({"lon": PROVINSI[other][1], "lat": PROVINSI[other][0],
                            "color": [245, 90, 75] if is_t else [80, 230, 150]})
            layers.append(pdk.Layer(
                "ScatterplotLayer", data=pd.DataFrame(pts),
                get_position=["lon", "lat"], get_fill_color="color",
                get_radius=22000, radius_min_pixels=4, radius_max_pixels=9,
                stroked=True, get_line_color=[255, 255, 255], line_width_min_pixels=1,
                pickable=False))
    view = pdk.ViewState(latitude=-2.5, longitude=118, zoom=zoom, pitch=0)
    tooltip = {"html": "<b>{provinsi}</b><br/>Cluster: {cluster}<br/>"
                       + komoditas_label + ": {nilai} ribu ton<br/><i>klik untuk detail</i>",
               "style": {"backgroundColor": "#15181d", "color": "white",
                         "border": "1px solid #444", "borderRadius": "6px"}}
    return pdk.Deck(layers=layers, initial_view_state=view,
                    map_provider="carto", map_style="dark", tooltip=tooltip)


def rekomendasi(r, masuk, keluar, kom_label):
    nilai = int(r[LABEL2KEY[kom_label]])
    if nilai < 0:  # defisit pada komoditas terpilih
        # Prioritas berasal dari klaster K-Means lintas seluruh komoditas,
        # sedangkan angka defisit di kalimat yang sama khusus komoditas
        # terpilih. Cakupannya disebut agar keduanya tidak terbaca sebagai
        # satu ukuran. Sinyal per komoditas sudah tersedia pada metrik
        # Peringkat di panel yang sama.
        prio = "TINGGI" if r["cluster"] == "Defisit Kritis" else "SEDANG"
        if len(masuk):
            pemasok = ", ".join(masuk.sort_values("volume_ton", ascending=False)["asal"].head(2))
            return (f"**Peran: PENERIMA {kom_label} · Prioritas nasional {prio}.** Defisit {abs(nilai):,} rb ton. "
                    f"Dipasok dari **{pemasok}**. Waspada menjelang Ramadan/Lebaran & paceklik.")
        return (f"**Peran: PENERIMA {kom_label} · Prioritas nasional {prio}.** Defisit {abs(nilai):,} rb ton — "
                f"belum ada rute pada solusi ini (pemenuhan 80% dialokasikan ke wilayah prioritas lain).")
    if nilai > 0:  # surplus pada komoditas terpilih
        if len(keluar):
            tujuan = ", ".join(keluar.sort_values("volume_ton", ascending=False)["tujuan"].head(2))
            return (f"**Peran: PEMASOK {kom_label}.** Surplus {nilai:,} rb ton, disalurkan ke "
                    f"**{tujuan}** untuk menekan disparitas harga antarwilayah.")
        return (f"**Peran: CADANGAN PENYANGGA.** Surplus {kom_label} {nilai:,} rb ton **tidak terserap** "
                f"solusi optimal — kebutuhan wilayah terdekat sudah tercukupi sumber lain (model "
                f"meminimalkan jarak/biaya). Posisikan sebagai **buffer stock strategis** untuk "
                f"stabilisasi harga nasional & antisipasi guncangan.")
    return f"**{kom_label} mendekati seimbang** di provinsi ini."


# state klik-peta
if "prov_pick" not in st.session_state:
    st.session_state.prov_pick = PLACEHOLDER
if st.session_state.get("pending_click"):
    st.session_state.prov_pick = st.session_state.pop("pending_click")

st.markdown("""
<div class="pl-hero">
  <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;">
    <span class="pl-wordmark">PradanaLog</span>
    <span class="pl-pill">AI-Driven Food Distribution</span>
  </div>
  <div class="pl-tag">Platform Optimasi Distribusi Pangan Nasional &nbsp;·&nbsp; <b>MOLP</b> + <b>Machine Learning</b> &nbsp;·&nbsp; 34 Provinsi &nbsp;·&nbsp; 6 Komoditas Strategis</div>
</div>
""", unsafe_allow_html=True)
tab_peta, tab_frontier, tab_harga, tab_dampak, tab_siap, tab_kab = st.tabs(
    ["🗺️  Peta Distribusi", "📈  Frontier Kebijakan", "💹  Prediksi Harga",
     "🎯  Dampak & Roadmap", "🧭  Kesiapan Data", "🏛️  Tinjauan Kabupaten"])

# ============================================================ TAB 1: PETA
with tab_peta:
    ca, cb = st.columns([1, 1])
    komoditas_label = ca.selectbox("Komoditas", list(LABEL.values()), index=0, key="kom_map")
    kkey = LABEL2KEY[komoditas_label]
    cb.selectbox("Pilih provinsi (atau klik di peta)", [PLACEHOLDER] + sorted(PROVINSI), key="prov_pick")
    active = None if st.session_state.prov_pick == PLACEHOLDER else st.session_state.prov_pick

    vmax_kom = float(profil[kkey].abs().max())
    for ft in geo["features"]:
        p = ft["properties"]["provinsi"]
        if p in profil.index:
            v = int(profil.loc[p, kkey])
            ft["properties"].update({"cluster": profil.loc[p, "cluster"], "nilai": v,
                                     "fill_color": warna_nilai(v, vmax_kom)})
        else:
            ft["properties"].update({"cluster": "-", "nilai": 0, "fill_color": [80, 84, 92, 120]})
    rute_kom = routes[routes["komoditas"] == komoditas_label]

    if active is None:
        col_nat, col_map = st.columns([0.95, 4.3], gap="small")
        col_prov = None
        map_zoom = 3.45
    else:
        col_nat, col_map, col_prov = st.columns([0.85, 3.05, 1.5], gap="small")
        map_zoom = 3.15

    with col_nat:
        with st.container(border=True):
            n_sur = int((profil[kkey] > 0).sum())
            n_def = int((profil[kkey] < 0).sum())
            total_jt = rute_kom["volume_ton"].sum() / 1e6
            top_sur = profil[kkey].sort_values(ascending=False).head(3)
            top_def = profil[kkey].sort_values().head(3)

            def _li(items, color):
                out = ""
                for i, v in items.items():
                    out += (f"<div style='margin:4px 0;line-height:1.15;'>"
                            f"<span style='color:{color};'>●</span> "
                            f"<span style='font-size:.78rem;'>{i}</span><br>"
                            f"<span style='font-size:.8rem;font-weight:700;margin-left:13px;'>"
                            f"{int(v):,}</span></div>")
                return out

            st.markdown(f"##### Nasional · {komoditas_label}")
            st.markdown(f"""
<div style='display:grid;grid-template-columns:1fr 1fr;gap:6px 10px;'>
  <div><div style='font-size:.7rem;color:#9aa3ad;'>Prov. surplus</div>
       <div style='font-size:1.3rem;font-weight:700;color:#2ecc71;'>{n_sur}</div></div>
  <div><div style='font-size:.7rem;color:#9aa3ad;'>Prov. defisit</div>
       <div style='font-size:1.3rem;font-weight:700;color:#e74c3c;'>{n_def}</div></div>
  <div><div style='font-size:.7rem;color:#9aa3ad;'>Rute MOLP</div>
       <div style='font-size:1.3rem;font-weight:700;'>{len(rute_kom)}</div></div>
  <div><div style='font-size:.7rem;color:#9aa3ad;'>Total distribusi</div>
       <div style='font-size:1.3rem;font-weight:700;'>{total_jt:.2f} jt t</div></div>
</div>
<hr style='margin:10px 0;border:none;border-top:1px solid #333;'>
<div style='display:grid;grid-template-columns:1fr 1fr;gap:10px;'>
  <div><div style='font-weight:700;font-size:.82rem;margin-bottom:2px;'>Top surplus</div>{_li(top_sur, '#2ecc71')}</div>
  <div><div style='font-weight:700;font-size:.82rem;margin-bottom:2px;'>Top defisit</div>{_li(top_def, '#e74c3c')}</div>
</div>
""", unsafe_allow_html=True)

    with col_map:
        clicked = None
        try:
            ev = st.pydeck_chart(build_deck(active, komoditas_label, rute_kom, map_zoom),
                                 use_container_width=True, on_select="rerun",
                                 selection_mode="single-object", key="prov_map")
            try:
                objs = ev.selection.get("objects", {}) if ev and ev.selection else {}
                items = objs.get("prov-layer") or next((v for v in objs.values() if v), [])
                if items:
                    o = items[0]
                    clicked = (o.get("provinsi")
                               or o.get("properties", {}).get("provinsi"))
            except Exception:
                clicked = None
        except TypeError:
            st.pydeck_chart(build_deck(active, komoditas_label, rute_kom, map_zoom),
                            use_container_width=True)
            st.info("Fitur klik butuh Streamlit terbaru: pip install -U streamlit.")
        prev_sel = st.session_state.get("last_map_sel", "__init__")
        cur_sel = clicked if clicked else None
        if cur_sel != prev_sel:
            st.session_state["last_map_sel"] = cur_sel
            if cur_sel and cur_sel != st.session_state.prov_pick:
                st.session_state.pending_click = cur_sel
                st.rerun()
        st.markdown(
            f"**Legenda ({komoditas_label}):** "
            "<span style='color:#2ecc71'>hijau</span>=surplus · "
            "<span style='color:#e74c3c'>merah</span>=defisit · panah hijau→merah=arah aliran · "
            "<span style='color:#ffd700'>halo emas</span>=provinsi dipilih.",
            unsafe_allow_html=True)
        if active is not None:
            rel_sel = rute_kom[(rute_kom["asal"] == active) | (rute_kom["tujuan"] == active)]
            if len(rel_sel) == 0:
                nilai_a = int(profil.loc[active, kkey])
                if nilai_a > 0:
                    st.info(f"**{active}** surplus **{komoditas_label}** namun bukan sumber pada solusi "
                            f"optimal komoditas ini (sumber terdekat sudah mencukupi) → berperan sebagai "
                            f"**cadangan penyangga**. Detail di panel kanan; coba komoditas lain untuk melihat rutenya.")
                elif nilai_a < 0:
                    st.info(f"**{active}** defisit **{komoditas_label}** namun belum memperoleh rute pada "
                            f"solusi ini (alokasi 80% ke wilayah prioritas). Lihat panel kanan.")

    if col_prov is not None:
        with col_prov:
            with st.container(border=True):
                r = profil.loc[active]
                # Lencana mengikuti komoditas terpilih, bukan klaster lintas
                # komoditas. Klaster K-Means dihitung atas seluruh komoditas,
                # sedangkan angka di panel ini dan warna pada peta keduanya per
                # komoditas. Menyandingkannya tanpa keterangan cakupan membuat
                # provinsi seperti Lampung tampak bertentangan: surplus secara
                # agregat, namun defisit untuk bawang merah.
                nilai_kom = int(r[kkey])
                status_kom = "Surplus" if nilai_kom >= 0 else "Defisit"
                w = CLUSTER_WARNA["Surplus Tinggi" if nilai_kom >= 0
                                  else "Defisit Kritis"]
                badge = (f"background:rgb({w[0]},{w[1]},{w[2]});color:white;padding:2px 10px;"
                         f"border-radius:10px;font-weight:600;font-size:0.78em;")
                st.markdown(
                    f"##### {active} &nbsp;<span style='{badge}'>"
                    f"{status_kom} &middot; {komoditas_label}</span>",
                    unsafe_allow_html=True)
                st.caption(f"Klaster nasional seluruh komoditas: {r['cluster']} \u00b7 "
                           f"status di atas berlaku untuk {komoditas_label} saja.")
                keluar = routes[(routes["asal"] == active) & (routes["komoditas"] == komoditas_label)]
                masuk = routes[(routes["tujuan"] == active) & (routes["komoditas"] == komoditas_label)]
                keluar_all = routes[routes["asal"] == active]
                masuk_all = routes[routes["tujuan"] == active]
                nilai = int(r[kkey])
                rank = int((profil[kkey] < r[kkey]).sum()) + 1
                peran = "Pemasok" if nilai >= 0 else "Penerima"
                p1, p2 = st.columns(2)
                p1.metric(komoditas_label, f"{nilai:,} rb t", delta=peran)
                p2.metric("Peringkat", f"#{rank}", help="dari 34, 1=paling surplus")
                p3, p4 = st.columns(2)
                p3.metric("Kirim", f"{keluar['volume_ton'].sum():,.0f} t")
                p4.metric("Terima", f"{masuk['volume_ton'].sum():,.0f} t")
                st.info(rekomendasi(r, masuk, keluar, komoditas_label))
                t1, t2, t3 = st.tabs(["Semua komoditas", "📤 Kirim", "📥 Terima"])
                with t1:
                    dft1 = pd.DataFrame({
                        "Komoditas": [LABEL[k] for k in KOMODITAS],
                        "Nilai (rb t)": [int(r[k]) for k in KOMODITAS],
                        "Status": ["Surplus" if r[k] > 0 else ("Defisit" if r[k] < 0 else "Seimbang")
                                   for k in KOMODITAS]})
                    st.markdown(df_to_html(dft1, right_cols=("Nilai (rb t)",),
                                           color_cols=("Nilai (rb t)",)), unsafe_allow_html=True)
                with t2:
                    if len(keluar):
                        d = (keluar[["tujuan", "volume_ton", "biaya_rp"]]
                             .sort_values("volume_ton", ascending=False)
                             .rename(columns={"tujuan": "Tujuan", "volume_ton": "Ton", "biaya_rp": "Biaya (jt)"}))
                        st.markdown(df_to_html(d, right_cols=("Ton", "Biaya (jt)")), unsafe_allow_html=True)
                    else:
                        st.caption("Tidak ada rute keluar.")
                with t3:
                    if len(masuk):
                        d = (masuk[["asal", "volume_ton", "biaya_rp"]]
                             .sort_values("volume_ton", ascending=False)
                             .rename(columns={"asal": "Asal", "volume_ton": "Ton", "biaya_rp": "Biaya (jt)"}))
                        st.markdown(df_to_html(d, right_cols=("Ton", "Biaya (jt)")), unsafe_allow_html=True)
                    else:
                        st.caption("Tidak ada rute masuk.")

# ============================================================ TAB HARGA: PREDIKSI
@st.cache_data
def load_harga():
    f1, f2, f3 = HERE / "harga_bulanan_panel.csv", HERE / "prediksi_harga.csv", HERE / "metrik_harga.csv"
    if not (f1.exists() and f2.exists()):
        return None, None, None
    hist = pd.read_csv(f1)
    pred = pd.read_csv(f2)
    met = pd.read_csv(f3) if f3.exists() else None
    return hist, pred, met


with tab_harga:
    hist, pred, met = load_harga()
    if hist is None:
        st.info("Letakkan **harga_bulanan_panel.csv** dan **prediksi_harga.csv** se-folder dengan "
                "aplikasi untuk mengaktifkan tab ini.")
    else:
        st.markdown("#### Prediksi Harga Komoditas (3 Bulan ke Depan)")
        st.caption("Sumber: PIHPS Bank Indonesia (harga eceran bulanan, Feb 2020–Jul 2026) · "
                   "Pemilihan metode berdasarkan backtest rolling-origin 24 bulan pada "
                   "34.344 titik uji, diukur dengan MASE terhadap peramal naif. "
                   "Persistensi optimal untuk beras di semua horizon; ensemble dipakai "
                   "hanya bila MASE < 0,95 — cabai rawit di semua horizon (0,80–0,90), "
                   "bawang merah pada horizon 2 dan 3 bulan, cabai besar pada horizon "
                   "3 bulan. Sembilan dari 140 pasangan provinsi–komoditas disaring dari "
                   "peramalan: tujuh tanpa observasi di PIHPS, satu berriwayat kurang "
                   "dari 14 bulan, satu berhenti melapor sejak Desember 2022.")
        hkoms = sorted(pred["komoditas"].unique())
        c1, c2 = st.columns([1, 2])
        with c1:
            kom_h = st.selectbox("Komoditas", hkoms,
                                 index=hkoms.index("Beras") if "Beras" in hkoms else 0, key="kom_harga")
            provs_h = sorted(pred[pred.komoditas == kom_h]["provinsi"].unique())
            default_p = "DKI Jakarta" if "DKI Jakarta" in provs_h else provs_h[0]
            prov_h = st.selectbox("Provinsi", provs_h, index=provs_h.index(default_p), key="prov_harga")

            pk = pred[(pred.komoditas == kom_h) & (pred.provinsi == prov_h)].sort_values("h")
            if len(pk):
                now = pk["harga_kini"].iloc[0]
                p3 = pk[pk.h == 3]["harga_prediksi"].iloc[0]
                chg = (p3 / now - 1) * 100
                m1, m2 = st.columns(2)
                m1.metric("Harga saat ini (Jul 2026)", f"Rp {now:,.0f}")
                m2.metric("Proyeksi Okt 2026", f"Rp {p3:,.0f}", delta=f"{chg:+.1f}%",
                          delta_color="inverse")
                if chg > 5:
                    sinyal, sw = "⚠️ POTENSI KENAIKAN — siapkan pasokan/operasi pasar", "#E67E22"
                elif chg < -5:
                    sinyal, sw = "▼ Tekanan turun — perhatikan harga di tingkat petani", "#3FCF87"
                else:
                    sinyal, sw = "● Stabil — dalam rentang normal", "#AEC6CC"
                st.markdown(f"<div style='border:1px solid {sw};border-radius:10px;padding:8px 12px;"
                            f"color:{sw};font-weight:600;'>{sinyal}</div>", unsafe_allow_html=True)
                # MAPE tidak ditampilkan sendirian: selalu bersama lantai naif dan MASE
                caption_akurasi(kom_h, h=3)
        with c2:
            h = hist[(hist.komoditas == kom_h) & (hist.provinsi == prov_h)].dropna(subset=["harga"]).copy()
            h["t"] = pd.PeriodIndex(h.bulan, freq="M").to_timestamp()
            h = h.sort_values("t").tail(30)
            pk2 = pk.copy()
            pk2["t"] = pd.PeriodIndex(pk2.bulan, freq="M").to_timestamp()
            if HAS_ALT and len(h):
                base = alt.Chart(h).mark_line(color="#3FCF87", strokeWidth=2.2).encode(
                    x=alt.X("t:T", title=None), y=alt.Y("harga:Q", title="Rp/kg",
                                                        scale=alt.Scale(zero=False)))
                # sambungkan titik terakhir histori ke prediksi
                bridge = pd.concat([h.tail(1)[["t", "harga"]].rename(columns={"harga": "harga_prediksi"}),
                                    pk2[["t", "harga_prediksi"]]])
                band = alt.Chart(pk2).mark_area(opacity=0.18, color="#EAC65E").encode(
                    x="t:T", y="lo:Q", y2="hi:Q")
                fline = alt.Chart(bridge).mark_line(color="#EAC65E", strokeDash=[6, 4],
                                                    strokeWidth=2.4).encode(x="t:T", y="harga_prediksi:Q")
                fpt = alt.Chart(pk2).mark_point(size=90, color="#EAC65E", filled=True).encode(
                    x="t:T", y="harga_prediksi:Q")
                ch = (band + base + fline + fpt).properties(height=330).configure(
                    background="transparent").configure_view(strokeWidth=0).configure_axis(
                    labelColor="#C7D3D5", titleColor="#C7D3D5",
                    gridColor="rgba(255,255,255,0.08)", domainColor="rgba(255,255,255,0.15)")
                st.altair_chart(ch, use_container_width=True, theme=None)
                st.caption("Garis hijau = histori · garis emas putus-putus = proyeksi · "
                           "pita emas = rentang ketidakpastian.")
            elif len(h):
                st.line_chart(h.set_index("t")["harga"], height=330)

        # Radar hanya aktif bila backtest membuktikan peramalan mengungguli persistensi
        render_radar(pred, kom_h, df_to_html, h=3)

# ============================================================ TAB 2: FRONTIER
with tab_frontier:
    st.markdown("#### Frontier Kebijakan: Ketahanan Pangan vs Biaya Logistik")
    st.caption("Berapa biaya untuk menjamin tiap tingkat pemenuhan defisit? Geser slider untuk "
               "melihat trade-off — dasar keputusan anggaran vs target ketahanan pangan.")
    fkoms = sorted(frontier["komoditas"].unique()) if len(frontier) else []
    if not fkoms:
        st.info("Data frontier belum tersedia. Unggah data & proses model, atau pastikan "
                "frontier_delta.csv ada di folder.")
        st.stop()
    c1, c2 = st.columns([1, 2])
    kom_f = c1.selectbox("Komoditas", fkoms, index=fkoms.index("Beras") if "Beras" in fkoms else 0)
    delta_sel = c1.slider("Target pemenuhan defisit δ (%)", 50, 100, 80, step=10)

    fr_k = frontier[frontier["komoditas"] == kom_f].sort_values("delta_pct")
    row_sel = fr_k[fr_k["delta_pct"] == delta_sel].iloc[0]
    row_80 = fr_k[fr_k["delta_pct"] == 80].iloc[0]
    biaya_sel = row_sel["biaya_juta"]
    delta_vs80 = (biaya_sel / row_80["biaya_juta"] - 1) * 100

    m1, m2, m3 = c1.columns(3)
    m1.metric("Biaya logistik", f"Rp {biaya_sel/1000:,.0f} M")
    m2.metric("vs default 80%", f"{delta_vs80:+.0f}%")
    if delta_sel < 100:
        nxt = fr_k[fr_k["delta_pct"] == delta_sel + 10]
        inc = (nxt.iloc[0]["biaya_juta"] - biaya_sel) / 1000 if len(nxt) else 0
        m3.metric("Naik +10% berikut", f"Rp {inc:,.0f} M")
    else:
        m3.metric("Status", "Penuh 100%")

    chart_df = fr_k.assign(biaya_M=fr_k["biaya_juta"] / 1000)
    if HAS_ALT:
        line = alt.Chart(chart_df).mark_line(color="#3FCF87", point=alt.OverlayMarkDef(
            color="#0E262B", stroke="#3FCF87", strokeWidth=2, size=80)).encode(
            x=alt.X("delta_pct:Q", title="Pemenuhan defisit δ (%)", scale=alt.Scale(domain=[45, 105])),
            y=alt.Y("biaya_M:Q", title="Biaya logistik (miliar Rp)"))
        pt = alt.Chart(chart_df[chart_df.delta_pct == delta_sel]).mark_point(
            size=320, color="#EAC65E", filled=True).encode(x="delta_pct:Q", y="biaya_M:Q")
        rule = alt.Chart(pd.DataFrame({"d": [delta_sel]})).mark_rule(
            strokeDash=[4, 4], color="#EAC65E").encode(x="d:Q")
        chart = ((line + rule + pt).properties(height=340)
                 .configure(background="transparent")
                 .configure_view(strokeWidth=0)
                 .configure_axis(labelColor="#C7D3D5", titleColor="#C7D3D5",
                                 gridColor="rgba(255,255,255,0.08)",
                                 domainColor="rgba(255,255,255,0.15)"))
        c2.altair_chart(chart, use_container_width=True, theme=None)
    else:
        c2.line_chart(chart_df.set_index("delta_pct")["biaya_M"], height=340)

    st.info("**Temuan kebijakan:** biaya meningkat makin curam pada pemenuhan tinggi — "
            "**10% terakhir paling mahal** karena menjangkau wilayah defisit tersulit di "
            "Kawasan Timur Indonesia. Ini justifikasi kuantitatif untuk **subsidi logistik "
            "lintas pulau yang tepat sasaran**, bukan subsidi merata.\n\n"
            "**Catatan robustness:** solusi optimal stabil terhadap pembobotan biaya/disparitas "
            "(constraint struktural dominan) — parameter yang benar-benar menggeser hasil adalah "
            "target pemenuhan δ, bukan preferensi subjektif analis.")

# ============================================================ TAB 3: DAMPAK & ROADMAP
with tab_dampak:
    st.markdown("#### Dampak Sistem & Rekomendasi Kebijakan")
    tot_rute = len(routes)
    tot_vol = routes["volume_ton"].sum()
    tot_biaya = routes["biaya_rp"].sum()
    prov_terlayani = routes["tujuan"].nunique()
    kti_rute = routes[routes["tujuan"].isin(KTI)]
    kti_vol = kti_rute["volume_ton"].sum()

    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Total rute MOLP", f"{tot_rute}")
    d2.metric("Volume terdistribusi", f"{tot_vol/1e6:.2f} jt ton")
    d3.metric("Provinsi defisit terlayani", f"{prov_terlayani}")
    d4.metric("Volume ke KTI", f"{kti_vol/1e3:,.0f} rb ton")

    st.divider()
    cL, cR = st.columns([1, 1])
    with cL:
        st.markdown("##### 🎯 Rekomendasi Kebijakan Otomatis")
        net = profil[KOMODITAS].sum(axis=1).sort_values()
        top3 = net.head(3)
        prio = " · ".join(f"{i}" for i in top3.index)
        st.markdown(
            f"1. **Prioritaskan wilayah defisit kritis:** {prio} — alokasikan lebih awal "
            "sebelum lonjakan harga menjelang Ramadan/Lebaran.\n\n"
            "2. **Subsidi logistik tepat sasaran ke Kawasan Timur Indonesia.** Rute lintas "
            "pulau ke Papua/Maluku/NTT paling mahal per ton — jadikan tanggung jawab fiskal "
            "negara, bukan mekanisme pasar (lihat tab Frontier).\n\n"
            "3. **Integrasi ke GNPIP & rapat koordinasi TPID.** Output 117 rute dapat langsung "
            "dipakai sebagai bahan keputusan distribusi antarprovinsi.\n\n"
            "4. **Perkuat backbone efisien Jawa↔Jawa & Sumatera↔Sumatera** sebagai penyeimbang "
            "biaya distribusi nasional.")
    with cR:
        st.markdown("##### 🗺️ Roadmap Pengembangan (12 bulan)")
        steps = [
            ("Bulan 1–2", "Finalisasi pipeline data & model; migrasi dari Colab ke sistem terstruktur."),
            ("Bulan 3–4", "Backend API + database (FastAPI/PostgreSQL); integrasi data berkala BPS."),
            ("Bulan 5–6", "Dashboard MVP + uji internal; integrasi Panel Harga Badan Pangan."),
            ("Bulan 7–12", "Pilot 2–3 pemerintah provinsi prioritas; iterasi berbasis umpan balik TPID."),
        ]
        for i, (t, desc) in enumerate(steps, 1):
            st.markdown(
                f"<div style='display:flex;gap:10px;margin-bottom:8px;'>"
                f"<div style='min-width:26px;height:26px;border-radius:50%;background:#2C7A4B;"
                f"color:white;font-weight:700;text-align:center;line-height:26px;'>{i}</div>"
                f"<div><b>{t}</b><br><span style='font-size:.86rem;color:#c9c9c9;'>{desc}</span></div>"
                f"</div>", unsafe_allow_html=True)

    st.divider()
    st.markdown("##### 📊 Cakupan Distribusi per Komoditas")
    cov = (routes.groupby("komoditas")
           .agg(Rute=("asal", "size"), Volume_ton=("volume_ton", "sum"),
                Biaya_juta=("biaya_rp", "sum"))
           .reset_index().rename(columns={"komoditas": "Komoditas"}))
    cov["Volume_ton"] = cov["Volume_ton"].round(0).astype(int)
    cov["Biaya_juta"] = cov["Biaya_juta"].round(0).astype(int)
    cov = cov.rename(columns={"Volume_ton": "Volume (ton)", "Biaya_juta": "Biaya (juta Rp)"})
    st.markdown(df_to_html(cov, right_cols=("Rute", "Volume (ton)", "Biaya (juta Rp)")),
                unsafe_allow_html=True)

    st.divider()
    st.markdown("##### 📄 Laporan Kebijakan Lengkap (siap dibawa ke rapat TPID)")
    st.caption("Satu PDF berisi ringkasan nasional + tinjauan tiap provinsi: profil komoditas, "
               "rute pasok/terima, dan rekomendasi otomatis.")
    try:
        pdf_bytes = build_pdf(routes, profil)
        st.download_button("⬇️  Unduh Laporan Kebijakan (PDF)", pdf_bytes,
                           file_name="Laporan_Kebijakan_PradanaLog.pdf",
                           mime="application/pdf", type="primary", use_container_width=True)
    except ImportError:
        st.warning("Untuk ekspor PDF, install dulu: `pip install reportlab`")
    except Exception as e:
        st.error(f"Gagal membuat PDF: {e}")

with tab_siap:
    render_tab_kesiapan(df_to_html)


with tab_kab:
    render_tab_kabupaten(df_to_html)
