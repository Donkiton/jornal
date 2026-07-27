"""Локальный прототип журнала пациентов.

Запуск: python app.py
Зависимости: только стандартная библиотека Python 3.11+.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


# В собранном приложении служебный __file__ указывает внутрь пакета,
# поэтому пользовательские данные всегда привязываем к папке самого .exe.
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "settings.json"
BACKUP_DIR = APP_DIR / "backups"
DEFAULT_DB = APP_DIR / "data" / "journal.db"
PAGE_SIZE = 10

DEFAULT_SETTINGS = {
    "db_path": str(DEFAULT_DB),
    "last_backup_week": "",
    "anesthesia_types": ["Общая эндотрахеальная", "Спинальная", "Местная", "Проводниковая", "Седация"],
    "doctors": ["Смирнов И. П.", "Соколов Д. А.", "Павлов Р. А."],
    "nurses": ["Кузнецова О. В.", "Морозова Т. С.", "Иванова Е. П."],
}


class JournalApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Журнал пациентов")
        self.geometry("1540x900")
        self.minsize(1120, 720)
        self.configure(bg="#f7f9fc")

        self.settings = self.load_settings()
        self.db: sqlite3.Connection | None = None
        self.db_error = ""
        self.page = 0
        self.total_rows = 0
        self.editing_history: str | None = None

        self.configure_style()
        self.build_layout()
        self.connect_database(silent=True)
        self.show_patients()

    # ---------- persistence ----------
    def load_settings(self) -> dict:
        try:
            saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
        except (json.JSONDecodeError, OSError):
            saved = {}
        settings = {**DEFAULT_SETTINGS, **saved}
        for key in ("anesthesia_types", "doctors", "nurses"):
            if not isinstance(settings.get(key), list):
                settings[key] = DEFAULT_SETTINGS[key].copy()
        return settings

    def save_settings(self) -> None:
        CONFIG_PATH.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8")

    def db_path(self) -> Path:
        return Path(self.settings["db_path"]).expanduser()

    def connect_database(self, silent: bool = False) -> bool:
        self.close_database()
        try:
            path = self.db_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(path)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA foreign_keys = ON")
            self.db.execute("PRAGMA journal_mode = WAL")
            self.create_schema()
            self.create_weekly_backup()
            self.db_error = ""
            return True
        except (OSError, sqlite3.Error) as error:
            self.close_database()
            self.db_error = str(error)
            if not silent:
                messagebox.showwarning("База недоступна", "Не удалось подключиться к базе данных.\n\n" + self.db_error)
            return False

    def close_database(self) -> None:
        if self.db is not None:
            try:
                self.db.close()
            except sqlite3.Error:
                pass
        self.db = None

    def create_schema(self) -> None:
        assert self.db is not None
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                history_number TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                age INTEGER,
                operation_kind TEXT NOT NULL DEFAULT 'Плановая',
                operation_date TEXT NOT NULL,
                diagnosis TEXT,
                anesthesia_type TEXT NOT NULL,
                anesthesia_start TEXT,
                anesthesia_end TEXT,
                procedure_name TEXT,
                doctor TEXT,
                nurse TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_patients_history ON patients(history_number);
            CREATE INDEX IF NOT EXISTS idx_patients_name ON patients(full_name COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_patients_date ON patients(operation_date DESC, created_at DESC);
            """
        )
        self.db.commit()

    def create_weekly_backup(self) -> None:
        """Копия создаётся при первом успешном запуске в текущую ISO-неделю."""
        current_week = date.today().strftime("%G-W%V")
        if self.settings.get("last_backup_week") == current_week:
            return
        source = self.db_path()
        if not source.exists():
            return
        BACKUP_DIR.mkdir(exist_ok=True)
        target = BACKUP_DIR / f"journal-{current_week}.db"
        if not target.exists():
            # backup API безопаснее обычного copy, когда SQLite открыт в WAL-режиме.
            with sqlite3.connect(target) as backup:
                assert self.db is not None
                self.db.backup(backup)
        self.settings["last_backup_week"] = current_week
        self.save_settings()

    # ---------- interface ----------
    def configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("App.TFrame", background="#f7f9fc")
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("Sidebar.TFrame", background="#ffffff")
        style.configure("Title.TLabel", background="#f7f9fc", foreground="#17233b", font=("Segoe UI", 22, "bold"))
        style.configure("Subtitle.TLabel", background="#f7f9fc", foreground="#6d7890", font=("Segoe UI", 10))
        style.configure("CardTitle.TLabel", background="#ffffff", foreground="#17233b", font=("Segoe UI", 12, "bold"))
        style.configure("TLabel", background="#ffffff", foreground="#25324b", font=("Segoe UI", 10))
        style.configure("Sidebar.TButton", background="#ffffff", foreground="#47546c", borderwidth=0, anchor="w", padding=(16, 12), font=("Segoe UI", 11))
        style.map("Sidebar.TButton", background=[("active", "#edf4ff")], foreground=[("active", "#1769e0")])
        style.configure("NavActive.TButton", background="#eaf2ff", foreground="#1769e0", borderwidth=0, anchor="w", padding=(16, 12), font=("Segoe UI", 11, "bold"))
        style.configure("Primary.TButton", background="#1769e0", foreground="#ffffff", borderwidth=0, padding=(14, 9), font=("Segoe UI", 10, "bold"))
        style.map("Primary.TButton", background=[("active", "#0e56bd"), ("disabled", "#b9c8df")])
        style.configure("Secondary.TButton", background="#ffffff", foreground="#1769e0", borderwidth=1, relief="solid", padding=(12, 8), font=("Segoe UI", 10, "bold"))
        style.configure("Treeview", background="#ffffff", fieldbackground="#ffffff", foreground="#26344d", rowheight=48, borderwidth=0, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background="#f8faff", foreground="#526079", relief="flat", font=("Segoe UI", 9, "bold"), padding=(6, 10))
        style.map("Treeview", background=[("selected", "#eaf2ff")], foreground=[("selected", "#17233b")])
        style.configure("TEntry", padding=7, fieldbackground="#ffffff")
        style.configure("TCombobox", padding=6, fieldbackground="#ffffff")
        style.configure("TNotebook", background="#f7f9fc", borderwidth=0)

    def build_layout(self) -> None:
        self.sidebar = ttk.Frame(self, style="Sidebar.TFrame", width=230)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        ttk.Label(self.sidebar, text="ЖУРНАЛ", background="#ffffff", foreground="#98a3b7", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=24, pady=(28, 18))
        self.nav_patients = ttk.Button(self.sidebar, text="👥  Пациенты", style="NavActive.TButton", command=self.show_patients)
        self.nav_patients.pack(fill="x", padx=14, pady=3)
        self.nav_reports = ttk.Button(self.sidebar, text="▥  Отчёты   · скоро", style="Sidebar.TButton", command=self.show_reports)
        self.nav_reports.pack(fill="x", padx=14, pady=3)
        ttk.Frame(self.sidebar, style="Sidebar.TFrame").pack(fill="both", expand=True)
        self.nav_settings = ttk.Button(self.sidebar, text="⚙  Настройки", style="Sidebar.TButton", command=self.show_settings)
        self.nav_settings.pack(fill="x", padx=14, pady=(3, 24))

        self.content = ttk.Frame(self, style="App.TFrame")
        self.content.pack(side="left", fill="both", expand=True)
        self.patient_view = ttk.Frame(self.content, style="App.TFrame")
        self.settings_view = ttk.Frame(self.content, style="App.TFrame")
        self.report_view = ttk.Frame(self.content, style="App.TFrame")
        self.build_patients_view()
        self.build_settings_view()
        self.build_reports_view()

    def select_nav(self, active: str) -> None:
        for name, button in (("patients", self.nav_patients), ("settings", self.nav_settings), ("reports", self.nav_reports)):
            button.configure(style="NavActive.TButton" if name == active else "Sidebar.TButton")

    def show_view(self, view: ttk.Frame, active: str) -> None:
        for candidate in (self.patient_view, self.settings_view, self.report_view):
            candidate.pack_forget()
        view.pack(fill="both", expand=True)
        self.select_nav(active)

    # ---------- patients ----------
    def build_patients_view(self) -> None:
        self.patient_header = ttk.Frame(self.patient_view, style="App.TFrame")
        self.patient_header.pack(fill="x", padx=34, pady=(28, 10))
        ttk.Label(self.patient_header, text="Журнал пациентов", style="Title.TLabel").pack(side="left")
        self.edit_button = ttk.Button(self.patient_header, text="Редактировать пациента", style="Primary.TButton", command=self.start_edit, state="disabled")
        self.edit_button.pack(side="right")

        self.db_notice = ttk.Frame(self.patient_view, style="Card.TFrame")
        self.db_notice.pack(fill="x", padx=34, pady=(0, 8))
        self.db_notice_label = ttk.Label(self.db_notice, text="", background="#fff4e8", foreground="#9a4d00", font=("Segoe UI", 10))
        self.db_notice_label.pack(side="left", fill="x", expand=True, padx=14, pady=10)
        ttk.Button(self.db_notice, text="Повторить подключение", style="Secondary.TButton", command=self.retry_connection).pack(side="right", padx=10, pady=7)

        filters = ttk.Frame(self.patient_view, style="App.TFrame")
        filters.pack(fill="x", padx=34, pady=(4, 10))
        ttk.Label(filters, text="Фильтры", style="Subtitle.TLabel").pack(side="left", padx=(0, 12))
        self.name_filter = ttk.Entry(filters, width=32)
        self.name_filter.insert(0, "")
        self.name_filter.pack(side="left", padx=5)
        self.name_filter.bind("<Return>", lambda _event: self.apply_filters())
        self.date_filter = ttk.Entry(filters, width=15)
        self.date_filter.pack(side="left", padx=5)
        self.date_filter.bind("<Return>", lambda _event: self.apply_filters())
        self.apply_filters_button = ttk.Button(filters, text="Применить", style="Secondary.TButton", command=self.apply_filters)
        self.apply_filters_button.pack(side="left", padx=5)
        self.reset_filters_button = ttk.Button(filters, text="Сбросить", style="Secondary.TButton", command=self.reset_filters)
        self.reset_filters_button.pack(side="left", padx=3)

        body = ttk.Frame(self.patient_view, style="App.TFrame")
        body.pack(fill="both", expand=True, padx=34, pady=(0, 28))
        table_card = ttk.Frame(body, style="Card.TFrame")
        table_card.pack(side="left", fill="both", expand=True)
        form_card = ttk.Frame(body, style="Card.TFrame", width=310)
        form_card.pack(side="left", fill="y", padx=(14, 0))
        form_card.pack_propagate(False)
        self.build_table(table_card)
        self.build_patient_form(form_card)

    def build_table(self, parent: ttk.Frame) -> None:
        columns = ("history", "name", "age", "kind", "date", "diagnosis", "anesthesia", "start", "end", "duration", "procedure", "doctor", "nurse")
        headings = ("№ истории", "ФИО", "Возраст", "Операция", "Дата операции", "Диагноз", "Вид наркоза", "Начало", "Окончание", "Длительность", "Название операции", "Врач", "Медсестра")
        widths = (104, 180, 62, 100, 104, 155, 135, 70, 88, 95, 170, 120, 125)
        holder = ttk.Frame(parent, style="Card.TFrame")
        holder.pack(fill="both", expand=True, padx=1, pady=1)
        self.tree = ttk.Treeview(holder, columns=columns, show="headings", selectmode="browse")
        for col, heading, width in zip(columns, headings, widths):
            self.tree.heading(col, text=heading)
            self.tree.column(col, width=width, minwidth=58, stretch=False, anchor="w")
        xbar = ttk.Scrollbar(holder, orient="horizontal", command=self.tree.xview)
        ybar = ttk.Scrollbar(holder, orient="vertical", command=self.tree.yview)
        self.tree.configure(xscrollcommand=xbar.set, yscrollcommand=ybar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        holder.grid_rowconfigure(0, weight=1)
        holder.grid_columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<Double-1>", lambda _event: self.start_edit())

        footer = ttk.Frame(parent, style="Card.TFrame")
        footer.pack(fill="x", padx=10, pady=(4, 8))
        self.page_info = ttk.Label(footer, text="Показано 0 из 0", background="#ffffff", foreground="#65728a")
        self.page_info.pack(side="left")
        self.prev_page = ttk.Button(footer, text="‹", style="Secondary.TButton", width=3, command=lambda: self.change_page(-1))
        self.prev_page.pack(side="right", padx=(4, 0))
        self.next_page = ttk.Button(footer, text="›", style="Secondary.TButton", width=3, command=lambda: self.change_page(1))
        self.next_page.pack(side="right", padx=4)
        self.page_number = ttk.Label(footer, text="1", background="#eaf2ff", foreground="#1769e0", padding=(12, 7), font=("Segoe UI", 10, "bold"))
        self.page_number.pack(side="right", padx=4)

    def build_patient_form(self, parent: ttk.Frame) -> None:
        self.form_title = ttk.Label(parent, text="Быстрое добавление", style="CardTitle.TLabel")
        self.form_title.pack(anchor="w", padx=16, pady=(16, 12))
        self.form_note = ttk.Label(parent, text="* обязательные поля", background="#ffffff", foreground="#7a879d", font=("Segoe UI", 9))
        self.form_note.pack(anchor="w", padx=16, pady=(0, 10))
        self.form_fields: dict[str, tk.Variable] = {}
        self.patient_input_widgets: list[ttk.Widget] = []

        def entry(label: str, key: str, required: bool = False, width: int = 29) -> None:
            ttk.Label(parent, text=label + (" *" if required else ""), background="#ffffff", font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(6, 2))
            var = tk.StringVar()
            widget = ttk.Entry(parent, textvariable=var, width=width)
            widget.pack(fill="x", padx=16)
            self.form_fields[key] = var
            self.patient_input_widgets.append(widget)

        def combo(label: str, key: str, values: list[str], required: bool = False) -> None:
            ttk.Label(parent, text=label + (" *" if required else ""), background="#ffffff", font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(6, 2))
            var = tk.StringVar()
            widget = ttk.Combobox(parent, textvariable=var, values=values, state="normal")
            widget.pack(fill="x", padx=16)
            self.form_fields[key] = var
            self.patient_input_widgets.append(widget)
            setattr(self, f"{key}_combo", widget)

        entry("№ истории", "history", True)
        entry("ФИО", "name", True)
        entry("Возраст", "age")
        ttk.Label(parent, text="Операция", background="#ffffff", font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(6, 2))
        self.form_fields["kind"] = tk.StringVar(value="Плановая")
        toggle = ttk.Frame(parent, style="Card.TFrame")
        toggle.pack(fill="x", padx=16)
        planned = ttk.Radiobutton(toggle, text="Плановая", variable=self.form_fields["kind"], value="Плановая")
        planned.pack(side="left")
        emergency = ttk.Radiobutton(toggle, text="Экстренная", variable=self.form_fields["kind"], value="Экстренная")
        emergency.pack(side="left", padx=9)
        self.patient_input_widgets.extend((planned, emergency))
        entry("Дата операции", "date", True)
        entry("Диагноз", "diagnosis")
        combo("Вид наркоза", "anesthesia", self.settings["anesthesia_types"], True)
        times = ttk.Frame(parent, style="Card.TFrame")
        times.pack(fill="x", padx=16)
        for label, key in (("Начало", "start"), ("Окончание", "end")):
            side = ttk.Frame(times, style="Card.TFrame")
            side.pack(side="left", fill="x", expand=True, padx=(0, 5) if key == "start" else (5, 0))
            ttk.Label(side, text=label, background="#ffffff", font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 2))
            var = tk.StringVar()
            widget = ttk.Entry(side, textvariable=var, width=10)
            widget.pack(fill="x")
            self.form_fields[key] = var
            self.patient_input_widgets.append(widget)
        ttk.Label(parent, text="Длительность (рассчитывается автоматически)", background="#ffffff", foreground="#7a879d", font=("Segoe UI", 8)).pack(anchor="w", padx=16, pady=(8, 2))
        self.duration_label = ttk.Label(parent, text="—", background="#f8faff", foreground="#4d5e79", padding=(8, 5))
        self.duration_label.pack(fill="x", padx=16)
        entry("Название операции", "procedure")
        combo("Врач", "doctor", self.settings["doctors"])
        combo("Медсестра", "nurse", self.settings["nurses"])
        self.save_button = ttk.Button(parent, text="Добавить пациента", style="Primary.TButton", command=self.save_patient)
        self.save_button.pack(fill="x", padx=16, pady=(15, 5))
        self.cancel_button = ttk.Button(parent, text="Отмена", style="Secondary.TButton", command=self.cancel_edit)
        self.cancel_button.pack(fill="x", padx=16, pady=(0, 16))
        self.cancel_button.pack_forget()
        self.form_fields["date"].set(date.today().isoformat())
        self.form_fields["start"].trace_add("write", lambda *_: self.update_duration())
        self.form_fields["end"].trace_add("write", lambda *_: self.update_duration())

    def show_patients(self) -> None:
        self.show_view(self.patient_view, "patients")
        self.refresh_patient_state()

    def refresh_patient_state(self) -> None:
        available = self.db is not None
        if available:
            self.db_notice.pack_forget()
            self.edit_button.configure(state="normal" if self.tree.selection() else "disabled")
            self.set_patient_controls_state("normal")
            self.load_patients()
        else:
            self.db_notice_label.configure(text="База данных недоступна. Просмотр, добавление и редактирование пациентов временно недоступны.")
            self.db_notice.pack(fill="x", padx=34, pady=(0, 8), after=self.patient_header)
            self.edit_button.configure(state="disabled")
            self.set_patient_controls_state("disabled")
            self.clear_tree()
            self.page_info.configure(text="База недоступна")

    def set_patient_controls_state(self, state: str) -> None:
        for widget in (self.name_filter, self.date_filter, self.apply_filters_button, self.reset_filters_button, self.save_button, *self.patient_input_widgets):
            widget.configure(state=state)
        self.prev_page.configure(state=state)
        self.next_page.configure(state=state)
        self.tree.configure(selectmode="browse" if state == "normal" else "none")

    def retry_connection(self) -> None:
        self.connect_database()
        self.refresh_patient_state()

    def query_filters(self) -> tuple[str, list[str]]:
        clauses, params = [], []
        name = self.name_filter.get().strip()
        operation_date = self.date_filter.get().strip()
        if name:
            clauses.append("full_name LIKE ? COLLATE NOCASE")
            params.append(f"%{name}%")
        if operation_date:
            clauses.append("operation_date = ?")
            params.append(operation_date)
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def load_patients(self) -> None:
        if self.db is None:
            return
        where, params = self.query_filters()
        try:
            self.total_rows = int(self.db.execute("SELECT COUNT(*) FROM patients" + where, params).fetchone()[0])
            max_page = max(0, (self.total_rows - 1) // PAGE_SIZE)
            self.page = min(self.page, max_page)
            rows = self.db.execute(
                "SELECT * FROM patients" + where + " ORDER BY operation_date DESC, created_at DESC LIMIT ? OFFSET ?",
                [*params, PAGE_SIZE, self.page * PAGE_SIZE],
            ).fetchall()
        except sqlite3.Error as error:
            self.db_error = str(error)
            self.close_database()
            self.refresh_patient_state()
            return
        self.clear_tree()
        for row in rows:
            duration = self.duration_text(row["anesthesia_start"], row["anesthesia_end"])
            self.tree.insert("", "end", iid=row["history_number"], values=(
                row["history_number"], row["full_name"], row["age"] or "—", row["operation_kind"], row["operation_date"],
                row["diagnosis"] or "—", row["anesthesia_type"], row["anesthesia_start"] or "—", row["anesthesia_end"] or "—",
                duration, row["procedure_name"] or "—", row["doctor"] or "—", row["nurse"] or "—",
            ))
        shown_from = self.page * PAGE_SIZE + 1 if self.total_rows else 0
        shown_to = min((self.page + 1) * PAGE_SIZE, self.total_rows)
        self.page_info.configure(text=f"Показано {shown_from}–{shown_to} из {self.total_rows}")
        self.page_number.configure(text=str(self.page + 1))
        self.prev_page.configure(state="normal" if self.page > 0 else "disabled")
        self.next_page.configure(state="normal" if shown_to < self.total_rows else "disabled")
        self.edit_button.configure(state="disabled")

    def clear_tree(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

    def apply_filters(self) -> None:
        self.page = 0
        self.load_patients()

    def reset_filters(self) -> None:
        self.name_filter.delete(0, "end")
        self.date_filter.delete(0, "end")
        self.apply_filters()

    def change_page(self, delta: int) -> None:
        self.page += delta
        self.load_patients()

    def on_tree_select(self, _event=None) -> None:
        self.edit_button.configure(state="normal" if self.tree.selection() and self.db is not None else "disabled")

    # ---------- patient form ----------
    def update_duration(self) -> None:
        self.duration_label.configure(text=self.duration_text(self.form_fields["start"].get(), self.form_fields["end"].get()))

    @staticmethod
    def duration_text(start: str | None, end: str | None) -> str:
        if not start or not end:
            return "—"
        try:
            start_time = datetime.strptime(start, "%H:%M")
            end_time = datetime.strptime(end, "%H:%M")
        except ValueError:
            return "Укажите ЧЧ:ММ"
        minutes = int((end_time - start_time).total_seconds() // 60)
        if minutes < 0:
            return "Проверьте время"
        return f"{minutes // 60} ч {minutes % 60} мин" if minutes >= 60 else f"{minutes} мин"

    def form_data(self) -> dict[str, str]:
        return {key: value.get().strip() for key, value in self.form_fields.items()}

    def validate_form(self, data: dict[str, str]) -> bool:
        required = {"history": "№ истории", "name": "ФИО", "date": "Дата операции", "anesthesia": "Вид наркоза"}
        missing = [title for key, title in required.items() if not data[key]]
        if missing:
            messagebox.showwarning("Не заполнены поля", "Обязательные поля: " + ", ".join(missing))
            return False
        try:
            datetime.strptime(data["date"], "%Y-%m-%d")
        except ValueError:
            messagebox.showwarning("Дата операции", "Используйте формат ГГГГ-ММ-ДД.")
            return False
        if data["age"]:
            try:
                age = int(data["age"])
                if not 0 <= age <= 130:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Возраст", "Возраст должен быть целым числом от 0 до 130.")
                return False
        duration = self.duration_text(data["start"], data["end"])
        if duration in ("Укажите ЧЧ:ММ", "Проверьте время"):
            messagebox.showwarning("Время наркоза", "Проверьте время начала и окончания (формат ЧЧ:ММ).")
            return False
        return True

    def save_patient(self) -> None:
        if self.db is None:
            return
        data = self.form_data()
        if not self.validate_form(data):
            return
        values = (data["history"], data["name"], int(data["age"]) if data["age"] else None, data["kind"], data["date"], data["diagnosis"], data["anesthesia"], data["start"], data["end"], data["procedure"], data["doctor"], data["nurse"])
        try:
            if self.editing_history is None:
                self.db.execute(
                    "INSERT INTO patients (history_number, full_name, age, operation_kind, operation_date, diagnosis, anesthesia_type, anesthesia_start, anesthesia_end, procedure_name, doctor, nurse) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    values,
                )
            else:
                self.db.execute(
                    "UPDATE patients SET history_number=?, full_name=?, age=?, operation_kind=?, operation_date=?, diagnosis=?, anesthesia_type=?, anesthesia_start=?, anesthesia_end=?, procedure_name=?, doctor=?, nurse=?, updated_at=CURRENT_TIMESTAMP WHERE history_number=?",
                    (*values, self.editing_history),
                )
            self.db.commit()
        except sqlite3.IntegrityError:
            messagebox.showwarning("Не удалось сохранить", "Запись с таким № истории уже существует.")
            return
        except sqlite3.Error as error:
            self.db_error = str(error)
            self.close_database()
            self.refresh_patient_state()
            return
        self.cancel_edit()
        self.load_patients()

    def start_edit(self) -> None:
        if self.db is None or not self.tree.selection():
            return
        history = self.tree.selection()[0]
        try:
            row = self.db.execute("SELECT * FROM patients WHERE history_number = ?", (history,)).fetchone()
        except sqlite3.Error:
            return
        if row is None:
            return
        self.editing_history = history
        mapping = {"history": "history_number", "name": "full_name", "age": "age", "kind": "operation_kind", "date": "operation_date", "diagnosis": "diagnosis", "anesthesia": "anesthesia_type", "start": "anesthesia_start", "end": "anesthesia_end", "procedure": "procedure_name", "doctor": "doctor", "nurse": "nurse"}
        for form_key, db_key in mapping.items():
            self.form_fields[form_key].set(row[db_key] or "")
        self.form_title.configure(text="Редактирование пациента")
        self.save_button.configure(text="Сохранить изменения")
        self.cancel_button.pack(fill="x", padx=16, pady=(0, 16))
        self.update_duration()

    def cancel_edit(self) -> None:
        self.editing_history = None
        for key, var in self.form_fields.items():
            var.set("Плановая" if key == "kind" else "")
        self.form_fields["date"].set(date.today().isoformat())
        self.form_title.configure(text="Быстрое добавление")
        self.save_button.configure(text="Добавить пациента")
        self.cancel_button.pack_forget()
        self.update_duration()

    # ---------- settings ----------
    def build_settings_view(self) -> None:
        ttk.Label(self.settings_view, text="Настройки", style="Title.TLabel").pack(anchor="w", padx=34, pady=(28, 2))
        ttk.Label(self.settings_view, text="Справочники и хранение данных", style="Subtitle.TLabel").pack(anchor="w", padx=34, pady=(0, 18))
        lists = ttk.Frame(self.settings_view, style="App.TFrame")
        lists.pack(fill="both", expand=True, padx=34)
        for index, (title, key, singular) in enumerate((("Виды наркоза", "anesthesia_types", "вид"), ("Врачи", "doctors", "врача"), ("Медсестры", "nurses", "медсестру"))):
            card = ttk.Frame(lists, style="Card.TFrame")
            card.grid(row=0, column=index, sticky="nsew", padx=(0, 12) if index < 2 else 0)
            lists.grid_columnconfigure(index, weight=1)
            self.build_reference_card(card, title, key, singular)
        storage = ttk.Frame(self.settings_view, style="Card.TFrame")
        storage.pack(fill="x", padx=34, pady=18)
        ttk.Label(storage, text="Хранение данных", style="CardTitle.TLabel").pack(anchor="w", padx=18, pady=(16, 10))
        ttk.Label(storage, text="Путь к базе данных", background="#ffffff").pack(anchor="w", padx=18)
        line = ttk.Frame(storage, style="Card.TFrame")
        line.pack(fill="x", padx=18, pady=(4, 8))
        self.db_path_var = tk.StringVar(value=self.settings["db_path"])
        ttk.Entry(line, textvariable=self.db_path_var).pack(side="left", fill="x", expand=True)
        ttk.Button(line, text="Выбрать файл", style="Secondary.TButton", command=self.choose_database).pack(side="left", padx=(8, 0))
        ttk.Button(line, text="Сохранить путь", style="Primary.TButton", command=self.save_database_path).pack(side="left", padx=(8, 0))
        self.connection_status = ttk.Label(storage, text="", background="#ffffff", foreground="#65728a")
        self.connection_status.pack(anchor="w", padx=18, pady=(0, 16))

    def build_reference_card(self, parent: ttk.Frame, title: str, key: str, singular: str) -> None:
        ttk.Label(parent, text=title, style="CardTitle.TLabel").pack(anchor="w", padx=16, pady=(16, 10))
        box = tk.Listbox(parent, height=10, activestyle="none", relief="flat", highlightthickness=1, highlightbackground="#e4e9f2", font=("Segoe UI", 10), selectbackground="#eaf2ff", selectforeground="#1769e0")
        box.pack(fill="both", expand=True, padx=16)
        setattr(self, f"{key}_listbox", box)
        buttons = ttk.Frame(parent, style="Card.TFrame")
        buttons.pack(fill="x", padx=16, pady=(10, 5))
        ttk.Button(buttons, text=f"+ Добавить {singular}", style="Secondary.TButton", command=lambda: self.add_reference(key, title)).pack(side="left")
        ttk.Button(buttons, text="Изменить", style="Secondary.TButton", command=lambda: self.edit_reference(key, title)).pack(side="left", padx=5)
        ttk.Button(buttons, text="Удалить", style="Secondary.TButton", command=lambda: self.delete_reference(key, title)).pack(side="left")
        ttk.Label(parent, text="Отображается в выпадающем списке", background="#ffffff", foreground="#7a879d", font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(2, 16))

    def refresh_reference_lists(self) -> None:
        for key in ("anesthesia_types", "doctors", "nurses"):
            box: tk.Listbox = getattr(self, f"{key}_listbox")
            box.delete(0, "end")
            for item in self.settings[key]:
                box.insert("end", item)
        self.anesthesia_combo.configure(values=self.settings["anesthesia_types"])
        self.doctor_combo.configure(values=self.settings["doctors"])
        self.nurse_combo.configure(values=self.settings["nurses"])

    def reference_value(self, title: str, initial: str = "") -> str | None:
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        ttk.Label(dialog, text=title, font=("Segoe UI", 11, "bold")).pack(padx=20, pady=(18, 8))
        var = tk.StringVar(value=initial)
        entry = ttk.Entry(dialog, textvariable=var, width=38)
        entry.pack(padx=20, pady=(0, 12))
        entry.focus_set()
        result: list[str | None] = [None]
        def accept() -> None:
            text = var.get().strip()
            if text:
                result[0] = text
                dialog.destroy()
        ttk.Button(dialog, text="Сохранить", style="Primary.TButton", command=accept).pack(padx=20, pady=(0, 18))
        dialog.wait_window()
        return result[0]

    def selected_reference(self, key: str) -> tuple[tk.Listbox, int] | None:
        box: tk.Listbox = getattr(self, f"{key}_listbox")
        if not box.curselection():
            messagebox.showinfo("Выберите значение", "Сначала выберите строку в списке.")
            return None
        return box, int(box.curselection()[0])

    def add_reference(self, key: str, title: str) -> None:
        value = self.reference_value(f"Добавить: {title}")
        if value and value not in self.settings[key]:
            self.settings[key].append(value)
            self.save_settings()
            self.refresh_reference_lists()

    def edit_reference(self, key: str, title: str) -> None:
        selected = self.selected_reference(key)
        if not selected:
            return
        _, index = selected
        value = self.reference_value(f"Изменить: {title}", self.settings[key][index])
        if value:
            self.settings[key][index] = value
            self.save_settings()
            self.refresh_reference_lists()

    def delete_reference(self, key: str, title: str) -> None:
        selected = self.selected_reference(key)
        if not selected:
            return
        _, index = selected
        value = self.settings[key][index]
        if messagebox.askyesno("Удалить", f"Удалить «{value}» из справочника «{title}»?"):
            self.settings[key].pop(index)
            self.save_settings()
            self.refresh_reference_lists()

    def choose_database(self) -> None:
        current = self.db_path()
        selected = filedialog.asksaveasfilename(title="Выберите файл базы", initialdir=current.parent, initialfile=current.name, defaultextension=".db", filetypes=[("SQLite", "*.db"), ("Все файлы", "*.*")])
        if selected:
            self.db_path_var.set(selected)

    def save_database_path(self) -> None:
        value = self.db_path_var.get().strip()
        if not value:
            messagebox.showwarning("Путь к базе", "Укажите путь к файлу базы.")
            return
        self.settings["db_path"] = value
        self.save_settings()
        self.connect_database()
        self.update_connection_status()
        self.refresh_patient_state()

    def update_connection_status(self) -> None:
        if self.db is not None:
            self.connection_status.configure(text="База доступна. Выбранный путь сохранён рядом с программой.", foreground="#16835a")
        else:
            self.connection_status.configure(text="База недоступна. Можно изменить путь и повторить подключение.", foreground="#b05600")

    def show_settings(self) -> None:
        self.show_view(self.settings_view, "settings")
        self.db_path_var.set(self.settings["db_path"])
        self.refresh_reference_lists()
        self.update_connection_status()

    def build_reports_view(self) -> None:
        ttk.Label(self.report_view, text="Отчёты", style="Title.TLabel").pack(anchor="w", padx=34, pady=(28, 4))
        ttk.Label(self.report_view, text="Раздел находится в разработке.", style="Subtitle.TLabel").pack(anchor="w", padx=34)

    def show_reports(self) -> None:
        self.show_view(self.report_view, "reports")


if __name__ == "__main__":
    JournalApp().mainloop()
