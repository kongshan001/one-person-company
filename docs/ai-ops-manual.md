# 🤖 AI 运维手册

> 这不是一本给人看的运维手册，这是给 AI Agent 的工作指南。

## 原则

1. **AI 先动手** — 所有操作 AI 先尝试，失败再升级给人
2. **操作留痕** — 每个操作记录到 memory，下次更快
3. **自动恢复** — 故障先自愈，5 分钟没恢复再告警
4. **渐进升级** — AI → 人 → 外部支持

## 各部门 SOP

### 🎨 美术部 (art-factory)

#### 接单流程
```
客户下单 → 解析需求 → 生成 prompt → 批量生图 → AI 质检 → 人工抽检 → 交付
   │            │           │           │           │           │
   ▼            ▼           ▼           ▼           ▼           ▼
 飞书通知    模板匹配    风格+主题    文生图API   去模糊/去重   审3-5张
```

#### Prompt 工程

**游戏 Icon 模板**：
```
[style] game item icon, [subject], [detail], [background], [size_hint]
```

| 风格 | Prompt 关键词 |
|------|-------------|
| 像素 | `pixel art, retro, 32x32 sprite, clean edges` |
| 卡通 | `cartoon, cute, bold outlines, flat shading, bright colors` |
| 写实 | `3D rendered, realistic, detailed texture, dramatic lighting` |
| 暗黑 | `dark fantasy, gothic, weathered, ominous glow, desaturated` |
| 日系 | `anime RPG, cel shading, pastel, kawaii, clean vector` |
| 国风 | `Chinese ink painting, watercolor, traditional, elegant` |

#### 质检规则
- 文件大小 > 5KB（排除空白/损坏）
- 分辨率正确（512×512）
- 不含 NSFW 内容（API 侧已过滤，二次确认）
- 批量生成去重（感知哈希相似度 < 90%）
- 每批抽检 10%，不合格率 > 30% → 整批重生成

### 🎧 客服部 (customer-service)

#### 响应策略
```
用户消息 → 意图分类 → 自动回复 / 转人工
   │
   ├─ 常见问题 → 模板回复（秒级）
   ├─ 技术问题 → AI 诊断 + 解决方案（分钟级）
   ├─ 投诉/退款 → 转人工（立即）
   └─ 合作咨询 → 转人工 + AI 准备方案（分钟级）
```

#### 常见问题回复模板
- 见 `agents/customer-service/responses/` 目录

### 📣 营销部 (marketing)

#### 内容日历
| 时间 | 平台 | 内容 |
|------|------|------|
| 周一 | Twitter/X | 产品更新 / 功能展示 |
| 周三 | Reddit | 技术分享 / 教程 |
| 周五 | 独立游戏社区 | 免费资产包 / 折扣 |
| 每日 | Product Hunt | 关注竞品动态 |

#### SEO 策略
- 关键词：`game icon generator`, `RPG assets`, `pixel art generator`
- 每周发 1 篇技术博客
- GitHub 开源引流

### 🔧 运维部 (devops)

#### 监控清单
| 指标 | 阈值 | 动作 |
|------|------|------|
| 服务存活 | 端口无响应 | 自动重启 + 告警 |
| CPU | > 80% 持续 5min | 告警 |
| 内存 | > 90% | 告警 + 清理缓存 |
| 磁盘 | > 85% | 清理日志 + 告警 |
| API 错误率 | > 5% | 切换供应商 + 告警 |

#### 故障处理 Playbook
- 见 `agents/devops/playbooks/` 目录

## 日常 Cron 任务

| 任务 | 频率 | Agent |
|------|------|-------|
| 系统健康检查 | 每 30 分钟 | devops |
| 过期数据清理 | 每 1 小时 | devops |
| 财务日报 | 每天 9:00 | finance |
| 社媒发帖 | 每周一/三/五 | marketing |
| 用户反馈汇总 | 每天 18:00 | customer-service |
| 竞品动态扫描 | 每周一 10:00 | marketing |
