"""Papkani ZIP qilib siqish (ichki papkalari bilan)."""
from __future__ import annotations

import os
import time
import zipfile
from pathlib import Path
from typing import Callable

# Allaqachon siqilgan fayllar qayta siqilmaydi - tezroq bo'ladi
STORE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".zip", ".rar", ".7z", ".mp4", ".mov",
             ".avi", ".mkv", ".mp3", ".cdr", ".docx", ".xlsx", ".pptx", ".psd", ".tif", ".tiff", ".heic"}
SKIP_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}
MAX_FILES = 50_000


class ZipTooBig(Exception):
    pass


def scan(folder: Path) -> tuple[list[Path], int]:
    """Papkadagi barcha fayllar va umumiy hajm."""
    files: list[Path] = []
    total = 0
    for dirpath, dirnames, filenames in os.walk(folder, onerror=lambda e: None):
        dirnames[:] = [d for d in dirnames if not d.startswith("$")]
        for n in filenames:
            if n.lower() in SKIP_NAMES or n.startswith("~$"):
                continue
            p = Path(dirpath) / n
            try:
                total += p.stat().st_size
            except OSError:
                continue
            files.append(p)
            if len(files) > MAX_FILES:
                raise ZipTooBig(f"Papkada {MAX_FILES} tadan ko'p fayl bor")
    return files, total


def make_zip(folder: Path, files: list[Path], total: int, out: Path,
             progress: Callable[[int, int], None] | None = None) -> list[str]:
    """ZIP yaratadi. O'qib bo'lmagan (band/ruxsatsiz) fayllar ro'yxatini qaytaradi."""
    skipped: list[str] = []
    done = 0
    last = 0.0
    with zipfile.ZipFile(out, "w", allowZip64=True) as z:
        for p in files:
            arc = Path(folder.name) / p.relative_to(folder)
            method = zipfile.ZIP_STORED if p.suffix.lower() in STORE_EXT else zipfile.ZIP_DEFLATED
            try:
                z.write(p, arc.as_posix(), compress_type=method, compresslevel=6 if method else None)
            except (OSError, ValueError):
                skipped.append(str(p.relative_to(folder)))
                continue
            try:
                done += p.stat().st_size
            except OSError:
                pass
            now = time.monotonic()
            if progress and now - last > 2:
                last = now
                progress(done, total)
    return skipped
