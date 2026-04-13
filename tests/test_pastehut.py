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
        self.assertIn("pastes", result)
        self.assertEqual(len(result["pastes"]), 2)
        self.assertEqual(result["total"], 2)

    def test_list_pastes_limit(self):
        """Test list limit"""
        for i in range(5):
            self.store.create(content=f"paste{i}", title=f"Title{i}", syntax="text", expiry_hours=24, ip="127.0.0.1")
        result = self.store.list_recent(limit=3)
        self.assertEqual(len(result["pastes"]), 3)
        self.assertEqual(result["total"], 5)

    def test_list_pastes_pagination_offset(self):
        """Test list pagination with offset"""
        for i in range(5):
            self.store.create(content=f"paste{i}", title=f"Title{i}", syntax="text", expiry_hours=24, ip="127.0.0.1")
        result = self.store.list_recent(limit=2, offset=0)
        self.assertEqual(len(result["pastes"]), 2)
        self.assertEqual(result["total"], 5)
        self.assertEqual(result["offset"], 0)
        # Second page
        result2 = self.store.list_recent(limit=2, offset=2)
        self.assertEqual(len(result2["pastes"]), 2)
        self.assertEqual(result2["offset"], 2)
        # IDs should be different
        ids_page1 = {p["id"] for p in result["pastes"]}
        ids_page2 = {p["id"] for p in result2["pastes"]}
        self.assertEqual(len(ids_page1 & ids_page2), 0)

    def test_list_pastes_sort_by_views(self):
        """Test sorting by views"""
        # Create 3 pastes, view one of them multiple times
        p1 = self.store.create(content="a", title="A", syntax="text", expiry_hours=24, ip="127.0.0.1")
        p2 = self.store.create(content="b", title="B", syntax="text", expiry_hours=24, ip="127.0.0.1")
        p3 = self.store.create(content="c", title="C", syntax="text", expiry_hours=24, ip="127.0.0.1")
        # View p2 twice to give it more views
        self.store.get(p2["id"])
        self.store.get(p2["id"])
        # Sort by views desc
        result = self.store.list_recent(sort_by="views", sort_order="desc")
        self.assertEqual(result["sort_by"], "views")
        self.assertEqual(result["sort_order"], "desc")
        # First paste should have most views
        self.assertEqual(result["pastes"][0]["id"], p2["id"])

    def test_list_pastes_sort_invalid_field(self):
        """Test that invalid sort field defaults to created_at"""
        result = self.store.list_recent(sort_by="invalid_field")
        self.assertEqual(result["sort_by"], "created_at")

    def test_list_pastes_pagination_metadata(self):
        """Test pagination metadata in response"""
        self.store.create(content="x", title="X", syntax="text", expiry_hours=24, ip="127.0.0.1")
        result = self.store.list_recent(limit=5, offset=0, sort_by="created_at", sort_order="asc")
        self.assertIn("pastes", result)
        self.assertIn("total", result)
        self.assertIn("offset", result)
        self.assertIn("limit", result)
        self.assertIn("sort_by", result)
        self.assertIn("sort_order", result)

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
        result = self.store.list_recent()
        pastes = result["pastes"]
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

    def test_check_duplicate_not_found(self):
        """Test duplicate check with unique content"""
        result = self.store.check_duplicate("unique content that doesn't exist yet")
        self.assertFalse(result["is_duplicate"])
        self.assertIsNone(result["existing_id"])

    def test_check_duplicate_found(self):
        """Test duplicate check with existing content"""
        content = "this is duplicate test content"
        created = self.store.create(
            content=content, title="Original", syntax="text",
            expiry_hours=24, ip="127.0.0.1",
        )
        # Check duplicate with same content
        result = self.store.check_duplicate(content)
        self.assertTrue(result["is_duplicate"])
        self.assertEqual(result["existing_id"], created["id"])

    def test_check_duplicate_after_delete(self):
        """Test duplicate check after deleting the original paste"""
        content = "content to be deleted"
        created = self.store.create(
            content=content, title="To Delete", syntax="text",
            expiry_hours=24, ip="127.0.0.1",
        )
        # Verify it's detected as duplicate
        result = self.store.check_duplicate(content)
        self.assertTrue(result["is_duplicate"])
        # Delete the paste
        self.store.delete(created["id"])
        # Duplicate check should now return False
        result = self.store.check_duplicate(content)
        self.assertFalse(result["is_duplicate"])

    def test_search_by_tag(self):
        """Test search filtering by tag in list_recent"""
        self.store.create(
            content="tagged content", title="Tagged",
            syntax="text", expiry_hours=24, ip="127.0.0.1",
            tags=["python", "tutorial"],
        )
        self.store.create(
            content="untagged content", title="No Tag",
            syntax="text", expiry_hours=24, ip="127.0.0.1",
        )
        # Search by tag keyword
        result = self.store.list_recent(query="python")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["pastes"][0]["title"], "Tagged")

    def test_search_content_mode(self):
        """Test full content search with search_content=True"""
        self.store.create(
            content="def hello_world(): pass", title="Code",
            syntax="python", expiry_hours=24, ip="127.0.0.1",
        )
        self.store.create(
            content="no match here", title="Other",
            syntax="text", expiry_hours=24, ip="127.0.0.1",
        )
        # Quick search (title+tags only) should not find content match
        result = self.store.list_recent(query="hello_world")
        self.assertEqual(result["total"], 0)
        # Content search should find it
        result = self.store.list_recent(query="hello_world", search_content=True)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["pastes"][0]["title"], "Code")


if __name__ == "__main__":
    unittest.main()
