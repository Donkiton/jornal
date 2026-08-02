from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog

import modern_app
from database_schema import initialize_schema
from modern_app import DataStore, JournalWindow


def insert_case(
    connection: sqlite3.Connection,
    *,
    history_number: str,
    full_name: str,
    operation_date: str,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO patients (
            history_number, full_name, operation_kind, operation_date, anesthesia_type
        ) VALUES (?, ?, 'Плановая', ?, 'Общая')
        """,
        (history_number, full_name, operation_date),
    )
    connection.commit()
    return int(cursor.lastrowid)


class AcceptedDeleteDialog:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def exec(self) -> QDialog.DialogCode:
        return QDialog.DialogCode.Accepted


class PatientCasesUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        (root / "data").mkdir()
        (root / "backups").mkdir()
        (root / "UPD" / "releases").mkdir(parents=True)

        store = DataStore.__new__(DataStore)
        store.settings = DataStore.validated_settings({}, root)
        store.conn = sqlite3.connect(":memory:")
        store.conn.row_factory = sqlite3.Row
        store.connected_root = root
        store.error = ""
        store.save_settings = lambda: None
        initialize_schema(store.conn)

        self.first_id = insert_case(
            store.conn,
            history_number="42",
            full_name="Первый случай",
            operation_date="2026-08-01",
        )
        self.second_id = insert_case(
            store.conn,
            history_number="42",
            full_name="Повторный случай",
            operation_date="2026-08-02",
        )
        self.store = store
        self.window = JournalWindow(store)

    def tearDown(self) -> None:
        self.window.close()
        self.temporary_directory.cleanup()

    def select_case(self, patient_id: int) -> None:
        for row in range(self.window.table.rowCount()):
            item = self.window.table.item(row, 0)
            if item.data(Qt.ItemDataRole.UserRole) == patient_id:
                self.window.table.selectRow(row)
                return
        self.fail(f"Случай id={patient_id} не найден в таблице")

    def test_edit_changes_only_selected_repeated_case(self) -> None:
        self.select_case(self.second_id)
        self.window.start_edit()
        self.assertEqual(self.window.editing_patient_id, self.second_id)

        self.window.fields["name"].setText("Изменённый повторный случай")
        self.window.save_patient()

        rows = self.store.conn.execute(
            "SELECT id, full_name FROM patients ORDER BY id"
        ).fetchall()
        self.assertEqual(
            [(row["id"], row["full_name"]) for row in rows],
            [
                (self.first_id, "Первый случай"),
                (self.second_id, "Изменённый повторный случай"),
            ],
        )

    def test_delete_removes_only_selected_repeated_case(self) -> None:
        self.select_case(self.second_id)
        self.window.start_edit()
        self.window.fields["history"].setText("изменённый-номер-в-форме")

        with patch.object(modern_app, "PatientDeleteDialog", AcceptedDeleteDialog):
            self.window.delete_patient()

        rows = self.store.conn.execute(
            "SELECT id, history_number FROM patients ORDER BY id"
        ).fetchall()
        self.assertEqual(
            [(row["id"], row["history_number"]) for row in rows],
            [(self.first_id, "42")],
        )


if __name__ == "__main__":
    unittest.main()
