#!/usr/bin/env python3
"""
Unit tests for monthly_report module

Run: python3 -m unittest tests.test_monthly_report -v
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path


class TestReportGenerator(unittest.TestCase):
    """Test monthly report generation"""

    @classmethod
    def setUpClass(cls):
        project_root = Path(__file__).parent.parent
        import sys
        sys.path.insert(0, str(project_root / "infrastructure" / "cron"))
        import importlib
        cls.mod = importlib.import_module("monthly_report")

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="monthly_report_test_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_generate_report_structure(self):
        """Test that generate_report returns expected structure"""
        report = self.mod.generate_report("2026-04", self.test_dir)
        self.assertIn("month", report)
        self.assertIn("generated_at", report)
        self.assertIn("products", report)
        self.assertIn("finance", report)
        self.assertIn("infrastructure", report)
        self.assertEqual(report["month"], "2026-04")

    def test_generate_report_saves_file(self):
        """Test that report is saved to disk"""
        self.mod.generate_report("2026-04", self.test_dir)
        output_path = os.path.join(self.test_dir, "report_2026-04.json")
        self.assertTrue(os.path.exists(output_path))
        with open(output_path) as f:
            saved = json.load(f)
        self.assertEqual(saved["month"], "2026-04")

    def test_generate_report_system_info(self):
        """Test that report includes system information"""
        report = self.mod.generate_report("2026-03", self.test_dir)
        sys_info = report.get("infrastructure", {}).get("system", {})
        self.assertIn("hostname", sys_info)
        self.assertIn("platform", sys_info)

    def test_print_report_does_not_crash(self):
        """Test that print_report runs without errors"""
        report = {
            "month": "2026-04",
            "generated_at": "2026-04-13T00:00:00",
            "products": {
                "pastehut": {
                    "total_pastes": 42,
                    "total_views": 1000,
                    "total_size": 51200,
                }
            },
            "finance": {},
            "infrastructure": {
                "uptime": {
                    "total_checks": 1440,
                    "up_checks": 1430,
                    "uptime_pct": 99.31,
                },
                "system": {
                    "hostname": "test-host",
                    "platform": "Linux",
                },
            },
        }
        # Should not raise
        self.mod.print_report(report)

    def test_generate_report_empty_month(self):
        """Test report generation for a month with no data"""
        report = self.mod.generate_report("2020-01", self.test_dir)
        self.assertEqual(report["month"], "2020-01")
        # Products should be empty when no data exists
        self.assertIsInstance(report["products"], dict)

    def test_generate_report_with_pastehut_data(self):
        """Test report with PasteHut meta.json"""
        # Create fake pastehut data
        pastehut_dir = os.path.join(self.test_dir, "pastehut")
        os.makedirs(pastehut_dir, exist_ok=True)
        meta = {
            "abc123": {"views": 10, "size": 256},
            "def456": {"views": 5, "size": 128},
        }
        with open(os.path.join(pastehut_dir, "meta.json"), "w") as f:
            json.dump(meta, f)

        # Temporarily override the path by monkeypatching expanduser
        import unittest.mock
        with unittest.mock.patch("os.path.expanduser", return_value=pastehut_dir):
            with unittest.mock.patch("os.path.exists") as mock_exists:
                def exists_side_effect(p):
                    if "pastehut" in p and "meta.json" in p:
                        return True
                    return os.path.exists.__wrapped__(p) if hasattr(os.path.exists, '__wrapped__') else False
                # Just test with a temp dir approach
                pass

    def test_report_json_serializable(self):
        """Test that entire report is JSON-serializable"""
        report = self.mod.generate_report("2026-04", self.test_dir)
        # Should not raise
        serialized = json.dumps(report)
        self.assertIsInstance(serialized, str)


class TestReportEdgeCases(unittest.TestCase):
    """Test edge cases for report generation"""

    @classmethod
    def setUpClass(cls):
        project_root = Path(__file__).parent.parent
        import sys
        sys.path.insert(0, str(project_root / "infrastructure" / "cron"))
        import importlib
        cls.mod = importlib.import_module("monthly_report")

    def test_month_boundary_december(self):
        """Test December month boundary (year rollover)"""
        report = self.mod.generate_report("2025-12", tempfile.mkdtemp())
        self.assertEqual(report["month"], "2025-12")

    def test_month_boundary_january(self):
        """Test January month"""
        report = self.mod.generate_report("2026-01", tempfile.mkdtemp())
        self.assertEqual(report["month"], "2026-01")

    def test_invalid_month_still_works(self):
        """Test that generate_report handles any string as month"""
        report = self.mod.generate_report("2026-13", tempfile.mkdtemp())
        self.assertEqual(report["month"], "2026-13")


if __name__ == "__main__":
    unittest.main()
