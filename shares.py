"""«Ulashish» tugmasi uchun: qisqa kod -> Telegram'dagi fayl (file_id).

Fayl bir marta Telegram'ga yuklangach, uni qayta yuklamasdan istalgan chatga
yuborish mumkin. Ro'yxat bot qayta yonganda ham yo'qolmasligi uchun faylda saqlanadi.
"""
import json
import secrets
import threading
from pathlib import Path

MAX_ITEMS = 1000


class ShareStore:
    def __init__(self, file: Path) -> None:
        self._file = file
        self._lock = threading.Lock()
        self._items: dict[str, dict] = {}
        try:
            self._items = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass

    def add(self, file_id: str, name: str, kind: str = "document") -> str:
        token = secrets.token_urlsafe(6)
        with self._lock:
            self._items[token] = {"file_id": file_id, "name": name, "kind": kind}
            if len(self._items) > MAX_ITEMS:  # eng eskilarini o'chiramiz
                for old in list(self._items)[: len(self._items) - MAX_ITEMS]:
                    del self._items[old]
            self._save()
        return token

    def get(self, token: str) -> dict | None:
        return self._items.get(token)

    def _save(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._items, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._file)
