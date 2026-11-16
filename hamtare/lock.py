"""flock på en fil i STATE_DIR, så schemat och en manuell körning inte krockar."""
import fcntl
import os
from pathlib import Path


class Lock:
    def __init__(self, path):
        self.path = Path(path)
        self._fd = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            raise BlockingIOError(f"En annan körning håller låset: {self.path}")
        self._fd = fd
        return self

    def __exit__(self, *exc):
        os.close(self._fd)
        self._fd = None
