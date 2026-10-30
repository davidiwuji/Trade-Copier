import time
from typing import Dict, Tuple


class DuplicateFilter:
    """
    Prevents duplicate trade execution when channels repost or forward
    the same signal within a configured time window.
    """
    def __init__(self, window_seconds: int = 300):
        self.window_seconds = window_seconds
        # Key: (symbol, action), Value: timestamp
        self._history: Dict[Tuple[str, str], float] = {}

    def is_duplicate(self, symbol: str, action: str) -> bool:
        key = (symbol.upper(), action.upper())
        now = time.time()

        if key in self._history:
            last_time = self._history[key]
            if now - last_time < self.window_seconds:
                return True

        self._history[key] = now
        self._cleanup(now)
        return False

    def _cleanup(self, now: float) -> None:
        """Remove entries older than 2x the window seconds."""
        cutoff = now - (self.window_seconds * 2)
        keys_to_remove = [k for k, t in self._history.items() if t < cutoff]
        for k in keys_to_remove:
            del self._history[k]
