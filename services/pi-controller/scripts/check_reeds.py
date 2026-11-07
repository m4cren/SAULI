"""Input-only first bring-up: BCM8/24 medium and BCM7/26 pocket.

This script deliberately does not import the SAULI controller or claim outputs.
"""

import time


def main() -> None:
    from gpiozero import DigitalInputDevice

    inputs = []
    try:
        for name, bcm, header in (("medium", 8, 24), ("pocket", 7, 26)):
            try:
                device = DigitalInputDevice(bcm, pull_up=True, bounce_time=0.05)
            except Exception as exc:
                raise SystemExit(
                    f"BCM{bcm} (physical {header}) is unavailable. Check SPI0 CE ownership "
                    "and stop the SAULI hardware service if it owns this input. "
                    f"Original error: {type(exc).__name__}"
                ) from exc
            inputs.append((name, bcm, header, device))
        previous = {}
        for name, bcm, header, device in inputs:
            high = bool(device.pin.state)
            previous[bcm] = high
            print(f"{name} BCM{bcm}/physical{header}: {'HIGH' if high else 'LOW'} at startup", flush=True)
        while True:
            time.sleep(0.05)
            for name, bcm, header, device in inputs:
                high = bool(device.pin.state)
                if high != previous[bcm]:
                    previous[bcm] = high
                    print(f"{name} BCM{bcm}/physical{header}: {'HIGH' if high else 'LOW'}", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        for _, _, _, device in inputs:
            device.close()


if __name__ == "__main__":
    main()
