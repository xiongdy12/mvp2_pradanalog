"""
uji_sistem.py — uji otomatis modul login dan drill-down kabupaten
=================================================================
    python uji_sistem.py

Berkas terpisah dari uji_ikd.py karena modul-modul ini mengimpor Streamlit di
tingkat modul; tiruan Streamlit harus dipasang sebelum impor pertama, dan itu
tidak bisa digabung dengan berkas uji yang sudah mengimpor Streamlit asli.
"""

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

DIPANGGIL = []


class _Kolom:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __getattr__(self, n): return _Fn(n)


class _Fn:
    def __init__(self, n): self.n = n

    def __call__(self, *a, **k):
        DIPANGGIL.append(self.n)
        if self.n == "columns":
            sp = a[0] if a else 1
            return [_Kolom() for _ in range(sp if isinstance(sp, int) else len(sp))]
        if self.n in ("expander", "container", "spinner", "form", "status"):
            return _Kolom()
        if self.n == "cache_data":
            return a[0] if (a and callable(a[0])) else (lambda f: f)
        if self.n == "selectbox":
            return a[1][k.get("index", 0)] if len(a) > 1 else None
        if self.n == "multiselect":
            return k.get("default", [])
        if self.n in ("button", "checkbox"):
            return False
        if self.n == "text_input":
            return ""
        return None


class _FakeSt(types.ModuleType):
    __file__ = "fake_streamlit.py"
    session_state = {}
    sidebar = _Kolom()

    def __getattr__(self, n): return _Fn(n)


sys.modules["streamlit"] = _FakeSt("streamlit")

import pandas as pd  # noqa: E402

import auth  # noqa: E402
import data_kabupaten as dk  # noqa: E402

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
    print(f"[{'  OK  ' if kondisi else ' GAGAL'}] {nama}" + (f"  — {pesan}" if pesan and not kondisi else ""))


# ------------------------------------------------------------------ 1-5
def uji_sandi():
    r = auth.buat_hash("KataSandiUji123")
    cek("1. Kata sandi tidak tersimpan apa adanya",
        "KataSandiUji123" not in str(r))
    cek("2. Sandi sama menghasilkan hash berbeda (garam acak)",
        auth.buat_hash("sama")["hash"] != auth.buat_hash("sama")["hash"])
    cek("3. Sandi benar diterima", auth._cocok("KataSandiUji123", r))
    cek("4. Sandi salah ditolak", not auth._cocok("KataSandiUji124", r))
    cek("5. Jumlah iterasi PBKDF2 memadai", r["iterasi"] >= 200_000,
        f"hanya {r['iterasi']}")


# ------------------------------------------------------------------ 6-9
def uji_lingkup():
    pengguna = {
        "p": {**auth.buat_hash("sandi-pusat-1"), "peran": "pusat"},
        "v": {**auth.buat_hash("sandi-prov-11"), "peran": "provinsi",
              "provinsi": "Jawa Timur"},
        "k": {**auth.buat_hash("sandi-kab-111"), "peran": "kabupaten",
              "provinsi": "Jawa Timur", "kabkota": "Kabupaten Malang"},
    }
    cek("6. Akun tidak terdaftar ditolak",
        auth.periksa("hantu", "apa saja", pengguna) is None)

    df = pd.DataFrame({
        "provinsi": ["Jawa Timur"] * 3 + ["Jawa Barat"],
        "kabkota": ["Kabupaten Malang", "Kota Surabaya", "Kabupaten Kediri",
                    "Kota Bandung"]})
    hasil = {n: auth.batasi(df, auth.periksa(n, s, pengguna))
             for n, s in [("p", "sandi-pusat-1"), ("v", "sandi-prov-11"),
                          ("k", "sandi-kab-111")]}
    cek("7. Peran pusat melihat seluruh wilayah", len(hasil["p"]) == 4)
    cek("8. Peran provinsi hanya melihat provinsinya",
        len(hasil["v"]) == 3 and set(hasil["v"].provinsi) == {"Jawa Timur"})
    cek("9. Peran kabupaten hanya melihat wilayahnya",
        len(hasil["k"]) == 1 and hasil["k"].kabkota.iloc[0] == "Kabupaten Malang")

    tanpa = df.drop(columns=["provinsi", "kabkota"])
    sesi = auth.periksa("v", "sandi-prov-11", pengguna)
    cek("10. Data tanpa kolom wilayah gagal ke arah tertutup, bukan terbuka",
        len(auth.batasi(tanpa, sesi)) == 0,
        "data penuh bocor ke peran yang seharusnya dibatasi")

    palsu = {"peran": "administrator_super", "provinsi": "Jawa Timur"}
    cek("11. Peran tak dikenal tidak diberi data", len(auth.batasi(df, palsu)) == 0)


