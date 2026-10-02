"""Smoke tests: boot the busy box, drive widgets, assert no exceptions."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).parent.parent / "app.py"


def _run():
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not at.exception, at.exception
    return at


def test_boots():
    at = _run()
    assert any("fleet" in (t.value or "").lower() for t in at.title)


def test_advance_feed():
    at = _run()
    at.button[0].set_value(True).run()  # "+1 min" is the first button
    assert not at.exception


def test_window_slider():
    at = _run()
    sliders = [s for s in at.slider if "window" in s.label.lower()]
    assert sliders, "window slider present"
    sliders[0].set_value(15).run()
    assert not at.exception


def test_reset_feed():
    at = _run()
    for b in at.button:
        if "reset" in b.label.lower():
            b.set_value(True).run()
            break
    assert not at.exception