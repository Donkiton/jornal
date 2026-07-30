"""Сборка onedir-приложения и опциональная публикация в общей папке UPD."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from app_version import APP_VERSION


PROJECT_DIR = Path(__file__).resolve().parent
DIST_DIR = PROJECT_DIR / "dist"
APP_BUILD_DIR = DIST_DIR / "JournalPatients"
VERSION_FILE = PROJECT_DIR / "windows_version_info.txt"


def generate_windows_version_file() -> None:
    major, minor, patch = (int(value) for value in APP_VERSION.split("."))
    VERSION_FILE.write_text(
        f"""# Автоматически создано build_release.py
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, 0),
    prodvers=({major}, {minor}, {patch}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '041904B0',
        [
          StringStruct('CompanyName', 'Журнал пациентов'),
          StringStruct('FileDescription', 'Журнал пациентов'),
          StringStruct('FileVersion', '{APP_VERSION}'),
          StringStruct('InternalName', 'JournalPatients'),
          StringStruct('OriginalFilename', 'JournalPatients.exe'),
          StringStruct('ProductName', 'Журнал пациентов'),
          StringStruct('ProductVersion', '{APP_VERSION}')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1049, 1200])])
  ]
)
""",
        encoding="utf-8",
    )


def build_application() -> None:
    generate_windows_version_file()
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "JournalPatients.spec"],
        cwd=PROJECT_DIR,
        check=True,
    )


def create_release_archive() -> Path:
    if not (APP_BUILD_DIR / "JournalPatients.exe").is_file():
        raise FileNotFoundError("Собранная программа не найдена")
    archive_path = DIST_DIR / f"JournalPatients-{APP_VERSION}.zip"
    temporary_path = archive_path.with_suffix(".zip.tmp")
    if temporary_path.exists():
        temporary_path.unlink()
    with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for item in APP_BUILD_DIR.rglob("*"):
            if item.is_file():
                archive.write(item, item.relative_to(APP_BUILD_DIR))
    os.replace(temporary_path, archive_path)
    return archive_path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def publish_release(archive_path: Path, shared_root: Path) -> Path:
    if not shared_root.is_dir():
        raise FileNotFoundError("Общая папка журнала не найдена")
    updates_dir = shared_root / "UPD"
    release_dir = updates_dir / "releases" / APP_VERSION
    release_dir.mkdir(parents=True, exist_ok=True)
    published_archive = release_dir / archive_path.name
    archive_temp = published_archive.with_suffix(".zip.tmp")
    shutil.copy2(archive_path, archive_temp)
    os.replace(archive_temp, published_archive)

    manifest = {
        "version": APP_VERSION,
        "package": f"releases/{APP_VERSION}/{archive_path.name}",
        "sha256": sha256(published_archive),
        "size": published_archive.stat().st_size,
        "published_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    manifest_path = updates_dir / "latest.json"
    manifest_temp = updates_dir / "latest.json.tmp"
    manifest_temp.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(manifest_temp, manifest_path)
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Сборка и публикация Журнала пациентов")
    parser.add_argument(
        "--publish-root",
        type=Path,
        help="Общая папка Jornal-oper; если не указана, релиз останется в dist",
    )
    arguments = parser.parse_args()
    build_application()
    archive = create_release_archive()
    print(f"Сборка: {APP_BUILD_DIR}")
    print(f"Архив: {archive}")
    if arguments.publish_root:
        manifest = publish_release(archive, arguments.publish_root)
        print(f"Опубликовано: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
