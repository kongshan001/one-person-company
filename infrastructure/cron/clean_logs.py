#!/usr/bin/env python3
"""
日志清理脚本

用法:
  python clean_logs.py [--dir DIR] [--days 7] [--dry-run]
"""

import argparse
import os
from datetime import datetime
from pathlib import Path


def clean_logs(log_dir: str, days: int = 7, dry_run: bool = False):
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
            if dry_run:
                print(f"  [DRY RUN] Would remove: {f} ({size} bytes)")
            else:
                f.unlink()
            removed += 1
            freed_bytes += size
    
    freed_mb = freed_bytes / (1024 * 1024)
    if dry_run:
        print(f"  🧹 [DRY RUN] Would remove {removed} log file(s), would free {freed_mb:.1f}MB")
    else:
        print(f"  🧹 Removed {removed} log file(s), freed {freed_mb:.1f}MB")


def main():
    parser = argparse.ArgumentParser(description="Log Cleanup")
    parser.add_argument("--dir", default=os.path.expanduser("~/.onepersonco/logs/"), help="Log directory")
    parser.add_argument("--days", type=int, default=7, help="Retain days")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without actually deleting")
    args = parser.parse_args()
    
    mode = " (dry run)" if args.dry_run else ""
    print(f"🧹 Cleaning logs older than {args.days} days in {args.dir}{mode}...")
    clean_logs(args.dir, args.days, dry_run=args.dry_run)
    print("✅ Done!")


if __name__ == "__main__":
    main()
