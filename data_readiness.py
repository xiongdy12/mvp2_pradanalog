"""
data_readiness.py — Indeks Kesiapan Data (IKD) PradanaLog, versi 2
==================================================================
Perubahan dari versi 1, menutup dua temuan audit:

1. Katalog dipecah jadi tiga berkas long-format (produksi, harga, wilayah)
   dengan sumber, URL, tanggal akses, dan status verifikasi per baris.
2. Enam dimensi kini dihitung dari data per komoditas, sehingga C, K, T, A
   dan G semuanya bervariasi antarprovinsi. Versi 1 punya tiga dimensi
   konstan yang membuat indeks efektif hanya berjalan di tiga sumbu.

Tambahan: titik_balik() menghitung pada nilai berapa sebuah parameter yang
belum terverifikasi mengubah pemenang. Kalau peringkat bergantung pada satu
tebakan, penulis wajib tahu dan menyebutnya.

Pakai:
    from data_readiness import compute_ikd, sensitivity, audit_trail, titik_balik
    python data_readiness.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
KOM = ["beras", "jagung", "bawang", "cabai_besar", "cabai_rawit", "kentang"]
N_KOMODITAS = len(KOM)

TAHUN_IDEAL = 8          # panjang deret nyaman untuk XGBoost-LSTM
LAG_TOLERANSI = 18       # bulan
MIN_KAB_PRODUKSI = 3     # produksi dianggap berarti jika tercatat di >=3 kab/kota
GATE_MIN_KOMODITAS = 4   # syarat gugur: minimal 4 dari 6 komoditas

FREK_SKOR = {"harian": 1.00, "mingguan": 0.75, "bulanan": 0.50, "tidak ada": 0.0}

BOBOT = {
    "C_cakupan_spasial":         0.20,
    "K_kelengkapan_komoditas":   0.25,
    "H_granularitas_harga":      0.25,
    "T_kedalaman_deret":         0.10,
    "A_aktualitas":              0.10,
    "G_geospasial_konektivitas": 0.10,
}

BOBOT_STATUS = {"terverifikasi": 1.0, "sebagian": 0.5, "estimasi": 0.0}


# ------------------------------------------------------------------ pemuatan
class KatalogTidakSah(ValueError):
    """Katalog cacat. Lebih baik indeks menolak jalan daripada memberi skor palsu."""


def validasi_katalog(prod, harga, wil, ketat: bool = True) -> list:
    """
    Periksa keutuhan katalog sebelum dihitung. Tanpa ini, satu provinsi yang
    barisnya hilang akan diam-diam dianggap berskor nol, dan nilai mustahil
    seperti n_kabkota_harga=999 diterima tanpa protes.
    """
    m = []
    prov_p = set(prod.provinsi)
    prov_h = set(harga.provinsi)
    prov_w = set(wil.provinsi)

    if prov_p != prov_w:
        m.append(f"Provinsi di katalog produksi dan wilayah tidak sama: "
                 f"{sorted(prov_p ^ prov_w)}")
    if prov_p != prov_h:
        m.append(f"Provinsi di katalog produksi dan harga tidak sama: "
                 f"{sorted(prov_p ^ prov_h)}")

    for nama, df in [("produksi", prod), ("harga", harga)]:
        asing = set(df.komoditas) - set(KOM)
        if asing:
            # Komoditas di luar daftar membuat K melebihi 1 karena penyebutnya
            # tetap 6, dan diam-diam ikut menggeser rata-rata H.
            m.append(f"Katalog {nama}: komoditas di luar daftar {sorted(asing)}. "
                     f"Tambahkan dulu ke KOM di data_readiness.py bila memang dipakai.")
        for prov, g in df.groupby("provinsi"):
            hilang = set(KOM) - set(g.komoditas)
            if hilang:
                m.append(f"Katalog {nama}: {prov} kehilangan komoditas {sorted(hilang)}")
            if g.komoditas.duplicated().any():
                m.append(f"Katalog {nama}: {prov} punya baris komoditas ganda")

    ganda = wil[wil.provinsi.duplicated()].provinsi.tolist()
    if ganda:
        # _agregasi memakai .iloc[0]; baris ganda akan dipilih diam-diam.
        m.append(f"Katalog wilayah: provinsi muncul lebih dari sekali {sorted(set(ganda))}")

    # Semua perbandingan rentang memakai salinan numerik. Tanpa ini, satu sel
    # berisi teks membuat program mati dengan TypeError alih-alih memberi pesan
    # yang bisa ditindaklanjuti.
    prod_n = prod.assign(**{c: pd.to_numeric(prod[c], errors="coerce")
                            for c in ["n_kabkota", "n_kabkota_produksi",
                                      "tahun_awal", "tahun_akhir"]})
    harga_n = harga.assign(**{c: pd.to_numeric(harga[c], errors="coerce")
                              for c in ["n_kabkota", "n_kabkota_harga", "keterisian"]})
    wil_n = wil.assign(fraksi_terhubung_darat=pd.to_numeric(
        wil.fraksi_terhubung_darat, errors="coerce"))

    lebih = prod_n[prod_n.n_kabkota_produksi > prod_n.n_kabkota]
    for _, r in lebih.iterrows():
        m.append(f"Produksi: {r.provinsi}/{r.komoditas} mencatat "
                 f"{r.n_kabkota_produksi} kab berproduksi dari {r.n_kabkota} kab yang ada")

    lebih = harga_n[harga_n.n_kabkota_harga > harga_n.n_kabkota]
    for _, r in lebih.iterrows():
        m.append(f"Harga: {r.provinsi}/{r.komoditas} memantau {r.n_kabkota_harga} "
                 f"kab dari {r.n_kabkota} kab yang ada")

    # Sel kosong lolos dari perbandingan < dan > karena NaN selalu False, jadi
    # diperiksa lebih dulu dan terpisah.
    numerik = {"produksi": (prod, ["n_kabkota", "n_kabkota_produksi",
                                   "tahun_awal", "tahun_akhir"]),
               "harga": (harga, ["n_kabkota", "n_kabkota_harga", "keterisian"]),
               "wilayah": (wil, ["n_kabkota", "geojson_kabkota",
                                 "fraksi_terhubung_darat", "lag_bulan_produksi"])}
    for nama, (df, kolom) in numerik.items():
        for c in kolom:
            if c not in df.columns:
                m.append(f"Katalog {nama}: kolom {c} tidak ada")
                continue
            nilai = pd.to_numeric(df[c], errors="coerce")
            kosong = nilai.isna()
            if kosong.any():
                contoh = df.loc[kosong, "provinsi"].unique()[:3]
                m.append(f"Katalog {nama}: kolom {c} punya {int(kosong.sum())} sel "
                         f"kosong atau bukan angka (mis. {list(contoh)})")
            if (nilai < 0).any():
                m.append(f"Katalog {nama}: kolom {c} punya nilai negatif")

    buruk = harga_n[(harga_n.keterisian < 0) | (harga_n.keterisian > 1)]
    for _, r in buruk.iterrows():
        m.append(f"Harga: keterisian {r.provinsi}/{r.komoditas} = {r.keterisian}, "
                 "harus di antara 0 dan 1")

    tak_dikenal = set(harga.frekuensi.str.lower()) - set(FREK_SKOR)
    if tak_dikenal:
        m.append(f"Frekuensi tidak dikenal: {sorted(tak_dikenal)} "
                 f"(yang sah: {sorted(FREK_SKOR)})")

    for nama, df in [("produksi", prod), ("harga", harga), ("wilayah", wil)]:
        salah = set(df.status_verifikasi.str.lower()) - set(BOBOT_STATUS)
        if salah:
            m.append(f"Katalog {nama}: status tidak dikenal {sorted(salah)}")

    salah_tahun = prod_n[prod_n.tahun_akhir < prod_n.tahun_awal]
    for _, r in salah_tahun.iterrows():
        m.append(f"Produksi: {r.provinsi}/{r.komoditas} tahun_akhir < tahun_awal")

    buruk = wil_n[(wil_n.fraksi_terhubung_darat < 0) | (wil_n.fraksi_terhubung_darat > 1)]
    for _, r in buruk.iterrows():
        m.append(f"Wilayah: fraksi_terhubung_darat {r.provinsi} = "
                 f"{r.fraksi_terhubung_darat}, harus di antara 0 dan 1")

    if m and ketat:
        raise KatalogTidakSah("Katalog tidak lolos pemeriksaan:\n  - " + "\n  - ".join(m))
    return m


def load_katalog(folder: Path = HERE, validasi: bool = True):
    prod = pd.read_csv(folder / "katalog_produksi.csv")
    harga = pd.read_csv(folder / "katalog_harga.csv")
    wil = pd.read_csv(folder / "katalog_wilayah.csv")
    if validasi:
        validasi_katalog(prod, harga, wil)
    return prod, harga, wil


# ------------------------------------------------------------------ dimensi
def _per_komoditas(prod: pd.DataFrame, harga: pd.DataFrame) -> pd.DataFrame:
    """Skor mentah tiap pasangan provinsi-komoditas."""
    p = prod.copy()
    p["c"] = (p.n_kabkota_produksi / p.n_kabkota).clip(0, 1)
    p["ada_produksi"] = p.n_kabkota_produksi >= MIN_KAB_PRODUKSI
    p["t"] = ((p.tahun_akhir - p.tahun_awal + 1) / TAHUN_IDEAL).clip(0, 1)

    h = harga.copy()
    h["frek"] = h.frekuensi.str.lower().map(FREK_SKOR).fillna(0.0)
    h["h"] = ((h.n_kabkota_harga / h.n_kabkota).clip(0, 1) * h.frek * h.keterisian).clip(0, 1)
    h["a_harga"] = h.frek   # sumber harian dianggap tanpa jeda

    return p.merge(h[["provinsi", "komoditas", "h", "a_harga", "sistem"]],
                   on=["provinsi", "komoditas"], how="left")


def _agregasi(pk: pd.DataFrame, wil: pd.DataFrame) -> pd.DataFrame:
    baris = []
    for prov, g in pk.groupby("provinsi"):
        ada = g[g.ada_produksi]
        w = wil[wil.provinsi == prov].iloc[0]
        a_prod = float(np.clip(1 - w.lag_bulan_produksi / LAG_TOLERANSI, 0, 1))

        # C dan T hanya atas komoditas yang benar-benar diproduksi, supaya
        # komoditas yang absen tidak dihukum dua kali (itu tugas K).
        C = float(ada.c.mean()) if len(ada) else 0.0
        T = float(ada.t.mean()) if len(ada) else 0.0
        K = min(len(ada) / N_KOMODITAS, 1.0)
        # H dan A atas keenam komoditas: absennya harga kentang dan jagung
        # memang menurunkan kesiapan sistem, dan itu harus terlihat.
        H = float(g.h.fillna(0).mean())
        A = 0.5 * a_prod + 0.5 * float(g.a_harga.fillna(0).mean())
        G = float(w.geojson_kabkota + w.fraksi_terhubung_darat) / 2

        baris.append(dict(provinsi=prov, C_cakupan_spasial=C,
                          K_kelengkapan_komoditas=K, H_granularitas_harga=H,
                          T_kedalaman_deret=T, A_aktualitas=A,
                          G_geospasial_konektivitas=G,
                          n_komoditas=len(ada), n_kabkota=int(w.n_kabkota)))
    return pd.DataFrame(baris)


def compute_ikd(katalog=None, bobot: dict = None) -> pd.DataFrame:
    prod, harga, wil = katalog if katalog else load_katalog()
    bobot = bobot or BOBOT
    d = _agregasi(_per_komoditas(prod, harga), wil)

    d["IKD"] = sum(d[k] * w for k, w in bobot.items())
    d["layak_pilot"] = np.where(d.n_komoditas >= GATE_MIN_KOMODITAS, "Ya", "Tidak")
    d.loc[d.layak_pilot == "Tidak", "IKD"] = 0.0

    d = d.sort_values("IKD", ascending=False).reset_index(drop=True)
    d["peringkat"] = np.arange(1, len(d) + 1)
    return d


# ------------------------------------------------------------- sensitivitas
def sensitivity(katalog=None, n_draw: int = 4000, konsentrasi: float = 40.0,
                seed: int = 42) -> pd.DataFrame:
    prod, harga, wil = katalog if katalog else load_katalog()
    d = _agregasi(_per_komoditas(prod, harga), wil)
    kunci = list(BOBOT)
    X = d[kunci].to_numpy()
    gate = (d.n_komoditas >= GATE_MIN_KOMODITAS).to_numpy().astype(float)

    rng = np.random.default_rng(seed)
    W = rng.dirichlet(np.array([BOBOT[k] for k in kunci]) * konsentrasi, size=n_draw)
    S = (X @ W.T) * gate[:, None]
    juara = (S.argmax(axis=0)[None, :] == np.arange(len(d))[:, None]).mean(axis=1)
    peringkat = (-S).argsort(axis=0).argsort(axis=0) + 1

    out = pd.DataFrame({
        "provinsi": d.provinsi,
        "IKD_dasar": (X @ np.array([BOBOT[k] for k in kunci])) * gate,
        "IKD_p05": np.quantile(S, 0.05, axis=1),
        "IKD_p95": np.quantile(S, 0.95, axis=1),
        "P_peringkat1": juara,
        "peringkat_terburuk": peringkat.max(axis=1),
    })
    return out.sort_values("IKD_dasar", ascending=False).reset_index(drop=True)


# -------------------------------------------------------------- titik balik
def titik_balik(katalog=None, provinsi="Jawa Tengah", sistem_key="SiHati",
                grid=None) -> pd.DataFrame:
    """
    Geser keterisian sistem harga satu provinsi, lihat kapan peringkat 1
    berpindah. Menguji kerapuhan kesimpulan terhadap parameter yang belum
    diverifikasi.
    """
    prod, harga, wil = katalog if katalog else load_katalog()
    grid = grid if grid is not None else np.arange(0.30, 1.001, 0.05)
    hasil = []
    for k in grid:
        h2 = harga.copy()
        m = (h2.provinsi == provinsi) & h2.sistem.astype(str).str.contains(sistem_key, na=False)
        h2.loc[m, "keterisian"] = k
        s = compute_ikd((prod, h2, wil))
        hasil.append(dict(
            keterisian=round(float(k), 2),
            pemenang=s.iloc[0].provinsi,
            IKD_pemenang=round(float(s.iloc[0].IKD), 4),
            IKD_target=round(float(s.loc[s.provinsi == provinsi, "IKD"].iloc[0]), 4)))
    return pd.DataFrame(hasil)


def _ringkas(lapis, parameter, ruang, rentang, jejak, dasar, fmt):
    """Rangkum satu sapuan parameter: apakah pemenang berpindah, dan di nilai berapa."""
    pemenang = [w for _, w in jejak]
    lain = sorted(set(pemenang) - {dasar})
    ambang = ""
    for (v, w) in jejak:
        if w != dasar:
            ambang = fmt.format(v)
            break
    return dict(lapis=lapis, parameter=parameter, ruang=ruang, rentang=rentang,
                pemenang_lain=" / ".join(lain) if lain else "—",
                ambang=ambang or "—", bisa_membalik=bool(lain))


def pindai_kerapuhan(katalog=None, n_grid: int = 11) -> pd.DataFrame:
    """
    Menguji SETIAP parameter yang masih berstatus estimasi, bukan hanya satu.

    titik_balik() hanya memeriksa keterisian satu sistem harga. Itu menjawab
    pertanyaan yang sudah kita tahu jawabannya dan membiarkan enam puluh
    parameter estimasi lain tak tersentuh. Fungsi ini menggeser tiap parameter
    estimasi ke seluruh rentang yang masuk akal dan melaporkan mana saja yang
    sanggup memindahkan peringkat 1.

    Kembalian: satu baris per parameter, kolom `bisa_membalik` menandai yang
    berbahaya. Kalau kolom itu semuanya False, kesimpulan aman terhadap sisa
    ketidakpastian katalog.
    """
    prod, harga, wil = katalog if katalog else load_katalog()
    dasar = compute_ikd((prod, harga, wil)).iloc[0].provinsi
    hasil = []

    # 1. keterisian sistem harga yang belum diverifikasi
    est = harga[harga.status_verifikasi.str.lower() == "estimasi"]
    for (prov, sistem), _ in est.groupby(["provinsi", "sistem"]):
        jejak = []
        for k in np.linspace(0, 1, n_grid):
            h2 = harga.copy()
            m = (h2.provinsi == prov) & (h2.sistem == sistem)
            h2.loc[m, "keterisian"] = k
            jejak.append((k, compute_ikd((prod, h2, wil)).iloc[0].provinsi))
        hasil.append(_ringkas("harga", "keterisian", f"{prov} / {sistem}",
                              "0,00–1,00", jejak, dasar, "{:.2f}"))

    # 2. jumlah kabupaten berproduksi, digeser serentak per provinsi
    est_p = prod[prod.status_verifikasi.str.lower() == "estimasi"]
    for prov in sorted(est_p.provinsi.unique()):
        jejak = []
        for f in np.linspace(0.5, 1.5, n_grid):
            p2 = prod.copy()
            m = (p2.provinsi == prov) & (p2.status_verifikasi.str.lower() == "estimasi")
            p2.loc[m, "n_kabkota_produksi"] = np.minimum(
                (p2.loc[m, "n_kabkota_produksi"] * f).round(), p2.loc[m, "n_kabkota"])
            jejak.append((f, compute_ikd((p2, harga, wil)).iloc[0].provinsi))
        hasil.append(_ringkas("produksi", "n_kabkota_produksi", prov,
                              "×0,5–×1,5", jejak, dasar, "×{:.2f}"))

    # 3. konektivitas darat
    est_w = wil[wil.status_verifikasi.str.lower() == "estimasi"]
    for prov in sorted(est_w.provinsi.unique()):
        jejak = []
        for f in np.linspace(0.3, 1.0, n_grid):
            w2 = wil.copy()
            w2.loc[w2.provinsi == prov, "fraksi_terhubung_darat"] = f
            jejak.append((f, compute_ikd((prod, harga, w2)).iloc[0].provinsi))
        hasil.append(_ringkas("wilayah", "fraksi_terhubung_darat", prov,
                              "0,30–1,00", jejak, dasar, "{:.2f}"))

    out = pd.DataFrame(hasil)
    out.attrs["pemenang_dasar"] = dasar
    return (out.sort_values(["bisa_membalik", "lapis", "ruang"],
                            ascending=[False, True, True]).reset_index(drop=True))


# -------------------------------------------------------------------- audit
def audit_trail(katalog=None) -> dict:
    prod, harga, wil = katalog if katalog else load_katalog()
    total, skor, rinci = 0, 0.0, {}
    for nama, df in [("produksi", prod), ("harga", harga), ("wilayah", wil)]:
        s = df.status_verifikasi.str.lower().map(BOBOT_STATUS).fillna(0.0)
        rinci[nama] = {"baris": len(df), "skor": float(s.sum()), "rasio": float(s.mean())}
        total += len(df)
        skor += float(s.sum())
    return {"total_baris": total, "skor_verifikasi": skor,
            "rasio": skor / total if total else 0.0, "rinci": rinci}


# --------------------------------------------------------------------- cetak
if __name__ == "__main__":
    pd.set_option("display.width", 170)
    skor = compute_ikd()
    kol = ["peringkat", "provinsi", "n_komoditas"] + list(BOBOT) + ["IKD", "layak_pilot"]
    print("\n=== INDEKS KESIAPAN DATA v2 (bobot dasar) ===")
    print(skor[kol].round(3).to_string(index=False))

    print("\n=== SIMPANGAN BAKU TIAP DIMENSI (nol = dimensi mati) ===")
    print(skor[list(BOBOT)].std().round(4).to_string())

    print("\n=== SENSITIVITAS BOBOT (4.000 kombinasi Dirichlet) ===")
    print(sensitivity().round(3).to_string(index=False))

    print("\n=== TITIK BALIK: keterisian SiHati Jateng ===")
    print(titik_balik().to_string(index=False))

    a = audit_trail()
    print(f"\nAudit katalog: skor verifikasi {a['skor_verifikasi']:.0f}/{a['total_baris']} "
          f"({a['rasio']*100:.0f}%).")
    for k, v in a["rinci"].items():
        print(f"  - {k:9s}: {v['rasio']*100:5.1f}% dari {v['baris']} baris")
