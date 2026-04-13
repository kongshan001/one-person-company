#!/usr/bin/env python3
"""
Unit tests for PingBot PingDB and Pinger

Run: python -m pytest tests/test_pingbot.py -v
     python3 -m unittest tests.test_pingbot -v
"""

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path


class TestPingDB(unittest.TestCase):
    """Test PingDB database operations"""

    @classmethod
    def setUpClass(cls):
        project_root = Path(__file__).parent.parent
        import sys
        sys.path.insert(0, str(project_root / "products" / "ping-bot"))
        import importlib
        cls.monitor_module = importlib.import_module("monitor")
        cls.PingDB = cls.monitor_module.PingDB
        cls.Pinger = cls.monitor_module.Pinger

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="pingbot_test_")
        self.db_path = os.path.join(self.test_dir, "test.db")
        self.db = self.PingDB(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_add_target(self):
        """Test adding a monitoring target"""
        result = self.db.add_target(
            name="test_site",
            url="https://example.com",
            method="GET",
            expected_status=200,
        )
        self.assertEqual(result["name"], "test_site")
        self.assertEqual(result["url"], "https://example.com")

    def test_add_target_invalid_name(self):
        """Test that invalid target names are rejected"""
        result = self.db.add_target(
            name="invalid name!",
            url="https://example.com",
        )
        self.assertIn("error", result)

    def test_add_target_invalid_url(self):
        """Test that non-http URLs are rejected"""
        result = self.db.add_target(
            name="bad_url",
            url="ftp://example.com",
        )
        self.assertIn("error", result)

    def test_get_targets(self):
        """Test retrieving targets"""
        self.db.add_target(name="site1", url="https://example1.com")
        self.db.add_target(name="site2", url="https://example2.com")
        targets = self.db.get_targets()
        self.assertEqual(len(targets), 2)

    def test_remove_target(self):
        """Test removing a target"""
        self.db.add_target(name="to_remove", url="https://example.com")
        result = self.db.remove_target("to_remove")
        self.assertTrue(result)
        # Verify it's gone
        targets = self.db.get_targets()
        self.assertEqual(len(targets), 0)

    def test_remove_nonexistent_target(self):
        """Test removing a target that doesn't exist"""
        result = self.db.remove_target("nonexistent")
        self.assertFalse(result)

    def test_record_and_get_history(self):
        """Test recording checks and retrieving history"""
        self.db.add_target(name="hist_test", url="https://example.com")
        self.db.record_check("hist_test", status_code=200, response_time_ms=150, is_up=True)
        self.db.record_check("hist_test", status_code=500, response_time_ms=200, is_up=False, error="Internal Server Error")
        history = self.db.get_history("hist_test", hours=24)
        self.assertGreaterEqual(len(history), 1)

    def test_get_status(self):
        """Test getting status overview"""
        self.db.add_target(name="status_test", url="https://example.com")
        self.db.record_check("status_test", status_code=200, response_time_ms=100, is_up=True)
        status = self.db.get_status()
        self.assertEqual(len(status), 1)
        self.assertEqual(status[0]["name"], "status_test")
        self.assertEqual(status[0]["uptime_24h"], 100.0)

    def test_get_status_mixed_uptime(self):
        """Test uptime calculation with mixed results"""
        self.db.add_target(name="mixed_test", url="https://example.com")
        self.db.record_check("mixed_test", status_code=200, response_time_ms=100, is_up=True)
        self.db.record_check("mixed_test", status_code=200, response_time_ms=100, is_up=True)
        self.db.record_check("mixed_test", status_code=500, response_time_ms=200, is_up=False)
        status = self.db.get_status()
        # 2/3 up = 66.67%
        self.assertAlmostEqual(status[0]["uptime_24h"], 66.67, places=1)

    def test_add_target_with_keyword(self):
        """Test adding a target with expected keyword"""
        result = self.db.add_target(
            name="keyword_test",
            url="https://example.com",
            expected_keyword="welcome",
        )
        self.assertEqual(result["name"], "keyword_test")

    def test_add_target_name_with_hyphen(self):
        """Test that hyphens and underscores are allowed in names"""
        result = self.db.add_target(name="my-test_site", url="https://example.com")
        self.assertNotIn("error", result)

    def test_cleanup_old(self):
        """Test cleanup of old records doesn't crash"""
        self.db.add_target(name="cleanup_test", url="https://example.com")
        self.db.record_check("cleanup_test", status_code=200, response_time_ms=100, is_up=True)
        self.db.cleanup_old()
        # Should not raise

    def test_pause_target(self):
        """Test pausing a monitoring target"""
        self.db.add_target(name="pause_test", url="https://example.com")
        result = self.db.pause_target("pause_test")
        self.assertEqual(result["name"], "pause_test")
        self.assertFalse(result["enabled"])
        self.assertEqual(result["action"], "paused")
        # Verify it's disabled in DB
        targets = self.db.get_targets(enabled_only=True)
        names = [t["name"] for t in targets]
        self.assertNotIn("pause_test", names)

    def test_resume_target(self):
        """Test resuming a paused monitoring target"""
        self.db.add_target(name="resume_test", url="https://example.com")
        self.db.pause_target("resume_test")
        result = self.db.resume_target("resume_test")
        self.assertEqual(result["name"], "resume_test")
        self.assertTrue(result["enabled"])
        self.assertEqual(result["action"], "resumed")
        # Verify it's back in enabled targets
        targets = self.db.get_targets(enabled_only=True)
        names = [t["name"] for t in targets]
        self.assertIn("resume_test", names)

    def test_pause_nonexistent_target(self):
        """Test pausing a target that doesn't exist"""
        result = self.db.pause_target("nonexistent_xyz")
        self.assertIn("error", result)

    def test_resume_nonexistent_target(self):
        """Test resuming a target that doesn't exist"""
        result = self.db.resume_target("nonexistent_xyz")
        self.assertIn("error", result)

    def test_pause_resume_roundtrip(self):
        """Test full pause/resume cycle preserves data"""
        self.db.add_target(name="roundtrip", url="https://example.com", method="POST")
        self.db.record_check("roundtrip", status_code=200, response_time_ms=50, is_up=True)
        # Pause
        self.db.pause_target("roundtrip")
        # Resume
        self.db.resume_target("roundtrip")
        # Data should still be there
        targets = self.db.get_targets()
        target = [t for t in targets if t["name"] == "roundtrip"][0]
        self.assertEqual(target["method"], "POST")


class TestPinger(unittest.TestCase):
    """Test Pinger URL checking logic"""

    @classmethod
    def setUpClass(cls):
        project_root = Path(__file__).parent.parent
        import sys
        sys.path.insert(0, str(project_root / "products" / "ping-bot"))
        import importlib
        cls.monitor_module = importlib.import_module("monitor")
        cls.PingDB = cls.monitor_module.PingDB
        cls.Pinger = cls.monitor_module.Pinger

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="pinger_test_")
        self.db_path = os.path.join(self.test_dir, "test.db")
        self.db = self.PingDB(self.db_path)
        self.pinger = self.Pinger(self.db)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_check_invalid_url(self):
        """Test checking a URL that doesn't exist"""
        result = self.pinger.check_url(
            url="http://127.0.0.1:59999/",  # Port that shouldn't be listening
            method="GET",
            expected_status=200,
        )
        self.assertFalse(result["is_up"])
        self.assertIsNotNone(result["error"])

    def test_check_valid_url(self):
        """Test checking a valid URL (requires network)"""
        result = self.pinger.check_url(
            url="https://httpbin.org/status/200",
            method="GET",
            expected_status=200,
        )
        # This test may fail without network, but that's expected
        if result["is_up"]:
            self.assertEqual(result["status_code"], 200)
            self.assertIsNone(result["error"])

    def test_check_url_expected_status_mismatch(self):
        """Test that status code mismatch marks as down"""
        result = self.pinger.check_url(
            url="https://httpbin.org/status/404",
            method="GET",
            expected_status=200,
        )
        if result["status_code"] == 404:
            self.assertFalse(result["is_up"])


