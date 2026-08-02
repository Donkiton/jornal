"""Визуальный прототип журнала пациентов на Qt.

Запуск: python modern_app.py
"""
from __future__ import annotations

import argparse
import json
import ctypes
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from ctypes import wintypes
from datetime import date, datetime
from pathlib import Path

PROCESS_STARTED_AT = time.perf_counter()

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, QSize, QThread, QTime, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainterPath, QPixmap, QRegion
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QRadioButton, QScrollArea, QSplashScreen,
    QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app_version import APP_VERSION
from database_schema import initialize_schema
from update_system import ReleaseInfo, apply_staged_update, find_newer_release, prepare_release


IS_FROZEN = bool(getattr(sys, "frozen", False))
APP_DIR = Path(sys.executable).resolve().parent if IS_FROZEN else Path(__file__).resolve().parent
LOCAL_STATE_DIR = (
    Path(os.environ.get("LOCALAPPDATA", str(APP_DIR))) / "JornalPatients"
    if IS_FROZEN else APP_DIR
)
LEGACY_CONFIG_PATH = APP_DIR / "settings.json"
LOCAL_LEGACY_SETTINGS_PATH = LOCAL_STATE_DIR / "settings.json"
LOCAL_CONNECTION_PATH = LOCAL_STATE_DIR / "connection.json"
SHARED_SETTINGS_NAME = "settings.json"
# При сборке PyInstaller помещает добавленные данные в _internal. Настройки и
# диагностические файлы храним в локальном профиле, а неизменяемые ресурсы
# берём из папки сборки.
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
ICON_DIR = RESOURCE_DIR / "assets" / "icons"
LOG_DIR = LOCAL_STATE_DIR / "logs"
STARTUP_LOG_PATH = LOG_DIR / "startup.log"
UPDATE_CACHE_DIR = LOCAL_STATE_DIR / "updates"
PAGE_SIZE = 10
DEFAULT_SETTINGS = {
    "database_root": "", "last_backup_week": "",
    "window_geometry": None,
    "window_maximized": False,
    "startup_logging": False,
    "anesthesia_types": ["Общая эндотрахеальная", "Спинальная", "Местная", "Проводниковая", "Седация"],
    "doctors": ["Смирнов И. П.", "Соколов Д. А.", "Павлов Р. А."],
    "nurses": ["Кузнецова О. В.", "Морозова Т. С.", "Иванова Е. П."],
    "reference_dialog_size": [560, 300],
}


QSS = """
* { font-family: '-apple-system', 'Segoe UI Variable', 'Segoe UI'; color: #1d1d1f; }
QMainWindow { background: #f5f5f7; }
QWidget#root { background: #f5f5f7; border: 1px solid #dedee3; border-radius: 10px; }
QFrame#titlebar { background: #f8f8fa; border-bottom: 1px solid #e5e5ea; border-top-left-radius: 10px; border-top-right-radius: 10px; }
QWidget#shell { background: #f5f5f7; border-bottom-left-radius: 10px; border-bottom-right-radius: 10px; }
QLabel#windowTitle { color: #1d1d1f; font-size: 13px; font-weight: 700; }
QLabel#windowSubtitle { color: #8e8e93; font-size: 10px; }
QLabel#connectionChip { color: #6e6e73; font-size: 11px; padding: 2px 8px; }
QPushButton#closeControl, QPushButton#minimizeControl, QPushButton#maximizeControl { border-radius: 6px; min-width: 12px; max-width: 12px; min-height: 12px; max-height: 12px; padding: 0; }
QPushButton#closeControl { background: #ff5f57; border: 1px solid #e0443e; }
QPushButton#minimizeControl { background: #ffbd2e; border: 1px solid #dfa321; }
QPushButton#maximizeControl { background: #28c840; border: 1px solid #1faa35; }
QPushButton#closeControl:hover { background: #ff7770; }
QPushButton#minimizeControl:hover { background: #ffcd5c; }
QPushButton#maximizeControl:hover { background: #55d369; }
QFrame#sidebar { background: #f8f8fa; border-right: 1px solid #e5e5ea; border-bottom-left-radius: 10px; }
QFrame#card { background: #ffffff; border: 1px solid #e5e5ea; border-radius: 14px; }
QLabel#title { font-size: 28px; font-weight: 700; color: #1d1d1f; letter-spacing: -0.7px; }
QLabel#muted { color: #6e6e73; font-size: 12px; }
QLabel#section { font-size: 14px; font-weight: 700; color: #1d1d1f; }
QLabel#reportMetric { color: #1d1d1f; font-size: 30px; font-weight: 700; letter-spacing: -0.6px; }
QLabel#reportMetricLabel { color: #6e6e73; font-size: 12px; }
QPushButton { border: 0; border-radius: 8px; padding: 9px 12px; font-size: 13px; background: transparent; }
QPushButton:hover { background: #ececf0; }
QPushButton:pressed { background: #e0e0e5; }
QPushButton#nav { text-align: left; padding: 10px 12px; color: #515154; }
QPushButton#nav:hover { color: #007aff; }
QPushButton#nav:checked { background: #e8f1ff; color: #007aff; font-weight: 600; }
QPushButton#primary { background: #007aff; color: white; font-weight: 600; padding: 10px 14px; }
QPushButton#primary:hover { background: #0071e3; }
QPushButton#primary:disabled { background: #c7d8ee; color: #f7fbff; }
QPushButton#outline { border: 1px solid #d2d2d7; background: white; color: #007aff; font-weight: 600; }
QPushButton#outline:hover { background: #f4f8ff; }
QPushButton#danger { background: #d1544d; color: white; font-weight: 600; }
QPushButton#danger:hover { background: #bb433e; }
QPushButton#danger:pressed { background: #a83834; }
QLineEdit, QComboBox { background: white; border: 1px solid #d2d2d7; border-radius: 8px; padding: 8px 10px; min-height: 20px; }
QLineEdit:focus, QComboBox:focus { border: 2px solid #007aff; }
QLineEdit:disabled, QComboBox:disabled { background: #f2f2f7; color: #8e8e93; }
QLineEdit[invalidTime="true"] { border: 2px solid #ff3b30; background: #fff8f7; }
QDialog#referenceDialog { background: #4d5562; border: 0; border-radius: 10px; }
QFrame#dialogTitlebar { background: #f8f8fa; border-bottom: 1px solid #e5e5ea; border-top-left-radius: 10px; border-top-right-radius: 10px; }
QLabel#dialogWindowTitle { color: #1d1d1f; font-size: 12px; font-weight: 700; }
QWidget#dialogBody { background: #f5f5f7; border-bottom-left-radius: 10px; border-bottom-right-radius: 10px; }
QFrame#dialogContent { background: white; border: 1px solid #e5e5ea; border-radius: 14px; }
QLabel#dialogEyebrow { color: #6e6e73; font-size: 11px; font-weight: 600; }
QLabel#dialogTitle { color: #1d1d1f; font-size: 20px; font-weight: 700; }
QLabel#dialogWarning { color: #d1544d; font-size: 11px; font-weight: 700; letter-spacing: 0.6px; }
QComboBox::drop-down { border: 0; width: 25px; }
QTableWidget { background: white; border: none; gridline-color: #f0f0f2; selection-background-color: #e8f1ff; selection-color: #1d1d1f; font-size: 12px; }
QHeaderView::section { background: #fbfbfc; border-top: 0; border-left: 0; border-right: 1px solid #c2c6ce; border-bottom: 1px solid #d5d8de; color: #535761; font-size: 11px; font-weight: 600; padding: 11px 8px; }
QHeaderView::section:hover { background: #f1f4f8; border-right: 2px solid #8f96a3; color: #1d1d1f; }
QTableWidget::item { border-bottom: 1px solid #f0f0f2; padding: 7px; }
QScrollBar { background: transparent; margin: 0; }
QScrollBar:horizontal { height: 10px; }
QScrollBar:vertical { width: 10px; }
QScrollBar::handle:horizontal, QScrollBar::handle:vertical { background: #c7c7cc; border-radius: 5px; }
QScrollBar::handle:horizontal { min-width: 40px; }
QScrollBar::handle:vertical { min-height: 40px; }
QScrollBar::handle:hover { background: #aeaeb2; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QListWidget { border: 1px solid #d2d2d7; border-radius: 8px; padding: 3px; background: white; }
QListWidget::item { padding: 9px; border-bottom: 1px solid #f0f0f2; }
QListWidget::item:selected { background: #e8f1ff; color: #007aff; border-radius: 5px; }
QRadioButton { padding: 8px 10px; border: 1px solid #d2d2d7; border-radius: 8px; background: white; }
QRadioButton::indicator { width: 0; height: 0; }
QRadioButton:checked { background: #e8f1ff; border-color: #8ec4ff; color: #007aff; font-weight: 600; }
QProgressBar { background: #e9e9ed; border: 0; border-radius: 5px; min-height: 10px; max-height: 10px; color: transparent; }
QProgressBar::chunk { background: #007aff; border-radius: 5px; }
"""


class _Overlapped(ctypes.Structure):
    _fields_ = [
        ("internal", ctypes.c_size_t),
        ("internal_high", ctypes.c_size_t),
        ("offset", wintypes.DWORD),
        ("offset_high", wintypes.DWORD),
        ("event", wintypes.HANDLE),
    ]


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_create_file = _kernel32.CreateFileW
_create_file.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
_create_file.restype = wintypes.HANDLE
_lock_file_ex = _kernel32.LockFileEx
_lock_file_ex.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(_Overlapped)]
_lock_file_ex.restype = wintypes.BOOL
_unlock_file_ex = _kernel32.UnlockFileEx
_unlock_file_ex.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(_Overlapped)]
_unlock_file_ex.restype = wintypes.BOOL
_close_handle = _kernel32.CloseHandle
_close_handle.argtypes = [wintypes.HANDLE]
_close_handle.restype = wintypes.BOOL
_delete_file = _kernel32.DeleteFileW
_delete_file.argtypes = [wintypes.LPCWSTR]
_delete_file.restype = wintypes.BOOL

_GENERIC_READ, _GENERIC_WRITE = 0x80000000, 0x40000000
_FILE_SHARE_READ, _FILE_SHARE_WRITE, _FILE_SHARE_DELETE = 0x1, 0x2, 0x4
_OPEN_ALWAYS, _FILE_ATTRIBUTE_NORMAL = 4, 0x80
_LOCKFILE_FAIL_IMMEDIATELY, _LOCKFILE_EXCLUSIVE_LOCK = 0x1, 0x2
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