# ---------------------------------------------------------------- 12-15
def uji_data_kabupaten():
    profil, harga = dk.buat_contoh()
    cek("12. Data contoh lolos validasi bentuk",
        dk.validasi(profil, harga, ketat=False) == [])

    semua_contoh = (profil.status_verifikasi == "contoh").all()
    cek("13. Setiap baris contoh ditandai sebagai contoh", bool(semua_contoh))

    try:
        dk.validasi(profil, harga, izinkan_contoh=False)
        cek("14. Data contoh ditolak masuk hasil akhir", False,
            "angka karangan lolos tanpa perlawanan")
    except dk.DataKabupatenTidakSah:
        cek("14. Data contoh ditolak masuk hasil akhir", True)

    kasus = {
        "kabupaten ganda": (pd.concat([profil, profil.head(1)]), harga),
        "harga negatif": (profil, harga.assign(
            harga=harga.harga.mask(harga.index == 0, -100))),
        "koordinat luar Indonesia": (profil.assign(
            lat=profil.lat.mask(profil.index == 0, 55)), harga),
        "komoditas asing": (profil, harga.assign(
            komoditas=harga.komoditas.mask(harga.index == 0, "gula"))),
        "penduduk nol": (profil.assign(
            penduduk=profil.penduduk.mask(profil.index == 0, 0)), harga),
        "kabupaten yatim di harga": (profil, harga.assign(
            kabkota=harga.kabkota.mask(harga.index == 0, "Kabupaten Antah"))),
    }
    tertangkap = sum(1 for a in kasus.values()
                     if _ditolak(lambda: dk.validasi(*a)))
    cek(f"15. Validasi data kabupaten menolak {len(kasus)} jenis cacat",
        tertangkap == len(kasus), f"hanya {tertangkap} tertangkap")


def _ditolak(fn):
    try:
        fn()
        return False
    except dk.DataKabupatenTidakSah:
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- 16-18
def uji_render():
    berkas = _cari_aplikasi()
    if berkas is not None:
        src = berkas.read_text(encoding="utf-8")
        blok = src[src.index("def warna_nilai"):src.index("def build_deck")]
        ns = {}
        exec("import html as _html\n" + blok, ns)
        df_to_html = ns["df_to_html"]
    else:
        def df_to_html(df, **k): return df.to_html(index=False)

    profil, harga = dk.buat_contoh()

    # tab_kabupaten membaca kab_profil.csv dan kab_harga.csv dari jalur tetap,
    # sehingga uji ini terpaksa menimpa berkas sesungguhnya. Isi aslinya
    # disalin lebih dulu dan dipulihkan saat proses berakhir, termasuk bila ada
    # uji yang gagal di tengah jalan. Tanpa itu, sekali menjalankan uji akan
    # menghapus data terverifikasi yang perlu berjam-jam untuk dibangun ulang.
    import atexit
    import shutil as _sh
    from pathlib import Path as _P

    def _jaga(nama):
        asli, cad = _P(nama), _P(f"._pulih_{nama}")
        if cad.exists():           # sisa proses yang mati mendadak
            _sh.copy2(cad, asli)
        if not asli.exists():
            return
        _sh.copy2(asli, cad)

        def _pulihkan():
            if cad.exists():
                _sh.copy2(cad, asli)
                cad.unlink(missing_ok=True)

        atexit.register(_pulihkan)

    for _n in ("kab_profil.csv", "kab_harga.csv"):
        _jaga(_n)

    profil.to_csv("kab_profil.csv", index=False)
    harga.to_csv("kab_harga.csv", index=False)

    import importlib

    import tab_kabupaten
    importlib.reload(tab_kabupaten)

    akun = [("pusat", None, None), ("provinsi", "Jawa Timur", None),
            ("kabupaten", "Jawa Timur", "Kabupaten Malang")]
    for peran, prov, kab in akun:
        sesi = {"pengguna": "uji", "nama_tampil": "Uji", "peran": peran,
                "provinsi": prov, "kabkota": kab,
                "kedaluwarsa": "2099-01-01T00:00:00"}
        sys.modules["streamlit"].session_state = {"pl_sesi": sesi}
        DIPANGGIL.clear()
        try:
            tab_kabupaten.render_tab_kabupaten(df_to_html)
            berhasil = DIPANGGIL.count("pydeck_chart") == 1 and DIPANGGIL.count("metric") >= 4
            cek(f"1{6 + akun.index((peran, prov, kab))}. Tab kabupaten dirender "
                f"untuk peran {peran}", berhasil,
                f"peta={DIPANGGIL.count('pydeck_chart')} metrik={DIPANGGIL.count('metric')}")
        except Exception as e:
            cek(f"1{6 + akun.index((peran, prov, kab))}. Tab kabupaten dirender "
                f"untuk peran {peran}", False, f"{type(e).__name__}: {e}")


