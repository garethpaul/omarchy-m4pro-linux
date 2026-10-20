#!/usr/bin/env python3
"""Offline only: actual parser, fake transport/sysfs and RAM helper fixtures.

No discovery of current devices, serial opens, init execution or probe command.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import collect_probe as host

HERE = Path(__file__).resolve().parent
NONCE = '6145' * 8
OTHER = '1234' * 8


def wire(payload=b'fixture\n', nonce=NONCE, command='status', size=None, sha=None):
    size = len(payload) if size is None else size
    sha = hashlib.sha256(payload).hexdigest() if sha is None else sha
    return f'J614S_FRAME_V1 {nonce} {command} {size} {sha}\n'.encode() + payload + f'\nJ614S_END_V1 {nonce}\n'.encode()


class ParserTests(unittest.TestCase):
    def test_every_two_chunk_split(self):
        raw = wire(b'payload\0\xff\nJ614S_FRAME_V1 nested\n')
        for split in range(len(raw) + 1):
            parser = host.FrameParser(NONCE, 'status')
            parser.feed(raw[:split]); parser.feed(raw[split:])
            self.assertEqual(parser.finish(), b'payload\0\xff\nJ614S_FRAME_V1 nested\n')

    def test_one_byte_chunks(self):
        parser = host.FrameParser(NONCE, 'status')
        for value in wire():
            parser.feed(bytes([value]))
        self.assertEqual(parser.finish(), b'fixture\n')

    def test_empty_payload(self):
        parser = host.FrameParser(NONCE, 'status'); parser.feed(wire(b''))
        self.assertEqual(parser.finish(), b'')

    def test_every_truncated_prefix_refused(self):
        raw = wire()
        for size in range(len(raw)):
            parser = host.FrameParser(NONCE, 'status'); parser.feed(raw[:size])
            with self.assertRaises(host.ProtocolError):
                parser.finish()

    def test_bad_digest(self):
        with self.assertRaisesRegex(host.ProtocolError, 'SHA256'):
            host.FrameParser(NONCE, 'status').feed(wire(sha='0' * 64))

    def test_stale_nonce(self):
        with self.assertRaisesRegex(host.ProtocolError, 'Stale'):
            host.FrameParser(NONCE, 'status').feed(wire(nonce=OTHER))

    def test_wrong_command(self):
        with self.assertRaisesRegex(host.ProtocolError, 'unexpected'):
            host.FrameParser(NONCE, 'status').feed(wire(command='logs'))

    def test_oversize_rejected_from_header(self):
        raw = wire(size=host.MAX_PAYLOAD + 1)
        header = raw.split(b'\n', 1)[0] + b'\n'
        with self.assertRaisesRegex(host.ProtocolError, 'Oversized'):
            host.FrameParser(NONCE, 'status').feed(header)

    def test_long_unterminated_header(self):
        with self.assertRaises(host.ProtocolError):
            host.FrameParser(NONCE, 'status').feed(b'x' * host.MAX_HEADER)

    def test_extra_frame_in_same_read(self):
        with self.assertRaisesRegex(host.ProtocolError, 'Extra'):
            host.FrameParser(NONCE, 'status').feed(wire() + wire())

    def test_extra_frame_in_next_read(self):
        parser = host.FrameParser(NONCE, 'status'); parser.feed(wire())
        with self.assertRaisesRegex(host.ProtocolError, 'Extra'):
            parser.feed(wire())

    def test_bad_completion_footer(self):
        with self.assertRaisesRegex(host.ProtocolError, 'footer'):
            host.FrameParser(NONCE, 'status').feed(wire()[:-2] + b'x\n')

    def test_no_resynchronization_past_unframed_banner(self):
        with self.assertRaises(host.ProtocolError):
            host.FrameParser(NONCE, 'status').feed(b'USB online\n' + wire())

    def test_crlf_header_rejected(self):
        raw = wire().replace(b'\n', b'\r\n', 1)
        with self.assertRaises(host.ProtocolError):
            host.FrameParser(NONCE, 'status').feed(raw)


class FakeTransport:
    def __init__(self, reads):
        self.reads = list(reads); self.sent = bytearray()

    def read(self, size, timeout):
        if not self.reads:
            return None
        data = self.reads.pop(0)
        if data is not None and len(data) > size:
            self.reads.insert(0, data[size:]); data = data[:size]
        return data

    def write(self, data, timeout):
        size = min(7, len(data)); self.sent.extend(data[:size]); return size


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def run_collection(self, reads):
        transport = FakeTransport(reads); recorder = host.Recorder(self.root / 'evidence')
        try:
            payload = host.receive_once(transport, recorder, 'status', NONCE)
            result = recorder.finish('FRAME_VALIDATED', payload=payload)
        except host.ProtocolError as error:
            result = recorder.finish('REJECTED', error=str(error))
        return transport, result

    def test_complete_frame_is_only_transport_evidence(self):
        raw = wire(b'ENUMERATED_RO\nWORKS\n')
        transport, result = self.run_collection([None, *[raw[n:n+3] for n in range(0, len(raw), 3)], None])
        self.assertEqual(result['status'], 'FRAME_VALIDATED')
        self.assertEqual(result['hardware'], 'UNTESTED')
        self.assertEqual(result['recovery'], 'UNVERIFIED')
        self.assertEqual(bytes(transport.sent), f'J614S_REQ_V1 {NONCE} status\n'.encode())
        self.assertEqual(transport.sent.count(b'\n'), 1)
        self.assertNotIn(b' probe\n', transport.sent)
        output = self.root / 'evidence'
        self.assertEqual((output / 'rx.bin').read_bytes(), raw)
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)
        for p in output.iterdir():
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)

    def test_truncation_keeps_raw_without_payload(self):
        raw = wire()[:-9]
        transport, result = self.run_collection([None, raw, None])
        self.assertEqual(result['status'], 'REJECTED')
        self.assertEqual((self.root / 'evidence/rx.bin').read_bytes(), raw)
        self.assertFalse((self.root / 'evidence/payload.bin').exists())
        self.assertEqual(transport.sent.count(b'\n'), 1)

    def test_preexisting_bytes_prevent_request(self):
        transport, result = self.run_collection([wire(nonce=OTHER)])
        self.assertEqual(result['status'], 'REJECTED')
        self.assertEqual(transport.sent, b'')

    def test_stale_response_not_retried(self):
        transport, result = self.run_collection([None, wire(nonce=OTHER)])
        self.assertEqual(result['status'], 'REJECTED')
        self.assertEqual(transport.sent.count(b'\n'), 1)

    def test_extra_frame_during_quiet_observation_rejected(self):
        _, result = self.run_collection([None, wire(), wire()])
        self.assertEqual(result['status'], 'REJECTED')
        self.assertFalse((self.root / 'evidence/payload.bin').exists())

    def test_disconnect_after_frame_not_recovery_proof(self):
        _, result = self.run_collection([None, wire(), b''])
        self.assertEqual(result['status'], 'REJECTED')
        self.assertEqual(result['recovery'], 'UNVERIFIED')

    def test_collect_cannot_select_probe(self):
        with self.assertRaises(host.ProtocolError):
            host.command_for('collect', 'probe')

    def test_transport_api_cannot_bypass_probe_gate(self):
        transport = FakeTransport([None]); recorder = host.Recorder(self.root / 'evidence')
        with self.assertRaises(host.ProtocolError):
            host.receive_once(transport, recorder, 'probe', NONCE)
        self.assertEqual(transport.sent, b'')
        self.assertEqual(transport.reads, [None])
        recorder.finish('REJECTED', error='deliberately missing primary gate in fixture')

    def test_probe_requires_separate_exact_gate(self):
        with self.assertRaises(host.ProtocolError):
            host.command_for('probe-once')
        with self.assertRaises(host.ProtocolError):
            host.command_for('probe-once', gate='yes')
        # Pure command-selection check only: never passed to a transport.
        self.assertEqual(host.command_for('probe-once', gate=host.PRIMARY_GATE), 'probe')


def fake_sysfs(root):
    interface = root / 'devices/usb1/1-3.2/1-3.2:1.0'
    usb = interface.parent
    interface.mkdir(parents=True)
    driver = root / 'bus/usb/drivers/cdc_acm'; driver.mkdir(parents=True)
    (interface / 'driver').symlink_to(driver)
    for name, value in host.DEVICE.items():
        (usb / name).write_text(value + '\n')
    for name, value in host.INTERFACE.items():
        (interface / name).write_text(value + '\n')
    (usb / 'busnum').write_text('1\n'); (usb / 'devnum').write_text('12\n')
    add_tty(root, interface, 'ttyACM0', '166:0')
    return usb, interface


def add_tty(root, interface, name, numbers):
    node = interface / 'tty' / name; node.mkdir(parents=True)
    (node / 'device').symlink_to(interface)
    (node / 'dev').write_text(numbers + '\n')
    klass = root / 'class/tty'; klass.mkdir(parents=True, exist_ok=True)
    (klass / name).symlink_to(node)


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.usb, self.interface = fake_sysfs(self.root)

    def test_exact_fixture_selected(self):
        match = host.discover('1-3.2', self.root)
        self.assertEqual(match.tty_name, 'ttyACM0'); self.assertEqual(match.device_numbers, (166, 0))

    def test_other_physical_port_rejected(self):
        with self.assertRaises(host.IdentityError):
            host.discover('1-3.3', self.root)

    def test_missing_or_path_port_rejected(self):
        for port in ('', '../1-3.2', 'auto', '1-3.2:1.0'):
            with self.assertRaises(host.IdentityError):
                host.discover(port, self.root)

    def test_proxy_or_sourcehelper_product_rejected(self):
        for product in ('m1n1', 'J614s native USB helper', 'J614s RAM-only Linux diagnostic'):
            (self.usb / 'product').write_text(product + '\n')
            with self.assertRaises(host.IdentityError):
                host.discover('1-3.2', self.root)

    def test_wrong_serial_rejected(self):
        (self.usb / 'serial').write_text('J614S-DIAG-OLD\n')
        with self.assertRaises(host.IdentityError):
            host.discover('1-3.2', self.root)

    def test_wrong_interface_or_protocol_rejected(self):
        for name, value in [('bInterfaceNumber', '01'), ('bInterfaceClass', 'ff'), ('bInterfaceProtocol', '00'), ('interface', 'CDC ACM Data')]:
            original = (self.interface / name).read_text()
            (self.interface / name).write_text(value + '\n')
            with self.assertRaises(host.IdentityError):
                host.discover('1-3.2', self.root)
            (self.interface / name).write_text(original)

    def test_ambiguity_rejected(self):
        add_tty(self.root, self.interface, 'ttyACM1', '166:1')
        with self.assertRaisesRegex(host.IdentityError, 'found 2'):
            host.discover('1-3.2', self.root)

    def test_revalidate_identity_before_any_open(self):
        candidate = host.discover('1-3.2', self.root)
        (self.usb / 'devnum').write_text('13\n')
        with patch.object(host.os, 'open') as opened:
            with self.assertRaises(host.IdentityError):
                host.open_verified(candidate, self.root, self.root / 'dev')
        opened.assert_not_called()

    def test_noncharacter_node_rejected_before_termios(self):
        candidate = host.discover('1-3.2', self.root)
        dev = self.root / 'dev'; dev.mkdir(); (dev / 'ttyACM0').write_text('ordinary fixture')
        with patch.object(host.tty, 'setraw') as raw:
            with self.assertRaises(host.IdentityError):
                host.open_verified(candidate, self.root, dev)
        raw.assert_not_called()
        self.assertEqual((dev / 'ttyACM0').read_text(), 'ordinary fixture')


class ShellFramerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def frame(self, payload):
        source = self.root / 'source'; source.write_bytes(payload)
        prefix = self.root / 'tx'
        subprocess.run(['sh', '-c', '. "$1"; make_frame "$2" status "$3" "$4"', 'check', str(HERE / 'probe-frame.sh'), NONCE, str(source), str(prefix)], check=True)
        return source, (self.root / 'tx.frame').read_bytes()

    def test_actual_shell_frame_matches_parser(self):
        source, raw = self.frame(b'stable fixture\0\xff\n')
        source.write_bytes(b'changed after frame assembly')
        parser = host.FrameParser(NONCE, 'status'); parser.feed(raw)
        self.assertEqual(parser.finish(), b'stable fixture\0\xff\n')

    @unittest.skipUnless(os.environ.get('J614S_BUSYBOX') and os.environ.get('J614S_QEMU'), 'Optional qualified native BusyBox applet round-trip')
    def test_qualified_native_busybox_applet_roundtrip(self):
        pins = json.loads((HERE / 'pins.json').read_text())
        binary = Path(os.environ['J614S_BUSYBOX']).resolve()
        self.assertEqual(hashlib.sha256(binary.read_bytes()).hexdigest(), pins['busybox_sha256'])
        source = self.root / 'source'; source.write_bytes(b'native applet fixture\0\xff\n')
        prefix = self.root / 'tx'
        shell = '''QEMU=$1; BUSYBOX=$2; . "$3"; shift 3
head() { "$QEMU" "$BUSYBOX" head "$@"; }
wc() { "$QEMU" "$BUSYBOX" wc "$@"; }
sha256sum() { "$QEMU" "$BUSYBOX" sha256sum "$@"; }
cat() { "$QEMU" "$BUSYBOX" cat "$@"; }
make_frame "$1" status "$2" "$3"
'''
        subprocess.run(['sh', '-c', shell, 'check', str(Path(os.environ['J614S_QEMU']).resolve()), str(binary), str(HERE / 'probe-frame.sh'), NONCE, str(source), str(prefix)], check=True)
        parser = host.FrameParser(NONCE, 'status'); parser.feed((self.root / 'tx.frame').read_bytes())
        self.assertEqual(parser.finish(), source.read_bytes())

    def test_oversize_source_becomes_explicit_bounded_refusal(self):
        _, raw = self.frame(b'x' * (host.MAX_PAYLOAD + 1))
        parser = host.FrameParser(NONCE, 'status'); parser.feed(raw)
        self.assertIn(b'REFUSED: response exceeds', parser.finish())
        self.assertLess(len(parser.finish()), 100)

    def test_missing_source_becomes_explicit_refusal(self):
        prefix = self.root / 'tx'
        subprocess.run(['sh', '-c', '. "$1"; make_frame "$2" status "$3" "$4"', 'check', str(HERE / 'probe-frame.sh'), NONCE, str(self.root / 'missing'), str(prefix)], check=True, capture_output=True)
        parser = host.FrameParser(NONCE, 'status'); parser.feed((self.root / 'tx.frame').read_bytes())
        self.assertIn(b'REFUSED:', parser.finish())

    def test_literal_request_grammar_and_64_character_bound(self):
        for command in host.COMMANDS:
            request = f'J614S_REQ_V1 {NONCE} {command}'
            self.assertLessEqual(len(request) + 1, 64)
            result = subprocess.run(['sh', '-c', '. "$1"; parse_request "$2" || exit; printf "%s %s" "$FRAME_REQUEST_ID" "$FRAME_COMMAND"', 'check', str(HERE / 'probe-frame.sh'), request], capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout, f'{NONCE} {command}')

    def test_malformed_crlf_extra_fields_and_arbitrary_commands_refused(self):
        marker = self.root / 'must-not-execute'
        for request in (f'J614S_REQ_V1 {NONCE} status\r', f'J614S_REQ_V1 {NONCE} status extra', f'J614S_REQ_V1 {NONCE} reboot', f'J614S_REQ_V1 {NONCE} $(touch {marker})', 'status', f'J614S_REQ_V1 {NONCE[:-1]} status'):
            result = subprocess.run(['sh', '-c', '. "$1"; parse_request "$2"', 'check', str(HERE / 'probe-frame.sh'), request], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
        self.assertFalse(marker.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
