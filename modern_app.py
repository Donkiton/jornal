"""Визуальный прототип журнала пациентов на Qt.

Запуск: python modern_app.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
    QMainWindow, QMessageBox, QPushButton, QRadioButton, QScrollArea,
    QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)


APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
CONFIG_PATH, BACKUP_DIR, DEFAULT_DB = APP_DIR / "settings.json", APP_DIR / "backups", APP_DIR / "data" / "journal.db"
PAGE_SIZE = 10
DEFAULT_SETTINGS = {
    "db_path": str(DEFAULT_DB), "last_backup_week": "",
    "anesthesia_types": ["Общая эндотрахеальная", "Спинальная", "Местная", "Проводниковая", "Седация"],
    "doctors": ["Смирнов И. П.", "Соколов Д. А.", "Павлов Р. А."],
    "nurses": ["Кузнецова О. В.", "Морозова Т. С.", "Иванова Е. П."],
}


QSS = """
* { font-family: 'Segoe UI'; color: #20304a; }
QMainWindow, QWidget#root { background: #f6f8fc; }
QFrame#sidebar { background: white; border-right: 1px solid #e6eaf1; }
QFrame#card { background: white; border: 1px solid #e7ebf2; border-radius: 16px; }
QLabel#title { font-size: 27px; font-weight: 700; color: #17233b; letter-spacing: -0.6px; }
QLabel#muted { color: #748198; font-size: 12px; }
QLabel#section { font-size: 14px; font-weight: 700; color: #25324b; }
QPushButton { border: 0; border-radius: 9px; padding: 9px 12px; font-size: 13px; background: transparent; }
QPushButton:hover { background: #f1f5fb; }
QPushButton:pressed { background: #e2ecfc; }
QPushButton#nav { text-align: left; padding: 11px 14px; color: #53617a; }
QPushButton#nav:checked { background: #eaf2ff; color: #1769e0; font-weight: 600; }
QPushButton#primary { background: #1769e0; color: white; font-weight: 600; padding: 10px 14px; }
QPushButton#primary:hover { background: #0e5dc9; }
QPushButton#primary:disabled { background: #c9d8ee; color: #f7fbff; }
QPushButton#outline { border: 1px solid #dfe6f0; background: white; color: #1769e0; font-weight: 600; }
QPushButton#outline:hover { background: #f4f8ff; }
QLineEdit, QComboBox { background: white; border: 1px solid #dfe6ef; border-radius: 9px; padding: 8px 10px; min-height: 20px; }
QLineEdit:focus, QComboBox:focus { border: 2px solid #80b0f2; }
QLineEdit:disabled, QComboBox:disabled { background: #f5f7fa; color: #9aa6b8; }
QComboBox::drop-down { border: 0; width: 25px; }
QTableWidget { background: white; border: none; gridline-color: #edf0f5; selection-background-color: #eaf2ff; selection-color: #17233b; font-size: 12px; }
QHeaderView::section { background: #fbfcfe; border: none; border-bottom: 1px solid #e7ebf2; color: #65738a; font-size: 11px; font-weight: 600; padding: 11px 8px; }
QTableWidget::item { border-bottom: 1px solid #edf0f5; padding: 7px; }
QScrollBar:horizontal { height: 10px; background: transparent; }
QScrollBar::handle:horizontal { background: #c5ccd8; min-width: 40px; border-radius: 5px; }
QListWidget { border: 1px solid #e1e6ef; border-radius: 9px; padding: 3px; background: white; }
QListWidget::item { padding: 9px; border-bottom: 1px solid #edf0f5; }
QListWidget::item:selected { background: #eaf2ff; color: #1769e0; border-radius: 5px; }
QRadioButton { padding: 8px 10px; border: 1px solid #dfe6ef; border-radius: 8px; background: white; }
QRadioButton::indicator { width: 0; height: 0; }
QRadioButton:checked { background: #eaf2ff; border-color: #a8c8f5; color: #1769e0; font-weight: 600; }
"""


class DataStore:
    def __init__(self) -> None:
        self.settings = self.load_settings()
        self.conn: sqlite3.Connection | None = None
        self.error = ""

    def load_settings(self) -> dict:
        try:
            source = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
        except (OSError, json.JSONDecodeError):
            source = {}
        settings = {**DEFAULT_SETTINGS, **source}
        for key in ("anesthesia_types", "doctors", "nurses"):
            settings[key] = settings[key] if isinstance(settings.get(key), list) else DEFAULT_SETTINGS[key].copy()
        return settings

    def save_settings(self) -> None:
        CONFIG_PATH.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8")

    @property
    def db_path(self) -> Path:
        return Path(self.settings["db_path"]).expanduser()

    def connect(self) -> bool:
        self.close()
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS patients (
                    id INTEGER PRIMARY KEY, history_number TEXT NOT NULL UNIQUE, full_name TEXT NOT NULL,
                    age INTEGER, operation_kind TEXT NOT NULL, operation_date TEXT NOT NULL,
                    diagnosis TEXT, anesthesia_type TEXT NOT NULL, anesthesia_start TEXT, anesthesia_end TEXT,
                    procedure_name TEXT, doctor TEXT, nurse TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_patients_history ON patients(history_number);
                CREATE INDEX IF NOT EXISTS idx_patients_name ON patients(full_name COLLATE NOCASE);
                CREATE INDEX IF NOT EXISTS idx_patients_date ON patients(operation_date DESC, created_at DESC);
            """)
            self.conn.commit()
            self.backup_if_needed()
            self.error = ""
            return True
        except (OSError, sqlite3.Error) as exc:
            self.error = str(exc)
            self.close()
            return False

    def close(self) -> None:
        if self.conn:
            try: self.conn.close()
            except sqlite3.Error: pass
        self.conn = None

    def backup_if_needed(self) -> None:
        week = date.today().strftime("%G-W%V")
        if self.settings.get("last_backup_week") == week or not self.db_path.exists(): return
        BACKUP_DIR.mkdir(exist_ok=True)
        target = BACKUP_DIR / f"journal-{week}.db"
        if not target.exists():
            with sqlite3.connect(target) as backup:
                assert self.conn is not None
                self.conn.backup(backup)
        self.settings["last_backup_week"] = week
        self.save_settings()


class ReferenceCard(QFrame):
    def __init__(self, owner: "JournalWindow", title: str, key: str, singular: str) -> None:
        super().__init__(); self.owner, self.key, self.title = owner, key, title
        self.setObjectName("card"); layout = QVBoxLayout(self); layout.setContentsMargins(18, 18, 18, 18); layout.setSpacing(10)
        label = QLabel(title); label.setObjectName("section"); layout.addWidget(label)
        self.listbox = QListWidget(); self.listbox.setMinimumHeight(220); layout.addWidget(self.listbox)
        actions = QHBoxLayout()
        for text, slot in ((f"+ Добавить {singular}", self.add), ("Изменить", self.edit), ("Удалить", self.delete)):
            button = QPushButton(text); button.setObjectName("outline"); button.clicked.connect(slot); actions.addWidget(button)
        layout.addLayout(actions); note = QLabel("Отображается в выпадающем списке"); note.setObjectName("muted"); layout.addWidget(note)
        self.refresh()

    def refresh(self) -> None:
        self.listbox.clear(); self.listbox.addItems(self.owner.store.settings[self.key])

    def add(self) -> None:
        text, ok = QInputDialog.getText(self, "Добавить", self.title)
        if ok and text.strip() and text.strip() not in self.owner.store.settings[self.key]:
            self.owner.store.settings[self.key].append(text.strip()); self.owner.persist_references()

    def edit(self) -> None:
        row = self.listbox.currentRow()
        if row < 0: return
        old = self.owner.store.settings[self.key][row]
        text, ok = QInputDialog.getText(self, "Изменить", self.title, text=old)
        if ok and text.strip(): self.owner.store.settings[self.key][row] = text.strip(); self.owner.persist_references()

    def delete(self) -> None:
        row = self.listbox.currentRow()
        if row < 0: return
        value = self.owner.store.settings[self.key][row]
        if QMessageBox.question(self, "Удалить", f"Удалить «{value}»?") == QMessageBox.StandardButton.Yes:
            self.owner.store.settings[self.key].pop(row); self.owner.persist_references()


class JournalWindow(QMainWindow):
    headers = ["№ истории", "ФИО", "Возраст", "Операция", "Дата операции", "Диагноз", "Вид наркоза", "Начало", "Окончание", "Длительность", "Название операции", "Врач", "Медсестра"]
    widths = [105, 175, 62, 100, 105, 150, 135, 68, 88, 95, 165, 120, 122]

    def __init__(self) -> None:
        super().__init__(); self.store = DataStore(); self.page = 0; self.total = 0; self.editing_history: str | None = None
        self.setWindowTitle("Журнал пациентов"); self.resize(1540, 900); self.setMinimumSize(1160, 720); self.setStyleSheet(QSS)
        self.build(); self.store.connect(); self.show_patients()

    def build(self) -> None:
        root = QWidget(); root.setObjectName("root"); self.setCentralWidget(root); shell = QHBoxLayout(root); shell.setContentsMargins(0,0,0,0); shell.setSpacing(0)
        sidebar = QFrame(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(232); side = QVBoxLayout(sidebar); side.setContentsMargins(14, 25, 14, 22); side.setSpacing(5)
        brand = QLabel("ЖУРНАЛ"); brand.setStyleSheet("color:#9aa6b8;font-size:11px;font-weight:700;letter-spacing:1.4px;padding:0 10px 14px;"); side.addWidget(brand)
        self.nav_group = QButtonGroup(self); self.nav_group.setExclusive(True)
        self.nav_patients = self.nav_button("👥  Пациенты", True, self.show_patients); side.addWidget(self.nav_patients)
        self.nav_reports = self.nav_button("▥  Отчёты   · скоро", False, self.show_reports); side.addWidget(self.nav_reports); side.addStretch()
        self.nav_settings = self.nav_button("⚙  Настройки", False, self.show_settings); side.addWidget(self.nav_settings); shell.addWidget(sidebar)
        self.stack = QStackedWidget(); shell.addWidget(self.stack, 1)
        self.patient_page = self.make_patient_page(); self.settings_page = self.make_settings_page(); self.report_page = self.make_report_page()
        self.stack.addWidget(self.patient_page); self.stack.addWidget(self.settings_page); self.stack.addWidget(self.report_page)

    def nav_button(self, text: str, checked: bool, slot) -> QPushButton:
        button = QPushButton(text); button.setObjectName("nav"); button.setCheckable(True); button.setChecked(checked); button.clicked.connect(slot); self.nav_group.addButton(button); return button

    def page_layout(self, widget: QWidget) -> QVBoxLayout:
        layout = QVBoxLayout(widget); layout.setContentsMargins(34, 28, 34, 28); layout.setSpacing(14); return layout

    def make_patient_page(self) -> QWidget:
        page = QWidget(); layout = self.page_layout(page)
        header = QHBoxLayout(); title = QLabel("Журнал пациентов"); title.setObjectName("title"); header.addWidget(title); header.addStretch()
        self.edit_button = QPushButton("Редактировать пациента"); self.edit_button.setObjectName("primary"); self.edit_button.setEnabled(False); self.edit_button.clicked.connect(self.start_edit); header.addWidget(self.edit_button); layout.addLayout(header)
        self.alert = QFrame(); self.alert.setObjectName("card"); alert_layout = QHBoxLayout(self.alert); alert_layout.setContentsMargins(14, 9, 10, 9)
        self.alert_text = QLabel(); self.alert_text.setStyleSheet("color:#9b5205;"); alert_layout.addWidget(self.alert_text, 1); retry = QPushButton("Повторить подключение"); retry.setObjectName("outline"); retry.clicked.connect(self.retry_connection); alert_layout.addWidget(retry); self.alert.hide(); layout.addWidget(self.alert)
        filters = QHBoxLayout(); label = QLabel("Фильтры"); label.setObjectName("muted"); filters.addWidget(label)
        self.filter_name = QLineEdit(); self.filter_name.setPlaceholderText("Поиск по ФИО"); self.filter_name.setFixedWidth(260); self.filter_name.returnPressed.connect(self.apply_filters); filters.addWidget(self.filter_name)
        self.filter_date = QLineEdit(); self.filter_date.setPlaceholderText("Дата операции · ГГГГ-ММ-ДД"); self.filter_date.setFixedWidth(205); self.filter_date.returnPressed.connect(self.apply_filters); filters.addWidget(self.filter_date)
        self.apply_button = QPushButton("Применить"); self.apply_button.setObjectName("outline"); self.apply_button.clicked.connect(self.apply_filters); filters.addWidget(self.apply_button)
        self.reset_button = QPushButton("Сбросить"); self.reset_button.setObjectName("outline"); self.reset_button.clicked.connect(self.reset_filters); filters.addWidget(self.reset_button); filters.addStretch(); layout.addLayout(filters)
        content = QHBoxLayout(); content.setSpacing(14); table_card = QFrame(); table_card.setObjectName("card"); table_layout = QVBoxLayout(table_card); table_layout.setContentsMargins(1,1,1,8); table_layout.setSpacing(3)
        self.table = QTableWidget(0, len(self.headers)); self.table.setHorizontalHeaderLabels(self.headers); self.table.verticalHeader().setVisible(False); self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows); self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection); self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); self.table.setAlternatingRowColors(False)
        for i, width in enumerate(self.widths): self.table.setColumnWidth(i, width)
        self.table.horizontalHeader().setStretchLastSection(False); self.table.itemSelectionChanged.connect(self.selection_changed); table_layout.addWidget(self.table, 1)
        footer = QHBoxLayout(); self.page_info = QLabel("Показано 0 из 0"); self.page_info.setObjectName("muted"); footer.addWidget(self.page_info); footer.addStretch(); self.prev = QPushButton("‹"); self.prev.setObjectName("outline"); self.prev.setFixedWidth(38); self.prev.clicked.connect(lambda: self.change_page(-1)); footer.addWidget(self.prev); self.page_num = QLabel("1"); self.page_num.setAlignment(Qt.AlignmentFlag.AlignCenter); self.page_num.setFixedWidth(38); self.page_num.setStyleSheet("background:#eaf2ff;color:#1769e0;border-radius:9px;padding:8px;font-weight:600;"); footer.addWidget(self.page_num); self.next = QPushButton("›"); self.next.setObjectName("outline"); self.next.setFixedWidth(38); self.next.clicked.connect(lambda: self.change_page(1)); footer.addWidget(self.next); table_layout.addLayout(footer); content.addWidget(table_card, 1)
        self.form_card = self.make_quick_form(); content.addWidget(self.form_card, 0); layout.addLayout(content, 1)
        return page

    def make_quick_form(self) -> QFrame:
        card = QFrame(); card.setObjectName("card"); card.setFixedWidth(330); outer = QVBoxLayout(card); outer.setContentsMargins(0,0,0,0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame); inner = QWidget(); form = QVBoxLayout(inner); form.setContentsMargins(18,18,18,18); form.setSpacing(7)
        self.form_title = QLabel("Быстрое добавление"); self.form_title.setObjectName("section"); form.addWidget(self.form_title); note = QLabel("* обязательные поля"); note.setObjectName("muted"); form.addWidget(note)
        self.fields: dict[str, QWidget] = {}; self.input_widgets: list[QWidget] = []
        def text(label: str, key: str, required=False, placeholder=""):
            lab = QLabel(label + (" *" if required else "")); lab.setObjectName("muted"); form.addWidget(lab); box = QLineEdit(); box.setPlaceholderText(placeholder); form.addWidget(box); self.fields[key] = box; self.input_widgets.append(box)
        def combo(label: str, key: str, values: list[str], required=False):
            lab = QLabel(label + (" *" if required else "")); lab.setObjectName("muted"); form.addWidget(lab); box = QComboBox(); box.setEditable(True); box.addItems(values); form.addWidget(box); self.fields[key] = box; self.input_widgets.append(box)
        text("№ истории", "history", True); text("ФИО", "name", True); text("Возраст", "age", False)
        form.addWidget(QLabel("Операция", objectName="muted")); kinds = QHBoxLayout(); self.kind_group = QButtonGroup(self); self.kind_planned = QRadioButton("Плановая"); self.kind_emergency = QRadioButton("Экстренная"); self.kind_planned.setChecked(True); self.kind_group.addButton(self.kind_planned); self.kind_group.addButton(self.kind_emergency); kinds.addWidget(self.kind_planned); kinds.addWidget(self.kind_emergency); form.addLayout(kinds); self.input_widgets += [self.kind_planned, self.kind_emergency]
        text("Дата операции", "date", True, "ГГГГ-ММ-ДД"); self.fields["date"].setText(date.today().isoformat()); text("Диагноз", "diagnosis"); combo("Вид наркоза", "anesthesia", self.store.settings["anesthesia_types"], True)
        time_row = QHBoxLayout(); start_box = QLineEdit(); end_box = QLineEdit(); start_box.setPlaceholderText("ЧЧ:ММ"); end_box.setPlaceholderText("ЧЧ:ММ"); self.fields["start"], self.fields["end"] = start_box, end_box; self.input_widgets += [start_box, end_box]
        for title, box in (("Начало", start_box), ("Окончание", end_box)):
            col = QVBoxLayout(); lab = QLabel(title); lab.setObjectName("muted"); col.addWidget(lab); col.addWidget(box); time_row.addLayout(col)
        form.addLayout(time_row); duration_label = QLabel("Длительность · рассчитывается автоматически"); duration_label.setObjectName("muted"); form.addWidget(duration_label); self.duration = QLineEdit("—"); self.duration.setReadOnly(True); form.addWidget(self.duration); start_box.textChanged.connect(self.update_duration); end_box.textChanged.connect(self.update_duration)
        text("Название операции", "procedure"); combo("Врач", "doctor", self.store.settings["doctors"]); combo("Медсестра", "nurse", self.store.settings["nurses"])
        self.save_button = QPushButton("Добавить пациента"); self.save_button.setObjectName("primary"); self.save_button.clicked.connect(self.save_patient); form.addWidget(self.save_button)
        self.cancel_button = QPushButton("Отмена"); self.cancel_button.setObjectName("outline"); self.cancel_button.clicked.connect(self.cancel_edit); self.cancel_button.hide(); form.addWidget(self.cancel_button); form.addStretch(); scroll.setWidget(inner); outer.addWidget(scroll); return card

    def make_settings_page(self) -> QWidget:
        page = QWidget(); layout = self.page_layout(page); title = QLabel("Настройки"); title.setObjectName("title"); layout.addWidget(title); subtitle = QLabel("Справочники и хранение данных"); subtitle.setObjectName("muted"); layout.addWidget(subtitle)
        cards = QHBoxLayout(); self.reference_cards = [ReferenceCard(self, "Виды наркоза", "anesthesia_types", "вид"), ReferenceCard(self, "Врачи", "doctors", "врача"), ReferenceCard(self, "Медсестры", "nurses", "медсестру")]
        for card in self.reference_cards: cards.addWidget(card, 1)
        layout.addLayout(cards)
        storage = QFrame(); storage.setObjectName("card"); grid = QGridLayout(storage); grid.setContentsMargins(18,18,18,18); grid.setSpacing(9); label = QLabel("Хранение данных"); label.setObjectName("section"); grid.addWidget(label, 0, 0, 1, 3); grid.addWidget(QLabel("Путь к базе данных", objectName="muted"), 1,0,1,3)
        self.path_field = QLineEdit(); grid.addWidget(self.path_field, 2,0); choose = QPushButton("Выбрать файл"); choose.setObjectName("outline"); choose.clicked.connect(self.choose_path); grid.addWidget(choose,2,1); save = QPushButton("Сохранить путь"); save.setObjectName("primary"); save.clicked.connect(self.save_path); grid.addWidget(save,2,2); self.connection_status = QLabel(); self.connection_status.setObjectName("muted"); grid.addWidget(self.connection_status, 3,0,1,3); layout.addWidget(storage); layout.addStretch(); return page

    def make_report_page(self) -> QWidget:
        page = QWidget(); layout = self.page_layout(page); label = QLabel("Отчёты"); label.setObjectName("title"); layout.addWidget(label); text = QLabel("Раздел находится в разработке."); text.setObjectName("muted"); layout.addWidget(text); layout.addStretch(); return page

    def select_page(self, index: int, button: QPushButton) -> None:
        self.stack.setCurrentIndex(index); button.setChecked(True)

    def show_patients(self) -> None:
        self.select_page(0, self.nav_patients); self.refresh_patient_state()

    def show_settings(self) -> None:
        self.select_page(1, self.nav_settings); self.path_field.setText(self.store.settings["db_path"]); self.refresh_references(); self.update_connection_status()

    def show_reports(self) -> None: self.select_page(2, self.nav_reports)

    def refresh_patient_state(self) -> None:
        available = self.store.conn is not None
        self.alert.setVisible(not available)
        if not available: self.alert_text.setText("База данных недоступна. Просмотр, добавление и редактирование пациентов временно недоступны.")
        for widget in [self.table, self.filter_name, self.filter_date, self.apply_button, self.reset_button, self.save_button, self.prev, self.next, *self.input_widgets]: widget.setEnabled(available)
        self.edit_button.setEnabled(available and bool(self.table.selectedItems()))
        if available: self.load_patients()
        else: self.table.setRowCount(0); self.page_info.setText("База недоступна")

    def retry_connection(self) -> None: self.store.connect(); self.refresh_patient_state(); self.update_connection_status()

    def where_clause(self) -> tuple[str, list[str]]:
        clauses, params = [], []
        if self.filter_name.text().strip(): clauses.append("full_name LIKE ? COLLATE NOCASE"); params.append("%" + self.filter_name.text().strip() + "%")
        if self.filter_date.text().strip(): clauses.append("operation_date = ?"); params.append(self.filter_date.text().strip())
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def load_patients(self) -> None:
        if not self.store.conn: return
        try:
            where, params = self.where_clause(); conn = self.store.conn; self.total = int(conn.execute("SELECT COUNT(*) FROM patients" + where, params).fetchone()[0]); self.page = min(self.page, max(0, (self.total - 1)//PAGE_SIZE)); rows = conn.execute("SELECT * FROM patients" + where + " ORDER BY operation_date DESC, created_at DESC LIMIT ? OFFSET ?", [*params, PAGE_SIZE, self.page * PAGE_SIZE]).fetchall()
        except sqlite3.Error as exc:
            self.store.error = str(exc); self.store.close(); self.refresh_patient_state(); return
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = [row["history_number"], row["full_name"], str(row["age"] or "—"), row["operation_kind"], row["operation_date"], row["diagnosis"] or "—", row["anesthesia_type"], row["anesthesia_start"] or "—", row["anesthesia_end"] or "—", self.duration_text(row["anesthesia_start"], row["anesthesia_end"]), row["procedure_name"] or "—", row["doctor"] or "—", row["nurse"] or "—"]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value); item.setData(Qt.ItemDataRole.UserRole, row["history_number"])
                if c == 3: item.setForeground(QColor("#1769e0") if value == "Плановая" else QColor("#d84d4d"))
                self.table.setItem(r,c,item)
            self.table.setRowHeight(r, 48)
        first = self.page*PAGE_SIZE+1 if self.total else 0; last = min((self.page+1)*PAGE_SIZE, self.total); self.page_info.setText(f"Показано {first}–{last} из {self.total}"); self.page_num.setText(str(self.page+1)); self.prev.setEnabled(self.page>0); self.next.setEnabled(last<self.total); self.edit_button.setEnabled(False)

    def apply_filters(self) -> None: self.page = 0; self.load_patients()
    def reset_filters(self) -> None: self.filter_name.clear(); self.filter_date.clear(); self.apply_filters()
    def change_page(self, delta: int) -> None: self.page += delta; self.load_patients()
    def selection_changed(self) -> None: self.edit_button.setEnabled(self.store.conn is not None and bool(self.table.selectedItems()))

    @staticmethod
    def duration_text(start: str | None, end: str | None) -> str:
        if not start or not end: return "—"
        try: minutes = int((datetime.strptime(end, "%H:%M") - datetime.strptime(start, "%H:%M")).total_seconds()//60)
        except ValueError: return "Укажите ЧЧ:ММ"
        if minutes < 0: return "Проверьте время"
        return f"{minutes//60} ч {minutes%60} мин" if minutes >= 60 else f"{minutes} мин"

    def update_duration(self) -> None: self.duration.setText(self.duration_text(self.fields["start"].text().strip(), self.fields["end"].text().strip()))
    def field_value(self, key: str) -> str: return self.fields[key].currentText().strip() if isinstance(self.fields[key], QComboBox) else self.fields[key].text().strip()

    def form_data(self) -> dict[str,str]:
        return {key:self.field_value(key) for key in self.fields} | {"kind":"Плановая" if self.kind_planned.isChecked() else "Экстренная"}

    def validate(self, data: dict[str,str]) -> bool:
        missing = [label for key,label in (("history","№ истории"),("name","ФИО"),("date","Дата операции"),("anesthesia","Вид наркоза")) if not data[key]]
        if missing: QMessageBox.warning(self,"Не заполнены поля","Обязательные поля: " + ", ".join(missing)); return False
        try: datetime.strptime(data["date"], "%Y-%m-%d")
        except ValueError: QMessageBox.warning(self,"Дата операции","Используйте формат ГГГГ-ММ-ДД."); return False
        if data["age"] and (not data["age"].isdigit() or not 0 <= int(data["age"]) <= 130): QMessageBox.warning(self,"Возраст","Возраст должен быть числом от 0 до 130."); return False
        if self.duration_text(data["start"], data["end"]) in ("Укажите ЧЧ:ММ","Проверьте время"): QMessageBox.warning(self,"Время наркоза","Проверьте начало и окончание в формате ЧЧ:ММ."); return False
        return True

    def save_patient(self) -> None:
        if not self.store.conn: return
        data = self.form_data()
        if not self.validate(data): return
        vals = (data["history"], data["name"], int(data["age"]) if data["age"] else None, data["kind"], data["date"], data["diagnosis"], data["anesthesia"], data["start"], data["end"], data["procedure"], data["doctor"], data["nurse"])
        try:
            if self.editing_history is None: self.store.conn.execute("INSERT INTO patients(history_number,full_name,age,operation_kind,operation_date,diagnosis,anesthesia_type,anesthesia_start,anesthesia_end,procedure_name,doctor,nurse) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", vals)
            else: self.store.conn.execute("UPDATE patients SET history_number=?,full_name=?,age=?,operation_kind=?,operation_date=?,diagnosis=?,anesthesia_type=?,anesthesia_start=?,anesthesia_end=?,procedure_name=?,doctor=?,nurse=?,updated_at=CURRENT_TIMESTAMP WHERE history_number=?", (*vals, self.editing_history))
            self.store.conn.commit()
        except sqlite3.IntegrityError: QMessageBox.warning(self,"Не удалось сохранить","Запись с таким № истории уже существует."); return
        except sqlite3.Error as exc: self.store.error=str(exc); self.store.close(); self.refresh_patient_state(); return
        self.cancel_edit(); self.load_patients()

    def start_edit(self) -> None:
        if not self.store.conn or not self.table.selectedItems(): return
        history = self.table.selectedItems()[0].data(Qt.ItemDataRole.UserRole); row = self.store.conn.execute("SELECT * FROM patients WHERE history_number=?",(history,)).fetchone()
        if not row: return
        self.editing_history = history
        mapping = {"history":"history_number","name":"full_name","age":"age","date":"operation_date","diagnosis":"diagnosis","anesthesia":"anesthesia_type","start":"anesthesia_start","end":"anesthesia_end","procedure":"procedure_name","doctor":"doctor","nurse":"nurse"}
        for key,column in mapping.items():
            target=self.fields[key]; value=str(row[column] or ""); target.setCurrentText(value) if isinstance(target,QComboBox) else target.setText(value)
        self.kind_planned.setChecked(row["operation_kind"] == "Плановая"); self.kind_emergency.setChecked(row["operation_kind"] == "Экстренная"); self.form_title.setText("Редактирование пациента"); self.save_button.setText("Сохранить изменения"); self.cancel_button.show(); self.update_duration()

    def cancel_edit(self) -> None:
        self.editing_history=None
        for key, target in self.fields.items(): target.setCurrentText("") if isinstance(target,QComboBox) else target.setText("")
        self.fields["date"].setText(date.today().isoformat()); self.kind_planned.setChecked(True); self.form_title.setText("Быстрое добавление"); self.save_button.setText("Добавить пациента"); self.cancel_button.hide(); self.update_duration()

    def refresh_references(self) -> None:
        for card in self.reference_cards: card.refresh()
        for key, source in (("anesthesia", "anesthesia_types"),("doctor","doctors"),("nurse","nurses")):
            box = self.fields[key]; value=box.currentText(); box.clear(); box.addItems(self.store.settings[source]); box.setCurrentText(value)

    def persist_references(self) -> None: self.store.save_settings(); self.refresh_references()
    def choose_path(self) -> None:
        path,_=QFileDialog.getSaveFileName(self,"Выберите файл базы",str(self.store.db_path),"SQLite (*.db);;Все файлы (*.*)")
        if path: self.path_field.setText(path)
    def save_path(self) -> None:
        if not self.path_field.text().strip(): return
        self.store.settings["db_path"] = self.path_field.text().strip(); self.store.save_settings(); self.store.connect(); self.refresh_patient_state(); self.update_connection_status()
    def update_connection_status(self) -> None:
        if self.store.conn: self.connection_status.setText("База доступна. Выбранный путь сохранён рядом с программой."); self.connection_status.setStyleSheet("color:#16835a;")
        else: self.connection_status.setText("База недоступна. Можно изменить путь и повторить подключение."); self.connection_status.setStyleSheet("color:#b05600;")


if __name__ == "__main__":
    app = QApplication(sys.argv); window = JournalWindow(); window.show(); sys.exit(app.exec())
