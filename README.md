# 🏢 One Person Company

> AI-Native Solo Company — 一个人 + AI Agent = 一家公司

## 宣言

一个人不是限制，是优势。没有会议，没有协调，没有政治。
决策 0 秒到达，执行 1 秒启动，迭代按分钟计。

AI 不是工具，是员工。7×24 不休息，不要工资，越用越熟练。

## 架构

```
                    ┌─────────────────────────┐
                    │   🧠 HQ — Hermes 中枢    │
                    │   统一调度 · 记忆 · 技能   │
                    └───────────┬─────────────┘
                                │
           ┌────────────────────┼────────────────────┐
           ▼                    ▼                    ▼
  🎨 美术资产工厂         🛠️ SaaS 工具线         🤖 Agent 服务
  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
  │  IconForge   │      │  PasteHut    │      │  定制部署     │
  │  SpriteKit   │      │  PingBot     │      │  运维托管     │
  │  AssetPack   │      │  CronBoss    │      │  流程自动化   │
  └──────┬───────┘      └──────┬───────┘      └──────┬───────┘
         │                     │                     │
         └─────────────────────┼─────────────────────┘
                               ▼
                      📊 统一运营后台
                      ├─ 💰 财务（自动记账/发票）
                      ├─ 🎧 客服（AI 自动回复）
                      ├─ 📣 营销（SEO + 社媒）
                      └─ 📈 数据（用户行为分析）
```

## AI 员工编制

| 部门 | Agent | 职责 | 工作模式 |
|------|-------|------|---------|
| 🎨 美术部 | `art-factory` | 批量生成游戏美术资产 | 按需触发 + Cron 批量 |
| 🎧 客服部 | `customer-service` | 回复用户问题、处理退款 | 7×24 监听 |
| 📣 营销部 | `marketing` | SEO、社媒发帖、内容营销 | Cron 定时 |
| 🔧 运维部 | `devops` | 部署、监控、告警、故障自愈 | 持续运行 |
| 💰 财务部 | 自动化脚本 | 记账、发票、成本分析 | Cron 每日 |

## 产品线

### 🎨 美术资产工厂

| 产品 | 状态 | 描述 | 定价 |
|------|------|------|------|
| IconForge | 🚧 开发中 | 游戏 Icon 批量生成器 | $9.9/月 |
| SpriteKit | 📋 计划中 | 角色 Sprite Sheet 生成 | $19.9/月 |
| AssetPack | 📋 计划中 | 完整场景资产包 | $29.9/包 |

### 🛠️ SaaS 工具

| 产品 | 状态 | 描述 | 定价 |
|------|------|------|------|
| PasteHut | ✅ 原型完成 | 开发者 Pastebin | Free / $5/月 |
| PingBot | ✅ 原型完成 | 网站监控 + 告警 | Free / $9.9/月 |
| CronBoss | 📋 计划中 | 可视化 Cron 管理 | $7/月 |

## 技术栈

| 层 | 选型 | 理由 |
|----|------|------|
| AI Agent | Hermes Agent | 自改进、多平台、技能积累 |
| 文生图 | Pollinations / Flux / DALL-E | 免费→付费渐进 |
| 后端 | Python stdlib (零依赖) | 部署简单、不依赖 pip |
| 数据库 | SQLite | 零配置、够用 |
| 部署 | Linux VPS | 便宜、可控 |
| 前端 | 内联 HTML/CSS/JS | 无需构建工具 |
| 版本控制 | GitHub | 协作、CI/CD |
| 通信 | 飞书 | IM + 审批 + 告警 |

## 关键原则

1. **零依赖优先** — 不依赖 pip/npm，用标准库，减少故障面
2. **AI 先行** — 能让 AI 做的，不自己做
3. **自动化一切** — 重复 2 次以上的事，必须自动化
4. **先收钱再完美** — MVP 先上线，迭代优化
5. **记忆即资产** — 每次踩坑、每个客户需求，都记到记忆里

## 目录结构

```
one-person-company/
├── docs/                       # 📚 公司文档
│   ├── business-plan.md        # 商业计划书
│   ├── ai-ops-manual.md        # AI 运维手册
│   ├── revenue-model.md        # 收入模型
│   └── tech-stack.md           # 技术栈决策
├── agents/                     # 🤖 AI Agent 配置
│   ├── art-factory/            # 美术工厂
│   ├── customer-service/       # 客服
│   ├── marketing/              # 营销
│   └── devops/                 # 运维
├── products/                   # 📦 产品代码
│   ├── icon-forge/             # 图标生成器
│   ├── paste-hut/              # Pastebin
│   └── ping-bot/               # 监控服务
├── infrastructure/             # 🏗️ 基础设施
│   ├── deploy/                 # 部署脚本
│   ├── monitoring/             # 监控配置
│   └── cron/                   # 定时任务
└── finance/                    # 💰 财务自动化
```

---

*Built with [Hermes Agent](https://github.com/NousResearch/hermes-agent) — the self-improving AI agent*