# ------------------------------------------------------------------- 19
def uji_peringatan_contoh():
    profil, harga = dk.buat_contoh()
    r = dk.ringkas_status(profil, harga, nama=["neraca", "harga"])
    cek("19. Porsi data contoh terhitung untuk spanduk peringatan",
        abs(r["rasio_contoh"] - 1.0) < 1e-9,
        f"rasio {r['rasio_contoh']:.2f}, seharusnya 1,00")

    # Setelah profil diverifikasi, rasio gabungan tetap hampir 100% karena
    # kab_harga barisnya ribuan sedangkan profil hanya 38. Rincian per berkas
    # harus membedakan keduanya; tanpa itu spanduk mengumumkan seluruh data
    # masih contoh padahal neraca surplus-defisit sudah nyata.
    profil2 = profil.copy()
    profil2["status_verifikasi"] = "terverifikasi"
    r2 = dk.ringkas_status(profil2, harga, nama=["neraca", "harga"])
    cek("20. Rincian membedakan neraca terverifikasi dari harga yang masih contoh",
        r2["rinci"]["neraca"]["rasio"] == 0 and r2["rinci"]["harga"]["rasio"] == 1.0
        and r2["rasio_contoh"] > 0.99,
        f"neraca {r2['rinci']['neraca']['rasio']} harga {r2['rinci']['harga']['rasio']}")


# ------------------------------------------------------------------- 20
def uji_penyandian():
    """
    Berkas kredensial harus UTF-8, bukan penyandian bawaan sistem.

    Di Windows, Path.write_text tanpa parameter encoding memakai cp1252, dan
    nama tampil seperti "Bapanas — Pusat" tersimpan rusak lalu gagal dibaca
    ulang. Ketahuan saat pengguna membuka kredensial.json di peramban dan
    melihat karakter berlian bertanda tanya.
    """
    from pathlib import Path
    t = Path("._uji_encoding.json")
    nama = "Bapanas — Pusat · TPID Ngawi"
    auth.simpan_pengguna(
        {"uji": {**auth.buat_hash("SandiUji12345"), "peran": "pusat",
                 "nama_tampil": nama}}, t)
    utf8 = "—".encode("utf-8") in t.read_bytes()
    kembali = auth.muat_pengguna(t)
    utuh = kembali["uji"]["nama_tampil"] == nama
    masuk = bool(auth.periksa("uji", "SandiUji12345", kembali))
    t.unlink(missing_ok=True)
    cek("21. Kredensial ditulis dan dibaca sebagai UTF-8", utf8 and utuh and masuk,
        f"utf8={utf8} utuh={utuh} login={masuk}")


