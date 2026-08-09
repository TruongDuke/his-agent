#!/usr/bin/env bash
#
# Deploy HIS Agent lên server production.
#
#   ./scripts/deploy.sh
#
# Script đẩy toàn bộ working tree hiện tại lên server rồi rebuild container.
# KHÔNG đụng vào data/ và his_users.db trên server — đó là dữ liệu chạy thật.
#
set -euo pipefail

SERVER="dev@103.253.20.203"
PORT=227
REMOTE="/data/ai/code/ai/his-agent"
PROJECT="his-agent"          # phải khớp `name:` trong docker-compose.yml
URL="http://103.253.20.203:8102"
LOCAL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Cho phép thay cách gọi ssh (vd: SSH_CMD="sshpass -p '...' ssh -p 227")
SSH_CMD="${SSH_CMD:-ssh -p $PORT}"

# Ghi lại commit nào đang chạy trên server — để sau này biết prod đang ở đâu
COMMIT="$(git -C "$LOCAL" rev-parse --short HEAD 2>/dev/null || echo unknown)"
BRANCH="$(git -C "$LOCAL" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
if [ -n "$(git -C "$LOCAL" status --porcelain 2>/dev/null)" ]; then
  DIRTY=" (kèm thay đổi chưa commit)"
else
  DIRTY=""
fi

echo "==> [1/2] Đẩy code lên $SERVER:$REMOTE"
echo "    $BRANCH @ $COMMIT$DIRTY"
rsync -az -e "$SSH_CMD" \
  --exclude 'venv/' \
  --exclude 'node_modules/' \
  --exclude 'frontend/dist/' \
  --exclude '.git/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude 'thesis/' \
  --exclude 'slides/' \
  --exclude '.DS_Store' \
  --exclude '*.log' \
  --exclude 'data/' \
  --exclude 'his_users.db' \
  "$LOCAL/" "$SERVER:$REMOTE/"

echo "==> [2/2] Build image, restart container, chờ app sẵn sàng"
# -p "$PROJECT" là bắt buộc: khoá container/network vào đúng project, không phụ thuộc thư mục.
# Frontend được build ngay trong Docker (stage node), không cần npm ở máy local.
$SSH_CMD "$SERVER" "
  set -e
  cd $REMOTE

  # Build trước để không phải tắt service trong lúc build
  docker compose -p $PROJECT build

  # Đổi docker-compose.yml (nhất là port) hoặc .env thì phải down hẳn rồi up,
  # vì 'up -d' không phải lúc nào cũng áp dụng được thay đổi port / biến môi trường.
  new=\$(cat docker-compose.yml .env 2>/dev/null | md5sum | cut -d' ' -f1)
  old=\$(cat .deploy-config-hash 2>/dev/null || echo none)
  if [ \"\$new\" != \"\$old\" ]; then
    echo '    docker-compose.yml/.env có thay đổi → down rồi up lại'
    docker compose -p $PROJECT down
  fi

  docker compose -p $PROJECT up -d
  echo \"\$new\" > .deploy-config-hash
  echo \"$BRANCH @ $COMMIT$DIRTY — \$(date '+%Y-%m-%d %H:%M:%S')\" > .deployed

  for i in \$(seq 1 60); do
    curl -s -m 3 http://127.0.0.1:8102/health | grep -q ok && exit 0
    sleep 3
  done
  echo 'App không lên sau 3 phút — log gần nhất:'
  docker compose -p $PROJECT logs --tail 40
  exit 1
"

echo
echo "Deploy xong: $URL"
