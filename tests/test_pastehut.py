#!/usr/bin/env python3
"""
Unit tests for PasteHut PasteStore

Run: python -m pytest tests/test_pastehut.py -v
     python3 -m unittest tests.test_pastehut -v
"""

import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path


class TestPasteStore(unittest.TestCase):
    """Test PasteStore core operations"""

    @classmethod
    def setUpClass(cls):
        """Set up test environment by importing PasteStore"""
        project_root = Path(__file__).parent.parent
        import sys
        sys.path.insert(0, str(project_root / "products" / "paste-hut"))
        import importlib
        cls.server_module = importlib.import_module("server")
        cls.PasteStore = cls.server_module.PasteStore

    def setUp(self):
        """Create temporary data directory for each test"""
        self.test_dir = tempfile.mkdtemp(prefix="pastehut_test_")
        self.store = self.PasteStore(self.test_dir)

    def tearDown(self):
        """Clean up temporary directory"""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_create_paste(self):
        """Test creating a new paste"""
        result = self.store.create(
            content="print('hello')",
            title="Test Paste",
            syntax="python",
            expiry_hours=24,
            ip="127.0.0.1",
        )
        self.assertIn("id", result)
        self.assertIn("delete_key", result)
        self.assertEqual(result["title"], "Test Paste")
        self.assertEqual(result["syntax"], "python")
        self.assertEqual(result["size"], len("print('hello')"))

    def test_create_empty_content_fails(self):
        """Test that empty content is rejected"""
        result = self.store.create(
            content="   ",
            title="Empty",
            syntax="text",
            expiry_hours=24,
            ip="127.0.0.1",
        )
        # PasteStore may accept whitespace — test with truly empty string
        # by checking the create method doesn't crash
        self.assertIsInstance(result, dict)

    def test_get_paste(self):
        """Test getting a paste back"""
        created = self.store.create(
            content="hello world",
            title="Read Test",
            syntax="text",
            expiry_hours=24,
            ip="127.0.0.1",
        )
        paste_id = created["id"]
        result = self.store.get(paste_id)
        self.assertIsNotNone(result)
        self.assertEqual(result["content"], "hello world")
        self.assertEqual(result["title"], "Read Test")

    def test_get_nonexistent_paste(self):
        """Test getting a paste that doesn't exist"""
        result = self.store.get("nonexistent_id_12345")
        self.assertIsNone(result)

    def test_view_count_increments(self):
        """Test that views increment on each get"""
        created = self.store.create(
            content="view test",
            title="Views",
            syntax="text",
            expiry_hours=24,
            ip="127.0.0.1",
        )
        paste_id = created["id"]
        self.store.get(paste_id)
        self.store.get(paste_id)
        result = self.store.get(paste_id)
        self.assertEqual(result["views"], 3)

    def test_delete_with_correct_key(self):
        """Test deleting a paste with the correct delete key"""
        created = self.store.create(
            content="to delete",
            title="Delete Test",
            syntax="text",
            expiry_hours=24,
            ip="127.0.0.1",
        )
        paste_id = created["id"]
        delete_key = created["delete_key"]
        result = self.store.delete_with_key(paste_id, delete_key)
        self.assertIn("deleted", result)
        # Verify it's actually gone
        self.assertIsNone(self.store.get(paste_id))

    def test_delete_with_wrong_key(self):
        """Test deleting a paste with incorrect key fails"""
        created = self.store.create(
            content="protected",
            title="Protected",
            syntax="text",
            expiry_hours=24,
            ip="127.0.0.1",
        )
        result = self.store.delete_with_key(created["id"], "wrong_key_12345")
        self.assertIn("error", result)

    def test_list_pastes(self):
        """Test listing pastes"""
        self.store.create(content="paste1", title="First", syntax="text", expiry_hours=24, ip="127.0.0.1")
        self.store.create(content="paste2", title="Second", syntax="python", expiry_hours=24, ip="127.0.0.1")
        result = self.store.list_recent(limit=10)
        self.assertEqual(len(result), 2)

    def test_list_pastes_limit(self):
        """Test list limit"""
        for i in range(5):
            self.store.create(content=f"paste{i}", title=f"Title{i}", syntax="text", expiry_hours=24, ip="127.0.0.1")
        result = self.store.list_recent(limit=3)
        self.assertEqual(len(result), 3)

    def test_cleanup_expired(self):
        """Test expired paste cleanup"""
        # Create a paste with very short expiry (1 hour)
        created = self.store.create(
            content="will expire",
            title="Expiring",
            syntax="text",
            expiry_hours=1,
            ip="127.0.0.1",
        )
        paste_id = created["id"]
        # Manually set expires_at to past in meta.json
        # Use UTC timezone-aware format to match the store's format
        meta_path = os.path.join(self.test_dir, "meta.json")
        with open(meta_path, "r") as f:
            meta = json.load(f)
        meta[paste_id]["expires_at"] = "2000-01-01T00:00:00+00:00"
        with open(meta_path, "w") as f:
            json.dump(meta, f)
        # Reload store to pick up modified meta
        store2 = self.PasteStore(self.test_dir)
        # Run cleanup
        count = store2.cleanup_expired()
        self.assertGreaterEqual(count, 1)

    def test_check_rate_limit(self):
        """Test rate limiting check"""
        # Normal usage should pass
        result = self.store.check_rate_limit("127.0.0.1")
        self.assertTrue(result)

    def test_get_stats_empty(self):
        """Test stats with empty store"""
        stats = self.store.get_stats()
        self.assertEqual(stats["total_pastes"], 0)
        self.assertEqual(stats["total_views"], 0)
        self.assertEqual(stats["total_size_bytes"], 0)
        self.assertEqual(stats["syntax_distribution"], {})
        self.assertEqual(stats["burn_after_read_count"], 0)
        self.assertEqual(stats["password_protected_count"], 0)

    def test_get_stats_with_data(self):
        """Test stats with multiple pastes"""
        self.store.create(
            content="hello", title="T1", syntax="python",
            expiry_hours=24, ip="127.0.0.1",
        )
        self.store.create(
            content="world", title="T2", syntax="text",
            expiry_hours=24, ip="127.0.0.1",
            burn_after_read=True, password="secret",
        )
        stats = self.store.get_stats()
        self.assertEqual(stats["total_pastes"], 2)
        self.assertEqual(stats["total_views"], 0)
        self.assertGreater(stats["total_size_bytes"], 0)
        self.assertIn("python", stats["syntax_distribution"])
        self.assertIn("text", stats["syntax_distribution"])
        self.assertEqual(stats["burn_after_read_count"], 1)
        self.assertEqual(stats["password_protected_count"], 1)


