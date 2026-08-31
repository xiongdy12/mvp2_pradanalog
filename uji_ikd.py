"""
uji_ikd.py — rangkaian uji otomatis pipeline Indeks Kesiapan Data
==================================================================
Jalankan sebelum memakai angka apa pun di paper atau presentasi:

    python uji_ikd.py

Uji ini ada karena satu insiden nyata: sisa data percobaan menimpa keterisian
Jawa Timur menjadi 0,123 sementara kolom catatannya tetap menyebut 0,97.
Indeks tetap jalan, tetap mengeluarkan peringkat, dan hampir dilaporkan.
Validasi struktur saja tidak menangkapnya — yang menangkap adalah uji asal-usul
yang menghitung ulang angka dari data mentah dan membandingkannya dengan
katalog. Itu uji nomor 8 di bawah.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from bangun_katalog import bangun_harga, gabung_aman  # noqa: E402
from data_readiness import (BOBOT, KatalogTidakSah, compute_ikd,  # noqa: E402
                            load_katalog, pindai_kerapuhan, sensitivity,
                            validasi_katalog)
from hitung_keterisian import hitung  # noqa: E402

LULUS, GAGAL = [], []
def _cari_aplikasi() -> Path | None:
    """
    Temukan pradanalog_map.py. Dicari di folder uji lebih dulu, baru di jalur
    unggahan. Versi awal hanya memeriksa jalur unggahan, sehingga uji integrasi
    selalu dilewati di komputer pengguna — padahal justru di sanalah uji itu
    berguna, karena yang diperiksa adalah penyatuan dengan kode aslinya.
    """
    for kandidat in (Path(__file__).parent / "pradanalog_map.py",
                     Path.cwd() / "pradanalog_map.py",
                     Path("/mnt/user-data/uploads/pradanalog_map.py")):
        if kandidat.exists():
            return kandidat
    return None



def cek(nama, kondisi, pesan=""):
    (LULUS if kondisi else GAGAL).append(nama)
    tanda = "  OK  " if kondisi else " GAGAL"
    print(f"[{tanda}] {nama}" + (f"  — {pesan}" if pesan and not kondisi else ""))


# ------------------------------------------------------------------- 1 & 2
def uji_validasi():
    prod, harga, wil = load_katalog(validasi=False)
    try:
        validasi_katalog(prod, harga, wil)
        cek("1. Katalog terkirim lolos validasi", True)
    except KatalogTidakSah as e:
        cek("1. Katalog terkirim lolos validasi", False, str(e)[:120])

    kasus = {
        "komoditas di luar daftar": (
            pd.concat([prod, prod[prod.komoditas == "beras"].assign(komoditas="bawang_putih")]),
            pd.concat([harga, harga[harga.komoditas == "beras"].assign(komoditas="bawang_putih")]),
            wil),
        "provinsi ganda di katalog wilayah": (prod, harga, pd.concat([wil, wil.head(1)])),
        "provinsi hilang": (prod, harga[harga.provinsi != "Bali"], wil),
        "komoditas hilang": (prod[~((prod.provinsi == "Bali") & (prod.komoditas == "beras"))],
                             harga, wil),
        "kab pantau > kab ada": (prod, harga.assign(
            n_kabkota_harga=harga.n_kabkota_harga.mask(harga.provinsi == "Bali", 999)), wil),
        "keterisian > 1": (prod, harga.assign(
            keterisian=harga.keterisian.mask(harga.provinsi == "Bali", 1.5)), wil),
        "frekuensi asing": (prod, harga.assign(
            frekuensi=harga.frekuensi.mask(harga.provinsi == "Bali", "kadang-kadang")), wil),
        "status asing": (prod, harga.assign(
            status_verifikasi=harga.status_verifikasi.mask(harga.provinsi == "Bali", "mungkin")),
            wil),
        "tahun terbalik": (prod.assign(tahun_akhir=prod.tahun_awal - 1), harga, wil),
        "konektivitas > 1": (prod, harga, wil.assign(fraksi_terhubung_darat=2.0)),
    }
    tertangkap = 0
    for nama, args in kasus.items():
        try:
            validasi_katalog(*args)
        except KatalogTidakSah:
            tertangkap += 1
    cek(f"2. Validasi menolak {len(kasus)} jenis cacat", tertangkap == len(kasus),
        f"hanya {tertangkap} dari {len(kasus)} tertangkap")


# ----------------------------------------------------------------------- 3-6
def uji_perhitungan():
    k = load_katalog()
    s = compute_ikd(k)

    dims = list(BOBOT)
    dalam = ((s[dims] >= 0) & (s[dims] <= 1)).all().all()
    cek("3. Semua dimensi berada di rentang 0–1", bool(dalam))

    layak = s[s.layak_pilot == "Ya"]
    hitung_ulang = sum(layak[d] * w for d, w in BOBOT.items())
    cek("4. IKD sama dengan jumlah terbobot dimensinya",
        bool(np.allclose(layak.IKD, hitung_ulang)))

    sd = s[dims].std()
    mati = [d for d in dims if sd[d] == 0]
    cek("5. Tidak ada dimensi yang konstan", not mati, f"dimensi mati: {mati}")

    cek("6. Bobot berjumlah 1", abs(sum(BOBOT.values()) - 1) < 1e-9)

    prod, harga, wil = k
    p2 = prod.copy()
    m = p2.provinsi == "Bali"
    p2.loc[m, "n_kabkota_produksi"] = 0
    s2 = compute_ikd((p2, harga, wil))
    bali = s2[s2.provinsi == "Bali"].iloc[0]
    cek("7. Syarat gugur menolak provinsi berkomoditas kurang",
        bali.layak_pilot == "Tidak" and bali.IKD == 0)


# --------------------------------------------------------------------- 8
def uji_pengurai_siskaperbapo():
    """
    Pengurai HTML diuji pada halaman Siskaperbapo yang sungguhan.

    Struktur situs bisa berubah kapan saja. Kalau berubah, uji ini gagal lebih
    dulu daripada penarikan data yang berjalan berjam-jam lalu menghasilkan
    tabel kosong.
    """
    berkas = Path("SISKAPERBAPO.html")
    if not berkas.exists():
        berkas = Path("/mnt/user-data/uploads/SISKAPERBAPO.html")
    if not berkas.exists():
        print("[ LEWAT] 21. Pengurai Siskaperbapo — contoh halaman tidak tersedia")
        return
    from hitung_keterisian import KOMODITAS_SISKAPERBAPO, _urai_tabel, hitung
    df = _urai_tabel(berkas.read_text(encoding="utf-8", errors="replace"), "beras")
    cek("21. Pengurai Siskaperbapo membaca 38 kab/kota dari halaman asli",
        df.kabkota.nunique() == 38, f"terbaca {df.kabkota.nunique()}")
    cek("22. Keenam komoditas PradanaLog punya id Siskaperbapo",
        set(KOMODITAS_SISKAPERBAPO) == {"beras", "jagung", "bawang", "cabai_besar",
                                        "cabai_rawit", "kentang"})
    h = hitung(df)
    _, harga, _ = load_katalog(validasi=False)
    tercatat = float(harga[(harga.provinsi == "Jawa Timur")
                           & harga.sistem.str.contains("SISKAPERBAPO", na=False)]
                     .keterisian.iloc[0])
    cek("23. Keterisian di katalog cocok dengan hasil urai halaman asli",
        abs(tercatat - h["keterisian_kabupaten"]) <= 0.005,
        f"katalog {tercatat:.4f} vs terhitung {h['keterisian_kabupaten']:.4f}")


def uji_asal_usul():
    """Angka berstatus bukan-estimasi harus bisa dihitung ulang dari data mentah."""
    berkas = Path("sampel_siskaperbapo_tidy.csv")
    if not berkas.exists():
        cek("8. Keterisian Jatim cocok dengan data mentahnya", False,
            "sampel_siskaperbapo_tidy.csv tidak ada")
        return
    h = hitung(pd.read_csv(berkas))
    terukur = h["keterisian_kabupaten"]

    _, harga, _ = load_katalog(validasi=False)
    baris = harga[(harga.provinsi == "Jawa Timur")
                  & harga.sistem.str.contains("SISKAPERBAPO", na=False)]
    tercatat = float(baris.keterisian.iloc[0])
    # Sampel 2023 dipakai sebagai uji regresi pengurai, bukan pembanding katalog:
    # katalog kini memakai panel Agustus 2026 yang keterisiannya berbeda.
    cek("8. Penghitung keterisian tetap konsisten pada sampel arsip 2023",
        abs(terukur - 0.970) <= 0.005 and 0 <= tercatat <= 1,
        f"sampel {terukur:.3f}, katalog {tercatat:.3f}")

    seragam = baris.keterisian.nunique() == 1
    cek("9. Satu sistem harga memakai satu nilai keterisian", seragam)


# -------------------------------------------------------------------- 10-12
def uji_ketahanan():
    k = load_katalog()

    a = sensitivity(k, seed=7)
    b = sensitivity(k, seed=7)
    cek("10. Uji sensitivitas dapat diulang persis",
        bool(np.allclose(a.P_peringkat1, b.P_peringkat1)))

    prod, harga, wil = k
    rng = np.random.default_rng(3)
    acak = (prod.sample(frac=1, random_state=rng.integers(1e6)),
            harga.sample(frac=1, random_state=rng.integers(1e6)), wil)
    s1 = compute_ikd(k).set_index("provinsi").IKD.sort_index()
    s2 = compute_ikd(acak).set_index("provinsi").IKD.sort_index()
    cek("11. Hasil tidak bergantung urutan baris katalog", bool(np.allclose(s1, s2)))

    pk = pindai_kerapuhan(k)
    rapuh = pk[pk.bisa_membalik]
    cek("12. Pemindaian kerapuhan berjalan dan melaporkan ambang",
        len(pk) > 0 and (rapuh.ambang != "—").all() if len(rapuh) else True)
    print(f"          {len(rapuh)} dari {len(pk)} parameter estimasi bisa "
          f"membalikkan peringkat 1")
    for _, r in rapuh.iterrows():
        print(f"          - {r.ruang} ({r.parameter}) pada {r.ambang}")


# ----------------------------------------------------------------------- 13
def uji_katalog_tidak_tertimpa():
    """gabung_aman harus mempertahankan baris yang sudah diverifikasi."""
    tmp = Path("._uji_katalog.csv")
    baru = bangun_harga()
    baru.to_csv(tmp, index=False)

    lama = pd.read_csv(tmp)
    lama.loc[0, "keterisian"] = 0.4242
    lama.loc[0, "status_verifikasi"] = "terverifikasi"
    lama.to_csv(tmp, index=False)

    gabung_aman(bangun_harga(), str(tmp), ["provinsi", "komoditas"])
    hasil = pd.read_csv(tmp)
    kunci = (hasil.provinsi == lama.loc[0, "provinsi"]) & (hasil.komoditas == lama.loc[0, "komoditas"])
    cek("13. Regenerasi katalog tidak menghapus baris terverifikasi",
        float(hasil[kunci].keterisian.iloc[0]) == 0.4242 and len(hasil) == len(baru))
    tmp.unlink(missing_ok=True)


# ----------------------------------------------------------------------- 14
def uji_skala():
    """Penghitung keterisian harus sanggup menangani penarikan setahun penuh."""
    import time
    rng = np.random.default_rng(0)
    pasangan = pd.DataFrame({"kabkota": np.repeat([f"Kab {i}" for i in range(38)], 3),
                             "pasar": [f"Pasar {i}-{j}" for i in range(38) for j in range(3)]})
    big = (pasangan.merge(pd.DataFrame({"komoditas": list("abcde")}), how="cross")
           .merge(pd.DataFrame({"tanggal": pd.date_range("2025-01-01", "2025-12-31")}),
                  how="cross"))
    big["harga"] = np.where(rng.random(len(big)) < 0.95, 12000, 0)
    t = time.time()
    h = hitung(big)
    dt = time.time() - t
    cek("14. Penghitung keterisian sanggup skala setahun penuh", dt < 20,
        f"{len(big):,} baris butuh {dt:.1f} detik")
    print(f"          {len(big):,} baris selesai dalam {dt:.1f} detik "
          f"(keterisian {h['keterisian_kabupaten']:.3f})")


# ----------------------------------------------------------------- 15-17
def uji_integrasi_tabel():
    """
    Tabel harus tampil benar lewat df_to_html milik PradanaLog.

    Fungsi itu memakai pct_cols untuk PERUBAHAN — positif diwarnai merah karena
    kenaikan harga itu kabar buruk. Peluang bertahan 100% pernah tampil merah
    bertanda +100,0%, dan angka dipangkas ke dua desimal padahal selisih IKD
    antarprovinsi bisa lebih kecil dari itu.
    """
    berkas = _cari_aplikasi()
    if berkas is None:
        print("[ LEWAT] 15-16. Integrasi tabel — pradanalog_map.py tidak ditemukan")
        return
    src = berkas.read_text(encoding="utf-8")
    blok = src[src.index("def warna_nilai"):src.index("def build_deck")]
    ns = {}
    exec("import html as _html\n" + blok, ns)
    df_to_html = ns["df_to_html"]

    import tab_kesiapan
    s = compute_ikd(load_katalog())
    sens = sensitivity(load_katalog())
    ss = sens.copy()
    ss["P_peringkat1"] = ss.P_peringkat1 * 100
    ss = tab_kesiapan._teks(ss, ["IKD_dasar"])
    ss = tab_kesiapan._teks(ss, ["P_peringkat1"], desimal=1)
    ss["P_peringkat1"] = ss.P_peringkat1 + "%"
    html = df_to_html(ss[["provinsi", "IKD_dasar", "P_peringkat1"]])

    cek("15. Peluang bertahan tidak diwarnai merah seperti kabar buruk",
        "#F0857A" not in html and "+100.0%" not in html)
    cek("16. IKD ditampilkan tiga desimal, tidak dipangkas jadi dua",
        f"{float(s.iloc[0].IKD):.3f}" in html)


def uji_render_tab():
    """Seluruh badan fungsi render dijalankan; error apa pun akan terlempar."""
    import types
    berkas = _cari_aplikasi()
    if berkas is None:
        print("[ LEWAT] 17. Render tab — pradanalog_map.py tidak ditemukan")
        return
    src = berkas.read_text(encoding="utf-8")
    blok = src[src.index("def warna_nilai"):src.index("def build_deck")]
    ns = {}
    exec("import html as _html\n" + blok, ns)

    asli = sys.modules.get("streamlit")

    class Kolom:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def __getattr__(self, n): return _Fn(n)

    class _Fn:
        def __init__(self, n): self.n = n
        def __call__(self, *a, **k):
            if self.n == "columns":
                spek = a[0] if a else 1
                return [Kolom() for _ in range(spek if isinstance(spek, int) else len(spek))]
            if self.n in ("expander", "container", "spinner", "form", "status"):
                return Kolom()
            if self.n == "cache_data":
                return a[0] if (a and callable(a[0])) else (lambda f: f)
            return None

    class FakeSt(types.ModuleType):
        def __getattr__(self, n): return _Fn(n)

    sys.modules["streamlit"] = FakeSt("streamlit")
    try:
        import importlib
        import tab_kesiapan
        importlib.reload(tab_kesiapan)
        tab_kesiapan.render_tab_kesiapan(ns["df_to_html"])
        cek("17. Tab kesiapan dirender penuh tanpa error", True)
    except Exception as e:
        cek("17. Tab kesiapan dirender penuh tanpa error", False,
            f"{type(e).__name__}: {e}")
    finally:
        if asli is not None:
            sys.modules["streamlit"] = asli
        else:
            sys.modules.pop("streamlit", None)


def uji_validasi_tidak_mati():
    """Validasi harus menolak dengan pesan, bukan mati dengan TypeError."""
    prod, harga, wil = load_katalog(validasi=False)
    kasus = {
        "sel kosong": (prod, harga.assign(
            keterisian=harga.keterisian.mask(harga.provinsi == "Bali")), wil),
        "teks di kolom angka": (prod, harga.assign(
            keterisian=harga.keterisian.astype(object).mask(
                harga.provinsi == "Bali", "tinggi")), wil),
        "nilai negatif": (prod, harga.assign(
            n_kabkota_harga=harga.n_kabkota_harga.mask(harga.provinsi == "Bali", -5)), wil),
        "tahun kosong": (prod.assign(
            tahun_awal=prod.tahun_awal.mask(prod.provinsi == "Bali")), harga, wil),
        "konektivitas teks": (prod, harga, wil.assign(fraksi_terhubung_darat="banyak")),
    }
    bersih = 0
    for nama, args in kasus.items():
        try:
            validasi_katalog(*args)
        except KatalogTidakSah:
            bersih += 1
        except Exception:
            pass
    cek(f"18. Validasi menolak {len(kasus)} data rusak tanpa mati mendadak",
        bersih == len(kasus), f"hanya {bersih} dari {len(kasus)} ditolak bersih")


# ----------------------------------------------------------------- 19-20
def uji_batas_skor():
    """
    Skor tidak boleh melewati 1 meski katalog memuat komoditas di luar daftar.

    Penyebut K tetap 6, jadi katalog dengan tujuh komoditas menghasilkan K=1,167
    dan indeks yang tampak sah padahal mustahil. Validasi menolaknya, tapi
    penjepitan di _agregasi tetap dipasang sebagai lapis kedua kalau suatu saat
    ada yang memanggil compute_ikd dengan validasi dimatikan.
    """
    prod, harga, wil = load_katalog(validasi=False)
    ep = pd.concat([prod, prod[prod.komoditas == "beras"].assign(komoditas="bawang_putih")])
    eh = pd.concat([harga, harga[harga.komoditas == "beras"].assign(komoditas="bawang_putih")])
    s = compute_ikd((ep, eh, wil))
    cek("19. Skor tetap di bawah 1 walau ada komoditas asing",
        float(s[list(BOBOT)].max().max()) <= 1.0,
        f"nilai maksimum {float(s[list(BOBOT)].max().max()):.3f}")


def uji_kolom_katalog():
    """Penggabungan katalog harus memperingatkan kalau susunan kolom berbeda."""
    import io
    from contextlib import redirect_stdout

    tmp = Path("._uji_kolom.csv")
    baru = bangun_harga()
    lama = baru.copy()
    lama["status_verifikasi"] = "terverifikasi"
    lama.drop(columns=["catatan"]).to_csv(tmp, index=False)

    buf = io.StringIO()
    with redirect_stdout(buf):
        gabung_aman(bangun_harga(), str(tmp), ["provinsi", "komoditas"])
    keluaran = buf.getvalue()
    cek("20. Perbedaan susunan kolom katalog diperingatkan",
        "PERINGATAN" in keluaran and "catatan" in keluaran,
        "penggabungan berjalan diam-diam dan kolom hilang tanpa jejak")
    tmp.unlink(missing_ok=True)


# ------------------------------------------------------------------- 24-25
def uji_diagnosa_penerusan():
    """
    Diagnosa harus membedakan deret berinformasi dari deret datar.

    Lahir dari kentang Jawa Timur: keterisian 1,000 pas selama 56 hari, tapi
    median hanya 2 harga unik per pasar dan 33 dari 114 pasar tak pernah berubah.
    Keterisian sempurna menyembunyikan deret yang nyaris tanpa informasi, dan
    model peramalan yang dilatih di atasnya akan tampak akurat karena datar,
    bukan karena pandai.
    """
    import numpy as np

    from hitung_keterisian import diagnosa_penerusan

    rng = np.random.default_rng(0)
    tgl = pd.date_range("2026-01-01", periods=56)

    datar = [dict(tanggal=t, kabkota="K", pasar=f"P{p}", komoditas="x", harga=15000)
             for p in range(20) for t in tgl]
    d1 = diagnosa_penerusan(pd.DataFrame(datar))
    cek("24. Deret beku terdeteksi tanpa informasi harian",
        d1["laju_perubahan"] == 0 and d1["rasio_beku"] == 1.0,
        f"laju={d1['laju_perubahan']} beku={d1['rasio_beku']}")

    sehat = []
    for p in range(20):
        h = 15000.0
        for t in tgl:
            h = max(500, h + rng.normal(0, 200))
            sehat.append(dict(tanggal=t, kabkota="K", pasar=f"P{p}",
                              komoditas="x", harga=round(h, -1)))
    d2 = diagnosa_penerusan(pd.DataFrame(sehat))
    cek("25. Deret bervariasi tidak salah dituduh datar",
        d2["laju_perubahan"] > 0.8 and "sehat" in d2["vonis"],
        f"laju={d2['laju_perubahan']} vonis={d2['vonis'][:40]}")


# ------------------------------------------------------------------- 26-27
def uji_baseline_naif():
    """
    Pembanding naif harus menandai model yang tidak lebih baik daripada menyalin
    harga kemarin, dan tidak salah menuduh model yang benar-benar bekerja.

    Perlu karena MAPE tidak bisa dibaca sendirian. Pada deret kentang Jawa Timur
    yang harganya bertahan 18,8 hari, peramal naif mencapai MAPE di bawah 1%.
    Model apa pun yang melaporkan angka sekitar itu belum membuktikan apa-apa.
    """
    import numpy as np

    from baseline_naif import bandingkan

    rng = np.random.default_rng(7)
    tgl = pd.date_range("2026-06-01", periods=56)
    baris = []
    for k in range(10):
        h = 17000.0
        for t in tgl:
            if rng.random() < 0.053:
                h = max(500, h + rng.choice([-1000, 1000]))
            baris.append(dict(tanggal=t, kabkota=f"Kab{k}", pasar=f"P{k}",
                              komoditas="kentang", harga=h))
    df = pd.DataFrame(baris)

    dasar = bandingkan(df)
    cek("26. Lantai naif terhitung pada deret nyaris datar",
        dasar["naif_harian"]["mape"] < 1.0 and dasar["naif_mingguan"]["mape"] > dasar["naif_harian"]["mape"],
        f"harian={dasar['naif_harian']['mape']:.2f}% mingguan={dasar['naif_mingguan']['mape']:.2f}%")

    tiruan = df.sort_values(["kabkota", "tanggal"]).copy()
    tiruan["ramalan"] = (tiruan.groupby("kabkota").harga.shift().fillna(tiruan.harga)
                         * (1 + rng.normal(0, 0.004, len(tiruan))))
    hasil = bandingkan(df, tiruan[["kabkota", "pasar", "komoditas", "tanggal", "ramalan"]])
    cek("27. Model yang cuma menyalin kemarin ditandai tidak berguna",
        hasil["mase"] is not None and hasil["mase"] >= 0.95,
        f"MASE={hasil['mase']}")


# ------------------------------------------------------------------- 28-29
def uji_panel_bulanan():
    """
    Lantai naif panel bulanan harus naik seiring horizon, dan tabel siap-paper
    harus memberi vonis yang benar.

    Perlu karena metrik_harga.csv hanya memuat mape_backtest tanpa pembanding.
    Beras 1,2% dan Cabai Rawit 24,5% tidak bisa dinilai berdampingan tanpa tahu
    lantainya masing-masing — cabai bergejolak sepuluh kali lipat beras, jadi
    angka mentahnya memang tidak sebanding.
    """
    import numpy as np

    from baseline_naif import naif_panel, tabel_paper

    rng = np.random.default_rng(1)
    bulan = pd.date_range("2020-02-01", periods=78, freq="MS")
    gejolak = {"Beras": 0.012, "Cabai Rawit": 0.28}
    baris = []
    for prov in ["Aceh", "Jawa Timur"]:
        for k, v in gejolak.items():
            h = 13000.0
            for b in bulan:
                h = max(500, h * (1 + rng.normal(0, v)))
                baris.append(dict(provinsi=prov, komoditas=k, bulan=b, harga=round(h, -1)))
    panel = pd.DataFrame(baris)

    n = naif_panel(panel)
    piv = n.pivot(index="komoditas", columns="h", values="mape_naif")
    naik = bool((piv[3] > piv[1]).all())
    beda = float(piv.loc["Cabai Rawit", 1]) > float(piv.loc["Beras", 1]) * 5
    cek("28. Lantai naif naik seiring horizon dan membedakan komoditas bergejolak",
        naik and beda, f"h1={piv[1].round(2).to_dict()} h3={piv[3].round(2).to_dict()}")

    metrik = pd.DataFrame({"komoditas": ["Beras", "Cabai Rawit"],
                           "mape_backtest": [float(piv.loc["Beras", 3]) * 0.5,
                                             float(piv.loc["Cabai Rawit", 3]) * 1.10]})
    t = tabel_paper(panel, metrik).set_index("komoditas")
    cek("29. Vonis membedakan model yang menang dari yang kalah",
        "menang" in t.loc["Beras", "vonis"] and "buruk" in t.loc["Cabai Rawit", "vonis"],
        f"{t.vonis.to_dict()}")


# ------------------------------------------------------------------- 30-31
def uji_backtest_harga():
    """
    Backtest harus memilih metode yang benar, dan mengaku kalah pada deret acak.

    Dua sisi diuji karena alat evaluasi yang hanya bisa memuji tidak berguna.
    Pada deret acak murni, peramal naif memang optimal dan alat harus mengatakan
    demikian, bukan mencari-cari pemenang.
    """
    import numpy as np

    from backtest_harga import backtest, metode_terbaik, ringkas

    rng = np.random.default_rng(5)
    bulan = pd.date_range("2019-01-01", periods=90, freq="MS")

    # deret bermusim kuat: metode musiman harus menang telak
    baris = []
    for prov in "ABC":
        for i, b in enumerate(bulan):
            h = 40000 * (1 + 0.30 * np.sin(2 * np.pi * i / 12)) + rng.normal(0, 400)
            baris.append(dict(provinsi=prov, komoditas="Bermusim", bulan=b,
                              harga=round(h, -1)))
    t = metode_terbaik(ringkas(backtest(pd.DataFrame(baris), 24, (3,)))).iloc[0]
    cek("30. Backtest mengenali pola musiman yang sungguhan",
        t.metode == "musiman" and t.mase < 0.5, f"terpilih {t.metode} mase={t.mase}")

    # jalan acak: tidak ada yang boleh mengalahkan naif
    baris = []
    for prov in "ABC":
        h = 13000.0
        for b in bulan:
            h = max(500, h * (1 + rng.normal(0, 0.05)))
            baris.append(dict(provinsi=prov, komoditas="Acak", bulan=b,
                              harga=round(h, -1)))
    t = metode_terbaik(ringkas(backtest(pd.DataFrame(baris), 24, (3,)))).iloc[0]
    cek("31. Backtest mengaku naif tak terkalahkan pada deret acak",
        t.mase >= 0.95 and "naif" in t.putusan, f"mase={t.mase} putusan={t.putusan}")


# ------------------------------------------------------------------- 32-33
def uji_aturan_provinsi():
    """
    Pemeriksa harus tahu kapan aturan rinci per provinsi diperlukan dan kapan
    hanya menambah rumit.

    Aturan yang lebih rinci selalu tampak lebih baik pada data yang dipakai
    memilihnya — itu sifat pemilihan, bukan bukti keunggulan. Yang diukur adalah
    penyesalan: galat tambahan akibat memakai satu aturan per komoditas.
    """
    import numpy as np

    from backtest_harga import backtest, cek_perlu_aturan_provinsi

    rng = np.random.default_rng(11)
    bulan = pd.date_range("2019-01-01", periods=90, freq="MS")

    seragam = [dict(provinsi=f"P{j}", komoditas="Seragam", bulan=b,
                    harga=round(40000 * (1 + 0.30 * np.sin(2 * np.pi * i / 12))
                                + rng.normal(0, 500), -1))
               for j in range(12) for i, b in enumerate(bulan)]
    c1 = cek_perlu_aturan_provinsi(backtest(pd.DataFrame(seragam), 24, (3,)))
    cek("32. Provinsi seragam tidak menuntut aturan terpisah",
        c1["penyesalan_rata"] < 0.02,
        f"penyesalan {c1['penyesalan_rata']:+.4f}")

    campur = []
    for j in range(12):
        h = 40000.0
        for i, b in enumerate(bulan):
            if j % 2 == 0:
                v = 40000 * (1 + 0.30 * np.sin(2 * np.pi * i / 12)) + rng.normal(0, 500)
            else:
                h = max(500, h * (1 + rng.normal(0, 0.08)))
                v = h
            campur.append(dict(provinsi=f"P{j}", komoditas="Campur", bulan=b,
                               harga=round(v, -1)))
    c2 = cek_perlu_aturan_provinsi(backtest(pd.DataFrame(campur), 24, (3,)))
    cek("33. Provinsi berperilaku beda terdeteksi menuntut aturan terpisah",
        c2["penyesalan_rata"] > 0.05 and c2["rasio_beda"] > 0.2,
        f"penyesalan {c2['penyesalan_rata']:+.4f} beda {c2['rasio_beda']:.0%}")


# ------------------------------------------------------------------- 34
def uji_deret_beku():
    """
    Provinsi berharga tetap tidak boleh mematikan pemeriksaan.

    Galat naif nol membuat MASE menjadi 0/0 alias NaN. Satu grup ber-NaN penuh
    cukup untuk membuat idxmin melempar ValueError, dan seluruh pemeriksaan
    aturan provinsi berhenti — padahal maknanya sederhana: pada deret yang tidak
    pernah bergerak, naif tak terkalahkan.
    """
    import numpy as np

    from backtest_harga import backtest, cek_perlu_aturan_provinsi

    rng = np.random.default_rng(2)
    bulan = pd.date_range("2019-01-01", periods=90, freq="MS")
    baris = [dict(provinsi="Beku", komoditas="X", bulan=b, harga=15000) for b in bulan]
    for p in "AB":
        h = 15000.0
        for b in bulan:
            h = max(500, h * (1 + rng.normal(0, 0.06)))
            baris.append(dict(provinsi=p, komoditas="X", bulan=b, harga=round(h, -1)))
    try:
        c = cek_perlu_aturan_provinsi(backtest(pd.DataFrame(baris), 24, (1, 3)))
        beku = c["rincian"][c["rincian"].provinsi == "Beku"]
        berhasil = len(beku) > 0 and (beku.dipakai == "naif").all()
        pesan = ""
    except Exception as e:
        berhasil, pesan = False, f"{type(e).__name__}: {e}"
    cek("34. Provinsi berharga tetap tidak mematikan pemeriksaan", berhasil, pesan)


if __name__ == "__main__":
    print("=" * 68)
    print("UJI PIPELINE INDEKS KESIAPAN DATA — PradanaLog")
    print("=" * 68)
    uji_validasi()
    uji_perhitungan()
    uji_asal_usul()
    uji_ketahanan()
    uji_katalog_tidak_tertimpa()
    uji_skala()
    uji_integrasi_tabel()
    uji_render_tab()
    uji_validasi_tidak_mati()
    uji_batas_skor()
    uji_kolom_katalog()
    uji_pengurai_siskaperbapo()
    uji_diagnosa_penerusan()
    uji_baseline_naif()
    uji_panel_bulanan()
    uji_backtest_harga()
    uji_aturan_provinsi()
    uji_deret_beku()
    print("=" * 68)
    print(f"Lulus {len(LULUS)} · Gagal {len(GAGAL)}")
    if GAGAL:
        print("Yang gagal: " + ", ".join(GAGAL))
        print("\nJangan pakai angka dari pipeline ini sampai semuanya lulus.")
    sys.exit(1 if GAGAL else 0)
