#!/usr/bin/env python3
"""Explicit physical-ACM evidence collection. No automatic probe or recovery action.

Importing this module does not discover USB devices or open serial ports.
"""
import argparse
from dataclasses import asdict, dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import select
import stat
import termios
import time
import tty

MAX_PAYLOAD = 2097152
MAX_HEADER = 192
READ_SIZE = 4096
READ_COMMANDS = ('status', 'before', 'after', 'logs', 'dmesg', 'help')
COMMANDS = (*READ_COMMANDS, 'probe')
PRIMARY_GATE = 'J614S-SINGLE-NVME-PROBE'
HEADER = re.compile(rb'J614S_FRAME_V1 ([0-9a-f]{32}) (status|before|after|logs|dmesg|help|probe) (0|[1-9][0-9]{0,6}) ([0-9a-f]{64})\n')
DEVICE = {'idVendor': '1d6b', 'idProduct': '0104', 'product': 'J614s supervised RAM-only probe',
          'serial': 'J614S-RO-PROBE-8F2F3D13', 'bConfigurationValue': '1'}
INTERFACE = {'bInterfaceNumber': '00', 'bInterfaceClass': '02', 'bInterfaceSubClass': '02',
             'bInterfaceProtocol': '01', 'interface': 'CDC Abstract Control Model (ACM)'}


class ProtocolError(ValueError):
    pass


class IdentityError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


class FrameParser:
    """One exact nonce/command frame. Never searches past stale or invalid bytes."""
    def __init__(self, nonce, command):
        if not re.fullmatch('[0-9a-f]{32}', nonce) or command not in COMMANDS:
            raise ProtocolError('Invalid expected request')
        self.nonce, self.command = nonce, command
        self.buffer = bytearray()
        self.length = None
        self.sha256 = None
        self.payload = None
        self.complete = False

    def feed(self, chunk):
        if self.complete and chunk:
            raise ProtocolError('Extra bytes after the single expected frame')
        if len(self.buffer) + len(chunk) > MAX_PAYLOAD + MAX_HEADER + 80:
            raise ProtocolError('Response exceeds bounded frame size')
        self.buffer.extend(chunk)
        if self.length is None:
            end = self.buffer.find(b'\n')
            if end < 0:
                if len(self.buffer) >= MAX_HEADER:
                    raise ProtocolError('Missing bounded frame header')
                return
            if end + 1 > MAX_HEADER:
                raise ProtocolError('Oversized frame header')
            match = HEADER.fullmatch(bytes(self.buffer[:end + 1]))
            if not match:
                raise ProtocolError('Invalid frame header')
            nonce, command, size, sha = match.groups()
            if nonce.decode() != self.nonce or command.decode() != self.command:
                raise ProtocolError('Stale or unexpected nonce/command')
            self.length, self.sha256 = int(size), sha.decode()
            if self.length > MAX_PAYLOAD:
                raise ProtocolError('Oversized payload')
            del self.buffer[:end + 1]
        footer = ('\nJ614S_END_V1 ' + self.nonce + '\n').encode()
        expected = self.length + len(footer)
        if len(self.buffer) > expected:
            raise ProtocolError('Extra bytes or frames after expected response')
        if len(self.buffer) < expected:
            return
        payload = bytes(self.buffer[:self.length])
        if bytes(self.buffer[self.length:]) != footer:
            raise ProtocolError('Invalid completion footer')
        if digest(payload) != self.sha256:
            raise ProtocolError('Payload SHA256 mismatch')
        self.payload, self.complete = payload, True
        self.buffer.clear()

    def finish(self):
        if not self.complete:
            raise ProtocolError('Truncated or timed-out response')
        return self.payload


@dataclass(frozen=True)
class Candidate:
    port: str
    tty_name: str
    device_numbers: tuple
    tty_path: str
    interface_path: str
    usb_path: str
    driver_path: str
    usb_inode: int
    interface_inode: int
    tty_inode: int
    busnum: str
    devnum: str


def attribute(path):
    raw = path.read_bytes()
    if len(raw) > 256 or b'\0' in raw or raw.count(b'\n') > 1:
        raise IdentityError('Malformed sysfs identity attribute')
    return raw.decode('ascii').removesuffix('\n')


def ancestors(path, root):
    while path.is_relative_to(root):
        yield path
        if path == root:
            break
        path = path.parent


