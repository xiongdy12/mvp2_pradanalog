"""
backtest_harga.py — backtest yang bisa direproduksi untuk modul prediksi harga
==============================================================================
Menggantikan metrik_harga.csv yang skrip pembuatnya hilang.

Masalah dengan metrik lama: ia memuat satu angka `mape_backtest` per komoditas
tanpa keterangan horizon, periode uji, maupun cakupan provinsi. Tanpa itu,
angkanya tidak bisa dibandingkan dengan apa pun. Beras 1,2% terlihat menang
telak terhadap lantai naif horizon 3 bulan (2,41%) tetapi kalah terhadap lantai
horizon 1 bulan (1,05%) — dan tidak ada cara memastikan yang mana yang berlaku.

Berkas ini menghitung ulang semuanya pada jendela yang sama persis untuk semua
metode, sehingga perbandingannya sah menurut konstruksi.

METODE YANG DIUJI
    naif        harga h bulan ke depan = harga bulan ini
    musiman     = harga bulan yang sama tahun lalu
    hanyut      = harga bulan ini + rata-rata perubahan 12 bulan terakhir
    campuran    = rata-rata naif dan musiman

BACKTEST ROLLING-ORIGIN
Titik asal digeser bulan demi bulan sepanjang periode uji. Pada tiap titik,
hanya data sampai bulan itu yang boleh dipakai. Cara ini menghindari kebocoran
masa depan yang membuat hasil terlihat bagus di laptop dan gagal di lapangan.

Pakai:
    python backtest_harga.py harga_bulanan_panel.csv
    python backtest_harga.py harga_bulanan_panel.csv --uji 24 --horizon 1,2,3
"""

import sys

import numpy as np
import pandas as pd


def _mape(benar, ramal):
    benar, ramal = np.asarray(benar, float), np.asarray(ramal, float)
    sah = benar > 0
    return float(np.mean(np.abs((benar[sah] - ramal[sah]) / benar[sah])) * 100) if sah.any() else np.nan


def _kolom(df, kandidat, wajib=True, nama=""):
    for c in kandidat:
        if c in df.columns:
            return c
    rendah = {c.lower(): c for c in df.columns}
    for c in kandidat:
        if c.lower() in rendah:
            return rendah[c.lower()]
    if wajib:
        raise KeyError(f"Kolom {nama or kandidat[0]} tidak ada. Yang tersedia: "
                       f"{df.columns.tolist()}")
    return None


def siapkan(panel: pd.DataFrame):
    d = panel.copy()
    kom = _kolom(d, ["komoditas", "commodity"], nama="komoditas")
    wkt = _kolom(d, ["bulan", "tanggal", "periode", "month"], nama="bulan")
    hrg = _kolom(d, ["harga", "harga_rp", "price", "nilai"], nama="harga")
    grp = _kolom(d, ["provinsi", "province", "wilayah"], wajib=False)
    d[wkt] = pd.to_datetime(d[wkt].astype(str), errors="coerce")
    d[hrg] = pd.to_numeric(d[hrg], errors="coerce")
    d = d[d[wkt].notna() & (d[hrg] > 0)]
    kunci = [k for k in [grp, kom] if k]
    return d.sort_values(kunci + [wkt]), kunci, kom, wkt, hrg


def _ramal(seri: pd.Series, h: int) -> dict:
    """
    Ramalan h langkah ke depan dari deret yang berakhir di titik asal.
    seri diindeks bulan dan hanya memuat data sampai titik asal.
    """
    kini = float(seri.iloc[-1])
    hasil = {"naif": kini}

    # musiman: nilai pada bulan target tahun lalu
    target = seri.index[-1] + pd.DateOffset(months=h)
    setahun_lalu = target - pd.DateOffset(months=12)
    hasil["musiman"] = float(seri.loc[setahun_lalu]) if setahun_lalu in seri.index else np.nan

    # hanyut: laju rata-rata 12 bulan terakhir
    if len(seri) >= 13:
        laju = (float(seri.iloc[-1]) - float(seri.iloc[-13])) / 12.0
        hasil["hanyut"] = kini + laju * h
    else:
        hasil["hanyut"] = np.nan

    nilai = [hasil["naif"]] + ([hasil["musiman"]] if not np.isnan(hasil["musiman"]) else [])
    hasil["campuran"] = float(np.mean(nilai))
    return hasil


