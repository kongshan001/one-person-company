#!/usr/bin/env python3
"""
IconForge 质检引擎 V2
从简单的大小检查升级为多维度质量评估

检测维度：
1. 基础校验 — 文件大小/分辨率/格式
2. 色彩分析 — 丰富度/主导色/饱和度/对比度
3. 去重检测 — 基于感知哈希(pHash)的相似图片检测
4. 构图评分 — 中心偏移/边缘空白/主体占比
5. 综合评分 — 加权总分 + 通过/不通过判定
"""

import hashlib
import os
import struct
import sys
from collections import Counter
from pathlib import Path

# 引入共享工具
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from utils import read_png_dimensions


# ============ 配置 ============

class QCConfig:
    MIN_FILE_SIZE = 5000       # 5KB
    MIN_UNIQUE_COLORS = 8      # 最少独特色彩数
    MIN_SATURATION = 0.05      # 最低平均饱和度
    MAX_CENTER_OFFSET = 0.3    # 最大中心偏移比
    MIN_SUBJECT_RATIO = 0.15   # 主体最少占比
    PHASH_THRESHOLD = 10       # 感知哈希汉明距离阈值(<=此值视为重复)
    PASS_SCORE = 60            # 综合及格分


# ============ 基础校验 ============

def check_basic(file_path: str, expected_size: int = 512) -> dict:
    """基础文件校验：大小/分辨率/格式"""
    result = {"passed": True, "issues": [], "scores": {}}
    
    # 文件大小
    file_size = os.path.getsize(file_path)
    result["file_size"] = file_size
    if file_size < QCConfig.MIN_FILE_SIZE:
        result["passed"] = False
        result["issues"].append(f"文件太小: {file_size} bytes")
        result["scores"]["file_size"] = 0
    else:
        # 大小评分: 5KB=60, 50KB=80, 200KB+=100
        result["scores"]["file_size"] = min(100, 60 + (file_size / 50000) * 20)
    
    # 分辨率
    dims = read_png_dimensions(file_path)
    if dims:
        w, h = dims
        result["dimensions"] = (w, h)
        if w != expected_size or h != expected_size:
            result["passed"] = False
            result["issues"].append(f"分辨率不匹配: 期望{expected_size}x{expected_size}, 实际{w}x{h}")
            result["scores"]["resolution"] = 50
        else:
            result["scores"]["resolution"] = 100
    else:
        result["dimensions"] = None
        result["issues"].append("无法读取分辨率")
        result["scores"]["resolution"] = 70
    
    return result


# ============ 色彩分析 ============

def analyze_colors(file_path: str) -> dict:
    """
    分析图片色彩特征
    纯 Python 实现，读取 PNG 像素数据
    
    返回: unique_colors, dominant_colors, avg_saturation, color_richness_score
    """
    result = {"passed": True, "issues": [], "scores": {}}
    
    try:
        pixels = _read_png_pixels(file_path)
        if pixels is None:
            result["scores"]["color"] = 50
            result["issues"].append("无法读取像素数据")
            return result
        
        # 统计色彩
        color_counter = Counter(pixels)
        unique_colors = len(color_counter)
        result["unique_colors"] = unique_colors
        
        # 主导色 (top 5)
        dominant = color_counter.most_common(5)
        result["dominant_colors"] = [
            {"rgb": _int_to_rgb(c), "count": cnt, "pct": round(cnt / len(pixels) * 100, 1)}
            for c, cnt in dominant
        ]
        
        # 饱和度分析
        saturations = [_rgb_to_saturation(*_int_to_rgb(c)) for c in pixels[::100]]  # 采样
        avg_sat = sum(saturations) / len(saturations) if saturations else 0
        result["avg_saturation"] = round(avg_sat, 3)
        
        # 色彩丰富度评分
        # 独特色数: <8=差, 20+=良, 50+=优
        color_score = min(100, (unique_colors / 50) * 100)
        sat_score = min(100, (avg_sat / 0.3) * 100) if avg_sat > QCConfig.MIN_SATURATION else 30
        result["scores"]["color"] = round(color_score * 0.6 + sat_score * 0.4, 1)
        
        if unique_colors < QCConfig.MIN_UNIQUE_COLORS:
            result["passed"] = False
            result["issues"].append(f"色彩过少: {unique_colors} 种独特色")
        
    except Exception as e:
        result["scores"]["color"] = 50
        result["issues"].append(f"色彩分析失败: {e}")
    
    return result