def discover(port, sysfs=Path('/sys')):
    """Called only by an explicit physical collection command, never on import."""
    if not re.fullmatch(r'[1-9][0-9]*-[1-9][0-9]*(?:\.[1-9][0-9]*)*', port):
        raise IdentityError('Supply an exact physical USB port such as 1-3.2')
    root = sysfs.resolve(strict=True)
    matches = []
    for item in sorted((root / 'class/tty').glob('ttyACM*')):
        if not re.fullmatch(r'ttyACM[0-9]+', item.name):
            continue
        try:
            physical = (item / 'device').resolve(strict=True)
            if not physical.is_relative_to(root):
                continue
            chain = list(ancestors(physical, root))
            interface = next(p for p in chain if (p / 'bInterfaceNumber').is_file())
            usb = next(p for p in ancestors(interface.parent, root) if (p / 'idVendor').is_file())
            if usb.name != port:
                continue
            if any(attribute(usb / name) != value for name, value in DEVICE.items()):
                continue
            if any(attribute(interface / name) != value for name, value in INTERFACE.items()):
                continue
            driver = (interface / 'driver').resolve(strict=True)
            if driver != (root / 'bus/usb/drivers/cdc_acm').resolve(strict=True):
                continue
            numbers = attribute(item / 'dev')
            if not re.fullmatch(r'[0-9]+:[0-9]+', numbers):
                continue
            busnum, devnum = attribute(usb / 'busnum'), attribute(usb / 'devnum')
            if not busnum.isdecimal() or not devnum.isdecimal() or int(busnum) != int(port.split('-', 1)[0]) or not 1 <= int(devnum) <= 127:
                continue
            matches.append(Candidate(port, item.name, tuple(map(int, numbers.split(':'))),
                                     str(item.resolve(strict=True)), str(interface), str(usb), str(driver),
                                     usb.stat().st_ino, interface.stat().st_ino, item.stat().st_ino, busnum, devnum))
        except (OSError, UnicodeError, IdentityError, StopIteration):
            continue
    if len(matches) != 1:
        raise IdentityError('Expected exactly one matching physical ACM interface; found ' + str(len(matches)))
    return matches[0]


