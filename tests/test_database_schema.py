from __future__ import annotations

import sqlite3
import unittest

from app_version import DATABASE_SCHEMA_VERSION
from database_schema import initialize_schema


OLD_SCHEMA = """
CREATE TABLE patients (
    id INTEGER PRIMARY KEY,
    history_number TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    age INTEGER,
    operation_kind TEXT NOT NULL,
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
PRAGMA user_version=1;
"""


PATIENT = (
    "42",
    "Иванов И. И.",
    60,
    "Плановая",
    "2026-08-01",
    "Диагноз",
    "Общая",
    "08:00",
    "09:00",
    "Операция",
    "Врач",
    "Медсестра",
)


def insert_patient(connection: sqlite3.Connection, patient: tuple = PATIENT) -> int:
    cursor = connection.execute(
        """
        INSERT INTO patients (
            history_number, full_name, age, operation_kind, operation_date,
            diagnosis, anesthesia_type, anesthesia_start, anesthesia_end,
            procedure_name, doctor, nurse
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        patient,
    )
    return int(cursor.lastrowid)


class DatabaseSchemaTests(unittest.TestCase):
    def test_new_database_accepts_repeated_history_number_as_new_cases(self) -> None:
        connection = sqlite3.connect(":memory:")
        initialize_schema(connection)

        first_id = insert_patient(connection)
        second = list(PATIENT)
        second[4] = "2026-08-02"
        second_id = insert_patient(connection, tuple(second))
        connection.commit()

        self.assertNotEqual(first_id, second_id)
        self.assertEqual(
            connection.execute(
                "SELECT COUNT(*) FROM patients WHERE history_number=?", (PATIENT[0],)
            ).fetchone()[0],
            2,
        )

    def test_migration_preserves_existing_case_and_removes_unique_constraint(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.executescript(OLD_SCHEMA)
        original_id = insert_patient(connection)
        connection.execute(
            "UPDATE patients SET created_at='2026-07-01 10:00:00' WHERE id=?",
            (original_id,),
        )
        connection.commit()

        initialize_schema(connection)
        repeated_id = insert_patient(connection)
        connection.commit()

        rows = connection.execute(
            "SELECT id, history_number, created_at FROM patients ORDER BY id"
        ).fetchall()
        self.assertEqual(rows[0], (original_id, "42", "2026-07-01 10:00:00"))
        self.assertNotEqual(rows[0][0], repeated_id)
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            connection.execute("PRAGMA user_version").fetchone()[0],
            DATABASE_SCHEMA_VERSION,
        )

    def test_existing_database_is_migrated_with_optional_department(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.executescript(
            OLD_SCHEMA.replace(" NOT NULL UNIQUE", " NOT NULL").replace(
                "PRAGMA user_version=1;", "PRAGMA user_version=2;"
            )
        )
        patient_id = insert_patient(connection)

        initialize_schema(connection)

        self.assertEqual(
            connection.execute(
                "SELECT department FROM patients WHERE id=?", (patient_id,)
            ).fetchone()[0],
            None,
        )
        self.assertIn(
            "department",
            {row[1] for row in connection.execute("PRAGMA table_info(patients)")},
        )

    def test_database_from_newer_application_is_rejected(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.execute(f"PRAGMA user_version={DATABASE_SCHEMA_VERSION + 1}")

        with self.assertRaisesRegex(sqlite3.DatabaseError, "более новой версией"):
            initialize_schema(connection)


if __name__ == "__main__":
    unittest.main()
