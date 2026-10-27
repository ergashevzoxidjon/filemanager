"""Papkalarni ko'rish va xavfsizlik tekshiruvi."""
import os
import threading
from pathlib import Path

# Bu papkalar ro'yxatda ko'rsatilmaydi
HIDDEN_NAMES = {"system volume information", "$recycle.bin", "recycler", "desktop.ini",
                "thumbs.db", "pagefile.sys", "hiberfil.sys", "swapfile.sys"}


class Registry:
    """Telegram tugmasiga uzun yo'lni sig'dirib bo'lmaydi (64 bayt),
    shuning uchun har bir yo'lga qisqa raqam beramiz."""

    def __init__(self) -> None:
        self._by_path: dict[str, str] = {}
        self._by_id: dict[str, str] = {}
        self._n = 0
        self._lock = threading.Lock()

    def id(self, path: Path) -> str:
        key = str(path)
        with self._lock:
            if key not in self._by_path:
                self._n += 1
                pid = format(self._n, "x")
                self._by_path[key] = pid
                self._by_id[pid] = key
            return self._by_path[key]

    def path(self, pid: str) -> Path | None:
        p = self._by_id.get(pid)
        return Path(p) if p else None


def _norm(path: Path) -> str:
    return os.path.normcase(os.path.abspath(str(path))).rstrip("\\/")


def same_path(a: Path, b: Path) -> bool:
    return _norm(a) == _norm(b)


def is_allowed(path: Path, allowed: list[Path]) -> bool:
    """Yo'l ruxsat berilgan papkalardan birining ichidami? (../ hiylalarga qarshi)"""
    try:
        p = _norm(path.resolve())
    except OSError:
        return False
    for root in allowed:
        r = _norm(root.resolve())
        if p == r or p.startswith(r + os.sep):
            return True
    return False


def list_dir(path: Path) -> tuple[list[Path], list[tuple[Path, int]], str | None]:
    """(papkalar, [(fayl, hajmi)], xato_matni)"""
    dirs: list[Path] = []
    files: list[tuple[Path, int]] = []
    try:
        with os.scandir(path) as it:
            for e in it:
                name = e.name
                if name.lower() in HIDDEN_NAMES or name.startswith("$") or name.startswith("~$"):
                    continue
                try:
                    if e.is_dir():
                        dirs.append(Path(e.path))
                    elif e.is_file():
                        files.append((Path(e.path), e.stat().st_size))
                except OSError:
                    continue
    except PermissionError:
        return [], [], "⛔ Bu papkaga kirishga ruxsat yo'q"
    except OSError as e:
        return [], [], f"⚠️ Ochib bo'lmadi: {e.strerror or e}"
    dirs.sort(key=lambda p: p.name.lower())
    files.sort(key=lambda f: f[0].name.lower())
    return dirs, files, None


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def short(name: str, limit: int = 38) -> str:
    return name if len(name) <= limit else name[: limit - 1] + "…"


def display_name(path: Path) -> str:
    """D:\\ uchun 'D:\\', boshqalar uchun papka nomi."""
    return path.name or str(path)
