#!/usr/bin/env python3
"""
数据库备份脚本

用法:
  python backup_db.py [--db PATH] [--backup-dir DIR]
"""

import argparse
import hashlib
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# 引入集中配置
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config import InfraConfig, PingBotConfig, PasteHutConfig

DEFAULT_BACKUP_DIR = InfraConfig.BACKUP_DIR
RETENTION_DAYS = InfraConfig.RETENTION_DAYS


def _sha256_file(filepath: str) -> str:
    """计算文件的 SHA256 哈希"""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def backup_file(src: str, backup_dir: str, prefix: str = "") -> str:
    """备份单个文件，并生成 SHA256 校验文件"""
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    basename = os.path.basename(src)
    name, ext = os.path.splitext(basename)
    dest = os.path.join(backup_dir, f"{prefix}{name}_{timestamp}{ext}")
    
    if ext.lower() in (".db", ".sqlite", ".sqlite3"):
        # SQLite hot-backup using backup API
        src_conn = sqlite3.connect(src)
        dst_conn = sqlite3.connect(dest)
        src_conn.backup(dst_conn)
        dst_conn.close()
        src_conn.close()
    else:
        shutil.copy2(src, dest)
    
    # SHA256 完整性校验
    sha256 = _sha256_file(dest)
    checksum_file = dest + ".sha256"
    with open(checksum_file, "w") as f:
        f.write(f"{sha256}  {os.path.basename(dest)}\n")
    
    print(f"  ✅ Backed up: {src} → {dest}")
    print(f"  🔒 SHA256: {sha256}")
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
        # 自动发现（从集中配置读取路径）
        candidates = [
            PingBotConfig.DB_PATH,
            str(Path(PasteHutConfig.DATA_DIR) / "meta.json"),
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
