#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read-only USB/webcam timeline. This never controls power or renews a watchdog."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

CANDIDATES = {('1209', '316d'), ('05ac', '1905'), ('0525', 'a4a2')}


def usb_snapshot(root=Path('/sys/bus/usb/devices')):
    devices = []
    for path in sorted(root.iterdir()):
        try:
            pair = tuple((path / name).read_text().strip()
                         for name in ('idVendor', 'idProduct'))
            if pair not in CANDIDATES:
                continue
            devices.append(dict(vendor=pair[0], product_id=pair[1],
                                product=(path / 'product').read_text().strip(),
                                bus=(path / 'busnum').read_text().strip(),
                                enumeration=(path / 'devnum').read_text().strip()))
        except FileNotFoundError:
            # A device disappearing between sysfs reads is a normal transition.
            continue
    return devices


def capture(path, device='/dev/video1'):
    run = subprocess.run([
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'v4l2',
        '-input_format', 'mjpeg', '-video_size', '1920x1080', '-i', device,
        '-vf', 'select=gte(n\\,15)', '-frames:v', '1', '-n', str(path),
    ], capture_output=True, text=True, timeout=15)
    if run.returncode:
        raise RuntimeError(f'camera capture exited {run.returncode}')
    data = path.read_bytes()
    if not (data.startswith(b'\xff\xd8') and data.endswith(b'\xff\xd9')):
        raise RuntimeError('camera output is not a complete JPEG')
    return dict(file=path.name, sha256=hashlib.sha256(data).hexdigest(),
                bytes=len(data), discarded_frames=15,
                decoder_diagnostic=bool(run.stderr.strip()))


def observe(output, seconds, interval, camera):
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    count = 0
    camera_errors = 0
    with (output / 'events.jsonl').open('x') as log:
        while True:
            record = dict(sample=count, elapsed_seconds=round(time.monotonic()-started, 3),
                          utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                          usb_before=usb_snapshot())
            if camera:
                try:
                    record['camera'] = capture(output / f'frame-{count:05d}.jpg')
                except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                    record['camera_error'] = str(exc)
                    camera_errors += 1
            record['usb_after'] = usb_snapshot()
            record['sample_complete_elapsed_seconds'] = round(time.monotonic()-started, 3)
            log.write(json.dumps(record, sort_keys=True)+'\n')
            log.flush()
            os.fsync(log.fileno())
            count += 1
            remaining = started+seconds-time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(interval, remaining))
    summary = dict(scope='read-only observation; no power/input/watchdog actions',
                   samples=count, camera_requested=camera, camera_errors=camera_errors,
                   status='PARTIAL' if camera_errors else 'CAPTURED',
                   elapsed_seconds=round(time.monotonic()-started, 3),
                   recovery_verified=False,
                   note='USB enumeration and frames alone do not prove recovery or OS identity')
    (output / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True,
                        help='new private evidence directory; frames may contain personal data')
    parser.add_argument('--seconds', type=float, required=True,
                        help='capture length for this test, not a goal/work limit')
    parser.add_argument('--interval', type=float, default=2)
    parser.add_argument('--camera', action='store_true')
    args = parser.parse_args()
    if args.seconds <= 0 or args.interval <= 0:
        parser.error('capture length and interval must be positive')
    os.umask(0o077)
    print(json.dumps(observe(args.output, args.seconds, args.interval, args.camera), indent=2))


if __name__ == '__main__':
    main()
