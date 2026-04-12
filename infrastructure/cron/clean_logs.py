#!/usr/bin/env python3
"""
日志清理脚本

用法:
  python clean_logs.py [--dir DIR] [--days 7]
"""

import argparse
import os
from datetime import datetime
from pathlib import Path


def clean_logs(log_dir: str, days: int = 7):
    """清理旧日志"""
    if not os.path.exists(log_dir):
        print(f"  ⚠️ Log directory not found: {log_dir}")
        return
    
    now = datetime.now().timestamp()
    cutoff = now - (days * 86400)
    
    removed = 0
    freed_bytes = 0
    
    for f in Path(log_dir).rglob("*.log*"):
        if f.is_file() and f.stat().st_mtime < cutoff:
            size = f.stat().st_size
            f.unlink()
            removed += 1
            freed_bytes += size
    
    freed_mb = freed_bytes / (1024 * 1024)
    print(f"  🧹 Removed {removed} log file(s), freed {freed_mb:.1f}MB")


def main():
    parser = argparse.ArgumentParser(description="Log Cleanup")
    parser.add_argument("--dir", default="/tmp", help="Log directory")
    parser.add_argument("--days", type=int, default=7, help="Retain days")
    args = parser.parse_args()
    
    print(f"🧹 Cleaning logs older than {args.days} days in {args.dir}...")
    clean_logs(args.dir, args.days)
    print("✅ Done!")


if __name__ == "__main__":
    main()
