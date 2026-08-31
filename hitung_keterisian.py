"""
hitung_keterisian.py — mengukur keterisian sistem harga daerah
===============================================================
Dipakai untuk mengganti tebakan `keterisian` di katalog_harga.csv dengan
angka hasil hitungan. Dua bagian:

  1. hitung()          — dari data harga tidy, hasilkan keterisian pasar & kabupaten
  2. perbarui_katalog()— tulis hasilnya ke katalog_harga.csv sekaligus ubah status

Format data masukan (CSV tidy, satu baris per pengamatan):
    tanggal,kabkota,pasar,komoditas,harga
    2025-01-01,Kabupaten Jember,Pasar Tanjung,beras,13500
Baris dengan harga kosong/0 boleh ada atau boleh dihilangkan; keduanya
diperlakukan sebagai sel tidak terisi selama daftar kabkota, pasar, tanggal,
dan komoditas yang seharusnya ada disediakan lewat parameter.

CATATAN PENTING — pilih unit yang benar.
PradanaLog mengambil keputusan di tingkat kabupaten, bukan pasar. Sebuah
kabupaten sudah terlayani kalau satu saja pasarnya melaporkan harga hari itu.
Karena itu yang masuk katalog adalah keterisian tingkat kabupaten. Memakai
keterisian tingkat pasar akan menghukum daerah yang punya banyak pasar sampel.
"""

from pathlib import Path

import pandas as pd


# ------------------------------------------------------------------ hitung
def hitung(df: pd.DataFrame, kolom_harga: str = "harga") -> dict:
    """
    df: tidy data harga. Kembalikan keterisian tingkat pasar dan kabupaten,
    plus rincian per tanggal dan per komoditas untuk pemeriksaan.
    """
    d = df.copy()
    d["tanggal"] = pd.to_datetime(d["tanggal"])
    d["terisi"] = pd.to_numeric(d[kolom_harga], errors="coerce").fillna(0).gt(0).astype(int)

    # rangka penuh: semua kombinasi yang seharusnya ada
    idx = pd.MultiIndex.from_product(
        [sorted(d.kabkota.unique()), sorted(d.komoditas.unique()),
         pd.date_range(d.tanggal.min(), d.tanggal.max(), freq="D")],
        names=["kabkota", "komoditas", "tanggal"])

    # Tingkat pasar. Rangka dibangun dari pasangan kabkota-pasar yang benar-benar
    # ada, bukan dari hasil kali kartesian seluruh kabkota x seluruh nama pasar.
    # Versi kartesian membangkitkan 38 x 120 x 5 x 365 = 8,3 juta entri lalu
    # menyaringnya dengan list comprehension Python — cukup untuk menggantung
    # laptop pada penarikan setahun penuh.
    pasangan = d[["kabkota", "pasar"]].drop_duplicates()
    komoditas = sorted(d.komoditas.unique())
    tanggal = pd.date_range(d.tanggal.min(), d.tanggal.max(), freq="D")
    rangka_pasar = (pasangan.merge(pd.DataFrame({"komoditas": komoditas}), how="cross")
                    .merge(pd.DataFrame({"tanggal": tanggal}), how="cross"))

    pasar = (d.groupby(["kabkota", "pasar", "komoditas", "tanggal"], as_index=False)
             .terisi.max())
    gab = rangka_pasar.merge(pasar, on=["kabkota", "pasar", "komoditas", "tanggal"],
                             how="left")
    k_pasar = float(gab.terisi.fillna(0).mean())

    # tingkat kabupaten: terisi jika minimal satu pasar melapor
    kab = d.groupby(["kabkota", "komoditas", "tanggal"]).terisi.max()
    kab = kab.reindex(idx).fillna(0)
    k_kab = float(kab.mean())

    per_tanggal = kab.groupby("tanggal").mean()
    per_komoditas = kab.groupby("komoditas").mean()
    per_kabkota = kab.groupby("kabkota").mean()

    return {
        "keterisian_pasar": round(k_pasar, 4),
        "keterisian_kabupaten": round(k_kab, 4),
        "n_kabkota": int(d.kabkota.nunique()),
        "n_pasar": int(d.groupby(["kabkota", "pasar"]).ngroups),
        "n_komoditas": int(d.komoditas.nunique()),
        "n_hari": int((d.tanggal.max() - d.tanggal.min()).days + 1),
        "per_tanggal": per_tanggal,
        "per_komoditas": per_komoditas.round(4),
        "per_kabkota": per_kabkota.round(4).sort_values(),
    }


