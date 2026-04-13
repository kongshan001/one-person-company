#!/usr/bin/env python3
"""
Unit tests for config module and utils module

Run: python3 -m unittest tests.test_config_and_utils -v
"""

import os
import sys
import unittest
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import utils as _utils
from config import PasteHutConfig, PingBotConfig, IconForgeConfig


class TestPasteHutConfig(unittest.TestCase):
    """Test PasteHut configuration"""

    def test_data_dir_is_expanded(self):
        """Data dir should have ~ expanded"""
        self.assertFalse(PasteHutConfig.DATA_DIR.startswith("~"))

    def test_max_paste_size_positive(self):
        """Max paste size should be positive"""
        self.assertGreater(PasteHutConfig.MAX_PASTE_SIZE, 0)

    def test_expiry_bounds(self):
        """Default expiry should be <= max expiry"""
        self.assertLessEqual(PasteHutConfig.DEFAULT_EXPIRY_HOURS, PasteHutConfig.MAX_EXPIRY_HOURS)

    def test_rate_limit_values(self):
        """Rate limit values should be positive"""
        self.assertGreater(PasteHutConfig.RATE_LIMIT_WINDOW, 0)
        self.assertGreater(PasteHutConfig.RATE_LIMIT_MAX, 0)

    def test_allowed_syntaxes_is_frozenset(self):
        """ALLOWED_SYNTAXES should be a frozenset"""
        self.assertIsInstance(PasteHutConfig.ALLOWED_SYNTAXES, frozenset)

    def test_allowed_syntaxes_includes_common(self):
        """Common syntaxes should be present"""
        for s in ["text", "python", "javascript", "html", "json"]:
            self.assertIn(s, PasteHutConfig.ALLOWED_SYNTAXES)

    def test_default_port(self):
        """Default port should be a valid port number"""
        self.assertGreaterEqual(PasteHutConfig.DEFAULT_PORT, 1)
        self.assertLessEqual(PasteHutConfig.DEFAULT_PORT, 65535)

    def test_views_flush_config(self):
        """Views flush interval and seconds should be positive"""
        self.assertGreater(PasteHutConfig.VIEWS_FLUSH_INTERVAL, 0)
        self.assertGreater(PasteHutConfig.VIEWS_FLUSH_SECONDS, 0)


class TestPingBotConfig(unittest.TestCase):
    """Test PingBot configuration"""

    def test_db_path_is_expanded(self):
        """DB path should have ~ expanded"""
        self.assertFalse(PingBotConfig.DB_PATH.startswith("~"))

    def test_intervals_positive(self):
        """Intervals should be positive"""
        self.assertGreater(PingBotConfig.CHECK_INTERVAL, 0)
        self.assertGreater(PingBotConfig.REQUEST_TIMEOUT, 0)

    def test_max_history_days(self):
        """Max history days should be reasonable"""
        self.assertGreater(PingBotConfig.MAX_HISTORY_DAYS, 0)
        self.assertLessEqual(PingBotConfig.MAX_HISTORY_DAYS, 365)

    def test_default_port(self):
        """Default port should differ from PasteHut"""
        self.assertNotEqual(PingBotConfig.DEFAULT_PORT, PasteHutConfig.DEFAULT_PORT)


class TestIconForgeConfig(unittest.TestCase):
    """Test IconForge configuration"""

    def test_pollinations_url_has_placeholders(self):
        """Pollinations URL should contain required placeholders"""
        self.assertIn("{prompt}", IconForgeConfig.POLLINATIONS_URL)
        self.assertIn("{w}", IconForgeConfig.POLLINATIONS_URL)
        self.assertIn("{h}", IconForgeConfig.POLLINATIONS_URL)

    def test_style_keywords_non_empty(self):
        """Style keywords should not be empty"""
        self.assertGreater(len(IconForgeConfig.STYLE_KEYWORDS), 0)

    def test_sizes_includes_common(self):
        """Sizes should include 64, 128, 256, 512"""
        for size in [64, 128, 256, 512]:
            self.assertIn(size, IconForgeConfig.SIZES)

    def test_default_size_in_sizes(self):
        """Default size should be in SIZES list"""
        self.assertIn(IconForgeConfig.DEFAULT_SIZE, IconForgeConfig.SIZES)

    def test_type_keywords_non_empty(self):
        """Type keywords should not be empty"""
        self.assertGreater(len(IconForgeConfig.TYPE_KEYWORDS), 0)

    def test_max_retries_reasonable(self):
        """Max retries should be reasonable"""
        self.assertGreaterEqual(IconForgeConfig.MAX_RETRIES, 0)
        self.assertLessEqual(IconForgeConfig.MAX_RETRIES, 10)


