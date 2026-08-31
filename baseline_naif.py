"""
baseline_naif.py — berapa yang harus dikalahkan modul prediksi harga
=====================================================================
Menjawab satu pertanyaan yang hampir pasti ditanyakan juri:

    "MAPE model Anda 2,8%. Berapa MAPE tebakan bodoh 'harga besok sama dengan
     harga hari ini'?"

Kalau jawabannya 2,9%, seluruh modul XGBoost-LSTM Anda menambah nilai 0,1 poin
dan pertanyaan berikutnya tidak akan menyenangkan.

Latar belakangnya: harga kentang Jawa Timur punya keterisian 1,000 tapi laju
perubahan hanya 0,053 — harga bertahan rata-rata 18,8 hari. Pada deret sedatar
itu, peramal naif nyaris tidak pernah salah. Galat rendah menandakan data yang
datar, bukan model yang pandai.

Yang dilaporkan:
  MAPE naif harian    — lantai yang harus dilampaui pada resolusi harian
  MAPE naif mingguan  — lantai setelah data diagregasi mingguan
  MASE               — galat model dibagi galat naif. Di bawah 1 berarti model
                        berguna; di atas atau sekitar 1 berarti tidak.

Pakai:
    python baseline_naif.py jatim_kentang_uji.csv
    python baseline_naif.py data_harga.csv ramalan_model.csv
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

KUNCI = ["kabkota", "pasar", "komoditas"]


def _mape(benar, ramal):
    benar = np.asarray(benar, dtype=float)
    ramal = np.asarray(ramal, dtype=float)
    sah = benar > 0
    if not sah.any():
        return float("nan")
    return float(np.mean(np.abs((benar[sah] - ramal[sah]) / benar[sah])) * 100)


def _siapkan(df, kolom_harga="harga"):
    d = df.copy()
    d["tanggal"] = pd.to_datetime(d["tanggal"])
    d = d[pd.to_numeric(d[kolom_harga], errors="coerce").fillna(0) > 0]
    kunci = [k for k in KUNCI if k in d.columns]
    return d.sort_values(kunci + ["tanggal"]), kunci


def naif_harian(df, kolom_harga="harga") -> dict:
    """Peramal naif: harga besok = harga hari ini. Hanya hari berurutan dinilai."""
    d, kunci = _siapkan(df, kolom_harga)
    d["ramal"] = d.groupby(kunci)[kolom_harga].shift()
    d["jeda"] = d.groupby(kunci)["tanggal"].diff().dt.days
    sah = d[(d.jeda == 1) & d.ramal.notna()]
    return {"mape": _mape(sah[kolom_harga], sah.ramal), "n": len(sah),
            "mae": float(np.mean(np.abs(sah[kolom_harga] - sah.ramal))) if len(sah) else float("nan")}


def naif_mingguan(df, kolom_harga="harga") -> dict:
    """Naif setelah agregasi mingguan: rata-rata minggu depan = rata-rata minggu ini."""
    d, kunci = _siapkan(df, kolom_harga)
    d["minggu"] = d.tanggal.dt.to_period("W").dt.start_time
    m = d.groupby(kunci + ["minggu"], as_index=False)[kolom_harga].mean()
    m = m.sort_values(kunci + ["minggu"])
    m["ramal"] = m.groupby(kunci)[kolom_harga].shift()
    m["jeda"] = m.groupby(kunci)["minggu"].diff().dt.days
    sah = m[(m.jeda == 7) & m.ramal.notna()]
    return {"mape": _mape(sah[kolom_harga], sah.ramal), "n": len(sah),
            "mae": float(np.mean(np.abs(sah[kolom_harga] - sah.ramal))) if len(sah) else float("nan")}


def mase(mae_model: float, mae_naif: float) -> float:
    """
    Galat model dibagi galat naif.

    Ukuran ini dipakai karena MAPE sendirian tidak bisa dibaca tanpa pembanding.
    MAPE 2% pada deret yang bergejolak adalah prestasi; MAPE 2% pada deret yang
    hampir tidak bergerak adalah hal yang bisa dicapai tanpa model apa pun.
    """
    if not mae_naif or np.isnan(mae_naif):
        return float("nan")
    return mae_model / mae_naif


# ------------------------------------------------------- panel bulanan
def _tebak_kolom(df, kandidat, wajib=True, nama=""):
    for c in kandidat:
        if c in df.columns:
            return c
    lower = {c.lower(): c for c in df.columns}
    for c in kandidat:
        if c.lower() in lower:
            return lower[c.lower()]
    if wajib:
        raise KeyError(f"Kolom {nama or kandidat[0]} tidak ditemukan. "
                       f"Kolom yang ada: {df.columns.tolist()}")
    return None


def naif_panel(panel: pd.DataFrame, horizon=(1, 2, 3)) -> pd.DataFrame:
    """
    Lantai naif pada panel bulanan provinsi x komoditas, per horizon.

    Dibuat terpisah dari naif_harian karena panel bulanan PradanaLog tidak punya
    kolom pasar dan satuan waktunya bulan. Peramal naif di sini: harga h bulan
    ke depan sama dengan harga bulan ini — persis pembanding yang dibutuhkan
    untuk menilai mape_backtest di metrik_harga.csv.

    Kembalian: satu baris per komoditas per horizon, berisi MAPE naif.
    """
    d = panel.copy()
    kom = _tebak_kolom(d, ["komoditas", "commodity"], nama="komoditas")
    wkt = _tebak_kolom(d, ["bulan", "tanggal", "periode", "month"], nama="bulan")
    hrg = _tebak_kolom(d, ["harga", "harga_rp", "price", "nilai"], nama="harga")
    grp = _tebak_kolom(d, ["provinsi", "province", "wilayah"], wajib=False)

    d[wkt] = pd.to_datetime(d[wkt].astype(str), errors="coerce")
    d = d[d[wkt].notna() & (pd.to_numeric(d[hrg], errors="coerce").fillna(0) > 0)]
    kunci = [k for k in [grp, kom] if k]
    d = d.sort_values(kunci + [wkt])

    baris = []
    for h in horizon:
        g = d.copy()
        g["ramal"] = g.groupby(kunci)[hrg].shift(h)
        g["jeda"] = (g.groupby(kunci)[wkt].diff(h).dt.days)
        # terima 28-31 hari per langkah bulan
        sah = g[g.ramal.notna() & g.jeda.between(28 * h - 3 * h, 31 * h + 3 * h)]
        for k, sub in sah.groupby(kom):
            baris.append(dict(komoditas=k, h=h, mape_naif=round(_mape(sub[hrg], sub.ramal), 2),
                              n=len(sub)))
    return pd.DataFrame(baris)


def tabel_paper(panel: pd.DataFrame, metrik: pd.DataFrame,
                horizon_utama: int = 3) -> pd.DataFrame:
    """
    Susun tabel siap-paper: MAPE model, MAPE naif, dan MASE per komoditas.

    Ini tabel yang membuat angka Anda bisa dibaca. MAPE 1,2% pada beras dan
    24,5% pada cabai rawit tidak bisa dibandingkan satu sama lain, apalagi
    dinilai bagus atau buruk, tanpa kolom lantainya.
    """
    naif = naif_panel(panel, horizon=(horizon_utama,))
    kom_m = _tebak_kolom(metrik, ["komoditas", "commodity"], nama="komoditas")
    kol_m = _tebak_kolom(metrik, ["mape_backtest", "mape", "MAPE"], nama="mape_backtest")

    t = (metrik[[kom_m, kol_m]].rename(columns={kom_m: "komoditas", kol_m: "mape_model"})
         .merge(naif[["komoditas", "mape_naif", "n"]], on="komoditas", how="outer"))
    t["rasio"] = (t.mape_model / t.mape_naif).round(3)
    t["vonis"] = t.rasio.map(_vonis_rasio)
    return t.sort_values("rasio").reset_index(drop=True)


def _vonis_rasio(r):
    if pd.isna(r):
        return "tidak bisa dinilai"
    if r < 0.8:
        return "model menang meyakinkan"
    if r < 0.95:
        return "model menang tipis"
    if r <= 1.05:
        return "setara naif — tidak menambah nilai"
    return "lebih buruk daripada naif"


def bandingkan(df_harga, df_ramal=None, kolom_harga="harga",
               kolom_ramal="ramalan") -> dict:
    h = naif_harian(df_harga, kolom_harga)
    w = naif_mingguan(df_harga, kolom_harga)
    hasil = {"naif_harian": h, "naif_mingguan": w, "model": None, "mase": None}

    if df_ramal is not None:
        g = df_ramal.copy()
        g["tanggal"] = pd.to_datetime(g["tanggal"])
        kunci = [k for k in KUNCI if k in g.columns]
        d, _ = _siapkan(df_harga, kolom_harga)
        gab = d.merge(g, on=kunci + ["tanggal"], how="inner")
        if len(gab):
            mape_m = _mape(gab[kolom_harga], gab[kolom_ramal])
            mae_m = float(np.mean(np.abs(gab[kolom_harga] - gab[kolom_ramal])))
            hasil["model"] = {"mape": mape_m, "mae": mae_m, "n": len(gab)}
            hasil["mase"] = mase(mae_m, h["mae"])
    return hasil


def laporkan(hasil: dict):
    h, w = hasil["naif_harian"], hasil["naif_mingguan"]
    print("\n--- Lantai yang harus dilampaui ---")
    print(f"MAPE naif harian    : {h['mape']:.2f}%   ({h['n']:,} pasangan hari)")
    print(f"MAPE naif mingguan  : {w['mape']:.2f}%   ({w['n']:,} pasangan minggu)")

    if hasil["model"]:
        m = hasil["model"]
        print(f"\nMAPE model Anda     : {m['mape']:.2f}%   ({m['n']:,} titik)")
        print(f"MASE                : {hasil['mase']:.3f}")
        if hasil["mase"] >= 0.95:
            print("\nModel tidak mengalahkan tebakan naif. Jangan laporkan MAPE-nya "
                  "sebagai keberhasilan.")
        elif hasil["mase"] >= 0.8:
            print("\nPerbaikan tipis atas tebakan naif. Laporkan MASE bersama MAPE, "
                  "jangan MAPE sendirian.")
        else:
            print("\nModel mengalahkan tebakan naif secara meyakinkan. Laporkan MASE "
                  "sebagai bukti, karena MAPE sendirian tidak membuktikan apa pun.")
    else:
        print("\nBelum ada ramalan model untuk dibandingkan. Jalankan ulang dengan "
              "berkas ramalan berkolom: kabkota, pasar, komoditas, tanggal, ramalan.")
        if h["mape"] < 1.0:
            print(f"\nPeringatan: peramal naif sudah mencapai MAPE {h['mape']:.2f}%. "
                  "Pada deret sedatar ini, angka MAPE berapa pun dari model Anda "
                  "nyaris tidak bermakna. Laporkan MASE, dan pertimbangkan pindah ke "
                  "resolusi mingguan agar peramalan punya sesuatu untuk diramalkan.")


def _baca(jalur: str, wajib: bool):
    """Berkas hilang harus jadi pesan yang bisa ditindaklanjuti, bukan jejak tumpukan."""
    p = Path(jalur)
    if p.exists():
        return pd.read_csv(p)
    if wajib:
        print(f"Berkas '{jalur}' tidak ditemukan di folder ini.")
        sys.exit(1)
    print(f"\nBerkas ramalan '{jalur}' belum ada, jadi perbandingan model dilewati.")
    print("Berkas itu adalah keluaran modul prediksi harga Anda sendiri, berkolom:")
    print("    kabkota, pasar, komoditas, tanggal, ramalan")
    print("Selama belum ada, yang bisa dihitung hanya lantai naifnya.")
    return None


def _mode_panel(argv):
    panel = _baca(argv[0], wajib=True)
    print(f"Panel bulanan : {Path(argv[0]).name}  ({len(panel):,} baris)")
    naif = naif_panel(panel)
    print("\n--- Lantai naif per komoditas per horizon (%) ---")
    print(naif.pivot(index="komoditas", columns="h", values="mape_naif")
          .rename(columns=lambda c: f"h={c}").to_string())

    if len(argv) > 1:
        metrik = _baca(argv[1], wajib=False)
        if metrik is not None:
            t = tabel_paper(panel, metrik)
            print("\n--- Tabel siap-paper (horizon 3 bulan) ---")
            print(t[["komoditas", "mape_model", "mape_naif", "rasio", "vonis"]]
                  .to_string(index=False))
            menang = t[t.rasio < 0.95]
            print(f"\n{len(menang)} dari {len(t)} komoditas benar-benar diuntungkan "
                  f"oleh model. Sisanya cukup dilayani persistensi.")
    return


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    if sys.argv[1] == "panel":
        _mode_panel(sys.argv[2:])
        sys.exit(0)
    harga = _baca(sys.argv[1], wajib=True)
    print(f"Berkas harga  : {Path(sys.argv[1]).name}  ({len(harga):,} baris)")
    ramal = _baca(sys.argv[2], wajib=False) if len(sys.argv) > 2 else None
    laporkan(bandingkan(harga, ramal))