def migrate_legacy_settings() -> None:
    """Сохраняет совместимость с настройками сборок до версии 1.0.1."""
    try:
        LOCAL_STATE_DIR.mkdir(parents=True, exist_ok=True)
        if (
            LOCAL_LEGACY_SETTINGS_PATH != LEGACY_CONFIG_PATH
            and LEGACY_CONFIG_PATH.is_file()
            and not LOCAL_LEGACY_SETTINGS_PATH.exists()
        ):
            shutil.copy2(LEGACY_CONFIG_PATH, LOCAL_LEGACY_SETTINGS_PATH)
        if not LOCAL_CONNECTION_PATH.exists():
            for candidate in (LOCAL_LEGACY_SETTINGS_PATH, LEGACY_CONFIG_PATH):
                source = read_json_object(candidate)
                database_root = source.get("database_root")
                if isinstance(database_root, str) and database_root.strip():
                    write_json_atomic(
                        LOCAL_CONNECTION_PATH,
                        {"database_root": str(normalize_database_root(database_root))},
                    )
                    break
    except OSError:
        # Ошибка миграции будет корректно обработана при сохранении настроек.
        pass


def read_json_object(path: Path) -> dict:
    try:
        source = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}
    return source if isinstance(source, dict) else {}


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary_path, path)


def load_local_database_root() -> Path | None:
    for candidate in (
        LOCAL_CONNECTION_PATH,
        LOCAL_LEGACY_SETTINGS_PATH,
        LEGACY_CONFIG_PATH,
    ):
        source = read_json_object(candidate)
        database_root = source.get("database_root")
        if isinstance(database_root, str) and database_root.strip():
            return normalize_database_root(database_root)
    return None


def shared_settings_path(root: Path) -> Path:
    return root / SHARED_SETTINGS_NAME


def archive_local_legacy_settings() -> None:
    """Убирает устаревший локальный settings.json, не удаляя его безвозвратно."""
    if not LOCAL_LEGACY_SETTINGS_PATH.is_file():
        return
    backup_path = LOCAL_STATE_DIR / "settings.local-backup.json"
    if not backup_path.exists():
        LOCAL_LEGACY_SETTINGS_PATH.replace(backup_path)


def normalize_database_root(value: str | Path) -> Path:
    """Принимает прямые и обратные разделители, сохраняя UNC-префикс."""
    raw = str(value).strip().strip('"')
    if raw.startswith("//"):
        raw = "\\\\" + raw[2:]
    raw = raw.replace("/", "\\")
    return Path(os.path.normpath(raw)).expanduser()


def parse_clock_time(value: str) -> QTime | None:
    """Разбирает время в формате ЧЧ:ММ или компактном ЧЧММ."""
    normalized = value.strip()
    if normalized.isdigit() and len(normalized) in (3, 4):
        normalized = normalized.zfill(4)
        normalized = f"{normalized[:2]}:{normalized[2:]}"
    for format_string in ("HH:mm", "H:mm"):
        parsed = QTime.fromString(normalized, format_string)
        if parsed.isValid():
            return parsed
    return None


