"""Fayl nomi bo'yicha qidiruv."""
import os
import time
from pathlib import Path

SKIP_DIRS = {"windows", "program files", "program files (x86)", "programdata", "appdata",
             "$recycle.bin", "system volume information", "node_modules", ".git"}


def search_files(roots: list[Path], query: str, limit: int = 30,
                 time_limit: float = 30.0) -> tuple[list[tuple[Path, bool]], bool]:
    """Nomida `query` bor fayl va papkalarni topadi.
    Qaytaradi: ([(yo'l, papkami)], natijalar_toʻliq_emasmi)"""
    words = query.lower().split()
    results: list[tuple[Path, bool]] = []
    seen: set[str] = set()
    started = time.monotonic()

    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None):
            dirnames[:] = [d for d in dirnames
                           if d.lower() not in SKIP_DIRS and not d.startswith("$")]
            for name, is_dir in [(d, True) for d in dirnames] + [(f, False) for f in filenames]:
                low = name.lower()
                if all(w in low for w in words):
                    full = os.path.join(dirpath, name)
                    if full in seen:
                        continue
                    seen.add(full)
                    results.append((Path(full), is_dir))
                    if len(results) >= limit:
                        return results, True
            if time.monotonic() - started > time_limit:
                return results, True
    return results, False
