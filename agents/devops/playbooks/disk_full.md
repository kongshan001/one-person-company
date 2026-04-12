# Playbook: 磁盘空间不足

**级别**: 🔴 Emergency  
**触发条件**: 磁盘使用 > 85%

## 自动处理

1. 检查磁盘使用：`df -h`
2. 清理临时文件：`find /tmp -type f -mtime +7 -delete`
3. 清理旧日志：`python clean_logs.py --days 3`
4. 清理旧备份：`python backup_db.py`（自动清理 > 30 天的备份）
5. 清理 Docker（如使用）：`docker system prune -f`

## 人工介入

1. 分析磁盘占用大户：`du -sh /* | sort -rh | head -10`
2. 决定是否需要扩容磁盘
3. 检查是否有异常的大文件

## 通知

- 清理后通知释放的空间
- 磁盘 > 95% → 紧急告警 + 自动清理
