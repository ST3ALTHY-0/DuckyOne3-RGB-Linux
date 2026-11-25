#!/usr/bin/env python3
"""V4 RGB CLI. Requires explicit --send before opening a HID device."""
import argparse
from dataclasses import asdict
import json
import math
import time

if __package__:
    from . import rgb_effects, rgb_v4
else:
    import rgb_effects
    import rgb_v4


def color(value):
    value = value.removeprefix("#")
    try:
        if len(value) == 6:
            return bytes.fromhex(value)
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("Use a six-digit RGB hex value")


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--device")
    cli.add_argument("--send", action="store_true")
    cli.add_argument("--brightness", type=int, default=65535)
    cli.add_argument("--overlays", type=lambda x: int(x, 0), default=0)
    cli.add_argument("--lease-ms", type=int, default=0)
    cli.add_argument("--leave-active", action="store_true")
    sub = cli.add_subparsers(dest="action", required=True)
    sub.add_parser("caps")
    sub.add_parser("status")
    native = sub.add_parser("native")
    native.add_argument("token", type=lambda x: int(x, 0))
    static = sub.add_parser("static")
    static.add_argument("color", type=color)
    key = sub.add_parser("key")
    key.add_argument("bank", type=int, choices=range(5))
    key.add_argument("index", type=int, choices=range(15))
    key.add_argument("color", type=color)
    gradient = sub.add_parser("gradient")
    gradient.add_argument("left", type=color)
    gradient.add_argument("right", type=color)
    rainbow = sub.add_parser("rainbow")
    rainbow.add_argument("--fps", type=float, default=30)
    rainbow.add_argument("--speed", type=float, default=0.3, help="Hue cycles per second")
    return cli


def frame(args, phase=0):
    if args.action == "static":
        return rgb_effects.solid(args.color)
    if args.action == "key":
        data = bytearray(rgb_v4.FRAME_BYTES)
        start = 3 * (args.bank * rgb_v4.SLOTS + args.index)
        data[start:start+3] = args.color
        return bytes(data)
    if args.action == "gradient":
        return rgb_effects.gradient(args.left, args.right)
    return rgb_effects.rainbow(phase)


def run(args, client):
    if args.action == "caps":
        print(json.dumps(asdict(client.caps)))
        return
    if args.action == "status":
        print(json.dumps(asdict(client.status())))
        return
    if args.action == "native":
        client.native(args.token)
        return
    client.external(lease_ms=args.lease_ms, overlays=args.overlays)
    client.brightness(args.brightness)
    if args.action == "rainbow":
        start = time.monotonic()
        while True:
            tick = time.monotonic()
            client.set_frame(frame(args, (tick - start) * args.speed), fast=True)
            delay = 1 / args.fps - (time.monotonic() - tick)
            if delay > 0:
                time.sleep(delay)
    reply = client.set_frame(frame(args), fast=True)
    client.wait_displayed(reply.accepted)
    if args.leave_active:
        print(f"Frame displayed. Return to native with native {client.token:#x}")
        return
    print("Frame displayed. Press Ctrl-C to restore native lighting.")
    while True:
        time.sleep(min(1, args.lease_ms / 3000) if args.lease_ms else 1)
        if args.lease_ms:
            client.keepalive()


def main():
    cli = parser()
    args = cli.parse_args()
    if args.action == "rainbow":
        if not 1 <= args.fps <= 200 or not math.isfinite(args.speed):
            cli.error("Use 1–200 FPS and a finite speed")
        if args.leave_active:
            cli.error("--leave-active applies to static frames")
    if not 0 <= args.brightness <= 65535:
        cli.error("Brightness must be between 0 and 65535")
    if not args.send:
        if args.action in ("static", "key", "gradient", "rainbow"):
            print(frame(args).hex())
        print("Offline preview. No HID device opened.")
        return
    client = None
    leave_active = False
    try:
        client = rgb_v4.RGBController.connect(args.device)
        run(args, client)
        leave_active = args.leave_active
    except KeyboardInterrupt:
        pass
    except (OSError, RuntimeError, ValueError) as error:
        cli.error(str(error))
    finally:
        if client is not None:
            try:
                client.close(restore=not leave_active)
            except (OSError, RuntimeError) as error:
                cli.exit(1, f"Could not confirm return to native mode: {error}\n")


if __name__ == "__main__":
    main()
