#!/usr/bin/env python3
"""
数据导出工具 — 将 PasteHut / PingBot 数据导出为 JSON

零依赖，纯 Python 标准库

用法:
  python export_data.py                          # 导出所有数据到 ./exports/
  python export_data.py --output-dir /tmp/backup  # 指定输出目录
  python export_data.py --product pastehut        # 只导出 PasteHut
  python export_data.py --compress                # gzip 压缩
  python export_data.py --pretty                  # 格式化 JSON
"""

import argparse
import gzip
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# 引入集中配置
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config import PasteHutConfig, PingBotConfig


def export_pastehut(output_dir: Path, pretty: bool = False) -> dict:
    """导出 PasteHut 数据为 JSON

    Args:
        output_dir: 输出目录
        pretty: 是否格式化 JSON

    Returns:
        包含文件路径和记录数的摘要字典
    """
    data_dir = Path(PasteHutConfig.DATA_DIR)
    meta_file = data_dir / "meta.json"

    if not meta_file.exists():
        return {"product": "pastehut", "status": "no_data", "file": None, "records": 0}

    # 读取元数据
    with open(meta_file, "r", encoding="utf-8") as f:
        meta = json.load(f)

    # 构建导出数据（含内容）
    export = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "product": "pastehut",
        "total_pastes": len(meta),
        "pastes": [],
    }

    for paste_id, paste_meta in meta.items():
        item = dict(paste_meta)
        # 读取内容文件
        content_file = data_dir / f"{paste_id}.txt"
        if content_file.exists():
            item["content"] = content_file.read_text(encoding="utf-8")
        export["pastes"].append(item)

    # 写入 JSON
    indent = 2 if pretty else None
    out_file = output_dir / f"pastehut_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=indent)

    return {
        "product": "pastehut",
        "status": "ok",
        "file": str(out_file),
        "records": len(meta),
    }


def export_pingbot(output_dir: Path, pretty: bool = False) -> dict:
    """导出 PingBot 数据为 JSON

    Args:
        output_dir: 输出目录
        pretty: 是否格式化 JSON

    Returns:
        包含文件路径和记录数的摘要字典
    """
    import sqlite3

    db_path = PingBotConfig.DB_PATH
    if not os.path.exists(db_path):
        return {"product": "pingbot", "status": "no_data", "file": None, "records": 0}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # 导出 targets
    targets = [dict(r) for r in conn.execute("SELECT * FROM targets").fetchall()]

    # 导出 checks
    checks = [dict(r) for r in conn.execute(
        "SELECT * FROM checks ORDER BY checked_at DESC LIMIT 10000"
    ).fetchall()]

    conn.close()

    export = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "product": "pingbot",
        "total_targets": len(targets),
        "total_checks": len(checks),
        "targets": targets,
        "checks": checks,
    }

    indent = 2 if pretty else None
    out_file = output_dir / f"pingbot_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=indent)

    return {
        "product": "pingbot",
        "status": "ok",
        "file": str(out_file),
        "records": len(targets) + len(checks),
    }


def compress_file(file_path: str) -> str:
    """使用 gzip 压缩文件

    Args:
        file_path: 原始文件路径

    Returns:
        压缩后的文件路径
    """
    gz_path = file_path + ".gz"
    with open(file_path, "rb") as f_in:
        with gzip.open(gz_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    # 删除原始文件
    os.unlink(file_path)
    return gz_path


def main():
    """CLI 入口"""
    parser = argparse.ArgumentParser(description="导出 OnePersonCo 产品数据为 JSON")
    parser.add_argument("--output-dir", default="./exports",
                        help="输出目录（默认 ./exports/）")
    parser.add_argument("--product", choices=["pastehut", "pingbot", "all"], default="all",
                        help="导出哪个产品数据（默认 all）")
    parser.add_argument("--compress", action="store_true",
                        help="使用 gzip 压缩导出文件")
    parser.add_argument("--pretty", action="store_true",
                        help="格式化 JSON 输出（便于阅读）")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []

    if args.product in ("pastehut", "all"):
        print("📦 导出 PasteHut 数据...")
        result = export_pastehut(output_dir, pretty=args.pretty)
        if result["status"] == "ok" and args.compress:
            result["file"] = compress_file(result["file"])
            result["compressed"] = True
        results.append(result)
        if result["status"] == "ok":
            print(f"  ✅ {result['records']} 条记录 → {result['file']}")
        else:
            print("  ⚠️ 无数据可导出")

    if args.product in ("pingbot", "all"):
        print("📦 导出 PingBot 数据...")
        result = export_pingbot(output_dir, pretty=args.pretty)
        if result["status"] == "ok" and args.compress:
            result["file"] = compress_file(result["file"])
            result["compressed"] = True
        results.append(result)
        if result["status"] == "ok":
            print(f"  ✅ {result['records']} 条记录 → {result['file']}")
        else:
            print("  ⚠️ 无数据可导出")

    print(f"\n📊 导出完成，共 {sum(1 for r in results if r['status'] == 'ok')} 个产品")
    return results


if __name__ == "__main__":
    main()
