from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app_version import APP_VERSION, DATABASE_SCHEMA_VERSION
from modern_app import DataStore, establish_startup_database, open_database_root
from update_system import ReleaseInfo


class StartupUpdateTests(unittest.TestCase):
    @staticmethod
    def make_store(root: Path) -> DataStore:
        store = DataStore.__new__(DataStore)
        store.settings = DataStore.validated_settings({}, root)
        store.conn = None
        store.connected_root = None
        store.error = ""
        store.update_required = False
        return store

    def test_connect_marks_newer_database_as_requiring_update(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_dir = root / "data"
            database_dir.mkdir()
            connection = sqlite3.connect(database_dir / "journal.db")
            connection.execute(f"PRAGMA user_version={DATABASE_SCHEMA_VERSION + 1}")
            connection.close()
            store = self.make_store(root)

            self.assertFalse(store.connect(root))

            self.assertTrue(store.update_required)
            self.assertIn("более новой версией", store.error)
            self.assertIsNone(store.conn)

    def test_open_database_root_returns_distinct_update_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = Mock()
            store.connect.return_value = False
            store.update_required = True
            store.error = "Нужно обновление"
            instance_lock = Mock()
            instance_lock.acquire.return_value = True

            with patch("modern_app.ProgramInstanceLock", return_value=instance_lock):
                lock, status, details = open_database_root(store, root, False)

            self.assertIsNone(lock)
            self.assertEqual(status, "update_required")
            self.assertEqual(details, "Нужно обновление")
            instance_lock.release.assert_called_once_with()

    def test_startup_returns_published_update_for_newer_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "UPD" / "releases" / "1.0.9" / "package.zip"
            package.parent.mkdir(parents=True)
            package.write_bytes(b"package")
            release = ReleaseInfo("1.0.9", package, "0" * 64, package.stat().st_size)
            store = Mock()
            store.database_root = root
            splash = Mock()

            with (
                patch(
                    "modern_app.open_database_root",
                    return_value=(None, "update_required", "Нужно обновление"),
                ),
                patch("modern_app.find_newer_release", return_value=release) as finder,
            ):
                lock, startup_release = establish_startup_database(store, splash)

            self.assertIsNone(lock)
            self.assertEqual(startup_release, release)
            finder.assert_called_once_with(root / "UPD", APP_VERSION)
            splash.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
