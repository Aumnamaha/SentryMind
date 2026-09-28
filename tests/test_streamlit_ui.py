"""Streamlit UI smoke and interaction tests without real external services."""

import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"

try:
    from streamlit.testing.v1 import AppTest
except ModuleNotFoundError:
    AppTest = None


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _SessionState(dict):
    def __getattr__(self, name):
        return self[name]

    def __setattr__(self, name, value):
        self[name] = value


class _FakeStreamlit:
    def __init__(self, clicks=(), state=None):
        self.clicks = set(clicks)
        self.session_state = state if state is not None else _SessionState()
        self.selectboxes = []
        self.buttons = []
        self.json_values = []
        self.text_inputs = []
        self.text_areas = []
        self.sidebar = self

    def __getattr__(self, name):
        if name in {
            "title",
            "caption",
            "markdown",
            "subheader",
            "code",
            "error",
            "success",
            "write",
            "header",
            "warning",
            "info",
            "metric",
            "expander",
            "columns",
            "form",
            "text_input",
            "text_area",
            "form_submit_button",
            "spinner",
            "cache_resource",
            "stop",
            "json",
            "selectbox",
            "toggle",
            "button",
            "set_page_config",
            "sidebar",
        }:
            return lambda *_args, **_kwargs: None
        raise AttributeError(name)

    def set_page_config(self, **_kwargs):
        pass

    def selectbox(self, label, options):
        self.selectboxes.append((label, options))
        return options[0]

    def toggle(self, label, value=False):
        return value

    def columns(self, count):
        return [_Context() for _ in range(count)]

    def button(self, label, key=None):
        self.buttons.append(label)
        return label in self.clicks

    def spinner(self, *_args, **_kwargs):
        return _Context()

    def expander(self, *_args, **_kwargs):
        return _Context()

    def form(self, *_args, **_kwargs):
        return _Context()

    def text_input(self, label, value=""):
        self.text_inputs.append(label)
        return value

    def text_area(self, label, value=""):
        self.text_areas.append(label)
        return value

    def form_submit_button(self, _label):
        return False

    def json(self, value):
        self.json_values.append(value)

    @staticmethod
    def cache_resource(function):
        return function

    @staticmethod
    def stop():
        raise RuntimeError("Streamlit stop")


class _FakeAppTest:
    def __init__(self, clicks=()):
        self.clicks = clicks
        self.state = _SessionState()
        self.exception = []
        self.json = []

    @classmethod
    def from_file(cls, _path):
        return cls()

    def run(self):
        fake = _FakeStreamlit(self.clicks, self.state)
        self.fake = fake
        with patch.dict(sys.modules, {"streamlit": fake}), patch(
            "agent.core.SentryMindAgent.query_local_qwen",
            return_value="deterministic test response",
        ):
            runpy.run_path(str(APP_PATH), run_name="__main__")
        self.exception = []
        self.json = [SimpleNamespace(value=value) for value in fake.json_values]
        return self

    @property
    def selectbox(self):
        return [
            SimpleNamespace(label=label, options=options)
            for label, options in self.fake.selectboxes
        ]

    @property
    def button(self):
        return [SimpleNamespace(label=label) for label in self.fake.buttons]

    def get(self, kind):
        return getattr(
            self.fake, {"text_input": "text_inputs", "text_area": "text_areas"}[kind]
        )


_UI_TESTER = AppTest if AppTest is not None else _FakeAppTest


def test_app_renders_incident_controls_and_retain_form():
    app = _UI_TESTER.from_file(str(APP_PATH)).run()
    assert not app.exception
    assert app.selectbox[0].label == "Select Production Alert"
    assert app.button[0].label == "Analyze Log (Without Memory)"
    assert app.button[1].label == "Analyze Log (With Memory Recall)"
    assert app.get("text_input")
    assert app.get("text_area")


def test_baseline_button_returns_analysis_without_memory():
    if AppTest is None:
        app = _FakeAppTest(clicks={"Analyze Log (Without Memory)"}).run()
        assert not app.exception
        # The fake app stores results in session_state
        analysis = app.state.get("last_analysis")
        assert analysis is not None
        assert analysis["result"]["use_memory"] is False
        assert analysis["result"]["memory_active"] is False
    else:
        app = AppTest.from_file(str(APP_PATH)).run()
        app.button[0].click().run()
        assert not app.exception
        # The new UI stores results in session_state, not st.json
        analysis = app.session_state.get("last_analysis")
        assert analysis is not None
        assert analysis["result"]["use_memory"] is False
        assert analysis["result"]["memory_active"] is False
