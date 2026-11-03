"""Enrollment must refuse credentials assigned to another unit."""

from pathlib import Path

import pytest

from sauli_pi.config import Config
from sauli_pi.main import DeviceApiError, enroll


def test_wrong_unit_enrollment_never_saves_credential(monkeypatch, tmp_path: Path):
    config = Config("https://api.example.test", "https://app.example.test", "KIOSK-A",
                    "SAULI-A", tmp_path / "credential")
    monkeypatch.setattr("sauli_pi.main.getpass.getpass", lambda _: "pairing-code")
    monkeypatch.setattr("sauli_pi.main.request_json", lambda *_args: {
        "device_credential": "secret", "unit_id": "uuid-b", "unit_code": "SAULI-B"})
    with pytest.raises(DeviceApiError, match="not accepted"):
        enroll(config)
    assert not config.credential_file.exists()
