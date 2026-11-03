"""Enroll once; then launch only the browser session assigned to this device."""

import argparse
import getpass
import logging
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import urlencode

from sauli_pi.communication.backend_client import DeviceApiError, request_json
from sauli_pi.config import Config, read_credential, save_credential

LOG = logging.getLogger("sauli.pi")
VERSION = "0.1.0"
BROWSER_RENEWAL_SECONDS = 7 * 60 * 60


def enroll(config: Config) -> None:
    if config.credential_file.exists():
        raise RuntimeError("This device is already enrolled. Revoke it before replacement.")
    pairing_code = getpass.getpass("Administrator-approved pairing code: ").strip()
    response = request_json(config.backend_url, "/api/kiosk-devices/enroll",
                            {"device_code": config.device_code, "pairing_code": pairing_code})
    credential = response.get("device_credential")
    if (not isinstance(credential, str) or not response.get("unit_id")
            or response.get("unit_code") != config.unit_code):
        raise DeviceApiError("Enrollment was not accepted")
    save_credential(config.credential_file, credential)
    LOG.info("Device %s enrolled for registered unit %s", config.device_code, config.unit_code)


def heartbeat(config: Config, credential: str) -> None:
    request_json(config.backend_url, "/api/kiosk-devices/heartbeat",
                 {"controller_version": VERSION}, credential)


def browser_url(config: Config, credential: str) -> str:
    response = request_json(config.backend_url, "/api/kiosk-devices/browser-bootstrap", {}, credential)
    code = response.get("bootstrap_code")
    if not isinstance(code, str) or len(code) < 50:
        raise DeviceApiError("Browser bootstrap was not issued")
    return config.frontend_url + "/kiosk/activate?" + urlencode({"code": code})


def run(config: Config) -> None:
    credential = read_credential(config.credential_file)
    heartbeat(config, credential)  # Fail closed before starting Chromium.
    url = browser_url(config, credential)
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        raise RuntimeError("A labwc display is required to launch Chromium")
    browser = subprocess.Popen([config.browser, "--kiosk", "--no-first-run", url],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    started_at = time.monotonic()
    LOG.info("Kiosk browser started for %s", config.device_code)
    while browser.poll() is None:
        time.sleep(config.heartbeat_seconds)
        try:
            heartbeat(config, credential)
        except DeviceApiError:
            LOG.error("Device heartbeat denied or unavailable; stopping kiosk browser")
            browser.terminate()
            try:
                browser.wait(timeout=5)
            except subprocess.TimeoutExpired:
                browser.kill()
            raise
        if time.monotonic() - started_at >= BROWSER_RENEWAL_SECONDS:
            LOG.info("Renewing kiosk browser session for %s", config.device_code)
            browser.terminate()
            try:
                browser.wait(timeout=5)
            except subprocess.TimeoutExpired:
                browser.kill()
            raise RuntimeError("Kiosk session renewal required")
    raise RuntimeError("Kiosk browser exited; systemd will start a fresh authenticated session")


def main() -> None:
    parser = argparse.ArgumentParser(description="SAULI registered Pi controller")
    parser.add_argument("command", choices=("enroll", "run", "heartbeat"))
    parser.add_argument("--config", type=Path, default=Path("/etc/sauli/controller.json"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    config = Config.load(args.config)
    if args.command == "enroll":
        enroll(config)
    elif args.command == "heartbeat":
        heartbeat(config, read_credential(config.credential_file))
    else:
        run(config)


if __name__ == "__main__":
    main()