# ------------------------------------------------------------------- 21
def uji_pindah_penyandian():
    """
    Berkas kredensial lama bersandi Windows harus dipindahkan, bukan mematikan
    aplikasi. muat_pengguna dipanggil oleh gerbang_login, jadi satu berkas yang
    tak terbaca sempat mengunci pengguna di luar tanpa jalan masuk.
    """
    import json
    from pathlib import Path
    t = Path("._uji_lama.json")
    isi = {"uji": {**auth.buat_hash("SandiUji12345"), "peran": "pusat",
                   "nama_tampil": "Bapanas — Pusat"}}
    t.write_text(json.dumps(isi, indent=2, ensure_ascii=False), encoding="cp1252")
    rusak = b"\x97" in t.read_bytes()
    try:
        hasil = auth.muat_pengguna(t)
        pulih = hasil["uji"]["nama_tampil"] == "Bapanas — Pusat"
        sudah_utf8 = "—".encode("utf-8") in t.read_bytes()
        masuk = bool(auth.periksa("uji", "SandiUji12345", hasil))
    except Exception as e:
        pulih = sudah_utf8 = masuk = False
        print(f"          {type(e).__name__}: {e}")
    t.unlink(missing_ok=True)
    cek("22. Kredensial bersandi lama dipindahkan, bukan mematikan aplikasi",
        rusak and pulih and sudah_utf8 and masuk,
        f"pulih={pulih} utf8={sudah_utf8} login={masuk}")


def uji_json_rusak():
    """Berkas rusak parah harus memberi petunjuk, bukan jejak tumpukan."""
    from pathlib import Path
    t = Path("._uji_rusak.json")
    t.write_text("{ini bukan json", encoding="utf-8")
    try:
        auth.muat_pengguna(t)
        hasil = False
        pesan = "berkas rusak diterima tanpa protes"
    except ValueError as e:
        hasil = "buat_kredensial" in str(e)
        pesan = f"pesan tidak menyebutkan cara memperbaiki: {e}"
    except Exception as e:
        hasil, pesan = False, f"melempar {type(e).__name__}, bukan pesan yang jelas"
    t.unlink(missing_ok=True)
    cek("23. Kredensial rusak memberi petunjuk perbaikan", hasil, pesan)


# ------------------------------------------------------------------- 23-25
def uji_radar_prioritas():
    """
    Radar prioritas harus diam ketika pi bernilai nol identik.

    Persamaan (3) menghitung pi dari rasio proyeksi terhadap harga kini. Bila
    metode terpilih persistensi, proyeksi sama dengan harga kini sehingga pi = 0
    untuk seluruh provinsi. Tabel berisi +0,0% pada setiap baris terbaca sebagai
    "harga stabil di mana-mana", padahal artinya "tidak ada sinyal proyeksi".
    """
    import numpy as np

    import radar_prioritas as rp

    prov = [f"Prov{i}" for i in range(10)]
    datar = pd.DataFrame({"provinsi": prov, "komoditas": "Beras", "h": 3,
                          "harga_kini": 13000, "harga_prediksi": 13000})
    rng = np.random.default_rng(0)
    hidup = pd.DataFrame({"provinsi": prov, "komoditas": "Cabai Rawit", "h": 3,
                          "harga_kini": 50000,
                          "harga_prediksi": (50000 * (1 + rng.normal(0.04, 0.06, 10))).round(-1)})
    pred = pd.concat([datar, hidup], ignore_index=True)

    # Aturan disuntikkan agar uji tidak bergantung pada ada tidaknya berkas
    # aturan di folder kerja; tanpa ini hasilnya berubah-ubah mengikuti isi disk.
    aturan = pd.DataFrame([
        dict(komoditas="Beras", h=3, metode_dipakai="naif", mase=1.345),
        dict(komoditas="Cabai Rawit", h=3, metode_dipakai="campuran", mase=0.800),
    ])

    a = rp.status_sinyal(pred, "Beras", 3, aturan)
    cek("23. Proyeksi datar dikenali sebagai tanpa sinyal prioritas",
        a["ada_sinyal"] is False, f"status {a}")

    b = rp.status_sinyal(pred, "Cabai Rawit", 3, aturan)
    cek("24. Proyeksi bervariasi tetap dikenali membawa sinyal",
        b["ada_sinyal"] is True, f"status {b}")

    DIPANGGIL.clear()
    rp.render_radar(pred, "Beras", lambda df, **k: df.to_html(index=False), h=3,
                    aturan=aturan)
    tanpa_tabel = DIPANGGIL.count("markdown") <= 1 and "info" in DIPANGGIL
    DIPANGGIL.clear()
    rp.render_radar(pred, "Cabai Rawit", lambda df, **k: df.to_html(index=False), h=3,
                    aturan=aturan)
    dengan_tabel = DIPANGGIL.count("markdown") >= 2
    cek("25. Tabel radar hanya dirender saat sinyal tersedia",
        tanpa_tabel and dengan_tabel,
        f"tanpa_sinyal_render_tabel={not tanpa_tabel} dengan_sinyal_render={dengan_tabel}")

    # Sinyal ada tetapi seluruh proyeksi menurun: pi = 0 di mana-mana, namun
    # maknanya berlawanan dengan kasus persistensi. Keadaan ini harus tetap
    # menampilkan peringkat sebagai daftar pantau, bukan dibuang.
    turun = pd.DataFrame({"provinsi": prov, "komoditas": "Cabai Rawit", "h": 3,
                          "harga_kini": 57900,
                          "harga_prediksi": (57900 * (1 + rng.uniform(-0.20, -0.03, 10))).round(-1)})
    DIPANGGIL.clear()
    rp.render_radar(turun, "Cabai Rawit", lambda df, **k: df.to_html(index=False), h=3,
                    aturan=aturan)
    cek("26. Proyeksi menurun seluruhnya tetap menampilkan daftar pantau",
        DIPANGGIL.count("markdown") >= 2 and "success" in DIPANGGIL,
        f"komponen {DIPANGGIL}")

    s_turun = rp.status_sinyal(turun, "Cabai Rawit", 3, aturan)
    cek("27. Proyeksi menurun tidak disalahartikan sebagai tanpa sinyal",
        s_turun["ada_sinyal"] is True, f"status {s_turun}")