def backtest(panel: pd.DataFrame, bulan_uji: int = 24, horizon=(1, 2, 3)) -> pd.DataFrame:
    d, kunci, kom, wkt, hrg = siapkan(panel)
    bulan_semua = np.sort(d[wkt].unique())
    if len(bulan_semua) < bulan_uji + 14:
        bulan_uji = max(6, len(bulan_semua) - 14)
        print(f"Periode uji dipendekkan ke {bulan_uji} bulan karena panel terlalu pendek.")
    mulai_uji = bulan_semua[-bulan_uji]

    baris = []
    for kunci_nilai, g in d.groupby(kunci):
        seri = g.set_index(wkt)[hrg].sort_index()
        seri = seri[~seri.index.duplicated(keep="last")]
        komoditas = kunci_nilai[-1] if isinstance(kunci_nilai, tuple) else kunci_nilai
        wilayah = (kunci_nilai[0] if isinstance(kunci_nilai, tuple) and len(kunci_nilai) > 1
                   else "(semua)")
        for asal in seri.index:
            if asal < mulai_uji:
                continue
            riwayat = seri.loc[:asal]
            if len(riwayat) < 14:
                continue
            for h in horizon:
                target = asal + pd.DateOffset(months=h)
                if target not in seri.index:
                    continue
                benar = float(seri.loc[target])
                for metode, nilai in _ramal(riwayat, h).items():
                    if not np.isnan(nilai):
                        baris.append(dict(provinsi=wilayah, komoditas=komoditas, h=h,
                                          metode=metode, benar=benar, ramal=nilai))
    if not baris:
        raise RuntimeError("Tidak ada titik uji yang terbentuk. Periksa kolom bulan "
                           "dan panjang panelnya.")
    return pd.DataFrame(baris)


def _mase_aman(mae, mae_naif):
    """
    MASE yang tidak pecah saat galat naif nol.

    Terjadi pada provinsi yang harganya tidak pernah berubah sepanjang periode
    uji: galat naif 0, galat metode lain juga 0, dan 0/0 menghasilkan NaN. Satu
    grup berisi NaN semua membuat idxmin melempar ValueError dan seluruh
    pemeriksaan mati — padahal maknanya sederhana: pada deret yang benar-benar
    beku, tidak ada yang bisa mengalahkan naif, dan tidak ada yang lebih buruk.
    """
    mae = np.asarray(mae, float)
    mae_naif = np.asarray(mae_naif, float)
    hasil = np.divide(mae, mae_naif, out=np.full_like(mae, np.nan),
                      where=mae_naif > 0)
    # naif sempurna dan metode lain juga sempurna -> setara
    hasil = np.where((mae_naif == 0) & (mae == 0), 1.0, hasil)
    # naif sempurna tapi metode lain meleset -> jelas lebih buruk
    hasil = np.where((mae_naif == 0) & (mae > 0), np.inf, hasil)
    return np.round(hasil, 3)


def ringkas(hasil: pd.DataFrame) -> pd.DataFrame:
    """MAPE per komoditas per horizon per metode, plus rasio terhadap naif."""
    r = (hasil.groupby(["komoditas", "h", "metode"])
         .apply(lambda g: pd.Series({"mape": _mape(g.benar, g.ramal),
                                     "mae": float(np.mean(np.abs(g.benar - g.ramal))),
                                     "n": len(g)}), include_groups=False)
         .reset_index())
    naif = (r[r.metode == "naif"][["komoditas", "h", "mae"]]
            .rename(columns={"mae": "mae_naif"}))
    r = r.merge(naif, on=["komoditas", "h"], how="left")
    # MASE: galat metode dibagi galat naif pada titik uji yang sama persis.
    # Di bawah 1 berarti metode itu benar-benar menambah nilai.
    r["mase"] = _mase_aman(r.mae, r.mae_naif)
    r["mape"] = r.mape.round(2)
    return r.drop(columns=["mae", "mae_naif"])


