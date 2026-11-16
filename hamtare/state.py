"""Statefil per show i STATE_DIR: guid -> löpnummer, plus omslagets URL.

Löpnumret delas ut i publiceringsordning första gången ett guid syns och
ändras sedan aldrig (beslut 2 i beslutsvyn 2026-11-16). Flödets eget
itunes:episode används inte, eftersom det har dubbletter.
"""
import json
import os
from pathlib import Path


class State:
    def __init__(self, path):
        self.path = Path(path)
        data = json.loads(self.path.read_text("utf-8")) if self.path.exists() else {}
        self.numbers: dict[str, int] = data.get("numbers", {})
        self.cover_url: str | None = data.get("cover_url")

    def assign_numbers(self, episodes):
        """Ger nya guid nästa lediga nummer, i den ordning de kommer (äldst först)."""
        nxt = max(self.numbers.values(), default=0) + 1
        for ep in episodes:
            if ep.guid not in self.numbers:
                self.numbers[ep.guid] = nxt
                nxt += 1

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"numbers": self.numbers, "cover_url": self.cover_url},
                                  ensure_ascii=False, indent=1), "utf-8")
        os.replace(tmp, self.path)