# ------------------------------------------------------------------- 28-30
def uji_metrik_akurasi():
    """
    MAPE harus selalu tampil bersama lantai naif dan MASE-nya.

    Lahir dari ketidaksinkronan di layar: caption menampilkan MAPE 1,2 persen
    untuk beras dari jendela lima bulan, sementara radar di layar yang sama
    memakai backtest 24 bulan. Angka 1,2 persen juga berdiri tanpa pembanding,
    padahal lantai naifnya 0,79 persen — lebih baik daripada model.
    """
    from pathlib import Path

    import metrik_akurasi as ma

    tmp = Path("._uji_metrik.csv")
    baris = []
    data = {
        "Beras": {"naif": (1.85, 1.0), "hanyut": (2.51, 1.346)},
        "Cabai Rawit": {"naif": (40.84, 1.0), "campuran": (33.24, 0.800)},
    }
    for k, m in data.items():
        for met, (mape, mase) in m.items():
            baris.append(dict(komoditas=k, h=3, metode=met, mape=mape, n=2774, mase=mase))
    pd.DataFrame(baris).to_csv(tmp, index=False)
    metrik = pd.read_csv(tmp)
    metrik["komoditas"] = metrik.komoditas.map(ma._baku)

    b = ma.ringkas_akurasi("Beras", 3, metrik)
    cek("28. Persistensi dilaporkan sebagai metode terpakai bila pesaing kalah",
        b["metode"] == "naif" and abs(b["mape"] - b["mape_naif"]) < 1e-9,
        f"{b}")
    cek("29. MASE pesaing terbaik dilaporkan apa adanya, bukan disetel ke 1",
        abs(b["mase_kandidat"] - 1.346) < 1e-6, f"mase_kandidat {b.get('mase_kandidat')}")

    c = ma.ringkas_akurasi("Cabai Rawit", 3, metrik)
    cek("30. MAPE selalu berpasangan dengan lantai naifnya",
        c["mape"] < c["mape_naif"] and c["mase"] < 0.95,
        f"mape {c['mape']} lantai {c['mape_naif']} mase {c['mase']}")
    tmp.unlink(missing_ok=True)


