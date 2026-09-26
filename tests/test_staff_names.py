from __future__ import annotations

import unittest

from staff_names import canonical_staff_name, merge_staff_counts


class StaffNameTests(unittest.TestCase):
    def test_typing_variants_match_reference(self) -> None:
        references = ["Ти Н.В.", "Иванова Е. П."]
        for variant in ("Ти н в", "Ти Н в", "Ти Н. В.", "  ТИ  н.в.  "):
            with self.subTest(variant=variant):
                self.assertEqual(canonical_staff_name(variant, references), "Ти Н.В.")

    def test_other_initials_stay_distinct_and_formatted_reference_wins(self) -> None:
        self.assertEqual(canonical_staff_name("Ти Н.А.", ["Ти Н.В."]), "Ти Н.А.")
        self.assertEqual(
            canonical_staff_name("Ти н в", ["Ти Н В", "Ти Н.В."]),
            "Ти Н.В.",
        )

    def test_report_merges_existing_variants_and_keeps_unknown_names(self) -> None:
        rows = [
            {"name": "Ти Н.В.", "count": 2},
            {"name": "Ти н в", "count": 1},
            {"name": "Ти Н. В.", "count": 1},
            {"name": "Петров И. П.", "count": 1},
            {"name": "Петров и п", "count": 2},
            {"name": "Ти Н.А.", "count": 1},
        ]
        self.assertEqual(
            merge_staff_counts(rows, ["Ти Н.В."]),
            [
                {"name": "Ти Н.В.", "count": 4},
                {"name": "Петров и п", "count": 3},
                {"name": "Ти Н.А.", "count": 1},
            ],
        )


if __name__ == "__main__":
    unittest.main()