def buang_hari_berjalan(df: pd.DataFrame, n: int = 2) -> pd.DataFrame:
    """
    Buang n hari terakhir sebelum menghitung.

    Alasannya: papan progres Siskaperbapo yang menampilkan "12 dari 38 kab/kota"
    mengukur entri hari itu yang belum selesai, bukan kelengkapan arsip. Sampel
    7 hari yang ditarik 20-08-2026 menunjukkan enam hari pertama terisi 100% di
    tingkat kabupaten sementara hari terakhir baru 78,9%. Kalau Anda ingin angka
    kelengkapan arsip, buang ekornya. Kalau Anda ingin tahu seberapa segar data
    untuk peramalan real-time, jangan dibuang — dan pakai angka itu untuk
    menetapkan jeda aman model.
    """
    d = df.copy()
    d["tanggal"] = pd.to_datetime(d["tanggal"])
    return d[d.tanggal <= d.tanggal.max() - pd.Timedelta(days=n)]


# ------------------------------------------------------- diagnosa penerusan
def diagnosa_penerusan(df: pd.DataFrame, kolom_harga: str = "harga") -> dict:
    """
    Bedakan "terisi" dari "dilaporkan hari itu".

    Keterisian menghitung sel yang ada isinya. Ia tidak bisa membedakan harga
    yang benar-benar disurvei hari itu dari harga kemarin yang diteruskan karena
    petugas tidak melapor. Keduanya terlihat sebagai sel terisi.

    Kejadian yang melahirkan fungsi ini: kentang Jawa Timur, 56 hari, 114 pasar,
    keterisian 1,000 pas — sementara median harga unik per pasar hanya 2 dan 33
    pasar tidak pernah sekali pun mengubah harga.

    Fungsi ini tidak menyimpulkan sebabnya. Harga datar bisa berarti angka
    diteruskan, bisa juga berarti harganya memang tidak bergerak. Yang diukur
    adalah akibatnya: berapa banyak informasi baru yang dibawa deret harian itu.

    Kenapa penting untuk PradanaLog: model peramalan yang dilatih pada deret
    hasil penerusan akan belajar bahwa harga besok sama dengan harga hari ini.
    MAPE-nya akan tampak sangat bagus dan modelnya tidak berguna. Galat rendah
    di sini menandakan data yang datar, bukan model yang pandai.

    Kembalian memuat `laju_perubahan`: bagian pasangan hari berurutan yang
    harganya berubah. Untuk pangan segar yang disurvei harian, angka wajar ada
    di kisaran 0,3–0,7. Di bawah 0,1 berarti deret harian itu semu.
    """
    d = df.copy()
    d["tanggal"] = pd.to_datetime(d["tanggal"])
    d = d[pd.to_numeric(d[kolom_harga], errors="coerce").fillna(0) > 0]
    d = d.sort_values(["kabkota", "pasar", "komoditas", "tanggal"])

    kunci = ["kabkota", "pasar", "komoditas"]
    d["sebelum"] = d.groupby(kunci)[kolom_harga].shift()
    d["hari_jeda"] = d.groupby(kunci)["tanggal"].diff().dt.days
    # hanya pasangan hari yang benar-benar berurutan yang dihitung
    pasangan = d[d.hari_jeda == 1]
    berubah = (pasangan[kolom_harga] != pasangan.sebelum)

    per_pasar = d.groupby(kunci)[kolom_harga].nunique()
    n_hari = d.groupby(kunci).tanggal.nunique()
    beku = int((per_pasar == 1).sum())

    laju = float(berubah.mean()) if len(pasangan) else float("nan")
    laju_pasar = (pasangan.assign(b=berubah.values).groupby(kunci).b.mean()
                  if len(pasangan) else pd.Series(dtype=float))

    return {
        "laju_perubahan": round(laju, 4),
        "harga_unik_median": float(per_pasar.median()),
        "hari_terpantau_median": float(n_hari.median()),
        "pasar_beku": beku,
        "pasar_total": int(len(per_pasar)),
        "rasio_beku": round(beku / len(per_pasar), 4) if len(per_pasar) else 0.0,
        "panjang_deret_datar": round(1 / laju, 1) if laju and laju > 0 else float("inf"),
        "laju_per_pasar": laju_pasar.round(3).sort_values(),
        "vonis": _vonis(laju),
    }