class TestUtils(unittest.TestCase):
    """Test shared utils module"""

    # --- sanitize_id ---

    def test_sanitize_id_valid(self):
        """Valid hex ID should pass"""
        self.assertEqual(_utils.sanitize_id("abc123"), "abc123")

    def test_sanitize_id_uppercase_rejected(self):
        """Uppercase hex should be rejected"""
        self.assertIsNone(_utils.sanitize_id("ABC123"))

    def test_sanitize_id_special_chars_rejected(self):
        """Special characters should be rejected"""
        self.assertIsNone(_utils.sanitize_id("abc../123"))

    def test_sanitize_id_empty(self):
        """Empty string should be rejected"""
        self.assertIsNone(_utils.sanitize_id(""))

    def test_sanitize_id_too_long(self):
        """Oversized ID should be rejected"""
        self.assertIsNone(_utils.sanitize_id("a" * 65))

    def test_sanitize_id_max_length(self):
        """ID at max length should be accepted"""
        self.assertEqual(_utils.sanitize_id("a" * 64), "a" * 64)

    # --- compute_percentiles ---

    def test_compute_percentiles_empty(self):
        """Empty list should return None for all percentiles"""
        result = _utils.compute_percentiles([])
        self.assertIsNone(result["p50"])
        self.assertIsNone(result["p95"])
        self.assertIsNone(result["p99"])

    def test_compute_percentiles_single_value(self):
        """Single value should be all percentiles"""
        result = _utils.compute_percentiles([100])
        self.assertEqual(result["p50"], 100)
        self.assertEqual(result["p95"], 100)
        self.assertEqual(result["p99"], 100)

    def test_compute_percentiles_typical(self):
        """Typical percentile computation"""
        values = list(range(1, 101))  # 1..100
        result = _utils.compute_percentiles(values)
        # p50 for 1..100 with int(n*0.50) = index 50 -> value 51
        self.assertIn(result["p50"], [50, 51])
        self.assertGreaterEqual(result["p95"], 94)
        self.assertGreaterEqual(result["p99"], 98)

    def test_compute_percentiles_custom(self):
        """Custom percentile list"""
        result = _utils.compute_percentiles([10, 20, 30], percentiles=[50])
        self.assertIn("p50", result)
        self.assertNotIn("p95", result)

    # --- format_uptime ---

    def test_format_uptime_100(self):
        """100% uptime formatting"""
        self.assertEqual(_utils.format_uptime(100.0), "100.00%")

    def test_format_uptime_99_95(self):
        """99.95% uptime formatting"""
        self.assertEqual(_utils.format_uptime(99.95), "99.95%")

    def test_format_uptime_zero(self):
        """0% uptime formatting"""
        self.assertEqual(_utils.format_uptime(0.0), "0.00%")


class TestDeployScript(unittest.TestCase):
    """Test deploy script utilities (non-destructive)"""

    @classmethod
    def setUpClass(cls):
        project_root = Path(__file__).parent.parent
        sys.path.insert(0, str(project_root / "infrastructure" / "deploy"))
        import importlib
        cls.mod = importlib.import_module("deploy")

    def test_services_dict_structure(self):
        """SERVICES dict should have required keys for each service"""
        for name, config in self.mod.SERVICES.items():
            self.assertIn("script", config, f"{name} missing 'script'")
            self.assertIn("type", config, f"{name} missing 'type'")
            if config["type"] == "http":
                self.assertIn("port", config, f"{name} (http) missing 'port'")

    def test_is_running_with_invalid_pid(self):
        """is_running should return False for non-existent PID"""
        self.assertFalse(self.mod.is_running(999999999))

    def test_is_running_with_none(self):
        """is_running should return False for None PID"""
        self.assertFalse(self.mod.is_running(None))

    def test_get_pid_returns_none_for_missing(self):
        """get_pid should return None for non-existent service"""
        result = self.mod.get_pid("nonexistent_service_xyz")
        self.assertIsNone(result)

    def test_health_check_timeout_positive(self):
        """Health check timeout should be positive"""
        self.assertGreater(self.mod.HEALTH_CHECK_TIMEOUT, 0)

    def test_pid_dir_path_is_absolute(self):
        """PID_DIR should be an absolute path"""
        self.assertTrue(self.mod.PID_DIR.is_absolute())


if __name__ == "__main__":
    unittest.main()
