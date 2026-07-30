"""Проверка, подготовка и безопасная установка локальных обновлений."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import shutil
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


ProgressCallback = Callable[[int, str], None]


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    package_path: Path
    sha256: str
    size: int


def version_tuple(value: str) -> tuple[int, int, int]:
    """Разбирает поддерживаемую трёхчастную версию."""
    parts = value.strip().split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise ValueError(f"Некорректная версия: {value}")
    return tuple(int(part) for part in parts)  # type: ignore[return-value]


def find_newer_release(updates_dir: Path, current_version: str) -> ReleaseInfo | None:
    """Возвращает опубликованный релиз, только если он новее текущего."""
    manifest_path = updates_dir / "latest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        version = str(payload["version"]).strip()
        package_value = str(payload["package"]).strip()
        sha256 = str(payload["sha256"]).strip().lower()
        size = int(payload["size"])
        if version_tuple(version) <= version_tuple(current_version):
            return None
        if len(sha256) != 64 or any(char not in "0123456789abcdef" for char in sha256):
            return None
        if size <= 0:
            return None
        package_path = (updates_dir / package_value).resolve()
        updates_root = updates_dir.resolve()
        if updates_root != package_path and updates_root not in package_path.parents:
            return None
        if not package_path.is_file():
            return None
        return ReleaseInfo(version, package_path, sha256, size)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def _copy_with_progress(
    source: Path,
    target: Path,
    callback: ProgressCallback,
    start_percent: int,
    end_percent: int,
    stage: str,
) -> None:
    total = max(source.stat().st_size, 1)
    copied = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as input_file, target.open("wb") as output_file:
        while True:
            chunk = input_file.read(1024 * 1024)
            if not chunk:
                break
            output_file.write(chunk)
            copied += len(chunk)
            percent = start_percent + int((end_percent - start_percent) * copied / total)
            callback(min(percent, end_percent), stage)
    shutil.copystat(source, target)


def _sha256_with_progress(
    path: Path,
    callback: ProgressCallback,
    start_percent: int,
    end_percent: int,
) -> str:
    total = max(path.stat().st_size, 1)
    processed = 0
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while True:
            chunk = file.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            processed += len(chunk)
            percent = start_percent + int((end_percent - start_percent) * processed / total)
            callback(min(percent, end_percent), "Проверка целостности релиза")
    return digest.hexdigest()


def _safe_extract(
    archive_path: Path,
    destination: Path,
    callback: ProgressCallback,
    start_percent: int,
    end_percent: int,
) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        members = [member for member in archive.infolist() if not member.is_dir()]
        total = max(sum(member.file_size for member in members), 1)
        extracted = 0
        destination_root = destination.resolve()
        for member in archive.infolist():
            member_target = (destination / member.filename).resolve()
            if destination_root != member_target and destination_root not in member_target.parents:
                raise ValueError("Архив обновления содержит небезопасный путь")
            if member.is_dir():
                member_target.mkdir(parents=True, exist_ok=True)
                continue
            member_target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, member_target.open("wb") as target:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    target.write(chunk)
                    extracted += len(chunk)
                    percent = start_percent + int((end_percent - start_percent) * extracted / total)
                    callback(min(percent, end_percent), "Распаковка новой версии")


def prepare_release(
    release: ReleaseInfo,
    cache_root: Path,
    callback: ProgressCallback,
) -> Path:
    """Копирует релиз с общего диска, проверяет и распаковывает локально."""
    version_dir = cache_root / release.version
    archive_path = version_dir / f"JournalPatients-{release.version}.zip"
    stage_dir = version_dir / "package"
    if version_dir.exists():
        shutil.rmtree(version_dir)
    version_dir.mkdir(parents=True, exist_ok=True)

    callback(2, "Подготовка обновления")
    _copy_with_progress(release.package_path, archive_path, callback, 3, 35, "Копирование обновления")
    if archive_path.stat().st_size != release.size:
        raise ValueError("Размер архива обновления не совпадает с опубликованным")
    digest = _sha256_with_progress(archive_path, callback, 35, 50)
    if digest != release.sha256:
        raise ValueError("Контрольная сумма обновления не совпадает")

    stage_dir.mkdir(parents=True, exist_ok=True)
    _safe_extract(archive_path, stage_dir, callback, 50, 70)
    if not (stage_dir / "JournalPatients.exe").is_file():
        raise ValueError("В архиве обновления отсутствует JournalPatients.exe")
    callback(70, "Новая версия подготовлена")
    return stage_dir


def _wait_for_process(process_id: int, callback: ProgressCallback) -> None:
    if process_id <= 0 or os.name != "nt":
        return
    synchronize = 0x00100000
    wait_timeout = 0x00000102
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    open_process.restype = ctypes.c_void_p
    wait_for_single_object = kernel32.WaitForSingleObject
    wait_for_single_object.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    wait_for_single_object.restype = ctypes.c_ulong
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_int

    handle = open_process(synchronize, False, process_id)
    if not handle:
        return
    try:
        callback(71, "Ожидание закрытия журнала")
        while wait_for_single_object(handle, 200) == wait_timeout:
            time.sleep(0.05)
    finally:
        close_handle(handle)


def _tree_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _copy_tree_with_progress(
    source: Path,
    destination: Path,
    callback: ProgressCallback,
    start_percent: int,
    end_percent: int,
) -> None:
    files = [item for item in source.rglob("*") if item.is_file()]
    total = max(sum(item.stat().st_size for item in files), 1)
    copied = 0
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.rglob("*"):
        relative = item.relative_to(source)
        target = destination / relative
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with item.open("rb") as input_file, target.open("wb") as output_file:
            while True:
                chunk = input_file.read(1024 * 1024)
                if not chunk:
                    break
                output_file.write(chunk)
                copied += len(chunk)
                percent = start_percent + int((end_percent - start_percent) * copied / total)
                callback(min(percent, end_percent), "Копирование файлов программы")
        shutil.copystat(item, target)


def apply_staged_update(
    stage_dir: Path,
    target_dir: Path,
    parent_process_id: int,
    callback: ProgressCallback,
) -> None:
    """Заменяет установленную onedir-сборку с возвратом старой при ошибке."""
    stage_dir = stage_dir.resolve()
    target_dir = target_dir.resolve()
    if stage_dir == target_dir or target_dir.parent == target_dir:
        raise ValueError("Некорректная папка установки")
    if not (stage_dir / "JournalPatients.exe").is_file():
        raise ValueError("Подготовленная версия приложения не найдена")

    _wait_for_process(parent_process_id, callback)
    candidate_dir = target_dir.parent / f"{target_dir.name}.new"
    backup_dir = target_dir.parent / f"{target_dir.name}.old"
    if candidate_dir.exists():
        shutil.rmtree(candidate_dir)
    if backup_dir.exists():
        shutil.rmtree(backup_dir)

    callback(72, "Подготовка файлов программы")
    _copy_tree_with_progress(stage_dir, candidate_dir, callback, 73, 92)
    if _tree_size(candidate_dir) <= 0:
        raise ValueError("Не удалось подготовить файлы новой версии")

    callback(94, "Замена версии программы")
    target_was_moved = False
    try:
        target_dir.rename(backup_dir)
        target_was_moved = True
        candidate_dir.rename(target_dir)
    except Exception:
        if target_was_moved and not target_dir.exists() and backup_dir.exists():
            backup_dir.rename(target_dir)
        raise

    callback(98, "Завершение установки")
    try:
        shutil.rmtree(backup_dir)
    except OSError:
        # Резервная папка безопасна и будет очищена при следующем обновлении.
        pass
    callback(100, "Обновление установлено")