def _vonis(laju: float) -> str:
    """
    Sengaja tidak menyimpulkan SEBABNYA laju rendah.

    Harga bisa datar karena petugas meneruskan angka kemarin, atau karena
    harganya memang tidak bergerak — beras dan komoditas pokok lain wajar
    lengket berminggu-minggu. Dari data saja keduanya tidak bisa dibedakan, dan
    mengaku tahu sebabnya berarti mengarang.

    Yang bisa disimpulkan: berapa banyak informasi baru yang dibawa deret harian
    itu. Untuk peramalan, dampaknya sama saja apa pun sebabnya — model akan
    belajar bahwa harga besok sama dengan harga hari ini.
    """
    if pd.isna(laju):
        return "tidak cukup hari berurutan untuk dinilai"
    if laju < 0.10:
        return ("informasi harian sangat rendah — resolusi efektif mingguan atau "
                "lebih kasar; latih model pada data teragregasi, jangan harian")
    if laju < 0.25:
        return ("informasi harian rendah — sebagian besar hari tidak membawa angka "
                "baru; sebutkan sebagai keterbatasan dan uji agregasi mingguan")
    if laju < 0.50:
        return "informasi harian sedang — wajar untuk pangan pokok, sebutkan di metodologi"
    return "variasi harian sehat — deret bisa dipakai apa adanya"


# --------------------------------------------------------- perbarui katalog
def perbarui_katalog(provinsi: str, sistem_key: str, keterisian: float,
                     catatan: str, status: str = "terverifikasi",
                     path: Path = Path("katalog_harga.csv")) -> pd.DataFrame:
    kat = pd.read_csv(path)
    m = (kat.provinsi == provinsi) & kat.sistem.astype(str).str.contains(sistem_key, na=False)
    if not m.any():
        raise ValueError(f"Tidak ada baris {provinsi} dengan sistem mengandung '{sistem_key}'")
    kat.loc[m, "keterisian"] = round(float(keterisian), 4)
    kat.loc[m, "status_verifikasi"] = status
    kat.loc[m, "catatan"] = catatan
    kat.loc[m, "tanggal_akses"] = pd.Timestamp.today().strftime("%Y-%m-%d")
    kat.to_csv(path, index=False)
    print(f"{int(m.sum())} baris diperbarui: {provinsi} / {sistem_key} -> {keterisian:.3f}")
    return kat


# ------------------------------------------------------------------ penarik
KOMODITAS_SISKAPERBAPO = {
    # id terverifikasi 22-08-2026 dari <select name="komoditas"> di
    # https://siskaperbapo.jatimprov.go.id/harga-komoditas (67 komoditas dipantau)
    "beras": 4,          # Beras Medium / kg   (Beras Premium = 2)
    "jagung": 25,        # Jagung Pipilan Kering / kg
    "bawang": 39,        # Bawang Merah / kg
    "cabai_besar": 38,   # Cabe Merah Besar / kg
    "cabai_rawit": 50,   # Cabe Rawit Merah / kg
    "kentang": 45,       # Kentang / kg
}

URL_SISKAPERBAPO = "https://siskaperbapo.jatimprov.go.id/harga-komoditas"


def tarik_siskaperbapo(tanggal_akhir: str, komoditas: str, jeda: float = 2.0,
                       url: str = URL_SISKAPERBAPO) -> pd.DataFrame:
    """
    Tarik satu jendela tujuh hari dari SISKAPERBAPO.

    Halamannya memakai formulir POST dengan csrf_token, bukan query string, jadi
    URL tidak bisa dirangkai sendiri. Alurnya: ambil halaman untuk mendapat token
    dan kuki sesi, lalu kirim POST memakai token itu dalam sesi yang sama.

    Formulir hanya menyediakan `tanggal_akhir`; tabel selalu menampilkan tujuh
    hari yang berakhir pada tanggal tersebut. Untuk rentang panjang, panggil
    berulang dengan tanggal_akhir mundur tujuh hari tiap kali.

    Kolom baris: penomoran bulat (1, 2) menandai kabupaten/kota, desimal (1.1)
    menandai pasar. Tanda strip berarti tidak ada laporan hari itu.
    """
    import time

    import requests
    from bs4 import BeautifulSoup

    if komoditas in KOMODITAS_SISKAPERBAPO:
        kom_id = KOMODITAS_SISKAPERBAPO[komoditas]
    else:
        kom_id = int(komoditas)

    sesi = requests.Session()
    sesi.headers.update({"User-Agent": "riset-akademik-pradanalog"})

    awal = sesi.get(url, timeout=30)
    awal.raise_for_status()
    token = BeautifulSoup(awal.text, "html.parser").find(
        "input", {"name": "csrf_token"})
    if token is None:
        raise RuntimeError("csrf_token tidak ditemukan; struktur halaman berubah.")

    time.sleep(jeda)
    r = sesi.post(url, timeout=45, data={"csrf_token": token["value"],
                                         "tanggal_akhir": tanggal_akhir,
                                         "komoditas": str(kom_id)})
    r.raise_for_status()
    time.sleep(jeda)
    return _urai_tabel(r.text, komoditas)