def open_verified(candidate, sysfs=Path('/sys'), devroot=Path('/dev')):
    # Do not open by a caller-supplied arbitrary tty pathname. Re-read all identity
    # attributes immediately before open, then check actual character device and
    # repeat identity validation before termios or serial I/O.
    if discover(candidate.port, sysfs) != candidate:
        raise IdentityError('TTY/USB identity changed before open')
    flags = os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW
    fd = os.open(devroot / candidate.tty_name, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISCHR(info.st_mode) or (os.major(info.st_rdev), os.minor(info.st_rdev)) != candidate.device_numbers:
            raise IdentityError('Opened node is not the selected tty character device')
        if discover(candidate.port, sysfs) != candidate:
            raise IdentityError('TTY/USB identity changed during open')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.ioctl(fd, termios.TIOCEXCL)
        # No input flush: stale buffered frames must be recorded and rejected.
        tty.setraw(fd, termios.TCSANOW)
        settings = termios.tcgetattr(fd)
        settings[2] |= termios.CREAD | termios.CLOCAL
        settings[2] &= ~termios.CRTSCTS
        settings[4] = settings[5] = termios.B115200
        termios.tcsetattr(fd, termios.TCSANOW, settings)
        return fd
    except BaseException:
        os.close(fd)
        raise


class FdTransport:
    def __init__(self, fd):
        self.fd = fd

    def read(self, size, timeout):
        if not select.select([self.fd], [], [], max(0, timeout))[0]:
            return None
        try:
            return os.read(self.fd, size)
        except BlockingIOError:
            return None

    def write(self, data, timeout):
        if not select.select([], [self.fd], [], max(0, timeout))[1]:
            return 0
        try:
            return os.write(self.fd, data)
        except BlockingIOError:
            return 0


class Recorder:
    """Private raw bytes are retained even when framing or identity fails."""
    def __init__(self, output):
        self.output = output
        output.mkdir(mode=0o700)  # New directory only; never overwrite evidence.
        self.rx = self.new_file('rx.bin')
        self.tx = self.new_file('tx.bin')
        self.result = {'schema': 1, 'hardware': 'UNTESTED', 'boot': 'UNTESTED', 'recovery': 'UNVERIFIED'}

    def new_file(self, name):
        fd = os.open(self.output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
        return os.fdopen(fd, 'wb')

    def received(self, data):
        self.rx.write(data); self.rx.flush()

    def transmitted(self, data):
        self.tx.write(data); self.tx.flush()

    def finish(self, status, error=None, payload=None):
        self.rx.close(); self.tx.close()
        self.result['status'] = status
        if error is not None:
            self.result['error'] = error
        if payload is not None:
            with self.new_file('payload.bin') as out:
                out.write(payload)
            self.result.update(payload_bytes=len(payload), payload_sha256=digest(payload))
        self.result['raw'] = {name: {'bytes': (self.output / name).stat().st_size,
                                    'sha256': digest((self.output / name).read_bytes())} for name in ('rx.bin', 'tx.bin')}
        with self.new_file('result.json') as out:
            out.write((json.dumps(self.result, indent=2, sort_keys=True) + '\n').encode())
        return self.result


def receive_once(transport, recorder, command, nonce, response_timeout=10.0, quiet_seconds=0.2, probe_gate=None):
    """One request only; partial I/O continues that request, never resends it."""
    if command == 'probe' and probe_gate != PRIMARY_GATE:
        raise ProtocolError('Separate primary one-shot invocation required before any probe transport')
    parser = FrameParser(nonce, command)
    recorder.result.update(command=command, request_nonce=nonce,
                           target_action='explicit-single-probe-request' if command == 'probe' else 'read-only-diagnostic-request')
    old = transport.read(READ_SIZE, quiet_seconds)
    if old is not None:
        recorder.received(old)
        raise ProtocolError('Stale bytes or closed channel before request')
    request = ('J614S_REQ_V1 ' + nonce + ' ' + command + '\n').encode()
    offset = 0; deadline = time.monotonic() + response_timeout
    while offset < len(request):
        left = deadline - time.monotonic()
        if left <= 0:
            raise ProtocolError('Request write timed out; not retried')
        count = transport.write(request[offset:], left)
        if not 0 < count <= len(request) - offset:
            raise ProtocolError('Request write incomplete; not retried')
        recorder.transmitted(request[offset:offset + count]); offset += count
    deadline = time.monotonic() + response_timeout
    while not parser.complete:
        left = deadline - time.monotonic()
        if left <= 0:
            raise ProtocolError('Truncated or timed-out response')
        chunk = transport.read(READ_SIZE, left)
        if chunk is None or chunk == b'':
            raise ProtocolError('Truncated or timed-out response')
        if len(chunk) > READ_SIZE:
            raise ProtocolError('Transport exceeded bounded read')
        recorder.received(chunk); parser.feed(chunk)
    extra = transport.read(READ_SIZE, quiet_seconds)
    if extra is not None:
        recorder.received(extra)
        raise ProtocolError('Extra bytes or disconnected channel after response')
    recorder.result['extra_data_observation_seconds'] = quiet_seconds
    # A valid frame proves byte completeness/correlation only, not hardware state.
    return parser.finish()


def command_for(mode, command=None, gate=None):
    if mode == 'collect' and command in READ_COMMANDS and gate is None:
        return command
    if mode == 'probe-once' and command is None and gate == PRIMARY_GATE:
        return 'probe'
    raise ProtocolError('Only read diagnostics or a separately deliberate single probe invocation are permitted')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    for name in ('collect', 'probe-once'):
        part = sub.add_parser(name)
        part.add_argument('--usb-port', required=True, help='Exact physical Linux USB port, e.g.1-3.2; no auto-selection')
        part.add_argument('--output', type=Path, required=True, help='New private evidence directory (0700/files0600)')
        if name == 'collect':
            part.add_argument('--command', choices=READ_COMMANDS, default='status')
        else:
            part.add_argument('--primary-invocation', required=True, choices=[PRIMARY_GATE], help='Primary operator deliberate one-shot gate; never implied by collect')
    args = parser.parse_args()
    command = command_for(args.mode, getattr(args, 'command', None), getattr(args, 'primary_invocation', None))
    recorder = Recorder(args.output)
    recorder.result.update(mode=args.mode, requested_command=command)
    fd = None
    try:
        candidate = discover(args.usb_port)
        recorder.result['identity'] = asdict(candidate)
        fd = open_verified(candidate)
        payload = receive_once(FdTransport(fd), recorder, command, secrets.token_hex(16), probe_gate=getattr(args, 'primary_invocation', None))
        result = recorder.finish('FRAME_VALIDATED', payload=payload)
    except (OSError, ValueError) as error:
        result = recorder.finish('REJECTED', error=str(error))
    finally:
        if fd is not None:
            os.close(fd)
    print(json.dumps({key: result[key] for key in ('status', 'hardware', 'boot', 'recovery')}, sort_keys=True))
    raise SystemExit(0 if result['status'] == 'FRAME_VALIDATED' else 1)


if __name__ == '__main__':
    main()