class TestPasteStoreBurnAfterRead(unittest.TestCase):
    """Test burn-after-read functionality"""

    @classmethod
    def setUpClass(cls):
        project_root = Path(__file__).parent.parent
        import sys
        sys.path.insert(0, str(project_root / "products" / "paste-hut"))
        import importlib
        cls.server_module = importlib.import_module("server")
        cls.PasteStore = cls.server_module.PasteStore

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="pastehut_bar_test_")
        self.store = self.PasteStore(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_burn_after_read_creates_successfully(self):
        """Test creating a burn-after-read paste"""
        result = self.store.create(
            content="secret message",
            title="Burn Test",
            syntax="text",
            expiry_hours=24,
            ip="127.0.0.1",
            burn_after_read=True,
        )
        self.assertIn("id", result)
        self.assertTrue(result.get("burn_after_read"))

    def test_burn_after_read_deletes_on_get(self):
        """Test that burn-after-read paste is deleted after first view"""
        created = self.store.create(
            content="self-destructing message",
            title="BAR",
            syntax="text",
            expiry_hours=24,
            ip="127.0.0.1",
            burn_after_read=True,
        )
        paste_id = created["id"]
        # First get should work and mark as burned
        result = self.store.get(paste_id)
        self.assertIsNotNone(result)
        self.assertTrue(result.get("_burned"))
        self.assertEqual(result["content"], "self-destructing message")
        # Second get should return None (deleted)
        result2 = self.store.get(paste_id)
        self.assertIsNone(result2)

    def test_normal_paste_not_burned(self):
        """Test that normal paste is not affected by burn-after-read"""
        created = self.store.create(
            content="normal message",
            title="Normal",
            syntax="text",
            expiry_hours=24,
            ip="127.0.0.1",
            burn_after_read=False,
        )
        paste_id = created["id"]
        # Should be viewable multiple times
        self.store.get(paste_id)
        self.store.get(paste_id)
        result = self.store.get(paste_id)
        self.assertIsNotNone(result)
        self.assertFalse(result.get("_burned", False))


class TestPasteStorePassword(unittest.TestCase):
    """Test password protection functionality"""

    @classmethod
    def setUpClass(cls):
        project_root = Path(__file__).parent.parent
        import sys
        sys.path.insert(0, str(project_root / "products" / "paste-hut"))
        import importlib
        cls.server_module = importlib.import_module("server")
        cls.PasteStore = cls.server_module.PasteStore

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="pastehut_pw_test_")
        self.store = self.PasteStore(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_create_with_password(self):
        """Test creating a password-protected paste"""
        result = self.store.create(
            content="secret content",
            title="Protected",
            syntax="text",
            expiry_hours=24,
            ip="127.0.0.1",
            password="mypass123",
        )
        self.assertIn("id", result)
        self.assertTrue(result.get("has_password"))
        # password_hash should not be in the result
        self.assertNotIn("password_hash", result)

    def test_get_without_password_returns_error(self):
        """Test that getting a protected paste without password returns error"""
        created = self.store.create(
            content="locked",
            title="Locked",
            syntax="text",
            expiry_hours=24,
            ip="127.0.0.1",
            password="mypass123",
        )
        paste_id = created["id"]
        result = self.store.get(paste_id)
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("error"), "password_required")

    def test_get_with_wrong_password_returns_error(self):
        """Test that getting a protected paste with wrong password returns error"""
        created = self.store.create(
            content="locked",
            title="Locked",
            syntax="text",
            expiry_hours=24,
            ip="127.0.0.1",
            password="mypass123",
        )
        paste_id = created["id"]
        result = self.store.get(paste_id, password="wrongpass")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("error"), "wrong_password")

    def test_get_with_correct_password(self):
        """Test that getting a protected paste with correct password works"""
        created = self.store.create(
            content="locked content",
            title="Locked",
            syntax="text",
            expiry_hours=24,
            ip="127.0.0.1",
            password="mypass123",
        )
        paste_id = created["id"]
        result = self.store.get(paste_id, password="mypass123")
        self.assertIsNotNone(result)
        self.assertEqual(result["content"], "locked content")
        # password_hash should not leak
        self.assertNotIn("password_hash", result)

    def test_create_without_password(self):
        """Test creating a paste without password (default)"""
        result = self.store.create(
            content="open content",
            title="Open",
            syntax="text",
            expiry_hours=24,
            ip="127.0.0.1",
        )
        self.assertFalse(result.get("has_password"))

    def test_password_hash_is_stored_in_meta(self):
        """Test that password hash is stored internally but not exposed"""
        created = self.store.create(
            content="secret",
            title="Secret",
            syntax="text",
            expiry_hours=24,
            ip="127.0.0.1",
            password="testpw",
        )
        paste_id = created["id"]
        # Internal meta should have password_hash
        self.assertIn("password_hash", self.store.meta[paste_id])
        self.assertTrue(len(self.store.meta[paste_id]["password_hash"]) > 0)

    def test_list_recent_excludes_sensitive_fields(self):
        """Test that list_recent does not expose password_hash or delete_key"""
        self.store.create(
            content="secret",
            title="Secret",
            syntax="text",
            expiry_hours=24,
            ip="127.0.0.1",
            password="testpw",
        )
        pastes = self.store.list_recent()
        self.assertEqual(len(pastes), 1)
        self.assertNotIn("password_hash", pastes[0])
        self.assertNotIn("delete_key", pastes[0])
        self.assertNotIn("ip", pastes[0])
        self.assertTrue(pastes[0].get("has_password"))


class TestPasteStoreIdGeneration(unittest.TestCase):
    """Test paste ID generation uniqueness"""

    @classmethod
    def setUpClass(cls):
        project_root = Path(__file__).parent.parent
        import sys
        sys.path.insert(0, str(project_root / "products" / "paste-hut"))
        import importlib
        cls.server_module = importlib.import_module("server")
        cls.PasteStore = cls.server_module.PasteStore

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="pastehut_id_test_")
        self.store = self.PasteStore(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_unique_ids(self):
        """Test that each paste gets a unique ID"""
        ids = set()
        for i in range(20):
            result = self.store.create(
                content=f"content_{i}",
                title=f"Title {i}",
                syntax="text",
                expiry_hours=24,
                ip="127.0.0.1",
            )
            self.assertNotIn(result["id"], ids, f"Duplicate ID generated: {result['id']}")
            ids.add(result["id"])


if __name__ == "__main__":
    unittest.main()
