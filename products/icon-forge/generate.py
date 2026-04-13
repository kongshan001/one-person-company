#!/usr/bin/env python3
"""
IconForge - AI 游戏图标生成器
核心生成脚本：批量文生图 + 质检 + 多尺寸 + 打包

用法:
  python generate.py --prompt "dark fantasy sword" --style dark --count 10
  python generate.py --batch prompts.txt --style pixel --output ./output
"""

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.parse
import zipfile
from datetime import datetime
from pathlib import Path

# 引入集中配置与 V2 引擎
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config import IconForgeConfig
from utils import read_png_dimensions

# V2 prompt 与质检引擎（同目录模块）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prompt_engine
import quality_engine
import cache as icon_cache_module


# ============ 配置（引用集中配置） ============

POLLINATIONS_URL = IconForgeConfig.POLLINATIONS_URL

STYLE_KEYWORDS = IconForgeConfig.STYLE_KEYWORDS  # V1 兼容

TYPE_KEYWORDS = IconForgeConfig.TYPE_KEYWORDS  # V1 兼容

SIZES = IconForgeConfig.SIZES
DEFAULT_SIZE = IconForgeConfig.DEFAULT_SIZE
MIN_FILE_SIZE = IconForgeConfig.MIN_FILE_SIZE
DELAY_BETWEEN_REQUESTS = IconForgeConfig.DELAY_BETWEEN_REQUESTS
MAX_RETRIES = IconForgeConfig.MAX_RETRIES

# 缓存实例（模块级单例）
_cache = icon_cache_module.IconCache()


# ============ 核心函数 ============

def build_prompt(user_prompt: str, style: str = None, asset_type: str = "icon",
                 use_v2: bool = True) -> dict:
    """构建文生图 prompt

    Args:
        user_prompt: 用户原始描述
        style: 风格名称
        asset_type: 资产类型
        use_v2: 是否使用 V2 prompt 引擎（默认 True）

    Returns:
        {"prompt": str, "negative": str} — V2 模式返回结构化 prompt；
        V1 模式 negative 为空字符串。
    """
    if use_v2:
        result = prompt_engine.build_pro_prompt(
            user_prompt, style=style, asset_type=asset_type,
            use_negative=True, use_anchor=True,
        )
        return {"prompt": result["prompt"], "negative": result["negative"]}

    # V1 回退：简单拼接
    parts = []
    if style and style in STYLE_KEYWORDS:
        parts.append(STYLE_KEYWORDS[style])
    parts.append(user_prompt)
    if asset_type in TYPE_KEYWORDS:
        parts.append(TYPE_KEYWORDS[asset_type])
    return {"prompt": ", ".join(parts), "negative": ""}