# ============ 去重检测 ============

def compute_phash(file_path: str, hash_size: int = 8) -> int:
    """
    感知哈希 (pHash) — 粗粒度图像指纹
    用于检测视觉上相似的图片
    
    原理：缩小→灰度→DCT→取低频→二值化→哈希
    纯 Python 实现
    """
    try:
        pixels = _read_png_pixels_grayscale(file_path, target_size=32)
        if pixels is None:
            return 0
        
        # 简化 DCT：用均值比较代替完整 DCT
        # 将 32x32 分成 8x8 块，每块 4x4 像素
        block_means = []
        for by in range(hash_size):
            for bx in range(hash_size):
                total = 0
                count = 0
                for y in range(by * 4, (by + 1) * 4):
                    for x in range(bx * 4, (bx + 1) * 4):
                        if y < len(pixels) and x < len(pixels[0]):
                            total += pixels[y][x]
                            count += 1
                block_means.append(total / count if count else 0)
        
        # 二值化：高于均值为1，低于为0
        avg = sum(block_means) / len(block_means)
        hash_val = 0
        for i, m in enumerate(block_means):
            if m > avg:
                hash_val |= (1 << i)
        
        return hash_val
        
    except Exception:
        return 0


def hamming_distance(hash1: int, hash2: int) -> int:
    """计算两个哈希的汉明距离"""
    x = hash1 ^ hash2
    dist = 0
    while x:
        dist += 1
        x &= x - 1
    return dist


def check_duplicates(file_path: str, existing_hashes: dict) -> dict:
    """
    检查是否与已有图片重复
    
    Args:
        file_path: 当前图片路径
        existing_hashes: {文件路径: pHash值} 字典
    
    返回:
        {"is_duplicate": bool, "duplicate_of": str or None, "hash": int}
    """
    result = {"is_duplicate": False, "duplicate_of": None, "hash": 0}
    
    current_hash = compute_phash(file_path)
    result["hash"] = current_hash
    
    if current_hash == 0:
        return result
    
    for path, existing_hash in existing_hashes.items():
        if existing_hash == 0:
            continue
        dist = hamming_distance(current_hash, existing_hash)
        if dist <= QCConfig.PHASH_THRESHOLD:
            result["is_duplicate"] = True
            result["duplicate_of"] = path
            result["hamming_distance"] = dist
            break
    
    return result


# ============ 构图评分 ============

