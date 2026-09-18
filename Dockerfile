# PradanaLog — citra produksi untuk server kampus
# =================================================================
# Python 3.12, bukan 3.11: numpy==2.5.0 di requirements.txt hanya
# tersedia untuk Python >= 3.12.
#
# Bangun:  docker build -t pradanalog:latest .
# Jalan :  docker compose up -d
#
# kredensial.json TIDAK ikut ke dalam citra (lihat .dockerignore).
# Berkas itu dipasang sebagai volume saat container dijalankan, supaya
# hash kata sandi tidak ikut tersebar bersama citra.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# curl dipakai HEALTHCHECK di bawah.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependensi disalin lebih dulu agar lapisan ini tidak dibangun ulang
# setiap kali kode berubah.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Berjalan sebagai pengguna biasa, bukan root.
RUN useradd --create-home --uid 10001 pradana \
 && chown -R pradana:pradana /app
USER pradana

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "pradanalog_map.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.fileWatcherType=none", \
     "--browser.gatherUsageStats=false"]
