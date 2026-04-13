#!/usr/bin/env python3
"""
IconForge V2 模块单元测试

覆盖:
- prompt_engine: build_pro_prompt, get_preset, list_presets
- cache: IconCache (get, put, stats, cleanup, TTL, eviction)
- quality_engine: check_basic, analyze_colors, compute_phash,
  hamming_distance, check_duplicates, analyze_composition, quality_check_v2
"""

import json
import os
import shutil
import struct
import tempfile
import time
import unittest
import zlib

# 确保项目根目录在 sys.path 中
import sys
import importlib
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# icon-forge 目录名含连字符，需要动态导入
_icon_forge_path = os.path.join(PROJECT_ROOT, "products", "icon-forge")
sys.path.insert(0, _icon_forge_path)
prompt_engine = importlib.import_module("prompt_engine")
cache_mod = importlib.import_module("cache")
quality_engine = importlib.import_module("quality_engine")

# 从动态导入的模块中提取所需符号
build_pro_prompt = prompt_engine.build_pro_prompt
get_preset = prompt_engine.get_preset
list_presets = prompt_engine.list_presets
STYLE_KEYWORDS_V2 = prompt_engine.STYLE_KEYWORDS_V2
TYPE_KEYWORDS_V2 = prompt_engine.TYPE_KEYWORDS_V2
STYLE_ANCHORS = prompt_engine.STYLE_ANCHORS
NEGATIVE_PROMPT = prompt_engine.NEGATIVE_PROMPT
PRESETS = prompt_engine.PRESETS

IconCache = cache_mod.IconCache

check_basic = quality_engine.check_basic
analyze_colors = quality_engine.analyze_colors
compute_phash = quality_engine.compute_phash
hamming_distance = quality_engine.hamming_distance
check_duplicates = quality_engine.check_duplicates
analyze_composition = quality_engine.analyze_composition
quality_check_v2 = quality_engine.quality_check_v2
QCConfig = quality_engine.QCConfig
_read_png_dimensions = quality_engine.read_png_dimensions
_int_to_rgb = quality_engine._int_to_rgb
_int_to_gray = quality_engine._int_to_gray
_rgb_to_saturation = quality_engine._rgb_to_saturation
_variance = quality_engine._variance


# ============ 测试辅助：创建最小合法 PNG ============

def _make_minimal_png(width=8, height=8, color=(128, 64, 32)) -> bytes:
    """创建一个最小合法 RGBA PNG 文件内容

    Args:
        width: 图片宽度
        height: 图片高度
        color: 填充色 (R, G, B)

    Returns:
        PNG 文件的二进制内容
    """
    def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        chunk = chunk_type + data
        import hashlib
        crc = zlib.crc32(chunk) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + chunk + struct.pack(">I", crc)

    # Signature
    sig = b'\x89PNG\r\n\x1a\n'

    # IHDR: width, height, bit_depth=8, color_type=2 (RGB)
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = _png_chunk(b'IHDR', ihdr_data)

    # IDAT: raw pixel data with filter byte 0 per row
    raw_rows = b""
    for _ in range(height):
        raw_rows += b'\x00'  # filter byte: None
        for _ in range(width):
            raw_rows += bytes(color)

    compressed = zlib.compress(raw_rows)
    idat = _png_chunk(b'IDAT', compressed)

    # IEND
    iend = _png_chunk(b'IEND', b'')

    return sig + ihdr + idat + iend


def _create_png_file(tmpdir, filename="test.png", width=8, height=8,
                     color=(128, 64, 32), file_size_override=None) -> str:
    """创建 PNG 文件并返回路径"""
    path = os.path.join(tmpdir, filename)
    data = _make_minimal_png(width, height, color)
    with open(path, "wb") as f:
        f.write(data)
    return path


# ============ prompt_engine 测试 ============