def _urai_tabel(html: str, komoditas: str) -> pd.DataFrame:
    import re

    sup_awal = html.index("<table")
    tab = html[sup_awal:html.index("</table>", sup_awal) + 8]
    kepala = [re.sub(r"<[^>]+>", "", h).strip()
              for h in re.findall(r"<th[^>]*>(.*?)</th>", tab, re.S)]
    tanggal = [h for h in kepala if re.match(r"\d{4}-\d{2}-\d{2}", h)]
    if not tanggal:
        raise RuntimeError("Kolom tanggal tidak terbaca; struktur tabel berubah.")

    baris, kab = [], None
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tab, re.S):
        sel = [re.sub(r"<[^>]+>", "", c).replace("\xa0", " ").strip()
               for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(sel) < 2 + len(tanggal):
            continue
        no, lokasi, nilai = sel[0], sel[1], sel[2:2 + len(tanggal)]
        if not re.match(r"^\d+\.\d+$", no):
            if re.match(r"^\d+$", no):
                kab = lokasi
            continue
        for t, v in zip(tanggal, nilai):
            h = pd.to_numeric(v.replace(".", "").replace(",", "."), errors="coerce")
            baris.append(dict(tanggal=t, kabkota=kab, pasar=lokasi,
                              komoditas=komoditas, harga=0 if pd.isna(h) else h))
    return pd.DataFrame(baris)


def tarik_rentang(tanggal_mulai: str, tanggal_selesai: str, komoditas: str,
                  jeda: float = 2.0) -> pd.DataFrame:
    """Panggil tarik_siskaperbapo berulang, mundur tujuh hari tiap kali."""
    mulai = pd.Timestamp(tanggal_mulai)
    kursor = pd.Timestamp(tanggal_selesai)
    kumpul = []
    while kursor >= mulai:
        potong = tarik_siskaperbapo(kursor.strftime("%Y-%m-%d"), komoditas, jeda)
        if len(potong):
            kumpul.append(potong)
            print(f"  {kursor:%Y-%m-%d}: {len(potong)} baris")
        kursor -= pd.Timedelta(days=7)
    if not kumpul:
        return pd.DataFrame(columns=["tanggal", "kabkota", "pasar", "komoditas", "harga"])
    gab = pd.concat(kumpul, ignore_index=True)
    return gab.drop_duplicates(subset=["tanggal", "kabkota", "pasar", "komoditas"])


# --------------------------------------------------------------------- CLI
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print(__doc__)
        print("Pakai: python hitung_keterisian.py data_harga.csv "
              "[provinsi] [sistem_key]")
        sys.exit(0)

    df = pd.read_csv(sys.argv[1])
    hasil = hitung(df)
    print(f"\nCakupan  : {hasil['n_kabkota']} kab/kota · {hasil['n_pasar']} pasar · "
          f"{hasil['n_komoditas']} komoditas · {hasil['n_hari']} hari")
    print(f"Keterisian tingkat pasar     : {hasil['keterisian_pasar']:.3f}")
    print(f"Keterisian tingkat kabupaten : {hasil['keterisian_kabupaten']:.3f}  "
          f"<-- angka untuk katalog")
    print("\nLima kabupaten terlemah:")
    print(hasil["per_kabkota"].head(5).to_string())
    print("\nPer komoditas:")
    print(hasil["per_komoditas"].to_string())

    d = diagnosa_penerusan(df)
    print(f"\n--- Diagnosa penerusan harga ---")
    print(f"Laju perubahan harga antar hari : {d['laju_perubahan']:.3f}")
    print(f"Harga unik per pasar (median)   : {d['harga_unik_median']:.0f} "
          f"dari {d['hari_terpantau_median']:.0f} hari")
    print(f"Pasar harga tak pernah berubah  : {d['pasar_beku']}/{d['pasar_total']} "
          f"({d['rasio_beku']:.0%})")
    print(f"Rata-rata harga bertahan        : {d['panjang_deret_datar']} hari")
    print(f"\nVonis: {d['vonis']}")

    if len(sys.argv) >= 4:
        perbarui_katalog(
            sys.argv[2], sys.argv[3], hasil["keterisian_kabupaten"],
            catatan=(f"Dihitung dari {hasil['n_hari']} hari x {hasil['n_komoditas']} "
                     f"komoditas x {hasil['n_kabkota']} kab/kota; keterisian tingkat "
                     f"pasar {hasil['keterisian_pasar']:.3f}."))