def metode_terbaik(r: pd.DataFrame) -> pd.DataFrame:
    """Metode dengan MASE terkecil untuk tiap komoditas dan horizon."""
    bukan_naif = r[r.metode != "naif"]
    idx = bukan_naif.groupby(["komoditas", "h"]).mase.idxmin()
    t = bukan_naif.loc[idx, ["komoditas", "h", "metode", "mape", "mase"]].copy()
    t["putusan"] = np.where(t.mase < 0.95, "pakai " + t.metode,
                            "pakai naif — tidak ada yang mengalahkannya")
    return t.sort_values(["komoditas", "h"]).reset_index(drop=True)


# --------------------------------------------------- aturan per provinsi
def ringkas_provinsi(hasil: pd.DataFrame) -> pd.DataFrame:
    """MASE per provinsi x komoditas x horizon x metode."""
    r = (hasil.groupby(["provinsi", "komoditas", "h", "metode"])
         .apply(lambda g: pd.Series({"mape": _mape(g.benar, g.ramal),
                                     "mae": float(np.mean(np.abs(g.benar - g.ramal))),
                                     "n": len(g)}), include_groups=False)
         .reset_index())
    naif = (r[r.metode == "naif"][["provinsi", "komoditas", "h", "mae"]]
            .rename(columns={"mae": "mae_naif"}))
    r = r.merge(naif, on=["provinsi", "komoditas", "h"], how="left")
    r["mase"] = _mase_aman(r.mae, r.mae_naif)
    return r


def cek_perlu_aturan_provinsi(hasil: pd.DataFrame, ambang: float = 0.95) -> dict:
    """
    Apakah aturan metode perlu dibedakan per provinsi, atau cukup per komoditas?

    Aturan yang lebih rinci selalu terlihat lebih baik pada data yang sama —
    itu sifat pemilihan, bukan bukti keunggulan. Yang diukur di sini adalah
    penyesalan (regret): berapa banyak galat tambahan yang ditanggung kalau
    memakai satu aturan per komoditas dibandingkan aturan khusus tiap provinsi.

    Penyesalan kecil berarti aturan sederhana sudah cukup, dan aturan rinci
    hanya menambah 34 kali lipat peluang salah pilih karena kebetulan.
    """
    rp = ringkas_provinsi(hasil)
    rk = ringkas(hasil)

    def pilih(df, kunci):
        # Grup yang seluruh MASE-nya tak terhingga atau kosong berarti tidak ada
        # pesaing yang sah; naif menang tanpa pertandingan. Menyaringnya di sini
        # mencegah idxmin melempar ValueError pada grup ber-NaN penuh.
        bukan = df[(df.metode != "naif") & np.isfinite(df.mase)]
        semua = df[kunci].drop_duplicates()
        if len(bukan):
            idx = bukan.groupby(kunci).mase.idxmin()
            t = bukan.loc[idx, kunci + ["metode", "mase"]].copy()
        else:
            t = pd.DataFrame(columns=kunci + ["metode", "mase"])
        t = semua.merge(t, on=kunci, how="left")
        t["metode"] = t.metode.fillna("naif")
        t["mase"] = t.mase.fillna(1.0)
        t["dipakai"] = np.where(t.mase < ambang, t.metode, "naif")
        return t

    prov = pilih(rp, ["provinsi", "komoditas", "h"])
    kom = pilih(rk, ["komoditas", "h"]).rename(columns={"dipakai": "dipakai_kom"})

    gab = prov.merge(kom[["komoditas", "h", "dipakai_kom"]], on=["komoditas", "h"])
    beda = gab[gab.dipakai != gab.dipakai_kom]

    # penyesalan: MASE aturan komoditas dikurangi MASE aturan provinsi,
    # dihitung pada titik uji provinsi itu sendiri
    m = rp.set_index(["provinsi", "komoditas", "h", "metode"]).mase
    pen = []
    for _, r in gab.iterrows():
        kunci_p = (r.provinsi, r.komoditas, r.h)
        def ambil(metode):
            if metode == "naif":
                return 1.0
            v = float(m.get(kunci_p + (metode,), 1.0))
            # metode tak terpakai di provinsi ini disamakan dengan naif, bukan
            # dianggap tak terhingga, supaya satu sel ekstrem tidak menenggelamkan
            # rata-rata penyesalan.
            return 1.0 if not np.isfinite(v) else v
        pen.append(ambil(r.dipakai_kom) - ambil(r.dipakai))
    gab["penyesalan"] = np.round(pen, 4)

    # Rata-rata saja menyesatkan di sini: satu sel dengan penyesalan 3,15 bisa
    # menarik rata-rata 400 sel melewati ambang, dan menyimpulkan bahwa seluruh
    # sistem butuh aturan rinci padahal yang bermasalah hanya segelintir wilayah.
    # Median dan kuantil menunjukkan apakah persoalannya menyebar atau menumpuk.
    arr = np.array(pen) if pen else np.array([0.0])
    return {"n_sel": len(gab), "n_beda": len(beda),
            "rasio_beda": round(len(beda) / len(gab), 3) if len(gab) else 0.0,
            "penyesalan_rata": round(float(np.mean(arr)), 4),
            "penyesalan_median": round(float(np.median(arr)), 4),
            "penyesalan_p90": round(float(np.quantile(arr, 0.90)), 4),
            "penyesalan_maks": round(float(np.max(arr)), 4),
            "rasio_nol": round(float((np.abs(arr) < 1e-9).mean()), 3),
            "rincian": gab, "per_provinsi": rp}