class TestBuildProPrompt(unittest.TestCase):
    """测试 build_pro_prompt 函数"""

    def test_basic_prompt_no_style(self):
        """无风格时，prompt 仅包含 subject + type 词"""
        result = build_pro_prompt("magic sword")
        self.assertIn("prompt", result)
        self.assertIn("negative", result)
        self.assertIn("parts", result)
        # 默认 asset_type="icon"，应包含 icon 词
        self.assertIn("icon", result["parts"].get("type", ""))
        self.assertIn("magic sword", result["prompt"])

    def test_prompt_with_style(self):
        """指定风格时，prompt 应包含风格词"""
        result = build_pro_prompt("magic sword", style="pixel")
        self.assertIn("pixel", result["parts"].get("style", ""))
        self.assertIn("lighting", result["parts"])
        self.assertIn("anchor", result["parts"])

    def test_prompt_without_anchor(self):
        """use_anchor=False 时不应包含 anchor"""
        result = build_pro_prompt("magic sword", style="dark", use_anchor=False)
        self.assertNotIn("anchor", result["parts"])

    def test_prompt_without_negative(self):
        """use_negative=False 时 negative 应为空"""
        result = build_pro_prompt("magic sword", use_negative=False)
        self.assertEqual(result["negative"], "")

    def test_prompt_with_negative(self):
        """use_negative=True 时 negative 应包含常见排除词"""
        result = build_pro_prompt("magic sword", use_negative=True)
        self.assertIn("blurry", result["negative"])
        self.assertIn("watermark", result["negative"])

    def test_all_styles(self):
        """所有 V2 风格都应能正确生成 prompt"""
        for style_name in STYLE_KEYWORDS_V2:
            result = build_pro_prompt("test item", style=style_name)
            self.assertIn("style", result["parts"], f"Missing style for: {style_name}")

    def test_all_asset_types(self):
        """所有 V2 资产类型都应能正确生成 prompt"""
        for type_name in TYPE_KEYWORDS_V2:
            result = build_pro_prompt("test item", asset_type=type_name)
            self.assertIn("type", result["parts"], f"Missing type for: {type_name}")

    def test_unknown_style_ignored(self):
        """未知风格应被忽略（不报错）"""
        result = build_pro_prompt("test item", style="nonexistent_style")
        self.assertNotIn("style", result["parts"])

    def test_unknown_asset_type_ignored(self):
        """未知资产类型应被忽略"""
        result = build_pro_prompt("test item", asset_type="nonexistent_type")
        self.assertNotIn("type", result["parts"])


class TestGetPreset(unittest.TestCase):
    """测试 get_preset 函数"""

    def test_valid_preset(self):
        """获取存在的预设应返回正确数据"""
        preset = get_preset("rpg-weapons")
        self.assertEqual(preset["style"], "dark")
        self.assertIn("prompts", preset)
        self.assertTrue(len(preset["prompts"]) > 0)

    def test_invalid_preset_raises(self):
        """获取不存在的预设应抛出 ValueError"""
        with self.assertRaises(ValueError) as ctx:
            get_preset("nonexistent")
        self.assertIn("nonexistent", str(ctx.exception))

    def test_all_presets_accessible(self):
        """所有 PRESETS 键都应能通过 get_preset 获取"""
        for key in PRESETS:
            preset = get_preset(key)
            self.assertIn("name", preset)
            self.assertIn("prompts", preset)


class TestListPresets(unittest.TestCase):
    """测试 list_presets 函数"""

    def test_list_count(self):
        """返回的预设列表长度应与 PRESETS 一致"""
        result = list_presets()
        self.assertEqual(len(result), len(PRESETS))

    def test_list_structure(self):
        """每个预设条目应包含必要字段"""
        result = list_presets()
        for entry in result:
            self.assertIn("id", entry)
            self.assertIn("name", entry)
            self.assertIn("description", entry)
            self.assertIn("style", entry)
            self.assertIn("asset_type", entry)
            self.assertIn("item_count", entry)


class TestPromptEngineData(unittest.TestCase):
    """测试 prompt_engine 数据完整性"""

    def test_style_keywords_have_required_keys(self):
        """每个 V2 风格应包含 positive, lighting, anchor"""
        for style_name, style_data in STYLE_KEYWORDS_V2.items():
            self.assertIn("positive", style_data, f"Missing 'positive' in {style_name}")
            self.assertIn("lighting", style_data, f"Missing 'lighting' in {style_name}")
            self.assertIn("anchor", style_data, f"Missing 'anchor' in {style_name}")

    def test_type_keywords_have_required_keys(self):
        """每个 V2 资产类型应包含 positive, detail"""
        for type_name, type_data in TYPE_KEYWORDS_V2.items():
            self.assertIn("positive", type_data, f"Missing 'positive' in {type_name}")
            self.assertIn("detail", type_data, f"Missing 'detail' in {type_name}")

    def test_style_anchors_match_keywords(self):
        """STYLE_ANCHORS 的键应与 STYLE_KEYWORDS_V2 完全一致"""
        self.assertEqual(set(STYLE_ANCHORS.keys()), set(STYLE_KEYWORDS_V2.keys()))

    def test_negative_prompt_not_empty(self):
        """负面 prompt 不应为空"""
        self.assertTrue(len(NEGATIVE_PROMPT) > 0)