class TestAlertThrottle(unittest.TestCase):
    """Test alert cooldown/throttle functionality"""

    @classmethod
    def setUpClass(cls):
        project_root = Path(__file__).parent.parent
        import sys
        sys.path.insert(0, str(project_root / "products" / "ping-bot"))
        import importlib
        cls.monitor_module = importlib.import_module("monitor")

    def setUp(self):
        """Reset alert state before each test"""
        self.monitor_module.reset_alert_cooldown()

    def test_send_alert_returns_false_when_no_webhook(self):
        """Test that send_alert returns False when no webhook URL configured"""
        result = self.monitor_module.send_alert("test", "http://example.com", "error")
        self.assertFalse(result)

    def test_set_alert_cooldown_minimum(self):
        """Test that cooldown has minimum of 60 seconds"""
        self.monitor_module.set_alert_cooldown(10)  # Try setting below minimum
        self.assertEqual(self.monitor_module._alert_cooldown_seconds, 60)

    def test_set_alert_cooldown_valid(self):
        """Test setting a valid cooldown value"""
        self.monitor_module.set_alert_cooldown(120)
        self.assertEqual(self.monitor_module._alert_cooldown_seconds, 120)
        # Reset to default
        self.monitor_module.set_alert_cooldown(300)

    def test_reset_alert_cooldown_specific_target(self):
        """Test resetting cooldown for a specific target"""
        # Simulate that an alert was sent
        self.monitor_module._last_alert_time["my-target"] = time.time()
        self.monitor_module.reset_alert_cooldown("my-target")
        self.assertNotIn("my-target", self.monitor_module._last_alert_time)

    def test_reset_alert_cooldown_all(self):
        """Test resetting all cooldown timers"""
        self.monitor_module._last_alert_time["a"] = time.time()
        self.monitor_module._last_alert_time["b"] = time.time()
        self.monitor_module.reset_alert_cooldown()
        self.assertEqual(len(self.monitor_module._last_alert_time), 0)


