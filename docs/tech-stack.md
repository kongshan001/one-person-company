# 🔧 技术栈决策

## 决策原则

| 原则 | 说明 | 优先级 |
|------|------|--------|
| 零依赖 | 不依赖 pip/npm/外部包 | P0 |
| AI 原生 | 从架构层面为 AI Agent 优化 | P0 |
| 极简部署 | 一条命令启动，零配置 | P1 |
| 成本最低 | 免费优先，按需升级 | P1 |
| 渐进增强 | 先跑起来，再优化 | P2 |

## 技术选型

### 后端

| 决策 | 选型 | 理由 | 备选 |
|------|------|------|------|
| 语言 | Python 3 | 标准库够用，AI 生态最好 | Go (更高性能) |
| HTTP | `http.server` (stdlib) | 零依赖，够用 | FastAPI (需要 pip) |
| 数据库 | SQLite | 零配置，单文件，线程安全 | PostgreSQL (规模化后) |
| 并发 | `threading` | stdlib，简单够用 | asyncio (更高效) |
| 缓存 | `dict` + TTL | 最简单的内存缓存 | Redis (分布式后) |

### 前端

| 决策 | 选型 | 理由 |
|------|------|------|
| 框架 | 无 | 内联 HTML/CSS/JS |
| 样式 | 内联 CSS | 暗黑主题，无需构建 |
| 交互 | 原生 JS | fetch API + DOM 操作 |
| 图标 | Emoji + SVG | 零依赖 |

### AI / 文生图

| 决策 | 选型 | 理由 |
|------|------|------|
| Agent 框架 | Hermes Agent | 自改进、多平台、技能积累 |
| 免费文生图 | Pollinations.ai | 无需 API Key，质量尚可 |
| 付费文生图 | Flux (via Replicate) | 质量最佳 |
| Prompt 生成 | LLM (当前模型) | 动态优化 prompt |
| 质检 | LLM + 感知哈希 | 自动筛选 + 去重 |

### 基础设施

| 决策 | 选型 | 理由 |
|------|------|------|
| 服务器 | Linux VPS | $5/月，够用 |
| 反向代理 | Nginx (后期) | SSL + 负载均衡 |
| 进程管理 | nohup / systemd | 简单可靠 |
| 监控 | 自建 PingBot | 自己的产品自己用 |
| 告警 | 飞书 Webhook | 即时通知 |
| CI/CD | GitHub Actions (后期) | 自动化部署 |
| 域名 | Cloudflare | 免费DNS + CDN |

### 支付

| 决策 | 选型 | 理由 |
|------|------|------|
| 国际 | LemonSqueezy | 不需要公司实体，低手续费 |
| 国内 | 微信/支付宝 (后期) | 需要企业资质 |

## 不选什么（及原因）

| 不选 | 原因 |
|------|------|
| Docker | 增加复杂度，VPS 直接跑更简单 |
| Node.js | 前后端都用 Python，减少上下文切换 |
| PostgreSQL | SQLite 够用到 $5000 MRR |
| Redis | 内存缓存够用 |
| Kubernetes | 杀鸡用牛刀 |
| React/Vue | 内联 HTML 更快，无需构建 |