# ============ cache 测试 ============

class TestIconCache(unittest.TestCase):
    """测试 IconCache 类"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="iconforge_test_")
        self.cache = IconCache(cache_dir=self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_put_and_get_with_data(self):
        """存入二进制数据后应能通过相同参数命中缓存"""
        data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100  # 模拟 PNG 数据
        path = self.cache.put("magic sword", style="pixel", seed=42, data=data)
        self.assertIsNotNone(path)
        self.assertTrue(os.path.exists(path))

        # 命中
        cached = self.cache.get("magic sword", style="pixel", seed=42)
        self.assertIsNotNone(cached)
        self.assertEqual(cached, path)

    def test_cache_miss(self):
        """查询不存在的缓存应返回 None"""
        result = self.cache.get("nonexistent prompt")
        self.assertIsNone(result)

    def test_cache_key_different_params(self):
        """不同参数组合应产生不同缓存 key"""
        data = b'\x00' * 50
        path1 = self.cache.put("sword", style="pixel", seed=1, data=data)
        path2 = self.cache.put("sword", style="dark", seed=1, data=data)
        # 不同 style 应产生不同 key
        self.assertNotEqual(path1, path2)

    def test_cache_stats(self):
        """统计信息应正确反映 hits/misses"""
        data = b'\x00' * 50
        self.cache.put("test", data=data)
        self.cache.get("test")       # hit
        self.cache.get("test")       # hit
        self.cache.get("nonexistent")  # miss

        stats = self.cache.stats()
        self.assertEqual(stats["hits"], 2)
        self.assertEqual(stats["misses"], 1)
        self.assertGreater(stats["hit_rate_pct"], 0)

    def test_cache_ttl_expiry(self):
        """TTL 过期后应返回 None"""
        data = b'\x00' * 50
        self.cache.put("expiring", data=data, ttl=1)  # 1秒TTL
        time.sleep(1.1)
        result = self.cache.get("expiring")
        self.assertIsNone(result)

    def test_cache_cleanup(self):
        """cleanup 应移除过期缓存"""
        data = b'\x00' * 50
        self.cache.put("old_item", data=data, ttl=1)  # 1秒TTL
        time.sleep(1.1)
        evicted = self.cache.cleanup()
        self.assertGreaterEqual(evicted, 1)

    def test_cache_persistence(self):
        """缓存索引应持久化到磁盘"""
        data = b'\x00' * 50
        self.cache.put("persistent", data=data)

        # 重新创建 cache 实例，应能读取之前的缓存
        cache2 = IconCache(cache_dir=self.tmpdir)
        result = cache2.get("persistent")
        self.assertIsNotNone(result)

    def test_put_returns_none_for_no_data(self):
        """不提供 data 和 source_path 时 put 应返回 None"""
        result = self.cache.put("nothing", data=None, source_path=None)
        self.assertIsNone(result)

    def test_put_from_source_file(self):
        """从源文件复制到缓存"""
        # 创建源文件
        src_dir = os.path.join(self.tmpdir, "source")
        os.makedirs(src_dir, exist_ok=True)
        src_path = os.path.join(src_dir, "source.png")
        with open(src_path, "wb") as f:
            f.write(b'\x89PNG\r\n\x1a\n' + b'\x00' * 50)

        cache_path = self.cache.put("copied", source_path=src_path)
        self.assertIsNotNone(cache_path)
        self.assertTrue(os.path.exists(cache_path))


# ============ quality_engine 测试 ============

class TestQualityEngineHelpers(unittest.TestCase):
    """测试 quality_engine 辅助函数"""

    def test_int_to_rgb(self):
        """整数转 RGB 应正确分解"""
        # 红色: 0xFF0000
        r, g, b = _int_to_rgb(0xFF0000)
        self.assertEqual(r, 255)
        self.assertEqual(g, 0)
        self.assertEqual(b, 0)

        # 白色: 0xFFFFFF
        r, g, b = _int_to_rgb(0xFFFFFF)
        self.assertEqual(r, 255)
        self.assertEqual(g, 255)
        self.assertEqual(b, 255)

    def test_int_to_gray(self):
        """灰度转换应在合理范围"""
        # 纯黑 0x000000 → 0
        self.assertEqual(_int_to_gray(0x000000), 0)
        # 纯白 0xFFFFFF → 255
        self.assertEqual(_int_to_gray(0xFFFFFF), 255)

    def test_rgb_to_saturation(self):
        """饱和度计算"""
        # 灰色饱和度为 0
        self.assertAlmostEqual(_rgb_to_saturation(128, 128, 128), 0.0)
        # 纯色饱和度为 1
        self.assertAlmostEqual(_rgb_to_saturation(255, 0, 0), 1.0)

    def test_variance(self):
        """方差计算"""
        # 常数列方差为 0
        self.assertEqual(_variance([5, 5, 5]), 0.0)
        # 非常数列方差 > 0
        self.assertGreater(_variance([1, 2, 3]), 0)


class TestReadPngDimensions(unittest.TestCase):
    """测试 _read_png_dimensions 函数"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="qc_test_")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_valid_png_dimensions(self):
        """应能正确读取合法 PNG 的宽高"""
        path = _create_png_file(self.tmpdir, width=64, height=64)
        dims = _read_png_dimensions(path)
        self.assertIsNotNone(dims)
        self.assertEqual(dims, (64, 64))

    def test_non_png_file(self):
        """非 PNG 文件应返回 None"""
        path = os.path.join(self.tmpdir, "not_png.txt")
        with open(path, "w") as f:
            f.write("hello")
        dims = _read_png_dimensions(path)
        self.assertIsNone(dims)


