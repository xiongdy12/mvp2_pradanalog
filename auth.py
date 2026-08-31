"""
auth.py — login berperan untuk PradanaLog
==========================================
Peran mengikuti rantai kelembagaan pengendalian inflasi yang sudah ada, bukan
istilah teknis buatan sendiri:

    pusat     — TPIP / Bapanas / BI pusat : melihat seluruh provinsi
    provinsi  — TPID Provinsi             : melihat kabupaten/kota di provinsinya
    kabupaten — TPID Kabupaten/Kota       : melihat wilayahnya sendiri

Kata sandi TIDAK PERNAH disimpan apa adanya. Berkas kredensial hanya memuat
hash PBKDF2-HMAC-SHA256 beserta garamnya. Buat pengguna lewat
`python buat_kredensial.py`.

BATAS YANG HARUS DISEBUT JUJUR SAAT PRESENTASI
Ini autentikasi tingkat demonstrasi, bukan tingkat produksi:
  - PBKDF2 stdlib dipakai supaya tidak menambah dependensi. Untuk produksi
    pakai bcrypt atau argon2 lewat pustaka yang dirawat.
  - Pembatasan lingkup terjadi di lapisan tampilan. Berkas CSV di server tetap
    utuh; siapa pun yang bisa mengakses berkasnya melewati pembatasan ini.
    Produksi butuh basis data dengan penyaringan di sisi kueri.
  - Belum ada pembatasan percobaan masuk, rotasi sesi, maupun jejak audit.
Sebutkan sendiri batas ini sebelum juri menanyakannya.
"""

import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st

HERE = Path(__file__).parent
KREDENSIAL = HERE / "kredensial.json"
ITERASI = 240_000
MENIT_SESI = 60

PERAN = {
    "pusat": "Pusat (TPIP / Bapanas)",
    "provinsi": "TPID Provinsi",
    "kabupaten": "TPID Kabupaten/Kota",
}


# --------------------------------------------------------------- kata sandi
def buat_hash(sandi: str, garam: str = None) -> dict:
    garam = garam or secrets.token_hex(16)
    turunan = hashlib.pbkdf2_hmac("sha256", sandi.encode(), bytes.fromhex(garam), ITERASI)
    return {"garam": garam, "hash": turunan.hex(), "iterasi": ITERASI}


def _cocok(sandi: str, rekaman: dict) -> bool:
    turunan = hashlib.pbkdf2_hmac("sha256", sandi.encode(),
                                  bytes.fromhex(rekaman["garam"]),
                                  int(rekaman.get("iterasi", ITERASI)))
    # compare_digest dipakai supaya lama pembandingan tidak membocorkan
    # seberapa jauh tebakan mendekati nilai benar.
    return hmac.compare_digest(turunan.hex(), rekaman["hash"])


# -------------------------------------------------------------- kredensial
def muat_pengguna(path: Path = KREDENSIAL) -> dict:
    """Baca dari st.secrets bila tersedia, kalau tidak dari berkas lokal."""
    try:
        rahasia = st.secrets.get("pradanalog_pengguna")
        if rahasia:
            return json.loads(rahasia) if isinstance(rahasia, str) else dict(rahasia)
    except Exception:
        pass
    if path.exists():
        return _baca_json(path)
    return {}


