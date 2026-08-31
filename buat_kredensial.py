"""
buat_kredensial.py — kelola akun PradanaLog
============================================
Kata sandi tidak pernah ditulis ke berkas; yang disimpan hanya hash PBKDF2
beserta garamnya.

    python buat_kredensial.py tambah                 # interaktif
    python buat_kredensial.py daftar                 # lihat akun yang ada
    python buat_kredensial.py hapus <nama_pengguna>
    python buat_kredensial.py contoh                 # 3 akun demo untuk presentasi

JANGAN commit kredensial.json ke repositori publik. Tambahkan ke .gitignore.
Untuk Streamlit Community Cloud, salin isinya ke Settings > Secrets dengan
kunci `pradanalog_pengguna`.
"""

import getpass
import json
import sys
from pathlib import Path

from auth import KREDENSIAL, PERAN, buat_hash, muat_pengguna, simpan_pengguna


def tambah(nama=None, sandi=None, peran=None, provinsi=None, kabkota=None,
           nama_tampil=None, diam=False):
    pengguna = muat_pengguna()
    if nama is None:
        nama = input("Nama pengguna: ").strip()
    if nama in pengguna and not diam:
        if input(f"'{nama}' sudah ada. Timpa? (y/t) ").lower() != "y":
            return pengguna
    if peran is None:
        print("Peran: " + " · ".join(f"{k} = {v}" for k, v in PERAN.items()))
        peran = input("Peran: ").strip()
    if peran not in PERAN:
        raise SystemExit(f"Peran '{peran}' tidak dikenal. Pilihan: {list(PERAN)}")

    if peran in ("provinsi", "kabupaten") and provinsi is None:
        provinsi = input("Provinsi: ").strip()
    if peran == "kabupaten" and kabkota is None:
        kabkota = input("Kabupaten/Kota: ").strip()
    if nama_tampil is None:
        nama_tampil = input("Nama tampil (boleh dikosongkan): ").strip() or nama

    if sandi is None:
        sandi = getpass.getpass("Kata sandi: ")
        if sandi != getpass.getpass("Ulangi kata sandi: "):
            raise SystemExit("Kata sandi tidak cocok.")
    if len(sandi) < 8:
        raise SystemExit("Kata sandi minimal 8 karakter.")

    pengguna[nama] = {**buat_hash(sandi), "peran": peran, "nama_tampil": nama_tampil}
    if provinsi:
        pengguna[nama]["provinsi"] = provinsi
    if kabkota:
        pengguna[nama]["kabkota"] = kabkota
    simpan_pengguna(pengguna)
    if not diam:
        print(f"Akun '{nama}' disimpan sebagai {PERAN[peran]}.")
    return pengguna


def daftar():
    pengguna = muat_pengguna()
    if not pengguna:
        print("Belum ada akun.")
        return
    print(f"{'PENGGUNA':<18}{'PERAN':<12}{'LINGKUP':<28}NAMA TAMPIL")
    for n, r in sorted(pengguna.items()):
        lingkup = r.get("kabkota") or r.get("provinsi") or "seluruh Indonesia"
        print(f"{n:<18}{r['peran']:<12}{lingkup:<28}{r.get('nama_tampil', '')}")


def hapus(nama):
    pengguna = muat_pengguna()
    if nama not in pengguna:
        raise SystemExit(f"Akun '{nama}' tidak ada.")
    pengguna.pop(nama)
    simpan_pengguna(pengguna)
    print(f"Akun '{nama}' dihapus.")


def contoh():
    """
    Tiga akun untuk demonstrasi lomba. Kata sandinya sengaja dicetak ke layar
    karena memang untuk dipamerkan di panggung — jangan pernah dipakai di
    lingkungan yang memuat data sungguhan.
    """
    akun = [
        ("pusat", "Demo#Pusat2026", "pusat", None, None, "Bapanas — Pusat"),
        ("jatim", "Demo#Jatim2026", "provinsi", "Jawa Timur", None,
         "TPID Provinsi Jawa Timur"),
        ("malang", "Demo#Malang2026", "kabupaten", "Jawa Timur", "Kabupaten Malang",
         "TPID Kabupaten Malang"),
    ]
    for nama, sandi, peran, prov, kab, tampil in akun:
        tambah(nama, sandi, peran, prov, kab, tampil, diam=True)
    print("Tiga akun demo dibuat:\n")
    for nama, sandi, peran, prov, kab, tampil in akun:
        print(f"  {nama:<10} {sandi:<18} {PERAN[peran]}")
    print(f"\nDisimpan di {KREDENSIAL}. Jangan dipakai untuk data sungguhan.")


if __name__ == "__main__":
    perintah = sys.argv[1] if len(sys.argv) > 1 else "tambah"
    if perintah == "tambah":
        tambah()
    elif perintah == "daftar":
        daftar()
    elif perintah == "hapus":
        hapus(sys.argv[2])
    elif perintah == "contoh":
        contoh()
    else:
        print(__doc__)