# ------------------------------------------------------------------- 31-33
def uji_sebab_pi_nol():
    """
    Tiga sebab berbeda membuat pi bernilai nol, dan pesannya harus berbeda.

    Ketahuan di layar: caption menyatakan bawang merah memakai campuran dengan
    MASE 0,888, sementara radar tepat di bawahnya menyatakan backtest memilih
    persistensi. Keduanya membaca aturan yang sama; yang berbeda adalah isi
    prediksi_harga.csv, yang masih berisi keluaran persistensi karena belum
    dibangkitkan ulang memakai aturan hasil backtest.
    """
    import numpy as np

    import radar_prioritas as rp

    prov = [f"P{i}" for i in range(8)]
    aturan = pd.DataFrame([
        dict(komoditas="Beras", h=3, metode_dipakai="naif", mase=1.345),
        dict(komoditas="Bawang Merah", h=3, metode_dipakai="campuran", mase=0.888),
        dict(komoditas="Cabai Rawit", h=3, metode_dipakai="campuran", mase=0.800),
    ])
    rng = np.random.default_rng(2)

    datar_naif = pd.DataFrame({"provinsi": prov, "komoditas": "Beras", "h": 3,
                               "harga_kini": 17000, "harga_prediksi": 17000})
    a = rp.status_sinyal(datar_naif, "Beras", 3, aturan)
    cek("31. Aturan persistensi dengan proyeksi datar dikenali sebagai wajar",
        a.get("sebab") == "aturan_naif" and a["ada_sinyal"] is False, f"{a}")

    datar_ensemble = pd.DataFrame({"provinsi": prov, "komoditas": "Bawang Merah",
                                   "h": 3, "harga_kini": 49800, "harga_prediksi": 49800})
    b = rp.status_sinyal(datar_ensemble, "Bawang Merah", 3, aturan)
    cek("32. Aturan ensemble dengan proyeksi datar dikenali sebagai berkas usang",
        b.get("sebab") == "prediksi_kedaluwarsa", f"{b}")

    DIPANGGIL.clear()
    rp.render_radar(datar_ensemble, "Bawang Merah",
                    lambda df, **k: df.to_html(index=False), h=3, aturan=aturan)
    cek("33. Berkas usang diberi peringatan, bukan pernyataan model",
        "warning" in DIPANGGIL and "info" not in DIPANGGIL, f"komponen {DIPANGGIL}")


# ------------------------------------------------------------------- 35
def uji_cache_ikut_berkas():
    """
    Kunci cache harus berubah ketika berkas data berubah.

    Versi sebelumnya memakai @st.cache_data pada fungsi tanpa argumen, sehingga
    hasil pemuatan disimpan selamanya. Mengganti kab_profil.csv dengan data
    terverifikasi tidak terlihat sampai aplikasi dimatikan, dan spanduk tetap
    mengumumkan data contoh padahal berkasnya sudah berganti.
    """
    import time
    from pathlib import Path

    import tab_kabupaten as tk

    berkas = Path(tk.__file__).parent / "kab_profil.csv"
    if not berkas.exists():
        print("[ LEWAT] 35. Kunci cache — kab_profil.csv tidak ada")
        return

    sebelum = tk._sidik_berkas()
    isi = berkas.read_bytes()
    time.sleep(0.01)
    berkas.write_bytes(isi)          # tulis ulang: isi sama, waktu ubah berbeda
    sesudah = tk._sidik_berkas()
    cek("35. Kunci cache berubah ketika berkas data disentuh",
        sebelum != sesudah, "kunci tidak berubah — perubahan berkas tidak terbaca")


if __name__ == "__main__":
    print("=" * 68)
    print("UJI MODUL LOGIN DAN DRILL-DOWN KABUPATEN — PradanaLog")
    print("=" * 68)
    uji_sandi()
    uji_lingkup()
    uji_data_kabupaten()
    uji_render()
    uji_peringatan_contoh()
    uji_penyandian()
    uji_pindah_penyandian()
    uji_json_rusak()
    uji_radar_prioritas()
    uji_metrik_akurasi()
    uji_sebab_pi_nol()
    uji_cache_ikut_berkas()
    print("=" * 68)
    print(f"Lulus {len(LULUS)} · Gagal {len(GAGAL)}")
    if GAGAL:
        print("Yang gagal: " + ", ".join(GAGAL))
    sys.exit(1 if GAGAL else 0)
