import cv2


class VideoSource:
    """Unified video source: camera index (int), RTSP/file path (str), or picamera2 object."""

    def __init__(self, source):
        self._picam = None
        if isinstance(source, int) or isinstance(source, str):
            self._cap = cv2.VideoCapture(source)
            if not self._cap.isOpened():
                raise RuntimeError(f"Cannot open video source: {source}")
        else:
            # Assume picamera2 object
            self._picam = source
            self._cap = None

    def read(self):
        """Returns (frame_bgr, gray) or raises StopIteration."""
        if self._picam is not None:
            import numpy as np
            frame = self._picam.capture_array()
            if frame.shape[2] == 4:  # RGBA from picamera2
                frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            return frame, gray

        ok, frame = self._cap.read()
        if not ok:
            raise StopIteration("Video source ended")
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return frame, gray

    def release(self):
        if self._cap is not None:
            self._cap.release()
