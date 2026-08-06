#!/usr/bin/env bash
# RSSHub dev server — 固定 PORT 1201，幂等启动
cd /home/yupeng/rsshub-src || exit 1
if curl -s -o /dev/null -w "%{http_code}" http://localhost:1201/healthz 2>/dev/null | grep -q 200; then
  echo "已在运行 (1201)"; exit 0
fi
pkill -f "tsx watch.*lib/index.ts" 2>/dev/null
sleep 2
export PORT=1201
setsid nohup pnpm dev > /tmp/rsshub-dev.log 2>&1 < /dev/null &
disown
# 等就绪（最多 60s）
for i in $(seq 1 20); do
  if curl -s -o /dev/null -w "%{http_code}" http://localhost:1201/healthz 2>/dev/null | grep -q 200; then
    echo "✅ dev server 就绪 (1201)"; exit 0
  fi
  sleep 3
done
echo "❌ 启动失败，看 /tmp/rsshub-dev.log"
exit 1