def generate_image(prompt: str, seed: int = None, size: int = DEFAULT_SIZE,
                   output_path: str = None, style: str = None) -> str:
    """调用 Pollinations.ai 生成单张图片
    
    优先查找缓存，命中则直接复用；未命中则调用 API 并写入缓存。
    
    Args:
        prompt: 完整的生成 prompt
        seed: 随机种子
        size: 图片尺寸
        output_path: 输出文件路径；None 时写入临时文件
        style: 风格名称（用于缓存 key）
    
    Returns:
        成功返回文件路径 str；失败返回 None。
    """
    import tempfile
    
    if seed is None:
        seed = int(time.time() * 1000) % 2**31
    
    # 缓存查找：命中则复制到目标路径
    cached_path = _cache.get(prompt, style=style, seed=seed, size=size)
    if cached_path is not None:
        import shutil
        save_path = output_path
        if save_path is None:
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            save_path = tmp.name
            tmp.close()
        shutil.copy2(cached_path, save_path)
        print(f"  💾 缓存命中 → {os.path.basename(save_path)}")
        return save_path
    
    encoded_prompt = urllib.parse.quote(prompt)
    url = POLLINATIONS_URL.format(prompt=encoded_prompt, w=size, h=size, seed=seed)
    
    for attempt in range(MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            
            if len(data) < MIN_FILE_SIZE:
                print(f"  ⚠️ 生成的图片太小 ({len(data)} bytes), 可能失败, 重试...")
                time.sleep(DELAY_BETWEEN_REQUESTS)
                continue
            
            # 如果未指定 output_path，创建临时文件
            save_path = output_path
            if save_path is None:
                tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                save_path = tmp.name
                tmp.close()
            
            # Pollinations 返回 JPEG, 先保存原始
            raw_path = save_path + ".raw"
            with open(raw_path, "wb") as f:
                f.write(data)
            
            # 转换为真正的 PNG
            try:
                subprocess.run(
                    ["convert", raw_path, save_path],
                    check=True, capture_output=True, timeout=30
                )
                os.remove(raw_path)
            except (subprocess.CalledProcessError, FileNotFoundError):
                # ImageMagick 不可用, 直接保存
                os.rename(raw_path, save_path)
            
            # 写入缓存（异步不影响主流程）
            try:
                _cache.put(prompt, style=style, seed=seed, size=size,
                           source_path=save_path)
            except Exception:
                pass  # 缓存写入失败不影响生成结果
            
            return save_path
            
        except Exception as e:
            print(f"  ⚠️ 生成失败 (尝试 {attempt+1}/{MAX_RETRIES+1}): {e}")
            if attempt < MAX_RETRIES:
                time.sleep(DELAY_BETWEEN_REQUESTS)
    
    return None


def resize_image(input_path: str, target_size: int, output_path: str) -> bool:
    """使用 ImageMagick 调整图片尺寸"""
    try:
        subprocess.run(
            ["convert", input_path, "-resize", f"{target_size}x{target_size}",
             "-quality", "95", output_path],
            check=True, capture_output=True, timeout=30
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        # 无 ImageMagick, 复制原文件
        shutil.copy2(input_path, output_path)
        return False


def _get_image_dimensions(file_path: str) -> tuple:
    """获取图片尺寸，优先用 identify，回退读 PNG header"""
    try:
        proc = subprocess.run(
            ["identify", "-format", "%w %h", file_path],
            capture_output=True, text=True, timeout=10
        )
        if proc.returncode == 0:
            parts = proc.stdout.strip().split()
            if len(parts) == 2:
                return (int(parts[0]), int(parts[1]))
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    # 回退：读 PNG header（使用 utils 中的统一实现）
    return read_png_dimensions(file_path)


def quality_check(file_path: str, expected_size: int = DEFAULT_SIZE,
                  existing_hashes: dict = None, use_v2: bool = True) -> dict:
    """质检单张图片

    Args:
        file_path: 图片文件路径
        expected_size: 期望尺寸 (px)
        existing_hashes: 已有图片的 pHash 字典 {path: hash}，用于去重
        use_v2: 是否使用 V2 多维度质检（默认 True）

    Returns:
        V2 模式返回 quality_engine.quality_check_v2 的完整结果；
        V1 模式返回简化的 {file, passed, issues} 字典。
    """
    if use_v2:
        return quality_engine.quality_check_v2(
            file_path, expected_size=expected_size,
            existing_hashes=existing_hashes,
        )

    # V1 回退：仅检查文件大小和分辨率
    result = {"file": file_path, "passed": True, "issues": []}
    size = os.path.getsize(file_path)
    if size < MIN_FILE_SIZE:
        result["passed"] = False
        result["issues"].append(f"文件太小: {size} bytes")
    dims = _get_image_dimensions(file_path)
    if dims is not None:
        w, h = dims
        if w != expected_size or h != expected_size:
            result["passed"] = False
            result["issues"].append(
                f"分辨率不匹配: 期望 {expected_size}x{expected_size}, 实际 {w}x{h}"
            )
    else:
        result["issues"].append("无法读取分辨率（非 PNG 或 identify 不可用）")
    return result


def create_preview(output_dir: str, manifest: list, project_name: str):
    """创建 HTML 预览页"""
    safe_name = html.escape(project_name)
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{safe_name} - Asset Preview</title>
<style>
  body {{ font-family: system-ui; background: #1a1a2e; color: #eee; padding: 20px; }}
  h1 {{ color: #e94560; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; }}
  .card {{ background: #16213e; border-radius: 8px; padding: 12px; text-align: center; }}
  .card img {{ max-width: 100%; border-radius: 4px; image-rendering: pixelated; }}
  .card .name {{ font-size: 12px; color: #aaa; margin-top: 8px; word-break: break-all; }}
</style>
</head>
<body>
<h1>🎨 {safe_name} - Generated Assets</h1>
<div class="grid">
"""
    for item in manifest:
        for size in SIZES:
            size_dir = f"size_{size}"
            rel_path = f"{size_dir}/{item['filename']}"
            safe_alt = html.escape(item.get('prompt', item['filename']))
            html_content += f"""<div class="card">
  <img src="{rel_path}" alt="{safe_alt}">
  <div class="name">{html.escape(item['filename'])} ({size}px)</div>
</div>\n"""

    html_content += """</div>
</body>
</html>"""
    
    preview_path = os.path.join(output_dir, "index.html")
    with open(preview_path, "w") as f:
        f.write(html_content)
    return preview_path


def create_zip(output_dir: str, project_name: str) -> str:
    """打包为 ZIP"""
    zip_path = os.path.join(output_dir, f"{project_name}_assets.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(output_dir):
            for file in files:
                if file.endswith(".zip"):
                    continue
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, output_dir)
                zf.write(file_path, arcname)
    return zip_path


# ============ 主流程 ============

def run_batch(prompts: list, style: str, asset_type: str, output_dir: str,
              project_name: str, count: int = 1, use_v2: bool = True) -> dict:
    """批量生成主流程"""
    os.makedirs(output_dir, exist_ok=True)
    
    manifest = []
    stats = {"total": 0, "success": 0, "failed": 0, "quality_issues": 0,
             "cache_hits": 0}
    existing_hashes = {}  # pHash 去重用
    
    for i, prompt_text in enumerate(prompts):
        prompt_result = build_prompt(prompt_text, style, asset_type, use_v2=use_v2)
        full_prompt = prompt_result["prompt"]
        negative = prompt_result.get("negative", "")
        print(f"\n🎨 [{i+1}/{len(prompts)}] 生成: {prompt_text}")
        print(f"   Prompt: {full_prompt}")
        if negative:
            print(f"   Negative: {negative[:80]}...")
        
        for j in range(count):
            stats["total"] += 1
            seed = int(time.time() * 1000 + i * 1000 + j) % 2**31
            safe_prompt = re.sub(r'[^a-zA-Z0-9_-]', '', prompt_text[:30])
            if not safe_prompt:
                safe_prompt = "icon"
            filename = f"{style or 'default'}_{safe_prompt}_{seed % 10000}.png"
            
            # 生成原始 512x512
            raw_dir = os.path.join(output_dir, f"size_{DEFAULT_SIZE}")
            os.makedirs(raw_dir, exist_ok=True)
            raw_path = os.path.join(raw_dir, filename)
            
            result = generate_image(full_prompt, seed=seed, output_path=raw_path,
                                    style=style)
            
            if result is None:
                print(f"  ❌ 生成失败")
                stats["failed"] += 1
                continue
            
            # 质检（V2 支持去重和多维度评分）
            qc = quality_check(raw_path, existing_hashes=existing_hashes, use_v2=use_v2)
            if not qc["passed"]:
                print(f"  ⚠️ 质检失败: {qc['issues']}")
                stats["quality_issues"] += 1
                # 不删除, 保留供人工审核
            
            # 记录 pHash 用于后续去重
            if use_v2 and qc.get("hash"):
                existing_hashes[raw_path] = qc["hash"]
            
            # 生成多尺寸
            for size in SIZES:
                if size == DEFAULT_SIZE:
                    continue
                size_dir = os.path.join(output_dir, f"size_{size}")
                os.makedirs(size_dir, exist_ok=True)
                size_path = os.path.join(size_dir, filename)
                resize_image(raw_path, size, size_path)
            
            # manifest 条目（V2 额外保存评分/去重信息）
            entry = {
                "filename": filename,
                "prompt": full_prompt,
                "negative": negative,
                "seed": seed,
                "style": style,
                "original_prompt": prompt_text,
                "quality_passed": qc["passed"],
            }
            if use_v2:
                entry["overall_score"] = qc.get("overall_score", 0)
                entry["is_duplicate"] = qc.get("is_duplicate", False)
            manifest.append(entry)
            
            stats["success"] += 1
            score_info = f" (score: {qc.get('overall_score', 'N/A')})" if use_v2 else ""
            print(f"  ✅ 成功 → {filename}{score_info}")
            
            # 限流延迟
            time.sleep(DELAY_BETWEEN_REQUESTS)
    
    # 保存 manifest
    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    
    # 创建预览页
    if manifest:
        create_preview(output_dir, manifest, project_name)
    
    # 打包
    zip_path = create_zip(output_dir, project_name)
    
    stats["manifest"] = manifest_path
    stats["zip"] = zip_path
    
    # 追加缓存统计
    cache_stats = _cache.stats()
    stats["cache_hits"] = cache_stats["hits"]
    stats["cache_hit_rate"] = cache_stats["hit_rate_pct"]
    
    return stats


# ============ CLI ============

def main():
    # 合并 V1/V2 的所有风格和资产类型
    v2_styles = list(prompt_engine.STYLE_KEYWORDS_V2.keys())
    v2_types = list(prompt_engine.TYPE_KEYWORDS_V2.keys())
    
    parser = argparse.ArgumentParser(description="IconForge - AI Game Icon Generator")
    parser.add_argument("--prompt", "-p", help="单个 prompt")
    parser.add_argument("--batch", "-b", help="批量 prompt 文件 (每行一个)")
    parser.add_argument("--style", "-s", choices=v2_styles, help="风格")
    parser.add_argument("--type", "-t", choices=v2_types, default="icon", help="资产类型")
    parser.add_argument("--count", "-n", type=int, default=1, help="每个 prompt 生成数量")
    parser.add_argument("--output", "-o", default="./output", help="输出目录")
    parser.add_argument("--name", help="项目名称 (用于ZIP和预览页)")
    parser.add_argument("--preset", help="使用预设方案 (如 rpg-weapons, pixel-items)")
    parser.add_argument("--list-presets", action="store_true", help="列出所有预设方案")
    parser.add_argument("--v1", action="store_true", help="使用 V1 简化模式 (回退)")
    
    args = parser.parse_args()
    
    if args.list_presets:
        presets = prompt_engine.list_presets()
        print("📦 可用预设方案:\n")
        for p in presets:
            print(f"  {p['id']:20} {p['name']} — {p['description']} ({p['item_count']} items, {p['style']} style)")
        return
    
    use_v2 = not args.v1
    
    # 预设模式
    if args.preset:
        try:
            preset = prompt_engine.get_preset(args.preset)
        except ValueError as e:
            print(f"❌ {e}")
            sys.exit(1)
        prompts = preset["prompts"]
        if not args.style:
            args.style = preset["style"]
        if args.type == "icon":
            args.type = preset["asset_type"]
        if not args.name:
            args.name = preset["name"]
        print(f"📦 使用预设: {preset['name']} ({len(prompts)} items)")
    
    if not args.prompt and not args.batch and not args.preset:
        parser.error("请提供 --prompt、--batch 或 --preset")
    
    # 收集 prompts
    prompts = []
    if args.prompt:
        prompts.append(args.prompt)
    if args.batch:
        with open(args.batch, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    prompts.append(line)
    
    project_name = args.name or f"iconforge_{datetime.now().strftime('%Y%m%d_%H%M')}"
    
    mode_label = "V2 Pro" if use_v2 else "V1 Basic"
    print(f"🚀 IconForge 启动 ({mode_label})")
    print(f"   Prompts: {len(prompts)}")
    print(f"   每个生成: {args.count} 张")
    print(f"   风格: {args.style or 'default'}")
    print(f"   类型: {args.type}")
    print(f"   输出: {args.output}")
    
    stats = run_batch(
        prompts=prompts,
        style=args.style,
        asset_type=args.type,
        output_dir=args.output,
        project_name=project_name,
        count=args.count,
        use_v2=use_v2,
    )
    
    print(f"\n{'='*50}")
    print(f"🎉 生成完成!")
    print(f"   总计: {stats['total']}")
    print(f"   成功: {stats['success']}")
    print(f"   失败: {stats['failed']}")
    print(f"   质检问题: {stats['quality_issues']}")
    print(f"   缓存命中: {stats.get('cache_hits', 0)} ({stats.get('cache_hit_rate', 0)}%)")
    print(f"   清单: {stats['manifest']}")
    print(f"   打包: {stats['zip']}")


if __name__ == "__main__":
    main()
