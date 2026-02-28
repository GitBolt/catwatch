# tests/test_picam_relay.py
import pytest
from unittest.mock import patch
import base64
import time


def test_build_frame_message():
    from pi5.relay import build_frame_message
    jpeg = b"\xff\xd8\xff" + b"\x00" * 10
    msg = build_frame_message(jpeg, frame_id=3, mode="cat")
    assert msg["type"] == "frame"
    assert msg["frame_id"] == 3
    assert msg["mode"] == "cat"
    assert "client_ts" in msg
    decoded = base64.b64decode(msg["data"])
    assert decoded == jpeg


def test_build_frame_message_general_mode():
    from pi5.relay import build_frame_message
    jpeg = b"\xff\xd8\xff"
    msg = build_frame_message(jpeg, frame_id=0, mode="general")
    assert msg["mode"] == "general"
    assert msg["type"] == "frame"
