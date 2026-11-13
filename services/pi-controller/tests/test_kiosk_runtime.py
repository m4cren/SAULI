"""Registered kiosk runtime stays authenticated through transient failures."""

from urllib.error import HTTPError

import pytest

from sauli_pi.communication.backend_client import DeviceApiError, request_json
from sauli_pi.config import Config
from sauli_pi.main import run


def config(tmp_path):
    return Config("https://api.example.test", "https://app.example.test",
                  "KIOSK-A", "SAULI-A", tmp_path / "credential", heartbeat_seconds=10)


class Browser:
    def __init__(self):
        self.terminated = False
        self.poll_count = 0

    def poll(self):
        self.poll_count += 1
        return None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout):
        assert timeout == 5


def prepare(monkeypatch):
    monkeypatch.setattr("sauli_pi.main.read_credential", lambda _path: "credential")
    monkeypatch.setattr("sauli_pi.main.browser_url", lambda *_args: "https://app.example.test/kiosk/activate?code=test")
    monkeypatch.setattr("sauli_pi.main.time.sleep", lambda _seconds: None)
    monkeypatch.setenv("DISPLAY", ":0")


def test_startup_retries_transient_heartbeat_before_opening_browser(monkeypatch, tmp_path):
    prepare(monkeypatch)
    attempts = []
    launches = []

    def heartbeat(_config, _credential):
        attempts.append(1)
        if len(attempts) < 3:
            raise DeviceApiError("unavailable", 503)

    def popen(*_args, **_kwargs):
        launches.append(1)
        browser = Browser()
        browser.poll = lambda: 0
        return browser

    monkeypatch.setattr("sauli_pi.main.heartbeat", heartbeat)
    monkeypatch.setattr("sauli_pi.main.subprocess.Popen", popen)
    with pytest.raises(RuntimeError, match="browser exited"):
        run(config(tmp_path))
    assert len(attempts) == 3
    assert len(launches) == 1


def test_denied_startup_heartbeat_does_not_launch_browser(monkeypatch, tmp_path):
    prepare(monkeypatch)
    monkeypatch.setattr("sauli_pi.main.heartbeat", lambda *_args: (_ for _ in ()).throw(DeviceApiError("denied", 403)))
    monkeypatch.setattr("sauli_pi.main.subprocess.Popen", lambda *_args, **_kwargs: pytest.fail("browser must stay closed"))
    with pytest.raises(DeviceApiError) as exc:
        run(config(tmp_path))
    assert exc.value.status_code == 403


def test_repeated_runtime_outage_stops_browser_after_bounded_retries(monkeypatch, tmp_path):
    prepare(monkeypatch)
    calls = []
    browser = Browser()

    def heartbeat(_config, _credential):
        calls.append(1)
        if len(calls) > 1:
            raise DeviceApiError("unavailable", 503)

    monkeypatch.setattr("sauli_pi.main.heartbeat", heartbeat)
    monkeypatch.setattr("sauli_pi.main.subprocess.Popen", lambda *_args, **_kwargs: browser)
    with pytest.raises(DeviceApiError) as exc:
        run(config(tmp_path))
    assert exc.value.status_code == 503
    assert len(calls) == 4
    assert browser.terminated


def test_http_error_preserves_status_without_provider_body(monkeypatch):
    def denied(*_args, **_kwargs):
        raise HTTPError("https://api.example.test", 403, "secret provider text", None, None)

    monkeypatch.setattr("sauli_pi.communication.backend_client.urlopen", denied)
    with pytest.raises(DeviceApiError) as exc:
        request_json("https://api.example.test", "/api/kiosk-devices/heartbeat", {}, "secret")
    assert exc.value.status_code == 403
    assert "secret" not in str(exc.value)
