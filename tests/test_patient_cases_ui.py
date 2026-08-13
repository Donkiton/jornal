from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QScrollArea

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

    def test_first_page_shows_fifteen_rows(self) -> None:
        for index in range(15):
            insert_case(
                self.store.conn,
                history_number=f"page-{index}",
                full_name=f"Пациент страницы {index}",
                operation_date="2026-01-01",
            )

        self.window.load_patients()

        self.assertEqual(modern_app.PAGE_SIZE, 15)
        self.assertEqual(self.window.table.rowCount(), 15)
        self.assertEqual(self.window.total, 17)
        self.assertEqual(self.window.page_info.text(), "Показано 1–15 из 17")

    def test_overnight_duration_and_department_are_saved_and_shown(self) -> None:
        self.assertEqual(JournalWindow.duration_text("23:10", "03:00"), "3 ч 50 мин")
        self.assertEqual(JournalWindow.duration_text("08:00", "09:00"), "1 ч 0 мин")

        self.window.fields["history"].setText("overnight")
        self.window.fields["name"].setText("Ночной пациент")
        self.window.fields["anesthesia"].setCurrentText("Общая")
        self.window.fields["start"].setText("23:10")
        self.window.fields["end"].setText("03:00")
        self.window.department_buttons["Хирургия"].setChecked(True)
        self.window.save_patient()

        saved_department = self.store.conn.execute(
            "SELECT department FROM patients WHERE history_number='overnight'"
        ).fetchone()[0]
        self.assertEqual(saved_department, "Хирургия")
        self.assertEqual(self.window.table.item(0, 4).text(), "Хирургия")

    def test_department_is_optional_and_not_selected_by_default(self) -> None:
        self.assertIsNone(self.window.department_group.checkedButton())

    def test_maximized_quick_form_has_no_horizontal_scrollbar(self) -> None:
        self.window.showMaximized()
        self.application.processEvents()

        scroll_area = self.window.form_card.findChild(QScrollArea)
        self.assertIsNotNone(scroll_area)
        self.assertEqual(self.window.form_card.width(), 355)
        self.assertEqual(scroll_area.horizontalScrollBar().maximum(), 0)

    def test_memo_navigation_displays_contained_image(self) -> None:
        self.window.show()
        self.window.show_memo()
        self.application.processEvents()

        self.assertIs(self.window.stack.currentWidget(), self.window.memo_page)
        self.assertTrue(self.window.nav_memo.isChecked())
        pixmap = self.window.memo_image_label.pixmap()
        self.assertIsNotNone(pixmap)
        self.assertFalse(pixmap.isNull())
        self.assertLessEqual(pixmap.width(), self.window.memo_image_label.width())
        self.assertLessEqual(pixmap.height(), self.window.memo_image_label.height())


if __name__ == "__main__":
    unittest.main()
