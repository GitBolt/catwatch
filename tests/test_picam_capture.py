# tests/test_picam_capture.py
import pytest
from unittest.mock import patch
from pi5.capture import PicamCapture


def test_get_frame_returns_jpeg_bytes():
    fake_jpeg = b"\xff\xd8\xff" + b"\x00" * 100
    with patch("pi5.capture.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.content = fake_jpeg
        cap = PicamCapture("http://fake-pi:8080", skip_health_check=True)
        frame = cap.get_frame()
    assert frame == fake_jpeg


def test_get_frame_returns_none_on_http_error():
    with patch("pi5.capture.requests.get") as mock_get:
        mock_get.return_value.status_code = 500
        mock_get.return_value.content = b""
        cap = PicamCapture("http://fake-pi:8080", skip_health_check=True)
        frame = cap.get_frame()
    assert frame is None


def test_get_frame_returns_none_on_connection_error():
    with patch("pi5.capture.requests.get", side_effect=Exception("connection refused")):
        cap = PicamCapture("http://fake-pi:8080", skip_health_check=True)
        frame = cap.get_frame()
    assert frame is None


def test_health_check_returns_true_when_reachable():
    with patch("pi5.capture.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        cap = PicamCapture("http://fake-pi:8080", skip_health_check=True)
        assert cap.health_check() is True


def test_health_check_returns_false_when_unreachable():
    with patch("pi5.capture.requests.get", side_effect=Exception("timeout")):
        cap = PicamCapture("http://fake-pi:8080", skip_health_check=True)
        assert cap.health_check() is False


def test_init_raises_when_pi_unreachable():
    with patch("pi5.capture.requests.get", side_effect=Exception("unreachable")):
        with pytest.raises(RuntimeError, match="Cannot reach picam"):
            PicamCapture("http://fake-pi:8080")