def analyze_composition(file_path: str) -> dict:
    """
    分析构图质量
    检查：中心偏移/边缘空白/主体占比
    
    原理：假设主体颜色更丰富/更突出，通过灰度梯度检测主体区域
    """
    result = {"passed": True, "issues": [], "scores": {}}
    
    try:
        pixels = _read_png_pixels_grayscale(file_path)
        if pixels is None:
            result["scores"]["composition"] = 50
            return result
        
        h = len(pixels)
        w = len(pixels[0]) if h > 0 else 0
        if h == 0 or w == 0:
            result["scores"]["composition"] = 50
            return result
        
        # 1. 计算图片"重心"（非空白区域的加权中心）
        total_weight = 0
        cx_sum = 0
        cy_sum = 0
        
        # 边缘检测：与邻域差异大的像素更有可能是主体
        for y in range(1, h - 1, 2):  # 采样步长2
            for x in range(1, w - 1, 2):
                # 简单梯度：与右邻和下邻的差异
                gx = abs(pixels[y][x] - pixels[y][min(x+1, w-1)])
                gy = abs(pixels[y][x] - pixels[min(y+1, h-1)][x])
                weight = gx + gy
                total_weight += weight
                cx_sum += x * weight
                cy_sum += y * weight
        
        if total_weight > 0:
            center_x = cx_sum / total_weight
            center_y = cy_sum / total_weight
            
            # 中心偏移 (0=完美居中, 1=偏到角落)
            offset_x = abs(center_x - w / 2) / (w / 2)
            offset_y = abs(center_y - h / 2) / (h / 2)
            center_offset = (offset_x + offset_y) / 2
            result["center_offset"] = round(center_offset, 3)
            
            # 中心偏移评分
            if center_offset > QCConfig.MAX_CENTER_OFFSET:
                result["issues"].append(f"主体偏移过大: {center_offset:.1%}")
                result["scores"]["centering"] = max(0, 100 - center_offset * 200)
            else:
                result["scores"]["centering"] = 100 - center_offset * 50
        else:
            result["scores"]["centering"] = 30
            result["issues"].append("图片可能是纯色/空白")
        
        # 2. 边缘空白检测
        border_size = max(1, min(w, h) // 10)
        border_pixels = []
        for y in range(h):
            for x in range(w):
                if x < border_size or x >= w - border_size or y < border_size or y >= h - border_size:
                    border_pixels.append(pixels[y][x])
        
        if border_pixels:
            border_variance = _variance(border_pixels)
            # 边缘方差小说明是纯色背景(好)，方差大说明主体延伸到边缘(可能不好)
            result["border_uniformity"] = round(border_variance, 1)
            result["scores"]["border"] = 80 if border_variance < 100 else 50
        
        # 构图综合评分
        centering = result["scores"].get("centering", 70)
        border = result["scores"].get("border", 70)
        result["scores"]["composition"] = round(centering * 0.6 + border * 0.4, 1)
        
    except Exception as e:
        result["scores"]["composition"] = 50
        result["issues"].append(f"构图分析失败: {e}")
    
    return result


# ============ 综合质检 ============

def quality_check_v2(file_path: str, expected_size: int = 512,
                     existing_hashes: dict = None) -> dict:
    """
    V2 综合质检
    
    返回:
        {
            "file": str,
            "passed": bool,
            "overall_score": float (0-100),
            "details": {各维度结果},
            "issues": [str],
            "hash": int  # pHash，用于后续去重
        }
    """
    all_issues = []
    all_scores = {}
    
    # 1. 基础校验
    basic = check_basic(file_path, expected_size)
    all_issues.extend(basic["issues"])
    all_scores.update(basic["scores"])
    
    # 2. 色彩分析
    color = analyze_colors(file_path)
    all_issues.extend(color["issues"])
    all_scores["color"] = color["scores"].get("color", 50)
    
    # 3. 构图评分
    comp = analyze_composition(file_path)
    all_issues.extend(comp["issues"])
    all_scores["composition"] = comp["scores"].get("composition", 50)
    
    # 4. 去重检测
    phash = 0
    is_dup = False
    dup_of = None
    if existing_hashes is not None:
        dup = check_duplicates(file_path, existing_hashes)
        phash = dup["hash"]
        is_dup = dup["is_duplicate"]
        dup_of = dup.get("duplicate_of")
        if is_dup:
            all_issues.append(f"与已有图片重复: {dup_of} (距离={dup.get('hamming_distance', '?')})")
            all_scores["uniqueness"] = 20
        else:
            all_scores["uniqueness"] = 100
    
    # 5. 加权综合评分
    weights = {
        "file_size": 0.15,
        "resolution": 0.15,
        "color": 0.25,
        "composition": 0.25,
        "uniqueness": 0.20,
    }
    
    overall = 0
    total_weight = 0
    for key, weight in weights.items():
        if key in all_scores:
            overall += all_scores[key] * weight
            total_weight += weight
    
    if total_weight > 0:
        overall = round(overall / total_weight, 1)
    else:
        overall = 0
    
    passed = overall >= QCConfig.PASS_SCORE and not is_dup
    
    return {
        "file": file_path,
        "passed": passed,
        "overall_score": overall,
        "scores": all_scores,
        "issues": all_issues,
        "hash": phash,
        "is_duplicate": is_dup,
        "duplicate_of": dup_of,
    }


# ============ PNG 读取辅助 ============

def _read_png_pixels(file_path: str, max_pixels: int = 65536) -> list:
    """
    读取 PNG 像素 RGB 值
    仅支持 8-bit RGB/RGBA PNG（Pollinations 输出格式）
    采样到 max_pixels 个像素
    """
    try:
        with open(file_path, "rb") as f:
            sig = f.read(8)
            if sig != b'\x89PNG\r\n\x1a\n':
                return None
            
            width = height = bit_depth = color_type = None
            idat_data = b""
            
            while True:
                chunk_len = f.read(4)
                if len(chunk_len) < 4:
                    break
                length = int.from_bytes(chunk_len, 'big')
                chunk_type = f.read(4)
                chunk_data = f.read(length)
                crc = f.read(4)
                
                if chunk_type == b'IHDR':
                    width = int.from_bytes(chunk_data[0:4], 'big')
                    height = int.from_bytes(chunk_data[4:8], 'big')
                    bit_depth = chunk_data[8]
                    color_type = chunk_data[9]
                elif chunk_type == b'IDAT':
                    idat_data += chunk_data
                elif chunk_type == b'IEND':
                    break
            
            if not width or not idat_data:
                return None
            
            # 解压 IDAT
            import zlib
            raw = zlib.decompress(idat_data)
            
            # 解析像素
            bytes_per_pixel = 4 if color_type == 6 else 3 if color_type == 2 else 1
            stride = width * bytes_per_pixel + 1  # +1 for filter byte per row
            
            pixels = []
            step = max(1, (width * height) // max_pixels)
            
            idx = 0
            for y in range(height):
                if y * width % step != 0 and y < height - 1:
                    # 跳行采样
                    idx += stride
                    continue
                filter_byte = raw[idx]
                idx += 1
                row_start = idx
                for x in range(width):
                    if (y * width + x) % step == 0:
                        r = raw[row_start + x * bytes_per_pixel]
                        g = raw[row_start + x * bytes_per_pixel + 1]
                        b = raw[row_start + x * bytes_per_pixel + 2]
                        pixels.append((r << 16) | (g << 8) | b)
                idx = row_start + width * bytes_per_pixel
            
            return pixels
            
    except Exception:
        return None


def _read_png_pixels_grayscale(file_path: str, target_size: int = 64) -> list:
    """
    读取 PNG 并转为灰度，缩小到 target_size x target_size
    返回 2D 列表 [[gray_val, ...], ...]
    """
    try:
        pixels_rgb = _read_png_pixels(file_path, max_pixels=target_size * target_size)
        if pixels_rgb is None:
            return None
        
        # 转灰度
        grays = [_int_to_gray(p) for p in pixels_rgb]
        
        # 重塑为 2D (近似)
        side = int(len(grays) ** 0.5)
        if side == 0:
            return None
        
        result = []
        for y in range(side):
            row = []
            for x in range(side):
                idx = y * side + x
                if idx < len(grays):
                    row.append(grays[idx])
            if row:
                result.append(row)
        
        return result
        
    except Exception:
        return None


def _int_to_rgb(color_int: int) -> tuple:
    """整数转 RGB 元组"""
    return ((color_int >> 16) & 0xFF, (color_int >> 8) & 0xFF, color_int & 0xFF)


def _int_to_gray(color_int: int) -> int:
    """整数转灰度值"""
    r, g, b = _int_to_rgb(color_int)
    return int(0.299 * r + 0.587 * g + 0.114 * b)


def _rgb_to_saturation(r: int, g: int, b: int) -> float:
    """RGB 转饱和度 (0-1)"""
    max_c = max(r, g, b) / 255.0
    min_c = min(r, g, b) / 255.0
    if max_c == 0:
        return 0
    return (max_c - min_c) / max_c


def _variance(values: list) -> float:
    """计算方差"""
    if not values:
        return 0
    mean = sum(values) / len(values)
    return sum((x - mean) ** 2 for x in values) / len(values)
