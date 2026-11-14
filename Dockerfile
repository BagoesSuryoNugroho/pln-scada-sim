FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# data sudah ikut di repo; kalau dihapus, generate ulang (deterministik, ~30 detik)
RUN test -f data/telemetry_tm.csv.gz || python -m simcore.generate --out data
ENV DATA_BACKEND=csv
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