def _baca_json(path: Path) -> dict:
    """
    Baca kredensial sebagai UTF-8, dengan pemindahan otomatis berkas lama.

    Riwayatnya: versi awal memanggil read_text tanpa menyebut encoding, jadi di
    Windows berkas ditulis memakai cp1252 dan karakter seperti tanda pisah em
    pada "Bapanas — Pusat" tersimpan sebagai byte 0x97. Setelah kode beralih ke
    UTF-8, berkas lama itu melempar UnicodeDecodeError — dan karena muat_pengguna
    dipanggil oleh gerbang_login, seluruh aplikasi ikut mati, bukan cuma bagian
    kredensialnya. Pengguna terkunci di luar tanpa jalan masuk.

    Karena itu berkas yang gagal dibaca sebagai UTF-8 dicoba ulang dengan
    penyandian Windows, lalu langsung ditulis ulang sebagai UTF-8 supaya
    persoalannya selesai sekali dan tidak berulang.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        pass
    except json.JSONDecodeError as e:
        raise ValueError(f"{path.name} bukan JSON yang sah: {e}. Hapus berkasnya "
                         f"lalu buat ulang akun dengan buat_kredensial.py.") from e

    for penyandian in ("cp1252", "latin-1"):
        try:
            data = json.loads(path.read_text(encoding=penyandian))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        simpan_pengguna(data, path)
        print(f"{path.name} dipindahkan dari {penyandian} ke UTF-8.")
        return data

    raise ValueError(f"{path.name} tidak terbaca dengan penyandian mana pun. "
                     f"Hapus berkasnya lalu jalankan: python buat_kredensial.py contoh")


def simpan_pengguna(pengguna: dict, path: Path = KREDENSIAL):
    path.write_text(json.dumps(pengguna, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def periksa(nama: str, sandi: str, pengguna: dict = None) -> dict | None:
    pengguna = muat_pengguna() if pengguna is None else pengguna
    rek = pengguna.get(nama)
    if not rek or not _cocok(sandi, rek):
        return None
    return {"pengguna": nama, "nama_tampil": rek.get("nama_tampil", nama),
            "peran": rek["peran"], "provinsi": rek.get("provinsi"),
            "kabkota": rek.get("kabkota")}


# -------------------------------------------------------------------- sesi
def _sesi_hidup() -> bool:
    s = st.session_state.get("pl_sesi")
    if not s:
        return False
    if datetime.now() > datetime.fromisoformat(s["kedaluwarsa"]):
        st.session_state.pop("pl_sesi", None)
        return False
    return True


def sesi_aktif() -> dict | None:
    return st.session_state["pl_sesi"] if _sesi_hidup() else None


def keluar():
    st.session_state.pop("pl_sesi", None)


def gerbang_login(judul: str = "Masuk ke PradanaLog") -> dict | None:
    """
    Tampilkan borang masuk bila belum ada sesi. Kembalikan data sesi bila sudah.
    Pemanggil menghentikan render tab ketika hasilnya None.
    """
    sesi = sesi_aktif()
    if sesi:
        return sesi

    pengguna = muat_pengguna()
    st.markdown(f"#### {judul}")
    if not pengguna:
        st.error("Belum ada pengguna terdaftar. Jalankan `python buat_kredensial.py` "
                 "untuk membuat akun pertama.")
        return None

    st.caption("Lingkup data yang tampil mengikuti peran akun: pusat melihat seluruh "
               "provinsi, TPID provinsi melihat kabupaten/kota di wilayahnya, "
               "operator kabupaten melihat wilayahnya sendiri.")

    k1, k2 = st.columns([1, 2])
    with k1:
        nama = st.text_input("Nama pengguna", key="pl_nama")
        sandi = st.text_input("Kata sandi", type="password", key="pl_sandi")
        if st.button("Masuk", type="primary", use_container_width=True):
            hasil = periksa(nama.strip(), sandi, pengguna)
            if hasil:
                hasil["kedaluwarsa"] = (datetime.now()
                                        + timedelta(minutes=MENIT_SESI)).isoformat()
                st.session_state["pl_sesi"] = hasil
                st.rerun()
            else:
                # Pesan sengaja tidak membedakan nama salah dan sandi salah,
                # supaya tidak bisa dipakai menebak nama pengguna yang ada.
                st.error("Nama pengguna atau kata sandi salah.")
    return None


def bilah_sesi(sesi: dict):
    """Tampilkan identitas dan lingkup akses di sidebar, plus tombol keluar."""
    with st.sidebar:
        st.markdown("---")
        st.markdown(f"**{sesi['nama_tampil']}**")
        lingkup = sesi.get("kabkota") or sesi.get("provinsi") or "Seluruh Indonesia"
        st.caption(f"{PERAN.get(sesi['peran'], sesi['peran'])} · {lingkup}")
        sisa = datetime.fromisoformat(sesi["kedaluwarsa"]) - datetime.now()
        st.caption(f"Sesi berakhir dalam {int(sisa.total_seconds() // 60)} menit")
        if st.button("Keluar", use_container_width=True):
            keluar()
            st.rerun()


# ------------------------------------------------------------------ lingkup
def batasi(df, sesi: dict, kolom_provinsi="provinsi", kolom_kabkota="kabkota"):
    """
    Saring data sesuai peran. Dipakai di setiap tempat data ditampilkan.

    Peran pusat mengembalikan data apa adanya. Peran provinsi dan kabupaten
    memerlukan kolom penanda wilayah; kalau kolomnya tidak ada, fungsi ini
    mengembalikan data kosong, bukan data penuh. Gagal ke arah tertutup, bukan
    terbuka.
    """
    if sesi["peran"] == "pusat":
        return df
    if sesi["peran"] == "provinsi":
        if kolom_provinsi not in df.columns:
            return df.iloc[0:0]
        return df[df[kolom_provinsi] == sesi["provinsi"]]
    if sesi["peran"] == "kabupaten":
        if kolom_kabkota not in df.columns:
            return df.iloc[0:0]
        return df[df[kolom_kabkota] == sesi["kabkota"]]
    return df.iloc[0:0]
