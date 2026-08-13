"""Схема SQLite и безопасные миграции журнала пациентов."""

from __future__ import annotations

import sqlite3

from app_version import DATABASE_SCHEMA_VERSION


PATIENT_COLUMNS = (
    "id",
    "history_number",
    "full_name",
    "age",
    "operation_kind",
    "department",
    "operation_date",
    "diagnosis",
    "anesthesia_type",
    "anesthesia_start",
    "anesthesia_end",
    "procedure_name",
    "doctor",
    "nurse",
    "created_at",
    "updated_at",
)


def _create_patients_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY,
            history_number TEXT NOT NULL,
            full_name TEXT NOT NULL,
            age INTEGER,
            operation_kind TEXT NOT NULL,
            department TEXT,
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
        )
        """
    )


def _create_patients_indexes(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_patients_history ON patients(history_number)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_patients_name ON patients(full_name COLLATE NOCASE)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_patients_date "
        "ON patients(operation_date DESC, created_at DESC)"
    )


def _history_number_is_unique(connection: sqlite3.Connection) -> bool:
    """Находит старое UNIQUE-ограничение независимо от user_version."""
    for index in connection.execute("PRAGMA index_list(patients)").fetchall():
        if not bool(index[2]):
            continue
        index_name = str(index[1]).replace('"', '""')
        columns = [
            str(row[2])
            for row in connection.execute(
                f'PRAGMA index_info("{index_name}")'
            ).fetchall()
        ]
        if columns == ["history_number"]:
            return True
    return False


def _migrate_repeated_patient_cases(connection: sqlite3.Connection) -> None:
    """Убирает UNIQUE с номера истории, сохраняя записи и их внутренние id."""
    legacy_table = "patients_schema_v1"
    connection.execute("SAVEPOINT migrate_patients_schema_v2")
    try:
        connection.execute(f"ALTER TABLE patients RENAME TO {legacy_table}")
        _create_patients_table(connection)
        legacy_columns = {
            str(row[1])
            for row in connection.execute(f"PRAGMA table_info({legacy_table})").fetchall()
        }
        columns = ", ".join(
            column for column in PATIENT_COLUMNS if column in legacy_columns
        )
        connection.execute(
            f"INSERT INTO patients ({columns}) SELECT {columns} FROM {legacy_table}"
        )
        connection.execute(f"DROP TABLE {legacy_table}")
    except Exception:
        connection.execute("ROLLBACK TO migrate_patients_schema_v2")
        connection.execute("RELEASE migrate_patients_schema_v2")
        raise
    connection.execute("RELEASE migrate_patients_schema_v2")


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Создаёт актуальную схему и обновляет совместимую старую базу."""
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version > DATABASE_SCHEMA_VERSION:
        raise sqlite3.DatabaseError(
            "База создана более новой версией программы. Обновите приложение."
        )

    _create_patients_table(connection)
    if _history_number_is_unique(connection):
        _migrate_repeated_patient_cases(connection)

    actual_columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(patients)").fetchall()
    }
    missing_columns = set(PATIENT_COLUMNS) - actual_columns
    if missing_columns == {"department"}:
        connection.execute("ALTER TABLE patients ADD COLUMN department TEXT")
    elif missing_columns:
        raise sqlite3.DatabaseError("Структура выбранной базы данных не поддерживается")

    _create_patients_indexes(connection)
    if version < DATABASE_SCHEMA_VERSION:
        connection.execute(f"PRAGMA user_version={DATABASE_SCHEMA_VERSION}")
    connection.commit()
