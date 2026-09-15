"""
optimasi_kabupaten.py — MOLP distribusi antarkabupaten/kota dalam satu provinsi
================================================================================
Menghasilkan kab_rute.csv (skema KOLOM_RUTE di data_kabupaten.py) yang dibaca
tab Tinjauan Kabupaten untuk menggambar busur distribusi, tonase, dan biaya.

Formulasi SAMA dengan lapisan antarprovinsi di pradanalog_map.py (_solve_molp),
supaya dua tingkat bisa dibandingkan apa adanya:

    min  wb·Σ x_ij·b_ij/max b  +  wd·Σ x_ij·|h_j − h̄|/max|h − h̄|  +  wj·Σ x_ij·d_ij/max d
    s.t. Σ_j x_ij ≤ S_i                  (pasokan tidak melebihi surplus)
         Σ_i x_ij ≥ δ·D_j                (pemenuhan defisit minimal δ)
         x_ij ≤ θ·S_i                    (tidak ada satu rute memonopoli surplus)
         x_ij ≥ 0

    d_ij  = jarak haversine antartitik pusat poligon kabupaten (km), diambil dari
            kab_batas.geojson; bila berkas itu tidak ada, dari lat/lon kab_profil.csv
    b_ij  = rata-rata _bpp(lon) asal–tujuan × d_ij   (Rp/ton, sama dengan nasional)
    h_j   = median harga 7 hari terakhir di kabupaten tujuan (SISKAPERBAPO)

CATATAN YANG PERLU DISEBUT SAAT PRESENTASI
  1. Jarak garis lurus antartitik pusat poligon, belum jarak jalan.
  2. Tarif _bpp mewarisi asumsi lapisan nasional (angka 800, 15, 95 belum
     berdasar empiris); di dalam satu provinsi tarifnya nyaris datar.
  3. Neraca kabupaten memakai konsumsi per kapita nasional (Susenas).
  4. Surplus yang sudah dialokasikan ke provinsi lain pada lapisan nasional
     belum dikurangkan; model ini hanya menyeimbangkan defisit internal.

Jalankan:  python optimasi_kabupaten.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
KOM = ["beras", "jagung", "bawang", "cabai_besar", "cabai_rawit", "kentang"]
DELTA, THETA = 0.8, 0.4
BOBOT = dict(wb=0.4, wd=0.4, wj=0.2)


def _haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = (np.sin(np.radians(lat2 - lat1) / 2) ** 2
         + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2)
    return float(2 * R * np.arcsin(np.sqrt(a)))


def _bpp(lon):
    """Identik dengan pradanalog_map._bpp — jangan diubah di satu tempat saja."""
    return max(500.0, 800.0 + 15.0 * (lon - 95.0))


def pakai_titik_batas(profil: pd.DataFrame, jalur=HERE / "kab_batas.geojson") -> pd.DataFrame:
    """
    Ganti lat/lon kab_profil (perkiraan kasar, sebagian meleset 12–30 km) dengan
    titik pusat poligon batas wilayah, supaya jarak rute dan letak busur di peta
    berasal dari sumber yang sama.
    """
    import json
    jalur = Path(jalur)
    if not jalur.exists():
        return profil
    with open(jalur, encoding="utf-8") as f:
        titik = {ft["properties"]["kabkota"]: (ft["properties"]["lat"], ft["properties"]["lon"])
                 for ft in json.load(f)["features"]}
    hasil = profil.copy()
    ada = hasil.kabkota.isin(titik)
    hasil.loc[ada, "lat"] = hasil.loc[ada, "kabkota"].map(lambda k: titik[k][0])
    hasil.loc[ada, "lon"] = hasil.loc[ada, "kabkota"].map(lambda k: titik[k][1])
    return hasil


def harga_terakhir(harga: pd.DataFrame, kom: str, hari: int = 7) -> dict:
    hk = harga[harga.komoditas == kom]
    if not len(hk):
        return {}
    batas = hk.tanggal.max() - pd.Timedelta(days=hari - 1)
    return hk[hk.tanggal >= batas].groupby("kabkota").harga.median().to_dict()


def solve_kabupaten(profil: pd.DataFrame, harga: pd.DataFrame, kom: str,
                    delta: float = DELTA, theta: float = THETA,
                    wb=BOBOT["wb"], wd=BOBOT["wd"], wj=BOBOT["wj"]):
    """
    Kembalikan (DataFrame rute, keterangan). DataFrame kosong bila tidak ada
    surplus/defisit, atau bila soal tidak layak pada δ yang diminta.
    """
    import pulp
    from pulp import LpMinimize, LpProblem, LpStatus, LpVariable, lpSum, value

    kosong = pd.DataFrame(columns=["provinsi", "asal", "tujuan", "komoditas",
                                   "volume_ton", "biaya_rp", "jarak_km"])
    idx = profil.set_index("kabkota")
    S = {k: float(v) for k, v in idx[kom].items() if v > 0}
    D = {k: float(-v) for k, v in idx[kom].items() if v < 0}
    if not S or not D:
        return kosong, "tidak ada pasangan surplus–defisit"

    hrg = harga_terakhir(harga, kom) if harga is not None else {}
    havg = float(np.mean(list(hrg.values()))) if hrg else 0.0

    jr, bk = {}, {}
    for i in S:
        for j in D:
            d = _haversine(idx.at[i, "lat"], idx.at[i, "lon"], idx.at[j, "lat"], idx.at[j, "lon"])
            jr[(i, j)] = d
            bk[(i, j)] = (_bpp(idx.at[i, "lon"]) + _bpp(idx.at[j, "lon"])) / 2 * d
    mb, mj = max(bk.values()) or 1, max(jr.values()) or 1
    md = max(abs(hrg.get(j, havg) - havg) for j in D) or 1

    prob = LpProblem(f"kab_{kom}", LpMinimize)
    x = {k: LpVariable(f"x{n}", lowBound=0) for n, k in enumerate(bk)}
    prob += (wb * lpSum(x[k] * bk[k] / mb for k in x)
             + wd * lpSum(x[k] * abs(hrg.get(k[1], havg) - havg) / md for k in x)
             + wj * lpSum(x[k] * jr[k] / mj for k in x))
    for i in S:
        prob += lpSum(x[(i, j)] for j in D) <= S[i]
    for j in D:
        prob += lpSum(x[(i, j)] for i in S) >= delta * D[j]
    for k in x:
        prob += x[k] <= theta * S[k[0]]
    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    if LpStatus[prob.status] != "Optimal":
        return kosong, f"tidak layak pada δ={delta:.0%} ({LpStatus[prob.status]})"

    prov = str(profil["provinsi"].iloc[0])
    rows = []
    for k, var in x.items():
        v = value(var)
        if v and v > 0.1:
            rows.append(dict(provinsi=prov, asal=k[0], tujuan=k[1], komoditas=kom,
                             volume_ton=round(v, 1),
                             biaya_rp=round(v * bk[k] / 1e6, 2),   # juta rupiah
                             jarak_km=round(jr[k], 1)))
    return pd.DataFrame(rows, columns=kosong.columns), "optimal"


def bangun_semua(profil, harga, delta=DELTA):
    hasil, catatan = [], {}
    for kom in KOM:
        df, ket = solve_kabupaten(profil, harga, kom, delta=delta)
        catatan[kom] = ket
        if len(df):
            hasil.append(df)
    rute = (pd.concat(hasil, ignore_index=True) if hasil
            else pd.DataFrame(columns=["provinsi", "asal", "tujuan", "komoditas",
                                       "volume_ton", "biaya_rp", "jarak_km"]))
    return rute, catatan


if __name__ == "__main__":
    profil = pd.read_csv(HERE / "kab_profil.csv")
    harga = pd.read_csv(HERE / "kab_harga.csv", parse_dates=["tanggal"])
    rute, catatan = bangun_semua(pakai_titik_batas(profil), harga)

    from data_kabupaten import validasi
    validasi(profil, harga, rute)
    rute.to_csv(HERE / "kab_rute.csv", index=False)

    print(f"kab_rute.csv: {len(rute)} rute (δ={DELTA:.0%}, θ={THETA:.0%})")
    for kom in KOM:
        r = rute[rute.komoditas == kom]
        dfc = -profil.loc[profil[kom] < 0, kom].sum()
        terima = r.volume_ton.sum()
        print(f"  {kom:12s} {len(r):3d} rute · {terima:>12,.0f} t · "
              f"Rp {r.biaya_rp.sum():>10,.1f} jt · pemenuhan "
              f"{(terima / dfc * 100) if dfc else 0:5.1f}% · {catatan[kom]}")
