# pi5/capture.py
import requests


class PicamCapture:
    """Polls a picam /snapshot endpoint and returns raw JPEG bytes."""

    def __init__(self, url: str, interval: float = 0.2, timeout: float = 3.0, skip_health_check: bool = False):
        self.url = url.rstrip("/")
        self.interval = interval
        self.timeout = timeout
        self._snapshot_url = f"{self.url}/snapshot"
        if not skip_health_check:
            if not self.health_check():
                raise RuntimeError(
                    f"Cannot reach picam at {self.url}. "
                    "Check that the Pi is running and the tunnel URL is correct."
                )

    def health_check(self) -> bool:
        try:
            r = requests.get(self._snapshot_url, timeout=self.timeout)
            return r.status_code == 200
        except Exception:
            return False

    def get_frame(self) -> bytes | None:
        try:
            r = requests.get(self._snapshot_url, timeout=self.timeout)
            if r.status_code == 200:
                return r.content
            return None
        except Exception:
            return None