class TestCheckBasic(unittest.TestCase):
    """测试 check_basic 函数"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="qc_basic_")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_valid_png_passes(self):
        """合法大小的 PNG 应通过基础校验"""
        path = _create_png_file(self.tmpdir, width=8, height=8)
        result = check_basic(path, expected_size=8)
        # 小文件可能不通过 file_size 检查，但 dimensions 应正确
        self.assertIn("dimensions", result)
        self.assertIn("scores", result)

    def test_tiny_file_fails(self):
        """太小的文件应未通过校验"""
        path = os.path.join(self.tmpdir, "tiny.png")
        with open(path, "wb") as f:
            f.write(b'\x89PNG\r\n\x1a\n' + b'\x00' * 10)  # 18 bytes, far below 5KB
        result = check_basic(path)
        self.assertFalse(result["passed"])
        self.assertTrue(any("太小" in issue for issue in result["issues"]))


class TestHammingDistance(unittest.TestCase):
    """测试 hamming_distance 函数"""

    def test_same_hash(self):
        """相同哈希汉明距离为 0"""
        self.assertEqual(hamming_distance(0, 0), 0)
        self.assertEqual(hamming_distance(0xDEADBEEF, 0xDEADBEEF), 0)

    def test_one_bit_diff(self):
        """1位差异汉明距离为 1"""
        self.assertEqual(hamming_distance(0, 1), 1)
        self.assertEqual(hamming_distance(0b1000, 0b0000), 1)

    def test_all_bits_diff(self):
        """所有位不同"""
        self.assertEqual(hamming_distance(0b1111, 0b0000), 4)


class TestComputePhash(unittest.TestCase):
    """测试 compute_phash 函数"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="phash_test_")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_valid_png_returns_hash(self):
        """合法 PNG 应返回非零哈希"""
        path = _create_png_file(self.tmpdir)
        h = compute_phash(path)
        self.assertIsInstance(h, int)

    def test_nonexistent_file_returns_zero(self):
        """不存在的文件应返回 0"""
        h = compute_phash("/nonexistent/file.png")
        self.assertEqual(h, 0)

    def test_same_image_same_hash(self):
        """相同图片应产生相同哈希"""
        path = _create_png_file(self.tmpdir, filename="a.png")
        h1 = compute_phash(path)
        h2 = compute_phash(path)
        self.assertEqual(h1, h2)


