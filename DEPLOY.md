# Lưu ý deploy — HIS Agent

Có, dự án chạy bằng **Docker Compose**.

| | |
|---|---|
| Server | `dev@103.253.20.203 -p 227` |
| Thư mục | `/data/ai/code/ai/his-agent` |
| Compose project | `his-agent` (chốt bằng `name:` trong `docker-compose.yml`) |
| Container | `his-agent` |
| URL | http://103.253.20.203:8102 |
| Dữ liệu bền | `./data/` và `./his_users.db` (bind mount) |

## Deploy

```bash
./scripts/deploy.sh
```

Chỉ một lệnh, cho mọi loại thay đổi. Script rsync working tree lên server → build image → restart → chờ `/health` trả `ok`.

Sửa `.py` hay sửa `.tsx` đều dùng lệnh này. Server không cài node — frontend được build trong Docker (stage `node:20-slim`), **không cần `npm run build` ở máy local**.

## 1. Không bao giờ rsync đè `data/` và `his_users.db`

Đó là dữ liệu chạy thật trên server: session hội thoại, cấu hình bác sĩ, nhắc uống thuốc, và 161 tài khoản đăng nhập. Script đã exclude sẵn — nếu chạy rsync tay thì phải tự thêm:

```
--exclude data/ --exclude his_users.db
```

## 2. Sửa `docker-compose.yml` (nhất là port) hoặc `.env` thì phải `down` hẳn

`docker compose up -d` không phải lúc nào cũng áp dụng được thay đổi port và biến môi trường — container cũ vẫn giữ cấu hình cũ.

Script tự phát hiện (hash 2 file này, so với lần deploy trước) và tự `down` rồi `up`. Nếu làm tay:

```bash
docker compose -p his-agent build          # build trước, tránh chết site trong lúc build
docker compose -p his-agent down
docker compose -p his-agent up -d
```

## 3. Luôn dùng `-p his-agent` khi gõ lệnh compose tay

Compose mặc định lấy tên project theo tên thư mục. Nếu có bản clone thứ hai cùng tên folder, hai bản sẽ dùng chung project name và **xoá container của nhau** — đúng lỗi mà `allard-prod` / `allard-console` gặp trên server này.

`docker-compose.yml` đã có `name: his-agent` nên `docker compose up -d` chạy trong đúng thư mục là an toàn. Cờ `-p` là lớp bảo vệ thứ hai.

## 4. Container chạy bằng uid 1001 (user `dev`), không phải root

Để file ghi ra bind mount không bị root chiếm. Kéo theo hai ràng buộc trong `Dockerfile`:

- `chmod a+rwx /app` — SQLite cần tạo file journal cạnh `his_users.db`
- `chmod -R a+rwX /app/.hf_cache` — thư viện HF ghi lock file

Bỏ hai dòng này thì login sẽ lỗi 500 `attempt to write a readonly database`.

## 5. Biết prod đang chạy code nào

Script ghi lại mỗi lần deploy:

```bash
ssh -p 227 dev@103.253.20.203 'cat /data/ai/code/ai/his-agent/.deployed'
# main @ 34545be1 (kèm thay đổi chưa commit) — 2026-08-09 09:21:11
```

Script deploy **working tree**, không phải commit — code chưa commit vẫn lên được. Tiện lúc sửa gấp, nhưng nếu sau này có người thứ hai cùng deploy thì phải chuyển sang deploy từ git, vì hai máy sẽ đè lên nhau mà không ai biết.

## Vận hành

```bash
ssh -p 227 dev@103.253.20.203
cd /data/ai/code/ai/his-agent

docker compose -p his-agent logs -f      # xem log
docker compose -p his-agent restart      # restart nhanh
docker compose -p his-agent ps           # trạng thái + healthcheck
```

## Thời gian rebuild

| Thay đổi | Thời gian |
|---|---|
| `.py` | ~20s |
| `.tsx` | ~40s (Docker chạy `npm run build`) |
| `package.json` | ~1 phút (`npm ci`) |
| `requirements.txt` | ~5 phút (pip cài lại) |

Tầng `torch` CPU-only và model embedding `paraphrase-multilingual-MiniLM-L12-v2` chỉ tải lần đầu, sau đó luôn dùng layer cache. Image ~3.9GB.

## Cảnh báo bảo mật

Port 8102 mở public, **không HTTPS, không xác thực ở tầng mạng**, và `.env` chứa key thật (Alibaba, OpenRouter, Aidbox, Gmail app password). CORS đang để `allow_origins=["*"]`. Đủ dùng để demo bảo vệ đồ án; nếu chạy lâu dài phải đưa sau nginx + domain + TLS.
