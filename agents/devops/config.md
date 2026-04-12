# 🔧 DevOps Agent 配置

name: devops
version: 1.0.0
description: 自动部署、监控告警、故障自愈

## 监控面板

### 服务列表
| 服务 | 端口 | 健康检查 | 告警阈值 |
|------|------|----------|----------|
| IconForge | CLI tool, no HTTP service | N/A | N/A |
| PasteHut | 9292 | /health | 5xx > 3/min |
| PingBot | 8081 | /health | 5xx > 3/min |
| 主站 | 80 | / | 响应 > 3s |

### 健康检查规则
```python
# 每 5 分钟执行
checks = {
    "http": lambda url: requests.get(url + "/health").status_code == 200,
    "disk": lambda: shutil.disk_usage("/").free > 1_000_000_000,  # > 1GB
    "memory": lambda: psutil.virtual_memory().percent < 90,
    "cpu": lambda: psutil.cpu_percent(interval=5) < 95,
}
```

## 部署流水线

### Git Push → 自动部署
```
1. GitHub Webhook → 接收 push event
2. git pull origin main
3. 运行测试 (pytest)
4. 构建 Docker image (可选)
5. 滚动更新服务
6. 健康检查确认
7. 失败 → 自动回滚
```

### 回滚策略
```
- 保留最近 3 个版本的 artifact
- 失败检测: 健康检查连续 3 次失败
- 回滚: 切换到上一个版本的 symlink
- 通知: 发送告警到飞书/Telegram
```

## 告警规则

| 级别 | 条件 | 动作 |
|------|------|------|
| 🟡 Warning | CPU > 80% 持续 5min | 日志记录 |
| 🟠 Critical | 服务 down > 2min | 自动重启 + 通知 |
| 🔴 Emergency | 磁盘 > 95% | 清理临时文件 + 通知 |
| ⚫ Fatal | 数据损坏 | 停止服务 + 通知 + 等待人工 |

## 备份策略

```yaml
database:
  frequency: daily
  retention: 30 days
  location: ~/backups/db/
  
uploads:
  frequency: daily
  retention: 90 days
  location: ~/backups/uploads/
  remote: s3://onepersonco-backups/  # 可选

config:
  frequency: on_change
  retention: forever (git)
  location: git@github.com:kongshan001/one-person-company.git
```

## Cron 任务

| 频率 | 任务 | 脚本 |
|------|------|------|
| */5 * * * * | 健康检查 | infrastructure/monitoring/health_check.py |
| 0 2 * * * | 数据库备份 | infrastructure/cron/backup_db.py |
| 0 3 * * 0 | 日志清理 | infrastructure/cron/clean_logs.py |
| 0 0 1 * * | 月度报告 | infrastructure/cron/monthly_report.py |