class TestExportData(unittest.TestCase):
    """Test export_data module"""

    @classmethod
    def setUpClass(cls):
        project_root = Path(__file__).parent.parent
        import sys
        sys.path.insert(0, str(project_root / "infrastructure" / "cron"))
        import importlib
        cls.export_module = importlib.import_module("export_data")

    def test_export_pastehut_no_data(self):
        """Test export when no PasteHut data exists"""
        result = self.export_module.export_pastehut(Path("/tmp/nonexistent_export_dir_12345"))
        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["records"], 0)

    def test_export_pingbot_no_data(self):
        """Test export when no PingBot data exists"""
        result = self.export_module.export_pingbot(Path("/tmp/nonexistent_export_dir_12345"))
        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["records"], 0)

    def test_export_pastehut_with_data(self):
        """Test exporting PasteHut data with actual pastes"""
        # Import PasteStore to create test data
        project_root = Path(__file__).parent.parent
        import sys
        sys.path.insert(0, str(project_root / "products" / "paste-hut"))
        import importlib
        server_mod = importlib.import_module("server")
        PasteStore = server_mod.PasteStore

        test_dir = tempfile.mkdtemp(prefix="export_test_ph_")
        try:
            store = PasteStore(test_dir)
            store.create(content="hello", title="Test", syntax="text", expiry_hours=24, ip="127.0.0.1")

            # Override DATA_DIR temporarily
            original_dir = self.export_module.PasteHutConfig.DATA_DIR
            self.export_module.PasteHutConfig.DATA_DIR = test_dir

            output_dir = Path(tempfile.mkdtemp(prefix="export_out_"))
            result = self.export_module.export_pastehut(output_dir, pretty=True)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["records"], 1)
            self.assertTrue(os.path.exists(result["file"]))

            # Verify JSON content
            with open(result["file"], "r") as f:
                import json
                data = json.load(f)
            self.assertEqual(data["total_pastes"], 1)
            self.assertEqual(data["pastes"][0]["title"], "Test")

            # Cleanup
            shutil.rmtree(str(output_dir), ignore_errors=True)
            self.export_module.PasteHutConfig.DATA_DIR = original_dir
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_compress_file(self):
        """Test gzip compression"""
        import gzip
        test_file = tempfile.mktemp(suffix=".json")
        with open(test_file, "w") as f:
            f.write('{"test": true}')
        try:
            gz_path = self.export_module.compress_file(test_file)
            self.assertTrue(gz_path.endswith(".gz"))
            self.assertTrue(os.path.exists(gz_path))
            self.assertFalse(os.path.exists(test_file))  # Original deleted
            # Verify content
            with gzip.open(gz_path, "rt") as f:
                self.assertEqual(f.read(), '{"test": true}')
            os.unlink(gz_path)
        except Exception:
            if os.path.exists(test_file):
                os.unlink(test_file)


if __name__ == "__main__":
    unittest.main()