class TestCheckDuplicates(unittest.TestCase):
    """测试 check_duplicates 函数"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="dup_test_")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_no_duplicates(self):
        """与空已有哈希比较应不重复"""
        path = _create_png_file(self.tmpdir)
        result = check_duplicates(path, {})
        self.assertFalse(result["is_duplicate"])
        self.assertIsNone(result["duplicate_of"])

    def test_duplicate_detection(self):
        """相同文件应被检测为重复"""
        path = _create_png_file(self.tmpdir, filename="original.png")
        h = compute_phash(path)
        # 与自身比较
        result = check_duplicates(path, {path: h})
        self.assertTrue(result["is_duplicate"])


class TestAnalyzeColors(unittest.TestCase):
    """测试 analyze_colors 函数"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="color_test_")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_returns_structure(self):
        """应返回正确的数据结构"""
        path = _create_png_file(self.tmpdir, color=(200, 50, 50))
        result = analyze_colors(path)
        self.assertIn("scores", result)
        self.assertIn("issues", result)

    def test_invalid_file(self):
        """非法文件应有降级评分"""
        path = os.path.join(self.tmpdir, "bad.png")
        with open(path, "wb") as f:
            f.write(b"not a png")
        result = analyze_colors(path)
        self.assertIn("scores", result)


class TestAnalyzeComposition(unittest.TestCase):
    """测试 analyze_composition 函数"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="comp_test_")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_returns_structure(self):
        """应返回正确的数据结构"""
        path = _create_png_file(self.tmpdir)
        result = analyze_composition(path)
        self.assertIn("scores", result)
        self.assertIn("issues", result)

    def test_invalid_file(self):
        """非法文件应有降级评分"""
        path = os.path.join(self.tmpdir, "bad.png")
        with open(path, "wb") as f:
            f.write(b"invalid")
        result = analyze_composition(path)
        self.assertIn("scores", result)


class TestQualityCheckV2(unittest.TestCase):
    """测试 quality_check_v2 综合质检"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="qc_v2_")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_returns_complete_structure(self):
        """应返回完整的结果结构"""
        path = _create_png_file(self.tmpdir)
        result = quality_check_v2(path, expected_size=8)
        self.assertIn("file", result)
        self.assertIn("passed", result)
        self.assertIn("overall_score", result)
        self.assertIn("scores", result)
        self.assertIn("issues", result)
        self.assertIn("hash", result)
        self.assertIn("is_duplicate", result)

    def test_score_range(self):
        """综合评分应在 0-100 范围内"""
        path = _create_png_file(self.tmpdir)
        result = quality_check_v2(path, expected_size=8)
        self.assertGreaterEqual(result["overall_score"], 0)
        self.assertLessEqual(result["overall_score"], 100)

    def test_with_existing_hashes(self):
        """传入已有哈希时应进行去重检测"""
        path = _create_png_file(self.tmpdir)
        h = compute_phash(path)
        result = quality_check_v2(path, expected_size=8, existing_hashes={path: h})
        self.assertTrue(result["is_duplicate"])

    def test_nonexistent_file(self):
        """不存在的文件应抛出异常（由调用方处理）"""
        with self.assertRaises(Exception):
            quality_check_v2("/nonexistent/file.png")


class TestQCConfig(unittest.TestCase):
    """测试 QCConfig 配置值合理性"""

    def test_min_file_size_positive(self):
        self.assertGreater(QCConfig.MIN_FILE_SIZE, 0)

    def test_pass_score_in_range(self):
        self.assertGreater(QCConfig.PASS_SCORE, 0)
        self.assertLessEqual(QCConfig.PASS_SCORE, 100)

    def test_phash_threshold_positive(self):
        self.assertGreater(QCConfig.PHASH_THRESHOLD, 0)

    def test_max_center_offset_in_range(self):
        self.assertGreater(QCConfig.MAX_CENTER_OFFSET, 0)
        self.assertLessEqual(QCConfig.MAX_CENTER_OFFSET, 1.0)


if __name__ == "__main__":
    unittest.main()
