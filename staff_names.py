"""Сопоставление вариантов записи ФИО сотрудников со справочником."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence


def staff_name_key(value: str) -> tuple[str, ...]:
    """Игнорирует регистр, пробелы и точки, сохраняя границы слов."""
    return tuple(re.findall(r"[^\W\d_]+", value.casefold()))


def _reference_names(references: Sequence[str]) -> dict[tuple[str, ...], str]:
    names: dict[tuple[str, ...], str] = {}
    for reference in references:
        key = staff_name_key(reference)
        if not key:
            continue
        canonical = reference.strip()
        if key not in names or canonical.count(".") > names[key].count("."):
            # В справочнике могут уже быть оба варианта: «Ти Н В» и «Ти Н.В.».
            # Предпочитаем запись с оформленными инициалами.
            names[key] = canonical
    return names


def canonical_staff_name(value: str, references: Sequence[str]) -> str:
    """Возвращает наиболее оформленное имя с теми же словами и инициалами."""
    original = value.strip()
    key = staff_name_key(original)
    if not key:
        return original
    return _reference_names(references).get(key) or original


def merge_staff_counts(
    rows: Iterable[Mapping[str, object]], references: Sequence[str]
) -> list[dict[str, str | int]]:
    """Объединяет варианты в отчёте без изменения старых записей БД."""
    known_names = _reference_names(references)
    counts: dict[tuple[object, ...], int] = defaultdict(int)
    labels: dict[tuple[object, ...], str] = {}
    label_weights: dict[tuple[object, ...], int] = {}
    for row in rows:
        original = str(row["name"]).strip()
        key = staff_name_key(original)
        if key:
            group = ("normalized", *key)
            label = known_names.get(key) or original
        else:
            group = ("literal", original)
            label = original
        count = int(row["count"])
        counts[group] += count
        if count > label_weights.get(group, -1):
            labels[group] = label
            label_weights[group] = count
    return [
        {"name": labels[group], "count": count}
        for group, count in sorted(counts.items(), key=lambda item: (-item[1], labels[item[0]]))
    ]
