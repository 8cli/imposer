# 本机 RSSHub dev 模式（端口 1201）

RSSHub 以源码 dev 模式运行（`NODE_ENV=dev`），动态加载 `lib/routes/` 路由——加路由文件即生效（tsx watch 自动重启），无需重建镜像。

## 启动

```bash
bash docs/rsshub-dev/start.sh   # 幂等：已在运行则退出，否则 pnpm dev 启动
```

- 源码目录: `~/news/rsshub-src`（dev 模式）
- 端口: 1201（局域网监听 `*:1201`）
- 日志: `/tmp/rsshub-dev.log`
- 开机自启: crontab `@reboot`（用户级，非仓库内容）

## 依赖

- `~/news/rsshub-src` 已 `pnpm install`（仓库不含 node_modules）
- 自定义路由在 `docs/rsshub-routes/`（87 个 .ts 备份）——恢复时复制到 `~/news/rsshub-src/lib/routes/`

## 恢复流程（换机器/重装）

1. 克隆 imposer 仓库 → `docs/rsshub-routes/` 是路由备份
2. 复制路由到 rsshub-src: `cp docs/rsshub-routes/*/namespace.ts docs/rsshub-routes/*/*.ts ~/news/rsshub-src/lib/routes/<name>/`
3. `pnpm install` + `bash docs/rsshub-dev/start.sh`
4. 验证: `curl localhost:1201/xinhuaenglish/news`
