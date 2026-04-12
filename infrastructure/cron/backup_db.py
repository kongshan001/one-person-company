#!/usr/bin/env python3
"""
数据库备份脚本

用法:
  python backup_db.py [--db PATH] [--backup-dir DIR]
"""

import argparse
import os
import shutil
from datetime import datetime
from pathlib import Path

DEFAULT_BACKUP_DIR = os.path.expanduser("~/.onepersonco/backups")
RETENTION_DAYS = 30


def backup_file(src: str, backup_dir: str, prefix: str = "") -> str:
    """备份单个文件"""
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    basename = os.path.basename(src)
    name, ext = os.path.splitext(basename)
    dest = os.path.join(backup_dir, f"{prefix}{name}_{timestamp}{ext}")
    
    shutil.copy2(src, dest)
    print(f"  ✅ Backed up: {src} → {dest}")
    return dest


def cleanup_old(backup_dir: str, retention_days: int = RETENTION_DAYS):
    """清理过期备份"""
    now = datetime.now().timestamp()
    cutoff = now - (retention_days * 86400)
    
    removed = 0
    for f in Path(backup_dir).iterdir():
        if f.is_file() and f.stat().st_mtime < cutoff:
            f.unlink()
            removed += 1
    
    if removed:
        print(f"  🧹 Cleaned up {removed} old backup(s)")


def main():
    parser = argparse.ArgumentParser(description="Database Backup")
    parser.add_argument("--db", help="Database file path")
    parser.add_argument("--backup-dir", default=DEFAULT_BACKUP_DIR)
    args = parser.parse_args()
    
    print("💾 Starting backup...")
    
    # 默认备份所有已知的数据库
    dbs = []
    if args.db:
        dbs = [args.db]
    else:
        # 自动发现
        candidates = [
            os.path.expanduser("~/.pingbot/pingbot.db"),
            os.path.expanduser("~/.pastehut/data/meta.json"),
        ]
        for db in candidates:
            if os.path.exists(db):
                dbs.append(db)
    
    if not dbs:
        print("  ⚠️ No databases found")
        return
    
    for db in dbs:
        if os.path.exists(db):
            backup_file(db, args.backup_dir)
        else:
            print(f"  ⚠️ Not found: {db}")
    
    cleanup_old(args.backup_dir)
    print("✅ Backup complete!")


if __name__ == "__main__":
    main()