def deteksi_beku(panel: pd.DataFrame, bulan_uji: int = 24) -> pd.DataFrame:
    """
    Cari provinsi-komoditas yang harganya nyaris tidak pernah berubah.

    Harga pangan yang benar-benar tetap selama dua tahun tidak masuk akal. Yang
    lebih mungkin: sel kosong diisi nilai terakhir, atau wilayah itu memang tidak
    disurvei. Deret seperti ini membuat galat naif nol, merusak MASE, dan ikut
    menyeret rata-rata nasional tanpa ada yang menyadarinya.
    """
    d, kunci, kom, wkt, hrg = siapkan(panel)
    bulan_semua = np.sort(d[wkt].unique())
    mulai = bulan_semua[-min(bulan_uji, len(bulan_semua))]
    uji = d[d[wkt] >= mulai]

    baris = []
    for k, g in uji.groupby(kunci):
        seri = g.sort_values(wkt)[hrg]
        if len(seri) < 3:
            continue
        ubah = float((seri.diff().fillna(0) != 0).mean())
        baris.append(dict(wilayah=k[0] if isinstance(k, tuple) else "(semua)",
                          komoditas=k[-1] if isinstance(k, tuple) else k,
                          n_bulan=len(seri), nilai_unik=int(seri.nunique()),
                          laju_ubah=round(ubah, 3)))
    t = pd.DataFrame(baris)
    return t[t.laju_ubah < 0.2].sort_values("laju_ubah").reset_index(drop=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    bulan_uji, horizon = 24, (1, 2, 3)
    if "--uji" in sys.argv:
        bulan_uji = int(sys.argv[sys.argv.index("--uji") + 1])
    if "--horizon" in sys.argv:
        horizon = tuple(int(x) for x in sys.argv[sys.argv.index("--horizon") + 1].split(","))

    panel = pd.read_csv(sys.argv[1])
    print(f"Panel        : {sys.argv[1]}  ({len(panel):,} baris)")
    print(f"Periode uji  : {bulan_uji} bulan terakhir, rolling-origin")
    print(f"Horizon      : {horizon}\n")

    hasil = backtest(panel, bulan_uji, horizon)
    r = ringkas(hasil)

    print("--- MAPE per metode (%) ---")
    print(r.pivot_table(index=["komoditas", "h"], columns="metode", values="mape")
          .round(2).to_string())

    print("\n--- MASE terhadap naif (di bawah 1 = menambah nilai) ---")
    print(r[r.metode != "naif"].pivot_table(index=["komoditas", "h"],
                                            columns="metode", values="mase")
          .round(3).to_string())

    print("\n--- Putusan per komoditas dan horizon ---")
    print(metode_terbaik(r).to_string(index=False))

    if "--cek-provinsi" in sys.argv:
        c = cek_perlu_aturan_provinsi(hasil)
        print("\n--- Perlukah aturan dibedakan per provinsi? ---")
        print(f"Sel provinsi x komoditas x horizon : {c['n_sel']}")
        print(f"Sel yang pilihannya berbeda        : {c['n_beda']} ({c['rasio_beda']:.0%})")
        print(f"Penyesalan rata-rata (MASE)        : {c['penyesalan_rata']:+.4f}")
        print(f"Penyesalan median                  : {c['penyesalan_median']:+.4f}")
        print(f"Penyesalan persentil 90            : {c['penyesalan_p90']:+.4f}")
        print(f"Penyesalan terburuk                : {c['penyesalan_maks']:+.4f}")
        print(f"Sel tanpa penyesalan sama sekali   : {c['rasio_nol']:.0%}")

        c["rincian"].to_csv("penyesalan_per_provinsi.csv", index=False)
        atas = c["rincian"].nlargest(8, "penyesalan")[
            ["provinsi", "komoditas", "h", "dipakai", "dipakai_kom", "penyesalan"]]
        print("\nDelapan sel dengan penyesalan terbesar:")
        print(atas.to_string(index=False))

        beku = deteksi_beku(panel, bulan_uji)
        if len(beku):
            print(f"\nDeret nyaris beku ({len(beku)} pasangan wilayah-komoditas, "
                  f"laju perubahan < 0,2):")
            print(beku.head(10).to_string(index=False))
            beku.to_csv("deret_beku.csv", index=False)
            print("Ditulis ke deret_beku.csv — periksa apakah ini data asli atau "
                  "sel kosong yang diisi nilai terakhir.")

        if c["penyesalan_median"] < 0.005 and c["penyesalan_rata"] < 0.02:
            print("\nAturan per komoditas sudah cukup. Membedakan per provinsi hanya "
                  "menambah puluhan kali peluang salah pilih karena kebetulan, dengan "
                  "imbalan galat yang hampir nol.")
        elif c["penyesalan_median"] < 0.005:
            print("\nMedian penyesalan hampir nol tetapi rata-ratanya tidak: perbedaan "
                  "menumpuk di segelintir wilayah, bukan menyebar. Pakai aturan per "
                  "komoditas sebagai bawaan, dan kecualikan hanya wilayah yang muncul "
                  "di daftar penyesalan terbesar di atas. Periksa dulu apakah wilayah "
                  "itu bermasalah datanya sebelum membuatkan aturan khusus.")
        else:
            print("\nAturan per provinsi memberi perbaikan berarti dan menyebar merata. "
                  "Pakai yang rinci, tapi laporkan bahwa pemilihannya dilakukan pada "
                  "data uji yang sama.")
        c["per_provinsi"].to_csv("metrik_harga_per_provinsi.csv", index=False)
        print("Ditulis ke metrik_harga_per_provinsi.csv")

    r.to_csv("metrik_harga_backtest.csv", index=False)
    print(f"\nDitulis ke metrik_harga_backtest.csv ({len(r)} baris). "
          f"Titik uji: {len(hasil):,}.")
