# ---------- Stage 1: build UI React (Vite) ----------
FROM node:20-slim AS frontend

WORKDIR /fe

# Cài deps trước, tách layer để chỉ chạy lại npm ci khi package.json/lock đổi
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# ---------- Stage 2: backend FastAPI ----------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.hf_cache \
    TZ=Asia/Ho_Chi_Minh

WORKDIR /app

# torch bản CPU-only (nhẹ hơn ~2GB so với bản CUDA mặc định trên PyPI)
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch

COPY requirements.txt .
RUN pip install -r requirements.txt

# Tải sẵn model embedding để lần chạy đầu không phải download
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"

# Container chạy bằng uid dev (1001) để file ghi ra volume không bị root chiếm
RUN chmod -R a+rwX /app/.hf_cache

COPY . .

# Bundle UI lấy từ stage 1 — không cần build sẵn ở máy local
COPY --from=frontend /fe/dist ./frontend/dist

# SQLite cần ghi file journal cạnh his_users.db → thư mục /app phải writable cho uid 1001
RUN chmod a+rwx /app

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