def create_startup_splash() -> QSplashScreen:
    """Показывает логотип, пока приложение открывает базу и строит интерфейс."""
    pixmap = QPixmap(str(ICON_DIR / "logo.png")).scaled(
        160, 160,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    return QSplashScreen(pixmap)


class TitleBar(QFrame):
    """Перетаскиваемая пользовательская верхняя панель окна Windows."""
    def __init__(self, window: "JournalWindow") -> None:
        super().__init__()
        self.window = window
        self.drag_offset: QPoint | None = None
        self.setObjectName("titlebar")
        self.setFixedHeight(42)
        self.setMouseTracking(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(0)

        status_area = QWidget()
        status_area.setFixedWidth(160)
        status_layout = QHBoxLayout(status_area)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(0)
        self.connection_chip = QLabel("● Проверка базы")
        self.connection_chip.setObjectName("connectionChip")
        status_layout.addWidget(self.connection_chip)
        status_layout.addStretch()
        layout.addWidget(status_area)
        layout.addStretch(1)

        title = QLabel("Журнал пациентов")
        title.setObjectName("windowTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addStretch(1)

        controls = QWidget()
        controls.setFixedWidth(160)
        control_layout = QHBoxLayout(controls)
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.setSpacing(8)
        # Цвета и расположение оставлены как в макете: зелёная кнопка слева,
        # оранжевая рядом с ней. Меняем только назначение действий.
        minimize = self.control("Свернуть окно", self.window.showMinimized, "maximizeControl")
        self.maximize = self.control("Развернуть окно", self.window.toggle_maximized, "minimizeControl")
        close = self.control("Закрыть окно", self.window.close, "closeControl")
        control_layout.addStretch()
        control_layout.addWidget(minimize)
        control_layout.addWidget(self.maximize)
        control_layout.addWidget(close)
        layout.addWidget(controls)

    @staticmethod
    def control(tooltip: str, slot, object_name: str) -> QPushButton:
        button = QPushButton()
        button.setObjectName(object_name)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.clicked.connect(slot)
        return button

    def set_connection_state(self, available: bool) -> None:
        if available:
            self.connection_chip.setText("● Общая база")
            self.connection_chip.setStyleSheet("")
        else:
            self.connection_chip.setText("● База недоступна")
            self.connection_chip.setStyleSheet("color:#c05c00;")

    def update_maximize_control(self, maximized: bool) -> None:
        self.maximize.setToolTip("Восстановить размер окна" if maximized else "Развернуть окно")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self.window.isMaximized():
            self.drag_offset = event.globalPosition().toPoint() - self.window.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window.move(event.globalPosition().toPoint() - self.drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self.drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.window.toggle_maximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class TimeField(QLineEdit):
    """Поле необязательного времени с явным разбором значения через QTime."""
    def __init__(self) -> None:
        super().__init__()
        self.setPlaceholderText("ЧЧ:ММ")
        self.setMaxLength(5)
        self.textEdited.connect(self.clear_invalid_state)
        self.editingFinished.connect(self.normalize)

    def parsed_time(self) -> QTime | None:
        return parse_clock_time(self.text())

    def clear_invalid_state(self) -> None:
        self.setProperty("invalidTime", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def normalize(self) -> None:
        value = self.text().strip()
        parsed = self.parsed_time()
        if not value:
            self.clear_invalid_state()
        elif parsed:
            self.setText(parsed.toString("HH:mm"))
            self.clear_invalid_state()
        else:
            self.setProperty("invalidTime", True)
            self.style().unpolish(self)
            self.style().polish(self)


class StartupLogger:
    """Короткий диагностический лог времени запуска без данных пациентов."""
    def __init__(self) -> None:
        self.enabled = self.settings_enable_logging()

    @staticmethod
    def settings_enable_logging() -> bool:
        root = load_local_database_root()
        settings = read_json_object(shared_settings_path(root)) if root else {}
        if not settings:
            settings = read_json_object(LOCAL_LEGACY_SETTINGS_PATH)
        return settings.get("startup_logging") is True

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def log(self, stage: str) -> None:
        if not self.enabled:
            return
        try:
            LOG_DIR.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            elapsed_ms = (time.perf_counter() - PROCESS_STARTED_AT) * 1000
            with STARTUP_LOG_PATH.open("a", encoding="utf-8") as file:
                file.write(f"{timestamp}\t{elapsed_ms:8.1f} мс\t{stage}\n")
        except OSError:
            # Диагностика не должна влиять на доступность журнала.
            pass


ACTIVE_STARTUP_LOGGER: StartupLogger | None = None


class DataStore:
    def __init__(self) -> None:
        migrate_legacy_settings()
        self.settings = self.load_settings()
        self.conn: sqlite3.Connection | None = None
        self.connected_root: Path | None = None
        self.error = ""

    @staticmethod
    def validated_settings(source: dict, root: Path | None = None) -> dict:
        settings = {**DEFAULT_SETTINGS, **source}
        settings.pop("db_path", None)
        for key in ("anesthesia_types", "doctors", "nurses"):
            value = settings.get(key)
            settings[key] = list(value) if isinstance(value, list) else DEFAULT_SETTINGS[key].copy()
        dialog_size = settings.get("reference_dialog_size")
        if not (isinstance(dialog_size, list) and len(dialog_size) == 2 and all(isinstance(value, int) and value > 0 for value in dialog_size)):
            settings["reference_dialog_size"] = DEFAULT_SETTINGS["reference_dialog_size"].copy()
        if not isinstance(settings.get("startup_logging"), bool):
            settings["startup_logging"] = False
        if not isinstance(settings.get("database_root"), str):
            settings["database_root"] = ""
        if root is not None:
            settings["database_root"] = str(root)
        return settings

    def load_settings(self) -> dict:
        root = load_local_database_root()
        source: dict = {}
        if root is not None:
            path = shared_settings_path(root)
            if path.is_file():
                source = read_json_object(path)
        if not source:
            source = read_json_object(LOCAL_LEGACY_SETTINGS_PATH)
        if not source:
            source = read_json_object(LEGACY_CONFIG_PATH)
        return self.validated_settings(source, root)

    def save_settings(self) -> None:
        root = self.database_root
        if root is None:
            raise OSError("Папка общей базы не выбрана")
        self.settings["database_root"] = str(root)
        write_json_atomic(shared_settings_path(root), self.settings)
        write_json_atomic(LOCAL_CONNECTION_PATH, {"database_root": str(root)})
        archive_local_legacy_settings()

    @property
    def database_root(self) -> Path | None:
        value = self.settings["database_root"].strip()
        return normalize_database_root(value) if value else None

    @property
    def is_configured(self) -> bool:
        return self.database_root is not None

    @property
    def db_path(self) -> Path:
        root = self.connected_root or self.database_root
        if root is None:
            raise RuntimeError("Папка базы данных не выбрана")
        return root / "data" / "journal.db"

    @property
    def backup_dir(self) -> Path:
        root = self.connected_root or self.database_root
        if root is None:
            raise RuntimeError("Папка базы данных не выбрана")
        return root / "backups"

    @property
    def lock_path(self) -> Path:
        root = self.database_root
        if root is None:
            raise RuntimeError("Папка базы данных не выбрана")
        return root / ".journal.lock"

    @property
    def updates_dir(self) -> Path:
        root = self.connected_root or self.database_root
        if root is None:
            raise RuntimeError("Папка базы данных не выбрана")
        return root / "UPD"

    @staticmethod
    def prepare_shared_root(value: str | Path) -> Path:
        """Проверяет доступ и создаёт служебную структуру общей папки."""
        root = normalize_database_root(value)
        if not root.is_dir():
            raise FileNotFoundError("Указанная папка журнала не найдена")

        probe = root / f".journal-access-{os.getpid()}.tmp"
        try:
            probe.write_text("access", encoding="utf-8")
            probe.unlink()
            (root / "data").mkdir(parents=True, exist_ok=True)
            (root / "backups").mkdir(parents=True, exist_ok=True)
            (root / "UPD" / "releases").mkdir(parents=True, exist_ok=True)
        finally:
            try:
                if probe.exists():
                    probe.unlink()
            except OSError:
                pass
        return root

    def activate_shared_settings(self, value: str | Path) -> None:
        """Загружает настройки выбранной базы или создаёт их рядом с ней."""
        root = normalize_database_root(value)
        previous_root = self.database_root
        path = shared_settings_path(root)
        if path.is_file():
            source = read_json_object(path)
        elif previous_root == root:
            # Первый запуск 1.0.1: переносим локальные настройки версии 1.0.0.
            source = self.settings
        else:
            source = {}
        self.settings = self.validated_settings(source, root)
        if previous_root != root:
            self.settings["last_backup_week"] = ""
        self.save_settings()

    def set_database_root(self, value: str | Path) -> None:
        self.activate_shared_settings(value)

    @staticmethod
    def _initialize_schema(connection: sqlite3.Connection) -> None:
        initialize_schema(connection)

    def connect(self, value: str | Path | None = None) -> bool:
        target = normalize_database_root(value) if value is not None else self.database_root
        if target is None:
            self.error = "Папка базы данных не выбрана"
            return False
        new_connection: sqlite3.Connection | None = None
        try:
            target = self.prepare_shared_root(target)
            new_connection = sqlite3.connect(target / "data" / "journal.db", timeout=5)
            new_connection.row_factory = sqlite3.Row
            new_connection.execute("PRAGMA busy_timeout=5000")
            # WAL использует общий shm-файл и ненадёжен на сетевых ресурсах.
            # Эксклюзивный lock приложения позволяет использовать обычный журнал.
            new_connection.execute("PRAGMA journal_mode=DELETE")
            self._initialize_schema(new_connection)
            old_connection = self.conn
            self.conn = new_connection
            self.connected_root = target
            if old_connection:
                try:
                    old_connection.close()
                except sqlite3.Error:
                    pass
            self.error = ""
            return True
        except (OSError, sqlite3.Error) as exc:
            self.error = str(exc)
            if new_connection:
                try:
                    new_connection.close()
                except sqlite3.Error:
                    pass
            return False

    def close(self) -> None:
        if self.conn:
            try: self.conn.close()
            except sqlite3.Error: pass
        self.conn = None
        self.connected_root = None

    def backup_if_needed(self) -> None:
        week = date.today().strftime("%G-W%V")
        if self.settings.get("last_backup_week") == week or not self.db_path.exists(): return
        self.backup_dir.mkdir(exist_ok=True)
        target = self.backup_dir / f"journal-{week}.db"
        if not target.exists():
            backup = sqlite3.connect(target)
            try:
                assert self.conn is not None
                self.conn.backup(backup)
                backup.commit()
            finally:
                backup.close()
        self.settings["last_backup_week"] = week
        self.save_settings()


class ProgramInstanceLock:
    """Эксклюзивная блокировка для общей папки приложения в сети."""
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: int | None = None
        self.overlapped = _Overlapped()
        self.error_code = 0

    def acquire(self) -> bool:
        ctypes.set_last_error(0)
        handle = _create_file(
            str(self.path),
            _GENERIC_READ | _GENERIC_WRITE,
            _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE,
            None,
            _OPEN_ALWAYS,
            _FILE_ATTRIBUTE_NORMAL,
            None,
        )
        if handle == _INVALID_HANDLE_VALUE:
            self.error_code = ctypes.get_last_error()
            return False
        if not _lock_file_ex(handle, _LOCKFILE_EXCLUSIVE_LOCK | _LOCKFILE_FAIL_IMMEDIATELY, 0, 1, 0, ctypes.byref(self.overlapped)):
            self.error_code = ctypes.get_last_error()
            _close_handle(handle)
            return False
        self.handle = handle
        self.error_code = 0
        return True

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            # Открываем файл с FILE_SHARE_DELETE: DeleteFileW помечает его к
            # удалению, но не даёт новой копии открыть старое имя до close.
            _delete_file(str(self.path))
        finally:
            _unlock_file_ex(self.handle, 0, 1, 0, ctypes.byref(self.overlapped))
            _close_handle(self.handle)
            self.handle = None


class DialogTitleBar(QFrame):
    """Компактная macOS-панель для модальных окон приложения."""
    def __init__(self, dialog: QDialog, title: str) -> None:
        super().__init__()
        self.dialog = dialog
        self.drag_offset: QPoint | None = None
        self.setObjectName("dialogTitlebar")
        self.setFixedHeight(42)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(0)

        spacer = QWidget()
        spacer.setFixedWidth(120)
        layout.addWidget(spacer)
        layout.addStretch(1)

        label = QLabel(title)
        label.setObjectName("dialogWindowTitle")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        layout.addStretch(1)

        controls = QWidget()
        controls.setFixedWidth(120)
        control_layout = QHBoxLayout(controls)
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.setSpacing(8)
        control_layout.addStretch()
        close = QPushButton()
        close.setObjectName("closeControl")
        close.setToolTip("Закрыть окно")
        close.setAccessibleName("Закрыть окно")
        close.clicked.connect(self.dialog.reject)
        control_layout.addWidget(close)
        layout.addWidget(controls)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_offset = event.globalPosition().toPoint() - self.dialog.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.dialog.move(event.globalPosition().toPoint() - self.drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self.drag_offset = None
        super().mouseReleaseEvent(event)


class ReferenceValueDialog(QDialog):
    """Безрамочный диалог добавления и изменения справочника в стиле приложения."""
    def __init__(self, action: str, reference_title: str, value: str, saved_size: list[int], parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("referenceDialog")
        self.setWindowTitle(f"{action} · {reference_title}")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(480, 320)
        self.resize(*saved_size)

        outer = QVBoxLayout(self)
        # Оставляем отдельную полосу внешнего контура: дочерние виджеты
        # не могут перекрыть её своей заливкой.
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        self.titlebar = DialogTitleBar(self, f"{action} · {reference_title}")
        outer.addWidget(self.titlebar)

        body = QWidget()
        body.setObjectName("dialogBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 20, 20, 20)
        content = QFrame()
        content.setObjectName("dialogContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(10)

        eyebrow = QLabel(reference_title.upper())
        eyebrow.setObjectName("dialogEyebrow")
        title = QLabel(action)
        title.setObjectName("dialogTitle")
        prompt = QLabel("Введите значение для справочника")
        prompt.setObjectName("muted")
        self.input = QLineEdit(value)
        self.input.setPlaceholderText("Например, новое значение")
        self.input.setClearButtonEnabled(True)
        self.input.returnPressed.connect(self.accept)

        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("Отмена")
        cancel.setObjectName("outline")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Сохранить")
        save.setObjectName("primary")
        save.clicked.connect(self.accept)
        actions.addWidget(cancel)
        actions.addWidget(save)

        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(prompt)
        layout.addWidget(self.input)
        layout.addLayout(actions)
        body_layout.addWidget(content)
        outer.addWidget(body, 1)
        self.input.setFocus()
        self.update_window_mask()
        for widget in self.findChildren(QWidget):
            widget.setMouseTracking(True)
            widget.installEventFilter(self)

    def update_window_mask(self) -> None:
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 10, 10)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.update_window_mask()

    def eventFilter(self, source, event) -> bool:
        if event.type() not in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress) or not hasattr(event, "globalPosition"):
            return super().eventFilter(source, event)
        point = self.mapFromGlobal(event.globalPosition().toPoint())
        margin, width, height = 7, self.width(), self.height()
        edges = Qt.Edge(0)
        if point.x() <= margin: edges |= Qt.Edge.LeftEdge
        elif point.x() >= width - margin: edges |= Qt.Edge.RightEdge
        if point.y() <= margin: edges |= Qt.Edge.TopEdge
        elif point.y() >= height - margin: edges |= Qt.Edge.BottomEdge
        if event.type() == QEvent.Type.MouseMove:
            if edges in (Qt.Edge.LeftEdge, Qt.Edge.RightEdge): cursor = Qt.CursorShape.SizeHorCursor
            elif edges in (Qt.Edge.TopEdge, Qt.Edge.BottomEdge): cursor = Qt.CursorShape.SizeVerCursor
            elif edges in (Qt.Edge.TopEdge | Qt.Edge.LeftEdge, Qt.Edge.BottomEdge | Qt.Edge.RightEdge): cursor = Qt.CursorShape.SizeFDiagCursor
            elif edges: cursor = Qt.CursorShape.SizeBDiagCursor
            else:
                self.unsetCursor()
                return super().eventFilter(source, event)
            self.setCursor(cursor)
        elif edges and event.button() == Qt.MouseButton.LeftButton and self.windowHandle():
            if self.windowHandle().startSystemResize(edges):
                return True
        return super().eventFilter(source, event)

    def value(self) -> str:
        return self.input.text().strip()


class PatientDeleteDialog(QDialog):
    """Подтверждение удаления пациента в визуальном стиле приложения."""
    def __init__(self, patient_name: str, history_number: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("referenceDialog")
        self.setWindowTitle("Удалить пациента")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(500, 300)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        outer.addWidget(DialogTitleBar(self, "Удалить пациента"))

        body = QWidget()
        body.setObjectName("dialogBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 20, 20, 20)
        content = QFrame()
        content.setObjectName("dialogContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(10)

        eyebrow = QLabel("УДАЛЕНИЕ ИЗ ЖУРНАЛА")
        eyebrow.setObjectName("dialogEyebrow")
        title = QLabel("Удалить пациента?")
        title.setObjectName("dialogTitle")
        details = QLabel(f"Будет удалена запись № {history_number}: {patient_name}.")
        details.setObjectName("muted")
        details.setWordWrap(True)
        warning = QLabel("Это действие нельзя отменить.")
        warning.setObjectName("muted")
        warning.setStyleSheet("color:#a13d38;")

        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("Отмена")
        cancel.setObjectName("outline")
        cancel.clicked.connect(self.reject)
        confirm = QPushButton("Удалить пациента")
        confirm.setObjectName("danger")
        confirm.clicked.connect(self.accept)
        actions.addWidget(cancel)
        actions.addWidget(confirm)

        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(details)
        layout.addWidget(warning)
        layout.addStretch()
        layout.addLayout(actions)
        body_layout.addWidget(content)
        outer.addWidget(body, 1)
        self.update_window_mask()

    def update_window_mask(self) -> None:
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 10, 10)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))


class ValidationErrorDialog(QDialog):
    """Неблокирующее по стилю, но модальное уведомление об ошибке ввода."""
    def __init__(self, title: str, message: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("referenceDialog")
        self.setWindowTitle(title)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(500, 280)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        outer.addWidget(DialogTitleBar(self, title))

        body = QWidget()
        body.setObjectName("dialogBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 20, 20, 20)
        content = QFrame()
        content.setObjectName("dialogContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(10)

        eyebrow = QLabel("ТРЕБУЕТСЯ ВНИМАНИЕ")
        eyebrow.setObjectName("dialogWarning")
        heading = QLabel(title)
        heading.setObjectName("dialogTitle")
        details = QLabel(message)
        details.setObjectName("muted")
        details.setWordWrap(True)

        actions = QHBoxLayout()
        actions.addStretch()
        acknowledge = QPushButton("Понятно")
        acknowledge.setObjectName("primary")
        acknowledge.clicked.connect(self.accept)
        actions.addWidget(acknowledge)

        layout.addWidget(eyebrow)
        layout.addWidget(heading)
        layout.addWidget(details)
        layout.addStretch()
        layout.addLayout(actions)
        body_layout.addWidget(content)
        outer.addWidget(body, 1)
        self.update_window_mask()
        acknowledge.setFocus()

    def update_window_mask(self) -> None:
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 10, 10)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))


class DatabaseFolderDialog(QDialog):
    """Первичная настройка общей папки журнала и базы данных."""
    def __init__(self, initial_path: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("referenceDialog")
        self.setWindowTitle("Выбор папки журнала")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(560, 350)
        self.resize(640, 380)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        outer.addWidget(DialogTitleBar(self, "Выбор папки журнала"))
        body = QWidget()
        body.setObjectName("dialogBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 20, 20, 20)
        content = QFrame()
        content.setObjectName("dialogContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(10)

        eyebrow = QLabel("ПЕРВИЧНАЯ НАСТРОЙКА")
        eyebrow.setObjectName("dialogEyebrow")
        title = QLabel("Где находится общий журнал?")
        title.setObjectName("dialogTitle")
        details = QLabel(
            "Выберите общую папку. При необходимости в ней будут созданы "
            "data\\journal.db, backups и UPD."
        )
        details.setObjectName("muted")
        details.setWordWrap(True)
        row = QHBoxLayout()
        self.path_field = QLineEdit(initial_path)
        self.path_field.setPlaceholderText(
            "//fs.acrb-amursk.ru/common/РАО/Пациенты/Jornal-oper"
        )
        self.path_field.setClearButtonEnabled(True)
        self.path_field.returnPressed.connect(self.accept)
        browse = QPushButton("Выбрать папку")
        browse.setObjectName("outline")
        browse.clicked.connect(self.choose_folder)
        row.addWidget(self.path_field, 1)
        row.addWidget(browse)
        self.error_label = QLabel()
        self.error_label.setObjectName("muted")
        self.error_label.setStyleSheet("color:#d1544d;")
        self.error_label.setWordWrap(True)
        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("Отмена")
        cancel.setObjectName("outline")
        cancel.clicked.connect(self.reject)
        continue_button = QPushButton("Подключить")
        continue_button.setObjectName("primary")
        continue_button.clicked.connect(self.accept)
        actions.addWidget(cancel)
        actions.addWidget(continue_button)
        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(details)
        layout.addLayout(row)
        layout.addWidget(self.error_label)
        layout.addStretch()
        layout.addLayout(actions)
        body_layout.addWidget(content)
        outer.addWidget(body, 1)
        self.path_field.setFocus()
        self.update_window_mask()

    def choose_folder(self) -> None:
        current = self.path_field.text().strip()
        try:
            initial = str(normalize_database_root(current)) if current else str(APP_DIR)
        except (OSError, ValueError):
            initial = str(APP_DIR)
        path = QFileDialog.getExistingDirectory(
            self, "Выберите папку журнала", initial, QFileDialog.Option.ShowDirsOnly
        )
        if path:
            self.path_field.setText(path)
            self.error_label.clear()

    def selected_path(self) -> Path | None:
        value = self.path_field.text().strip()
        return normalize_database_root(value) if value else None

    def accept(self) -> None:
        path = self.selected_path()
        if path is None:
            self.error_label.setText("Укажите папку общего журнала.")
            return
        try:
            DataStore.prepare_shared_root(path)
        except OSError:
            self.error_label.setText(
                "Нет доступа к этой папке. Проверьте сеть и права на запись "
                "или обратитесь к системному администратору."
            )
            return
        super().accept()

    def update_window_mask(self) -> None:
        path = QPainterPath(); path.addRoundedRect(QRectF(self.rect()), 10, 10); self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.update_window_mask()


class DatabaseAccessDialog(QDialog):
    """Выбор действия, когда сохранённая общая база недоступна."""

    RETRY = 1
    CHOOSE_ANOTHER = 2

    def __init__(self, path: Path, details: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("referenceDialog")
        self.setWindowTitle("Нет доступа к базе данных")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(620, 380)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        outer.addWidget(DialogTitleBar(self, "Нет доступа к базе данных"))
        body = QWidget()
        body.setObjectName("dialogBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 20, 20, 20)
        content = QFrame()
        content.setObjectName("dialogContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(10)

        eyebrow = QLabel("ПОДКЛЮЧЕНИЕ НЕ ВЫПОЛНЕНО")
        eyebrow.setObjectName("dialogWarning")
        heading = QLabel("Нет доступа к базе данных")
        heading.setObjectName("dialogTitle")
        message = QLabel(
            "Проверьте подключение к сети или обратитесь к системному администратору. "
            "Можно повторить попытку либо указать другую общую базу."
        )
        message.setObjectName("muted")
        message.setWordWrap(True)
        path_label = QLineEdit(str(path))
        path_label.setReadOnly(True)
        path_label.setToolTip(str(path))
        technical = QLabel(details)
        technical.setObjectName("muted")
        technical.setWordWrap(True)
        technical.setVisible(bool(details))

        actions = QHBoxLayout()
        close = QPushButton("Закрыть программу")
        close.setObjectName("outline")
        close.clicked.connect(self.reject)
        choose = QPushButton("Указать другую базу")
        choose.setObjectName("outline")
        choose.clicked.connect(lambda: self.done(self.CHOOSE_ANOTHER))
        retry = QPushButton("Повторить")
        retry.setObjectName("primary")
        retry.clicked.connect(lambda: self.done(self.RETRY))
        actions.addWidget(close)
        actions.addStretch()
        actions.addWidget(choose)
        actions.addWidget(retry)

        layout.addWidget(eyebrow)
        layout.addWidget(heading)
        layout.addWidget(message)
        layout.addWidget(path_label)
        layout.addWidget(technical)
        layout.addStretch()
        layout.addLayout(actions)
        body_layout.addWidget(content)
        outer.addWidget(body, 1)
        self.update_window_mask()
        retry.setFocus()

    def update_window_mask(self) -> None:
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 10, 10)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))


class UpdateProgressDialog(QDialog):
    """Отзывчивое окно с фактическим прогрессом обновления."""

    retry_requested = Signal()

    def __init__(
        self,
        current_version: str,
        target_version: str,
        close_text: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("referenceDialog")
        self.setWindowTitle("Обновление журнала")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(560, 340)
        self.busy = True
        self._base_status = "Подготовка обновления"
        self._pulse_step = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        outer.addWidget(DialogTitleBar(self, "Обновление журнала"))
        body = QWidget()
        body.setObjectName("dialogBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 20, 20, 20)
        content = QFrame()
        content.setObjectName("dialogContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(10)

        eyebrow = QLabel("ОБНОВЛЕНИЕ ПРОГРАММЫ")
        eyebrow.setObjectName("dialogEyebrow")
        title = QLabel(f"Версия {current_version} → {target_version}")
        title.setObjectName("dialogTitle")
        self.status_label = QLabel(self._base_status)
        self.status_label.setObjectName("muted")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.percent_label = QLabel("0%")
        self.percent_label.setObjectName("muted")
        self.details = QLabel("Окно продолжает обновляться во время работы. Не выключайте компьютер.")
        self.details.setObjectName("muted")
        self.details.setWordWrap(True)
        progress_row = QHBoxLayout()
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.percent_label)

        actions = QHBoxLayout()
        actions.addStretch()
        self.close_button = QPushButton(close_text)
        self.close_button.setObjectName("outline")
        self.close_button.clicked.connect(self.accept)
        self.close_button.hide()
        self.retry_button = QPushButton("Повторить")
        self.retry_button.setObjectName("primary")
        self.retry_button.clicked.connect(self.retry_requested.emit)
        self.retry_button.hide()
        actions.addWidget(self.close_button)
        actions.addWidget(self.retry_button)

        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(self.status_label)
        layout.addLayout(progress_row)
        layout.addWidget(self.details)
        layout.addStretch()
        layout.addLayout(actions)
        body_layout.addWidget(content)
        outer.addWidget(body, 1)
        self.update_window_mask()

        self.pulse_timer = QTimer(self)
        self.pulse_timer.timeout.connect(self.animate_activity)
        self.pulse_timer.start(350)

    def reject(self) -> None:
        if self.busy:
            return
        super().reject()

    def animate_activity(self) -> None:
        if not self.busy:
            return
        self._pulse_step = (self._pulse_step + 1) % 4
        self.status_label.setText(self._base_status + "." * self._pulse_step)

    def set_progress(self, percent: int, status: str) -> None:
        self.busy = True
        self._base_status = status
        self.status_label.setText(status)
        value = max(0, min(100, percent))
        self.progress.setValue(value)
        self.percent_label.setText(f"{value}%")

    def set_error(self, message: str) -> None:
        self.busy = False
        self.pulse_timer.stop()
        self._base_status = "Не удалось установить обновление"
        self.status_label.setText(self._base_status)
        self.details.setText(message)
        self.close_button.show()
        self.retry_button.show()
        self.retry_button.setFocus()

    def set_success(self) -> None:
        self.busy = False
        self.pulse_timer.stop()
        self.set_progress(100, "Обновление установлено")
        self.busy = False
        self.details.setText("Новая версия будет использована при следующем запуске журнала.")
        self.retry_button.hide()
        self.close_button.setText("Готово")
        self.close_button.show()

    def reset_for_retry(self) -> None:
        self.busy = True
        self.details.setText("Окно продолжает обновляться во время работы. Не выключайте компьютер.")
        self.close_button.hide()
        self.retry_button.hide()
        self.pulse_timer.start(350)
        self.set_progress(0, "Повторная подготовка обновления")

    def update_window_mask(self) -> None:
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 10, 10)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))


class PrepareUpdateWorker(QObject):
    progress = Signal(int, str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, release: ReleaseInfo) -> None:
        super().__init__()
        self.release = release

    def run(self) -> None:
        try:
            stage = prepare_release(
                self.release,
                UPDATE_CACHE_DIR,
                lambda percent, status: self.progress.emit(percent, status),
            )
            self.finished.emit(stage)
        except Exception as exc:
            self.failed.emit(str(exc))


class ApplyUpdateWorker(QObject):
    progress = Signal(int, str)
    finished = Signal()
    failed = Signal(str)

    def __init__(self, stage_dir: Path, target_dir: Path, parent_process_id: int) -> None:
        super().__init__()
        self.stage_dir = stage_dir
        self.target_dir = target_dir
        self.parent_process_id = parent_process_id

    def run(self) -> None:
        try:
            apply_staged_update(
                self.stage_dir,
                self.target_dir,
                self.parent_process_id,
                lambda percent, status: self.progress.emit(percent, status),
            )
            self.finished.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


def open_database_root(
    store: DataStore,
    value: str | Path,
    persist: bool,
) -> tuple[ProgramInstanceLock | None, str, str]:
    """Подготавливает папку, получает общий lock и открывает SQLite."""
    try:
        root = DataStore.prepare_shared_root(value)
    except OSError as exc:
        return None, "access", str(exc)

    instance_lock = ProgramInstanceLock(root / ".journal.lock")
    if not instance_lock.acquire():
        if instance_lock.error_code == 33:
            return None, "locked", "Общий файл журнала уже заблокирован."
        return None, "access", f"Не удалось создать файл блокировки (код {instance_lock.error_code})."

    if not store.connect(root):
        instance_lock.release()
        return None, "access", store.error

    try:
        # Общий settings.json становится активным только после успешного
        # подключения к выбранной базе и получения сетевой блокировки.
        store.activate_shared_settings(root)
    except OSError as exc:
        store.close()
        instance_lock.release()
        return None, "access", str(exc)
    try:
        store.backup_if_needed()
    except (OSError, sqlite3.Error):
        # Ошибка резервной копии не должна лишать доступа к основной БД.
        pass
    return instance_lock, "ok", ""


class ReferenceCard(QFrame):
    def __init__(self, owner: "JournalWindow", title: str, key: str, singular: str) -> None:
        super().__init__(); self.owner, self.key, self.title = owner, key, title
        self.setObjectName("card"); layout = QVBoxLayout(self); layout.setContentsMargins(18, 18, 18, 18); layout.setSpacing(10)
        label = QLabel(title); label.setObjectName("section"); layout.addWidget(label)
        self.listbox = QListWidget(); self.listbox.setMinimumHeight(220); self.listbox.setFocusPolicy(Qt.FocusPolicy.NoFocus); layout.addWidget(self.listbox)
        actions = QHBoxLayout()
        for text, slot in ((f"+ Добавить {singular}", self.add), ("Изменить", self.edit), ("Удалить", self.delete)):
            button = QPushButton(text); button.setObjectName("outline"); button.clicked.connect(slot); actions.addWidget(button)
        layout.addLayout(actions); note = QLabel("Отображается в выпадающем списке"); note.setObjectName("muted"); layout.addWidget(note)
        self.refresh()

    def refresh(self) -> None:
        self.listbox.clear(); self.listbox.addItems(self.owner.store.settings[self.key])

    def request_value(self, action: str, value: str = "") -> str | None:
        dialog = ReferenceValueDialog(action, self.title, value, self.owner.store.settings["reference_dialog_size"], self)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        self.owner.store.settings["reference_dialog_size"] = [dialog.width(), dialog.height()]
        self.owner.store.save_settings()
        return dialog.value() if accepted else None

    def add(self) -> None:
        text = self.request_value("Добавить")
        if text and text not in self.owner.store.settings[self.key]:
            self.owner.store.settings[self.key].append(text); self.owner.persist_references()

    def edit(self) -> None:
        row = self.listbox.currentRow()
        if row < 0: return
        old = self.owner.store.settings[self.key][row]
        text = self.request_value("Изменить", old)
        if text: self.owner.store.settings[self.key][row] = text; self.owner.persist_references()

    def delete(self) -> None:
        row = self.listbox.currentRow()
        if row < 0: return
        value = self.owner.store.settings[self.key][row]
        if QMessageBox.question(self, "Удалить", f"Удалить «{value}»?") == QMessageBox.StandardButton.Yes:
            self.owner.store.settings[self.key].pop(row); self.owner.persist_references()


class JournalWindow(QMainWindow):
    headers = ["№ истории", "ФИО", "Возраст", "Операция", "Дата операции", "Диагноз", "Вид наркоза", "Начало", "Окончание", "Длительность", "Название операции", "Врач", "Медсестра"]
    widths = [105, 175, 62, 100, 105, 150, 135, 68, 88, 95, 165, 120, 122]

    def __init__(self, store: DataStore | None = None, instance_lock: ProgramInstanceLock | None = None) -> None:
        super().__init__()
        if ACTIVE_STARTUP_LOGGER: ACTIVE_STARTUP_LOGGER.log("Создание главного окна")
        self.store = store or DataStore()
        self.instance_lock = instance_lock
        self.page = 0
        self.total = 0
        self.editing_patient_id: int | None = None
        self._update_in_progress = False
        self._skip_update_on_close = False
        self._pending_release: ReleaseInfo | None = None
        self._update_thread: QThread | None = None
        self._update_worker: PrepareUpdateWorker | None = None
        self.update_dialog: UpdateProgressDialog | None = None
        if ACTIVE_STARTUP_LOGGER: ACTIVE_STARTUP_LOGGER.log("Настройки загружены")
        self.setWindowTitle("Журнал пациентов"); self.setWindowIcon(QIcon(str(ICON_DIR / "logo.png"))); self.setWindowFlag(Qt.WindowType.FramelessWindowHint); self.resize(1540, 900); self.setMinimumSize(1160, 720); self.setStyleSheet(QSS)
        self.restore_window_geometry()
        self.build(); self.update_window_mask()
        if ACTIVE_STARTUP_LOGGER: ACTIVE_STARTUP_LOGGER.log("Интерфейс построен")
        if self.store.conn is None:
            self.store.connect()
        if ACTIVE_STARTUP_LOGGER: ACTIVE_STARTUP_LOGGER.log("Подключение к базе завершено")
        self.show_patients()
        if ACTIVE_STARTUP_LOGGER: ACTIVE_STARTUP_LOGGER.log("Начальные данные загружены")
        QTimer.singleShot(0, self.restore_maximized_state)

    def build(self) -> None:
        root = QWidget(); root.setObjectName("root"); root.setMouseTracking(True); self.setCentralWidget(root)
        outer = QVBoxLayout(root); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        self.titlebar = TitleBar(self); outer.addWidget(self.titlebar)
        shell_widget = QWidget(); shell_widget.setObjectName("shell"); shell = QHBoxLayout(shell_widget); shell.setContentsMargins(0,0,0,0); shell.setSpacing(0); outer.addWidget(shell_widget, 1)
        sidebar = QFrame(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(232); side = QVBoxLayout(sidebar); side.setContentsMargins(14, 18, 14, 22); side.setSpacing(5)
        brand = QLabel("ЖУРНАЛ"); brand.setStyleSheet("color:#9aa6b8;font-size:11px;font-weight:700;letter-spacing:1.4px;padding:0 10px 14px;"); side.addWidget(brand)
        self.nav_group = QButtonGroup(self); self.nav_group.setExclusive(True)
        self.nav_patients = self.nav_button("Журнал", "journal.png", True, self.show_patients); side.addWidget(self.nav_patients)
        self.nav_reports = self.nav_button("Отчёты", "reports.png", False, self.show_reports); side.addWidget(self.nav_reports); side.addStretch()
        self.nav_settings = self.nav_button("Настройки", "settings.png", False, self.show_settings); side.addWidget(self.nav_settings); shell.addWidget(sidebar)
        self.stack = QStackedWidget(); shell.addWidget(self.stack, 1)
        self.patient_page = self.make_patient_page(); self.settings_page = self.make_settings_page(); self.report_page = self.make_report_page()
        self.stack.addWidget(self.patient_page); self.stack.addWidget(self.settings_page); self.stack.addWidget(self.report_page)
        for widget in self.findChildren(QWidget):
            widget.setMouseTracking(True)
            widget.installEventFilter(self)

    def toggle_maximized(self) -> None:
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def update_window_mask(self) -> None:
        """Скругляет нативную форму окна без прозрачного Qt-холста."""
        if self.isMaximized():
            self.clearMask()
            return
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 10, 10)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.update_window_mask()

    def restore_window_geometry(self) -> None:
        geometry = self.store.settings.get("window_geometry")
        if not (isinstance(geometry, list) and len(geometry) == 4 and all(isinstance(value, int) for value in geometry)):
            return
        x, y, width, height = geometry
        if width < self.minimumWidth() or height < self.minimumHeight():
            return
        saved_rect = QRect(x, y, width, height)
        if any(screen.availableGeometry().intersects(saved_rect) for screen in QApplication.screens()):
            self.setGeometry(saved_rect)

    def save_window_geometry(self) -> None:
        is_maximized = self.isMaximized()
        rect = self.normalGeometry() if is_maximized else self.geometry()
        self.store.settings["window_geometry"] = [rect.x(), rect.y(), rect.width(), rect.height()]
        self.store.settings["window_maximized"] = is_maximized
        try:
            self.store.save_settings()
        except OSError:
            pass

    def restore_maximized_state(self) -> None:
        if self.store.settings.get("window_maximized") is True:
            self.showMaximized()

    def closeEvent(self, event) -> None:
        self.save_window_geometry()
        if self._update_in_progress:
            event.ignore()
            return
        if self._skip_update_on_close or not IS_FROZEN or self.store.conn is None:
            self.store.close()
            self.release_instance_lock()
            event.accept()
            return
        try:
            release = find_newer_release(self.store.updates_dir, APP_VERSION)
        except (OSError, RuntimeError):
            release = None
        if release is not None:
            event.ignore()
            self.begin_update(release)
            return
        self.store.close()
        self.release_instance_lock()
        super().closeEvent(event)

    def begin_update(self, release: ReleaseInfo) -> None:
        self._update_in_progress = True
        self._pending_release = release
        self.hide()
        self.update_dialog = UpdateProgressDialog(
            APP_VERSION,
            release.version,
            "Закрыть без обновления",
            None,
        )
        self.update_dialog.retry_requested.connect(self.retry_update)
        self.update_dialog.accepted.connect(self.close_without_update)
        self.update_dialog.show()
        self.start_prepare_update()

    def start_prepare_update(self) -> None:
        if self._pending_release is None or self.update_dialog is None:
            return
        self.update_dialog.reset_for_retry()
        thread = QThread(self)
        worker = PrepareUpdateWorker(self._pending_release)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.update_dialog.set_progress)
        worker.finished.connect(self.update_prepared)
        worker.failed.connect(self.update_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        self._update_thread = thread
        self._update_worker = worker
        thread.start()

    def retry_update(self) -> None:
        if self._update_thread and self._update_thread.isRunning():
            return
        self.start_prepare_update()

    def update_prepared(self, stage_dir: Path) -> None:
        if self._pending_release is None or self.update_dialog is None:
            return
        self.update_dialog.set_progress(70, "Запуск установщика обновления")
        executable = stage_dir / "JournalPatients.exe"
        command = [
            str(executable),
            "--apply-update",
            "--target", str(APP_DIR),
            "--parent-pid", str(os.getpid()),
            "--from-version", APP_VERSION,
            "--version", self._pending_release.version,
        ]
        try:
            subprocess.Popen(
                command,
                cwd=str(stage_dir),
                close_fds=True,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        except OSError as exc:
            self.update_failed(str(exc))
            return
        self.store.close()
        self.release_instance_lock()
        self._skip_update_on_close = True
        self._update_in_progress = False
        self.update_dialog.hide()
        QApplication.quit()

    def update_failed(self, message: str) -> None:
        if self.update_dialog:
            self.update_dialog.set_error(
                message or "Проверьте доступ к общей папке UPD и повторите попытку."
            )

    def close_without_update(self) -> None:
        if self.update_dialog and self.update_dialog.busy:
            return
        self._skip_update_on_close = True
        self._update_in_progress = False
        self.store.close()
        self.release_instance_lock()
        QApplication.quit()

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "titlebar"):
            self.titlebar.update_maximize_control(self.isMaximized())
            self.update_window_mask()
        super().changeEvent(event)

    def eventFilter(self, source, event) -> bool:
        """Возвращает системное изменение размера на границах frameless-окна."""
        if self.isMaximized() or event.type() not in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress):
            return super().eventFilter(source, event)
        if not hasattr(event, "globalPosition"):
            return super().eventFilter(source, event)
        point = self.mapFromGlobal(event.globalPosition().toPoint())
        margin, width, height = 7, self.width(), self.height()
        edges = Qt.Edge(0)
        if point.x() <= margin: edges |= Qt.Edge.LeftEdge
        elif point.x() >= width - margin: edges |= Qt.Edge.RightEdge
        if point.y() <= margin: edges |= Qt.Edge.TopEdge
        elif point.y() >= height - margin: edges |= Qt.Edge.BottomEdge
        if event.type() == QEvent.Type.MouseMove:
            if edges in (Qt.Edge.LeftEdge, Qt.Edge.RightEdge): cursor = Qt.CursorShape.SizeHorCursor
            elif edges in (Qt.Edge.TopEdge, Qt.Edge.BottomEdge): cursor = Qt.CursorShape.SizeVerCursor
            elif edges in (Qt.Edge.TopEdge | Qt.Edge.LeftEdge, Qt.Edge.BottomEdge | Qt.Edge.RightEdge): cursor = Qt.CursorShape.SizeFDiagCursor
            elif edges: cursor = Qt.CursorShape.SizeBDiagCursor
            else:
                self.unsetCursor()
                return super().eventFilter(source, event)
            self.setCursor(cursor)
        elif edges and event.button() == Qt.MouseButton.LeftButton and self.windowHandle():
            if self.windowHandle().startSystemResize(edges):
                return True
        return super().eventFilter(source, event)

    def nav_button(self, text: str, icon_name: str, checked: bool, slot) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("nav")
        button.setIcon(QIcon(str(ICON_DIR / icon_name)))
        button.setIconSize(QSize(17, 17))
        button.setCheckable(True)
        button.setChecked(checked)
        button.clicked.connect(slot)
        self.nav_group.addButton(button)
        return button

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
        self.table = QTableWidget(0, len(self.headers)); self.table.setHorizontalHeaderLabels(self.headers); self.table.verticalHeader().setVisible(False); self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows); self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection); self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus); self.table.setAlternatingRowColors(False)
        for i, width in enumerate(self.widths): self.table.setColumnWidth(i, width)
        table_header = self.table.horizontalHeader(); table_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive); table_header.setMinimumSectionSize(52); table_header.setStretchLastSection(False); self.table.itemSelectionChanged.connect(self.selection_changed); table_layout.addWidget(self.table, 1)
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
        time_row = QHBoxLayout(); start_box = TimeField(); end_box = TimeField(); self.fields["start"], self.fields["end"] = start_box, end_box; self.input_widgets += [start_box, end_box]
        for title, box in (("Начало", start_box), ("Окончание", end_box)):
            col = QVBoxLayout(); lab = QLabel(title); lab.setObjectName("muted"); col.addWidget(lab); col.addWidget(box); time_row.addLayout(col)
        form.addLayout(time_row); duration_label = QLabel("Длительность · рассчитывается автоматически"); duration_label.setObjectName("muted"); form.addWidget(duration_label); self.duration = QLineEdit("—"); self.duration.setReadOnly(True); form.addWidget(self.duration); start_box.textChanged.connect(self.update_duration); end_box.textChanged.connect(self.update_duration)
        text("Название операции", "procedure"); combo("Врач", "doctor", self.store.settings["doctors"]); combo("Медсестра", "nurse", self.store.settings["nurses"])
        self.save_button = QPushButton("Добавить пациента"); self.save_button.setObjectName("primary"); self.save_button.clicked.connect(self.save_patient); form.addWidget(self.save_button)
        self.cancel_button = QPushButton("Отмена"); self.cancel_button.setObjectName("outline"); self.cancel_button.clicked.connect(self.cancel_edit); self.cancel_button.hide(); form.addWidget(self.cancel_button)
        self.delete_patient_button = QPushButton("Удалить пациента"); self.delete_patient_button.setObjectName("danger"); self.delete_patient_button.clicked.connect(self.delete_patient); self.delete_patient_button.hide(); form.addWidget(self.delete_patient_button)
        form.addStretch(); scroll.setWidget(inner); outer.addWidget(scroll); return card

    def make_settings_page(self) -> QWidget:
        page = QWidget(); layout = self.page_layout(page); title = QLabel("Настройки"); title.setObjectName("title"); layout.addWidget(title); subtitle = QLabel("Справочники и хранение данных"); subtitle.setObjectName("muted"); layout.addWidget(subtitle)
        cards = QHBoxLayout(); self.reference_cards = [ReferenceCard(self, "Виды наркоза", "anesthesia_types", "вид"), ReferenceCard(self, "Врачи", "doctors", "врача"), ReferenceCard(self, "Медсестры", "nurses", "медсестру")]
        for card in self.reference_cards: cards.addWidget(card, 1)
        layout.addLayout(cards)
        storage = QFrame(); storage.setObjectName("card"); grid = QGridLayout(storage); grid.setContentsMargins(18,18,18,18); grid.setSpacing(9); label = QLabel("Хранение данных"); label.setObjectName("section"); grid.addWidget(label, 0, 0, 1, 3); grid.addWidget(QLabel("Папка общего журнала", objectName="muted"), 1,0,1,3)
        self.path_field = QLineEdit(); self.path_field.setPlaceholderText("//fs.acrb-amursk.ru/common/РАО/Пациенты/Jornal-oper"); grid.addWidget(self.path_field, 2,0); choose = QPushButton("Выбрать папку"); choose.setObjectName("outline"); choose.clicked.connect(self.choose_database_root); grid.addWidget(choose,2,1); save = QPushButton("Подключить"); save.setObjectName("primary"); save.clicked.connect(self.save_database_root); grid.addWidget(save,2,2)
        note = QLabel("База: data\\journal.db; блокировка: .journal.lock; релизы: UPD в выбранной папке."); note.setObjectName("muted"); note.setWordWrap(True); grid.addWidget(note, 3,0,1,3); self.connection_status = QLabel(); self.connection_status.setObjectName("muted"); grid.addWidget(self.connection_status, 4,0,1,3); layout.addWidget(storage)
        diagnostics = QFrame(); diagnostics.setObjectName("card"); diagnostics_layout = QVBoxLayout(diagnostics); diagnostics_layout.setContentsMargins(18, 15, 18, 15); diagnostics_layout.setSpacing(5)
        diagnostics_title = QLabel("Диагностика запуска"); diagnostics_title.setObjectName("section"); diagnostics_layout.addWidget(diagnostics_title)
        self.startup_logging_checkbox = QCheckBox("Записывать лог запуска")
        self.startup_logging_checkbox.toggled.connect(self.set_startup_logging)
        diagnostics_layout.addWidget(self.startup_logging_checkbox)
        diagnostics_note = QLabel(f"Версия {APP_VERSION}. Лог содержит только время этапов запуска и сохраняется в локальном профиле Windows. После измерения отключите запись."); diagnostics_note.setObjectName("muted"); diagnostics_note.setWordWrap(True); diagnostics_layout.addWidget(diagnostics_note)
        layout.addWidget(diagnostics); layout.addStretch(); return page

    def make_report_page(self) -> QWidget:
        page = QWidget(); layout = self.page_layout(page)
        title = QLabel("Статистический отчёт"); title.setObjectName("title"); layout.addWidget(title)
        subtitle = QLabel("Количество операций, видов наркоза и участников за выбранный период"); subtitle.setObjectName("muted"); layout.addWidget(subtitle)

        filters = QFrame(); filters.setObjectName("card"); filter_layout = QHBoxLayout(filters); filter_layout.setContentsMargins(18, 14, 18, 14); filter_layout.setSpacing(9)
        filter_layout.addWidget(QLabel("Период", objectName="section")); filter_layout.addSpacing(8)
        filter_layout.addWidget(QLabel("с", objectName="muted")); self.report_date_from = QLineEdit(); self.report_date_from.setPlaceholderText("ГГГГ-ММ-ДД"); self.report_date_from.setFixedWidth(130); filter_layout.addWidget(self.report_date_from)
        filter_layout.addWidget(QLabel("по", objectName="muted")); self.report_date_to = QLineEdit(); self.report_date_to.setPlaceholderText("ГГГГ-ММ-ДД"); self.report_date_to.setFixedWidth(130); filter_layout.addWidget(self.report_date_to)
        apply = QPushButton("Сформировать"); apply.setObjectName("primary"); apply.clicked.connect(self.refresh_report); filter_layout.addWidget(apply)
        reset = QPushButton("За всё время"); reset.setObjectName("outline"); reset.clicked.connect(self.reset_report_filters); filter_layout.addWidget(reset); filter_layout.addStretch(); layout.addWidget(filters)

        metrics = QHBoxLayout(); metrics.setSpacing(14)
        self.report_total = self.make_report_metric("Всего операций", metrics)
        self.report_planned = self.make_report_metric("Плановых", metrics)
        self.report_emergency = self.make_report_metric("Экстренных", metrics)
        layout.addLayout(metrics)

        tables = QHBoxLayout(); tables.setSpacing(14)
        anesthesia_card, self.report_anesthesia_table = self.make_report_table("Виды наркоза", "Вид наркоза")
        doctor_card, self.report_doctor_table = self.make_report_table("Врачи", "Врач")
        nurse_card, self.report_nurse_table = self.make_report_table("Медсёстры", "Медсестра")
        tables.addWidget(anesthesia_card, 1); tables.addWidget(doctor_card, 1); tables.addWidget(nurse_card, 1); layout.addLayout(tables, 1)
        self.report_status = QLabel(); self.report_status.setObjectName("muted"); layout.addWidget(self.report_status)
        return page

    @staticmethod
    def make_report_metric(label_text: str, parent_layout: QHBoxLayout) -> QLabel:
        card = QFrame(); card.setObjectName("card"); card_layout = QVBoxLayout(card); card_layout.setContentsMargins(18, 14, 18, 14); card_layout.setSpacing(2)
        value = QLabel("0"); value.setObjectName("reportMetric"); caption = QLabel(label_text); caption.setObjectName("reportMetricLabel")
        card_layout.addWidget(value); card_layout.addWidget(caption); parent_layout.addWidget(card, 1)
        return value

    @staticmethod
    def make_report_table(title_text: str, first_column: str) -> tuple[QFrame, QTableWidget]:
        card = QFrame(); card.setObjectName("card"); layout = QVBoxLayout(card); layout.setContentsMargins(1, 1, 1, 10); layout.setSpacing(3)
        title = QLabel(title_text); title.setObjectName("section"); title.setContentsMargins(16, 14, 16, 5); layout.addWidget(title)
        table = QTableWidget(0, 3); table.setHorizontalHeaderLabels([first_column, "Кол-во", "Доля"]); table.verticalHeader().setVisible(False); table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); table.setSelectionMode(QTableWidget.SelectionMode.NoSelection); table.setFocusPolicy(Qt.FocusPolicy.NoFocus); table.setShowGrid(False)
        header = table.horizontalHeader(); header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch); header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents); header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(table, 1)
        return card, table

    def select_page(self, index: int, button: QPushButton) -> None:
        self.stack.setCurrentIndex(index); button.setChecked(True)

    def show_patients(self) -> None:
        self.select_page(0, self.nav_patients); self.refresh_patient_state()

    def show_settings(self) -> None:
        self.select_page(1, self.nav_settings); self.path_field.setText(str(self.store.database_root or "")); self.refresh_references(); self.update_connection_status()
        self.startup_logging_checkbox.blockSignals(True)
        self.startup_logging_checkbox.setChecked(self.store.settings["startup_logging"])
        self.startup_logging_checkbox.blockSignals(False)

    def show_reports(self) -> None:
        self.select_page(2, self.nav_reports)
        self.refresh_report()

    def report_where_clause(self) -> tuple[str, list[str]]:
        clauses, params = [], []
        for field, operator in ((self.report_date_from, ">="), (self.report_date_to, "<=")):
            value = field.text().strip()
            if not value:
                continue
            datetime.strptime(value, "%Y-%m-%d")
            clauses.append(f"operation_date {operator} ?")
            params.append(value)
        return (" WHERE " + " AND ".join(clauses) if clauses else ""), params

    def reset_report_filters(self) -> None:
        self.report_date_from.clear(); self.report_date_to.clear(); self.refresh_report()

    @staticmethod
    def fill_report_table(table: QTableWidget, rows, total: int) -> None:
        table.setRowCount(0)
        for index, row in enumerate(rows):
            count = int(row["count"])
            table.insertRow(index)
            values = [str(row["name"]), str(count), f"{count / total * 100:.1f}%" if total else "0%"]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(index, column, item)
            table.setRowHeight(index, 40)

    def refresh_report(self) -> None:
        if not self.store.conn:
            self.report_total.setText("—"); self.report_planned.setText("—"); self.report_emergency.setText("—")
            for table in (self.report_anesthesia_table, self.report_doctor_table, self.report_nurse_table): table.setRowCount(0)
            self.report_status.setText("База данных недоступна.")
            return
        try:
            where, params = self.report_where_clause()
        except ValueError:
            self.show_validation_error("Период отчёта", "Используйте для дат формат ГГГГ-ММ-ДД.")
            return
        try:
            connection = self.store.conn
            total = int(connection.execute("SELECT COUNT(*) FROM patients" + where, params).fetchone()[0])
            planned = int(connection.execute("SELECT COUNT(*) FROM patients" + where + (" AND " if where else " WHERE ") + "operation_kind='Плановая'", params).fetchone()[0])
            emergency = int(connection.execute("SELECT COUNT(*) FROM patients" + where + (" AND " if where else " WHERE ") + "operation_kind='Экстренная'", params).fetchone()[0])
            anesthesia = connection.execute("SELECT COALESCE(NULLIF(TRIM(anesthesia_type),''),'Не указан') AS name, COUNT(*) AS count FROM patients" + where + " GROUP BY name ORDER BY count DESC, name", params).fetchall()
            doctors = connection.execute("SELECT COALESCE(NULLIF(TRIM(doctor),''),'Не указан') AS name, COUNT(*) AS count FROM patients" + where + " GROUP BY name ORDER BY count DESC, name", params).fetchall()
            nurses = connection.execute("SELECT COALESCE(NULLIF(TRIM(nurse),''),'Не указана') AS name, COUNT(*) AS count FROM patients" + where + " GROUP BY name ORDER BY count DESC, name", params).fetchall()
        except sqlite3.Error as exc:
            self.store.error = str(exc); self.store.close(); self.refresh_patient_state(); return
        self.report_total.setText(str(total)); self.report_planned.setText(str(planned)); self.report_emergency.setText(str(emergency))
        self.fill_report_table(self.report_anesthesia_table, anesthesia, total)
        self.fill_report_table(self.report_doctor_table, doctors, total)
        self.fill_report_table(self.report_nurse_table, nurses, total)
        period = "за всё время" if not params else "за выбранный период"
        self.report_status.setText(f"Сформировано {period}. Всего записей: {total}.")

    def refresh_patient_state(self) -> None:
        available = self.store.conn is not None
        self.titlebar.set_connection_state(available)
        self.alert.setVisible(not available)
        if not available: self.alert_text.setText("База данных недоступна. Просмотр, добавление и редактирование пациентов временно недоступны.")
        for widget in [self.table, self.filter_name, self.filter_date, self.apply_button, self.reset_button, self.save_button, self.prev, self.next, *self.input_widgets]: widget.setEnabled(available)
        self.edit_button.setEnabled(available and bool(self.table.selectedItems()))
        if available: self.load_patients()
        else: self.table.setRowCount(0); self.page_info.setText("База недоступна")

    def retry_connection(self) -> None:
        root = self.store.database_root
        if root is None:
            self.choose_database_root()
            return
        while not self.store.connect(root):
            dialog = DatabaseAccessDialog(root, self.store.error, self)
            action = dialog.exec()
            if action == DatabaseAccessDialog.RETRY:
                continue
            if action == DatabaseAccessDialog.CHOOSE_ANOTHER:
                self.choose_database_root()
            break
        try:
            if self.store.conn:
                self.store.activate_shared_settings(root)
                self.store.backup_if_needed()
        except (OSError, sqlite3.Error):
            pass
        self.refresh_patient_state()
        self.update_connection_status()

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
        # После фильтрации модель таблицы пересоздаётся. Явно сбрасываем
        # текущую ячейку вместе с выделением, иначе Qt может сохранить
        # устаревший текущий индекс и не послать сигнал при повторном клике.
        self.table.clearSelection()
        self.table.setCurrentItem(None)
        self.table.clearContents()
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = [row["history_number"], row["full_name"], str(row["age"] or "—"), row["operation_kind"], row["operation_date"], row["diagnosis"] or "—", row["anesthesia_type"], row["anesthesia_start"] or "—", row["anesthesia_end"] or "—", self.duration_text(row["anesthesia_start"], row["anesthesia_end"]), row["procedure_name"] or "—", row["doctor"] or "—", row["nurse"] or "—"]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value); item.setData(Qt.ItemDataRole.UserRole, row["id"])
                if c == 3: item.setForeground(QColor("#1769e0") if value == "Плановая" else QColor("#d84d4d"))
                self.table.setItem(r,c,item)
            self.table.setRowHeight(r, 48)
        first = self.page*PAGE_SIZE+1 if self.total else 0; last = min((self.page+1)*PAGE_SIZE, self.total); self.page_info.setText(f"Показано {first}–{last} из {self.total}"); self.page_num.setText(str(self.page+1)); self.prev.setEnabled(self.page>0); self.next.setEnabled(last<self.total); self.selection_changed()

    def apply_filters(self) -> None: self.page = 0; self.load_patients()
    def reset_filters(self) -> None: self.filter_name.clear(); self.filter_date.clear(); self.apply_filters()
    def change_page(self, delta: int) -> None: self.page += delta; self.load_patients()
    def selection_changed(self) -> None: self.edit_button.setEnabled(self.store.conn is not None and bool(self.table.selectedItems()))

    @staticmethod
    def duration_text(start: str | None, end: str | None) -> str:
        if not start or not end: return "—"
        start_time = JournalWindow.parse_time(start)
        end_time = JournalWindow.parse_time(end)
        if not start_time or not end_time: return "Укажите ЧЧ:ММ"
        minutes = start_time.secsTo(end_time) // 60
        if minutes < 0: return "Проверьте время"
        return f"{minutes//60} ч {minutes%60} мин" if minutes >= 60 else f"{minutes} мин"

    @staticmethod
    def parse_time(value: str) -> QTime | None:
        return parse_clock_time(value)

    def update_duration(self) -> None: self.duration.setText(self.duration_text(self.fields["start"].text().strip(), self.fields["end"].text().strip()))
    def field_value(self, key: str) -> str: return self.fields[key].currentText().strip() if isinstance(self.fields[key], QComboBox) else self.fields[key].text().strip()

    def form_data(self) -> dict[str,str]:
        return {key:self.field_value(key) for key in self.fields} | {"kind":"Плановая" if self.kind_planned.isChecked() else "Экстренная"}

    def show_validation_error(self, title: str, message: str) -> None:
        ValidationErrorDialog(title, message, self).exec()

    def validate(self, data: dict[str,str]) -> bool:
        missing = [label for key,label in (("history","№ истории"),("name","ФИО"),("date","Дата операции"),("anesthesia","Вид наркоза")) if not data[key]]
        if missing:
            self.show_validation_error("Не заполнены поля", "Обязательные поля: " + ", ".join(missing))
            return False
        try: datetime.strptime(data["date"], "%Y-%m-%d")
        except ValueError:
            self.show_validation_error("Дата операции", "Используйте формат ГГГГ-ММ-ДД.")
            return False
        if data["age"] and (not data["age"].isdigit() or not 0 <= int(data["age"]) <= 130):
            self.show_validation_error("Возраст", "Возраст должен быть числом от 0 до 130.")
            return False
        if self.duration_text(data["start"], data["end"]) in ("Укажите ЧЧ:ММ","Проверьте время"):
            self.show_validation_error("Время наркоза", "Проверьте начало и окончание в формате ЧЧ:ММ.")
            return False
        return True

    def save_patient(self) -> None:
        if not self.store.conn: return
        data = self.form_data()
        if not self.validate(data): return
        vals = (data["history"], data["name"], int(data["age"]) if data["age"] else None, data["kind"], data["date"], data["diagnosis"], data["anesthesia"], data["start"], data["end"], data["procedure"], data["doctor"], data["nurse"])
        try:
            if self.editing_patient_id is None: self.store.conn.execute("INSERT INTO patients(history_number,full_name,age,operation_kind,operation_date,diagnosis,anesthesia_type,anesthesia_start,anesthesia_end,procedure_name,doctor,nurse) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", vals)
            else: self.store.conn.execute("UPDATE patients SET history_number=?,full_name=?,age=?,operation_kind=?,operation_date=?,diagnosis=?,anesthesia_type=?,anesthesia_start=?,anesthesia_end=?,procedure_name=?,doctor=?,nurse=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (*vals, self.editing_patient_id))
            self.store.conn.commit()
        except sqlite3.IntegrityError:
            self.show_validation_error("Не удалось сохранить", "Проверьте обязательные поля записи.")
            return
        except sqlite3.Error as exc: self.store.error=str(exc); self.store.close(); self.refresh_patient_state(); return
        self.cancel_edit(); self.load_patients()

    def start_edit(self) -> None:
        if not self.store.conn or not self.table.selectedItems(): return
        patient_id = self.table.selectedItems()[0].data(Qt.ItemDataRole.UserRole); row = self.store.conn.execute("SELECT * FROM patients WHERE id=?",(patient_id,)).fetchone()
        if not row: return
        self.editing_patient_id = int(row["id"])
        mapping = {"history":"history_number","name":"full_name","age":"age","date":"operation_date","diagnosis":"diagnosis","anesthesia":"anesthesia_type","start":"anesthesia_start","end":"anesthesia_end","procedure":"procedure_name","doctor":"doctor","nurse":"nurse"}
        for key,column in mapping.items():
            target=self.fields[key]; value=str(row[column] or ""); target.setCurrentText(value) if isinstance(target,QComboBox) else target.setText(value)
        self.kind_planned.setChecked(row["operation_kind"] == "Плановая"); self.kind_emergency.setChecked(row["operation_kind"] == "Экстренная"); self.form_title.setText("Редактирование пациента"); self.save_button.setText("Сохранить изменения"); self.cancel_button.show(); self.delete_patient_button.show(); self.update_duration()

    def cancel_edit(self) -> None:
        self.editing_patient_id=None
        for key, target in self.fields.items(): target.setCurrentText("") if isinstance(target,QComboBox) else target.setText("")
        self.fields["date"].setText(date.today().isoformat()); self.kind_planned.setChecked(True); self.form_title.setText("Быстрое добавление"); self.save_button.setText("Добавить пациента"); self.cancel_button.hide(); self.delete_patient_button.hide(); self.update_duration()

    def delete_patient(self) -> None:
        if not self.store.conn or self.editing_patient_id is None:
            return
        row = self.store.conn.execute(
            "SELECT full_name, history_number FROM patients WHERE id=?",
            (self.editing_patient_id,),
        ).fetchone()
        if row is None:
            return
        dialog = PatientDeleteDialog(
            str(row["full_name"]), str(row["history_number"]), self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.store.conn.execute("DELETE FROM patients WHERE id=?", (self.editing_patient_id,))
            self.store.conn.commit()
        except sqlite3.Error as exc:
            self.store.error = str(exc)
            self.store.close()
            self.refresh_patient_state()
            return
        self.page = 0
        self.cancel_edit()
        self.load_patients()

    def refresh_references(self) -> None:
        for card in self.reference_cards: card.refresh()
        for key, source in (("anesthesia", "anesthesia_types"),("doctor","doctors"),("nurse","nurses")):
            box = self.fields[key]; value=box.currentText(); box.clear(); box.addItems(self.store.settings[source]); box.setCurrentText(value)

    def persist_references(self) -> None: self.store.save_settings(); self.refresh_references()
    def choose_database_root(self) -> None:
        dialog = DatabaseFolderDialog(self.path_field.text().strip(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_path():
            self.path_field.setText(str(dialog.selected_path()))
            self.save_database_root()

    def save_database_root(self) -> None:
        value = self.path_field.text().strip()
        root = normalize_database_root(value) if value else None
        if root is None:
            self.show_validation_error("Папка журнала", "Укажите папку общего журнала.")
            return
        try:
            root = DataStore.prepare_shared_root(root)
        except OSError as exc:
            dialog = DatabaseAccessDialog(root, str(exc), self)
            if dialog.exec() == DatabaseAccessDialog.CHOOSE_ANOTHER:
                self.choose_database_root()
            return
        current_root = self.store.database_root
        if current_root == root:
            if not self.store.connect(root):
                DatabaseAccessDialog(root, self.store.error, self).exec()
            else:
                try:
                    self.store.activate_shared_settings(root)
                except OSError as exc:
                    DatabaseAccessDialog(root, str(exc), self).exec()
            self.refresh_patient_state()
            self.update_connection_status()
            return

        new_lock = ProgramInstanceLock(root / ".journal.lock")
        if not new_lock.acquire():
            if new_lock.error_code == 33:
                self.show_validation_error(
                    "Журнал уже открыт",
                    "Выбранная общая база сейчас используется на другом компьютере.",
                )
            else:
                DatabaseAccessDialog(
                    root,
                    f"Не удалось создать файл блокировки (код {new_lock.error_code}).",
                    self,
                ).exec()
            return
        if not self.store.connect(root):
            new_lock.release()
            DatabaseAccessDialog(root, self.store.error, self).exec()
            return
        try:
            self.store.set_database_root(root)
        except OSError:
            if current_root is not None:
                self.store.connect(current_root)
                try:
                    self.store.activate_shared_settings(current_root)
                except OSError:
                    pass
            new_lock.release()
            self.show_validation_error(
                "Не удалось сохранить путь",
                "Проверьте доступ к локальному профилю Windows.",
            )
            return
        if self.instance_lock:
            self.instance_lock.release()
        self.instance_lock = new_lock
        try:
            self.store.backup_if_needed()
        except (OSError, sqlite3.Error):
            pass
        self.path_field.setText(str(root))
        self.refresh_patient_state()
        self.update_connection_status()

    def release_instance_lock(self) -> None:
        if self.instance_lock:
            self.instance_lock.release()
            self.instance_lock = None
    def set_startup_logging(self, enabled: bool) -> None:
        if ACTIVE_STARTUP_LOGGER and ACTIVE_STARTUP_LOGGER.enabled and not enabled:
            ACTIVE_STARTUP_LOGGER.log("Запись диагностического лога отключена")
        self.store.settings["startup_logging"] = enabled
        try:
            self.store.save_settings()
        except OSError:
            self.startup_logging_checkbox.blockSignals(True)
            self.startup_logging_checkbox.setChecked(not enabled)
            self.startup_logging_checkbox.blockSignals(False)
            return
        if ACTIVE_STARTUP_LOGGER:
            ACTIVE_STARTUP_LOGGER.set_enabled(enabled)
            if enabled:
                ACTIVE_STARTUP_LOGGER.log("Запись диагностического лога включена")
    def update_connection_status(self) -> None:
        if self.store.conn: self.connection_status.setText("База доступна в выбранной общей папке."); self.connection_status.setStyleSheet("color:#16835a;")
        else: self.connection_status.setText("База недоступна. Проверьте путь к общей папке и доступ к каталогу data."); self.connection_status.setStyleSheet("color:#b05600;")


def parse_arguments(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--apply-update", action="store_true")
    parser.add_argument("--target", default="")
    parser.add_argument("--parent-pid", type=int, default=0)
    parser.add_argument("--from-version", default=APP_VERSION)
    parser.add_argument("--version", default=APP_VERSION)
    parsed, _ = parser.parse_known_args(arguments[1:])
    return parsed


def run_update_installer(app: QApplication, arguments: argparse.Namespace) -> int:
    stage_dir = Path(sys.executable).resolve().parent
    target_dir = Path(arguments.target).resolve() if arguments.target else APP_DIR
    dialog = UpdateProgressDialog(
        arguments.from_version,
        arguments.version,
        "Закрыть",
        None,
    )
    thread_holder: dict[str, object] = {}

    def start_worker() -> None:
        existing = thread_holder.get("thread")
        if isinstance(existing, QThread) and existing.isRunning():
            return
        dialog.reset_for_retry()
        thread = QThread()
        worker = ApplyUpdateWorker(stage_dir, target_dir, arguments.parent_pid)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(dialog.set_progress)
        worker.finished.connect(dialog.set_success)
        worker.finished.connect(thread.quit)
        worker.failed.connect(dialog.set_error)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread_holder["thread"] = thread
        thread_holder["worker"] = worker
        thread.start()

    dialog.retry_requested.connect(start_worker)
    dialog.accepted.connect(app.quit)
    dialog.show()
    start_worker()
    return app.exec()


def establish_startup_database(
    store: DataStore,
    splash: QSplashScreen,
) -> ProgramInstanceLock | None:
    root = store.database_root
    persist = False
    while True:
        if root is None:
            splash.close()
            picker = DatabaseFolderDialog()
            if picker.exec() != QDialog.DialogCode.Accepted:
                if ACTIVE_STARTUP_LOGGER:
                    ACTIVE_STARTUP_LOGGER.log("Запуск отменён: папка журнала не выбрана")
                return None
            root = picker.selected_path()
            persist = True
            if root is None:
                continue

        instance_lock, status, details = open_database_root(store, root, persist)
        if status == "ok" and instance_lock is not None:
            splash.show()
            QApplication.processEvents()
            if ACTIVE_STARTUP_LOGGER:
                ACTIVE_STARTUP_LOGGER.log("Общая база подключена")
            return instance_lock

        splash.close()
        if status == "locked":
            if ACTIVE_STARTUP_LOGGER:
                ACTIVE_STARTUP_LOGGER.log("Запуск отменён: экземпляр уже открыт")
            ValidationErrorDialog(
                "Программа уже открыта",
                "Журнал уже используется на другом компьютере. "
                "Закройте его там, прежде чем продолжить работу здесь.",
                None,
            ).exec()
            return None

        if ACTIVE_STARTUP_LOGGER:
            ACTIVE_STARTUP_LOGGER.log("Общая база недоступна")
        access_dialog = DatabaseAccessDialog(root, details, None)
        action = access_dialog.exec()
        if action == DatabaseAccessDialog.RETRY:
            continue
        if action == DatabaseAccessDialog.CHOOSE_ANOTHER:
            picker = DatabaseFolderDialog(str(root))
            if picker.exec() != QDialog.DialogCode.Accepted:
                return None
            root = picker.selected_path()
            persist = True
            continue
        return None


def main() -> int:
    global ACTIVE_STARTUP_LOGGER
    migrate_legacy_settings()
    arguments = parse_arguments(sys.argv)
    app = QApplication(sys.argv)
    # Fusion не использует нестабильные растровые эффекты WindowsVistaStyle
    # при наведении и фокусе, из-за которых Qt мог выводить QPainter-предупреждения.
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    app.setWindowIcon(QIcon(str(ICON_DIR / "logo.png")))

    if arguments.apply_update:
        return run_update_installer(app, arguments)

    ACTIVE_STARTUP_LOGGER = StartupLogger()
    ACTIVE_STARTUP_LOGGER.log("Запуск приложения: импорт Python и Qt завершён")
    ACTIVE_STARTUP_LOGGER.log("Qt-приложение создано")
    splash = create_startup_splash()
    splash.show()
    app.processEvents()
    ACTIVE_STARTUP_LOGGER.log("Стартовая заставка показана")
    store = DataStore()
    instance_lock = establish_startup_database(store, splash)
    if instance_lock is None:
        return 0
    ACTIVE_STARTUP_LOGGER.set_enabled(store.settings.get("startup_logging") is True)
    ACTIVE_STARTUP_LOGGER.log("Блокировка единственного экземпляра получена")
    window = JournalWindow(store, instance_lock)
    app.aboutToQuit.connect(window.release_instance_lock)
    window.show()
    splash.finish(window)
    ACTIVE_STARTUP_LOGGER.log("Главное окно показано; запуск завершён")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
