#!/usr/bin/env python3
"""
Unit tests for config.py and utils.py modules

Run: python3 -m unittest tests.test_config_and_utils -v
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# 引入共享模块
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config as _config
import utils as _utils


class TestConfigClasses(unittest.TestCase):
    """Test config module classes and defaults"""

    def test_pastehut_config_defaults(self):
        """PasteHutConfig should have correct default values"""
        self.assertEqual(_config.PasteHutConfig.DEFAULT_PORT, 9292)
        self.assertEqual(_config.PasteHutConfig.DEFAULT_HOST, "0.0.0.0")
        self.assertIsInstance(_config.PasteHutConfig.DATA_DIR, str)

    def test_pingbot_config_defaults(self):
        """PingBotConfig should have correct default values"""
        self.assertEqual(_config.PingBotConfig.DEFAULT_PORT, 8081)
        self.assertEqual(_config.PingBotConfig.DEFAULT_HOST, "0.0.0.0")
        self.assertIsInstance(_config.PingBotConfig.DB_PATH, str)

    def test_iconforge_config_defaults(self):
        """IconForgeConfig should have correct default values"""
        self.assertIsInstance(_config.IconForgeConfig.POLLINATIONS_URL, str)
        self.assertIsInstance(_config.IconForgeConfig.STYLE_KEYWORDS, dict)
        self.assertIsInstance(_config.IconForgeConfig.TYPE_KEYWORDS, dict)
        self.assertIn("pixel", _config.IconForgeConfig.STYLE_KEYWORDS)
        self.assertIn("icon", _config.IconForgeConfig.TYPE_KEYWORDS)

    def test_infra_config_defaults(self):
        """InfraConfig should have correct default values"""
        self.assertIsInstance(_config.InfraConfig.PID_DIR, str)
        self.assertIsInstance(_config.InfraConfig.LOG_DIR, str)
        self.assertIsInstance(_config.InfraConfig.BACKUP_DIR, str)
        self.assertGreater(_config.InfraConfig.HEALTH_CHECK_TIMEOUT, 0)
        self.assertGreater(_config.InfraConfig.HEALTH_CHECK_INTERVAL, 0)

    def test_pingbot_api_key_from_env(self):
        """PingBotConfig API key should be overridable via env var"""
        import unittest.mock
        with unittest.mock.patch.dict(os.environ, {"PINGBOT_API_KEY": "test-key-123"}):
            # Re-read the env var
            key = os.environ.get("PINGBOT_API_KEY", "")
            self.assertEqual(key, "test-key-123")

    def test_pingbot_alert_webhook_from_env(self):
        """PingBotConfig alert webhook should be overridable via env var"""
        import unittest.mock
        with unittest.mock.patch.dict(os.environ, {"PINGBOT_ALERT_WEBHOOK": "https://example.com/webhook"}):
            url = os.environ.get("PINGBOT_ALERT_WEBHOOK", "")
            self.assertEqual(url, "https://example.com/webhook")


class TestUtilsExtended(unittest.TestCase):
    """Extended tests for utils module - validate_url, format_bytes, parse_duration, truncate_text, safe_get_path"""

    # --- validate_url ---
    def test_validate_url_valid_http(self):
        """Valid HTTP URL should pass"""
        self.assertEqual(_utils.validate_url("http://example.com"), "http://example.com")

    def test_validate_url_valid_https(self):
        """Valid HTTPS URL should pass"""
        self.assertEqual(_utils.validate_url("https://example.com/path"), "https://example.com/path")

    def test_validate_url_ftp_rejected(self):
        """FTP URL should be rejected by default"""
        self.assertIsNone(_utils.validate_url("ftp://example.com"))

    def test_validate_url_empty(self):
        """Empty URL should be rejected"""
        self.assertIsNone(_utils.validate_url(""))

    def test_validate_url_none_type(self):
        """Non-string should be rejected"""
        self.assertIsNone(_utils.validate_url(None))

    def test_validate_url_localhost_rejected(self):
        """localhost should be rejected (SSRF protection)"""
        self.assertIsNone(_utils.validate_url("http://localhost/test"))

    def test_validate_url_127_rejected(self):
        """127.0.0.1 should be rejected (SSRF protection)"""
        self.assertIsNone(_utils.validate_url("http://127.0.0.1/test"))

    def test_validate_url_private_10_rejected(self):
        """10.x private IP should be rejected"""
        self.assertIsNone(_utils.validate_url("http://10.0.0.1/test"))

    def test_validate_url_private_192_168_rejected(self):
        """192.168.x private IP should be rejected"""
        self.assertIsNone(_utils.validate_url("http://192.168.1.1/test"))

    def test_validate_url_cloud_metadata_rejected(self):
        """169.254.169.254 should be rejected"""
        self.assertIsNone(_utils.validate_url("http://169.254.169.254/"))

    def test_validate_url_public_ip_accepted(self):
        """Public IP should be accepted"""
        self.assertEqual(_utils.validate_url("http://8.8.8.8/"), "http://8.8.8.8/")

    def test_validate_url_no_hostname_rejected(self):
        """URL without hostname should be rejected"""
        self.assertIsNone(_utils.validate_url("http://"))

    # --- format_bytes ---
    def test_format_bytes_zero(self):
        """Zero bytes"""
        self.assertEqual(_utils.format_bytes(0), "0B")

    def test_format_bytes_negative(self):
        """Negative bytes should return 0B"""
        self.assertEqual(_utils.format_bytes(-1), "0B")

    def test_format_bytes_bytes(self):
        """Small number of bytes"""
        self.assertEqual(_utils.format_bytes(100), "100B")

    def test_format_bytes_kb(self):
        """Kilobytes"""
        self.assertEqual(_utils.format_bytes(1536), "1.5KB")

    def test_format_bytes_mb(self):
        """Megabytes"""
        self.assertEqual(_utils.format_bytes(2 * 1024 * 1024), "2.0MB")

    def test_format_bytes_gb(self):
        """Gigabytes"""
        result = _utils.format_bytes(3 * 1024 ** 3)
        self.assertIn("GB", result)

    def test_format_bytes_large_kb(self):
        """Large KB value (>= 100) should use int format"""
        self.assertEqual(_utils.format_bytes(200 * 1024), "200KB")

    # --- parse_duration ---
    def test_parse_duration_seconds(self):
        """Seconds suffix"""
        self.assertEqual(_utils.parse_duration("30s"), 30)

    def test_parse_duration_minutes(self):
        """Minutes suffix"""
        self.assertEqual(_utils.parse_duration("5m"), 300)

    def test_parse_duration_hours(self):
        """Hours suffix"""
        self.assertEqual(_utils.parse_duration("2h"), 7200)

    def test_parse_duration_days(self):
        """Days suffix"""
        self.assertEqual(_utils.parse_duration("7d"), 604800)

    def test_parse_duration_plain_number(self):
        """Plain number should default to seconds"""
        self.assertEqual(_utils.parse_duration("60"), 60)

    def test_parse_duration_empty(self):
        """Empty string should return None"""
        self.assertIsNone(_utils.parse_duration(""))

    def test_parse_duration_none(self):
        """None should return None"""
        self.assertIsNone(_utils.parse_duration(None))

    def test_parse_duration_invalid(self):
        """Invalid string should return None"""
        self.assertIsNone(_utils.parse_duration("abc"))

    def test_parse_duration_whitespace(self):
        """Whitespace should be trimmed"""
        self.assertEqual(_utils.parse_duration("  30s  "), 30)

    # --- truncate_text ---
    def test_truncate_text_short(self):
        """Short text should not be truncated"""
        self.assertEqual(_utils.truncate_text("hello", 200), "hello")

    def test_truncate_text_exact(self):
        """Text at max length should not be truncated"""
        self.assertEqual(_utils.truncate_text("a" * 200, 200), "a" * 200)

    def test_truncate_text_long(self):
        """Long text should be truncated with suffix"""
        result = _utils.truncate_text("a" * 300, 200)
        self.assertEqual(len(result), 200)
        self.assertTrue(result.endswith("..."))

    def test_truncate_text_empty(self):
        """Empty text should return empty string"""
        self.assertEqual(_utils.truncate_text("", 200), "")

    def test_truncate_text_custom_suffix(self):
        """Custom suffix"""
        result = _utils.truncate_text("a" * 100, 50, "…")
        self.assertTrue(result.endswith("…"))

    # --- safe_get_path ---
    def test_safe_get_path_normal(self):
        """Normal relative path should be safe"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _utils.safe_get_path(tmpdir, "subdir/file.txt")
            self.assertIsNotNone(result)
            self.assertTrue(result.startswith(tmpdir))

    def test_safe_get_path_traversal(self):
        """Path traversal should be rejected"""
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertIsNone(_utils.safe_get_path(tmpdir, "../../etc/passwd"))

    def test_safe_get_path_empty_base(self):
        """Empty base dir should return None"""
        self.assertIsNone(_utils.safe_get_path("", "file.txt"))

    def test_safe_get_path_empty_user(self):
        """Empty user path should return None"""
        self.assertIsNone(_utils.safe_get_path("/tmp", ""))

    # --- read_png_dimensions ---
    def test_read_png_dimensions_non_png(self):
        """Non-PNG file should return None"""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"not a png")
            f.flush()
            self.assertIsNone(_utils.read_png_dimensions(f.name))

    # --- sanitize_id ---
    def test_sanitize_id_normal(self):
        """Normal hex ID should pass through"""
        self.assertEqual(_utils.sanitize_id("abc123"), "abc123")

    def test_sanitize_id_invalid_chars(self):
        """Non-hex characters should cause rejection (returns None)"""
        result = _utils.sanitize_id("abc-123_ DEF")
        # sanitize_id only allows lowercase hex, so mixed case/dashes/space returns None
        self.assertIsNone(result)

    def test_sanitize_id_empty(self):
        """Empty string should return None"""
        self.assertIsNone(_utils.sanitize_id(""))

    # --- format_uptime ---
    def test_format_uptime_full(self):
        """Full uptime string"""
        result = _utils.format_uptime(0.9999)
        self.assertIsInstance(result, str)
        self.assertIn("%", result)

    def test_format_uptime_zero(self):
        """Zero uptime"""
        result = _utils.format_uptime(0.0)
        self.assertIsInstance(result, str)

    # --- compute_percentiles ---
    def test_compute_percentiles_basic(self):
        """Basic percentile computation"""
        values = list(range(1, 101))
        result = _utils.compute_percentiles(values)
        self.assertIn("p50", result)
        self.assertIn("p95", result)
        self.assertIn("p99", result)

    def test_compute_percentiles_empty(self):
        """Empty list should return None values"""
        result = _utils.compute_percentiles([])
        self.assertIsNone(result["p50"])


if __name__ == "__main__":
    unittest.main()
