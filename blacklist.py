import json
import os
from datetime import datetime

BLACKLIST_FILE = "blacklist.json"


class BlacklistManager:
    def __init__(self):
        self.filepath = BLACKLIST_FILE
        self._data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save(self):
        with open(self.filepath, "w") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def add(self, wallet: str, rug_count: int):
        if wallet == "unknown" or not wallet:
            return
        self._data[wallet] = {
            "rug_count": rug_count,
            "last_rug": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "added_at": datetime.now().isoformat()
        }
        self._save()

    def is_blacklisted(self, wallet: str) -> bool:
        return wallet in self._data

    def get(self, wallet: str) -> dict:
        return self._data.get(wallet, {})

    def get_all(self) -> dict:
        return self._data

    def remove(self, wallet: str):
        if wallet in self._data:
            del self._data[wallet]
            self._save()
