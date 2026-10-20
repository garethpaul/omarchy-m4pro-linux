#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Capture-only adaptation of published pre-init mailbox observation.

Importing this module never attaches to a target. attach() is only for an
already approved guest session; it does not boot or start firmware.
"""
import ctypes as C
import hashlib
import json
import os
from pathlib import Path

ASC_BASE = 0x28A600000
FW = "mBoot-18000.161.10"
class Range(C.Structure):
    _fields_ = [("start", C.c_uint64), ("size", C.c_uint64)]
Read = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_uint64, C.POINTER(C.c_uint8), C.c_size_t)
class Reader(C.Structure):
    _fields_ = [("read", Read), ("cookie", C.c_void_p), ("ranges", C.POINTER(Range)), ("range_count", C.c_size_t)]
class Capture(C.Structure):
    _fields_ = [("root_va", C.c_uint64), ("main_va", C.c_uint64), ("first_body_va", C.c_uint64), ("root", C.c_uint8 * 0xc8), ("main_header", C.c_uint8 * 8), ("first_body", C.c_uint8 * 16), ("main", C.c_uint8 * 0x479)]

class Observer:
    """No MMIO writes, replay, UAT constructors, INIT sends or resets exist here."""
    def __init__(self, read_physical, ram_ranges, table, library, output):
        if not ram_ranges or any(not isinstance(start, int) or not isinstance(size, int) or start < 0 or size <= 0 or start + size > 1 << 64 for start, size in ram_ranges):
            raise ValueError("Malformed RAM allowlist")
        if not isinstance(table, int) or table < 0 or table >= 1 << 42:
            raise ValueError("Native root outside qualified physical width")
        self.read_physical = read_physical
        self.ranges = (Range * len(ram_ranges))(*(Range(*r) for r in ram_ranges))
        if not ram_ranges or table & 0x3fff:
            raise ValueError("Independent RAM allowlist and aligned native root required")
        self.table, self.output = table, Path(output)
        self.library = C.CDLL(str(Path(library).resolve(strict=True)))
        self.library_sha256 = hashlib.sha256(Path(library).read_bytes()).hexdigest()
        self.qualification = {"scope": "offline observer until live attach guards pass"}
        self.library.g16s_capture_size.restype = C.c_size_t
        if self.library.g16s_capture_size() != C.sizeof(Capture):
            raise ValueError("Capture bridge layout mismatch")
        self.library.g16s_capture_bridge.argtypes = [C.POINTER(Reader), C.c_uint64, C.c_uint64, C.POINTER(Capture)]
        self.library.g16s_capture_bridge.restype = C.c_int
        self.pending = None
        self.root_va = None
        self.phases = set()
        self.messages = []
        self.reads = []
        self.read_bytes = 0
        self.callback_error = None
        self.disabled = False
        self._read_callback = Read(self._read)
        self.reader = Reader(self._read_callback, None, self.ranges, len(ram_ranges))

    def _read(self, cookie, address, destination, size):
        try:
            if len(self.reads) >= 256 or self.read_bytes + size > 0x10000:
                raise ValueError("Capture read bound exceeded")
            data = self.read_physical(address, size)
            if not isinstance(data, bytes) or len(data) != size:
                raise ValueError("Short physical capture")
            # Overlapping bytes in one stopped-vCPU capture must agree.
            # Agreement alone does not prove an atomic snapshot against other
            # CPUs or firmware; publication/cache coherence stays unqualified.
            for old_address, old in self.reads:
                lo, hi = max(address, old_address), min(address + size, old_address + len(old))
                if lo < hi and data[lo-address:hi-address] != old[lo-old_address:hi-old_address]:
                    raise ValueError("Incoherent overlapping capture")
            C.memmove(destination, data, size)
            self.reads.append((address, data))
            self.read_bytes += size
            return 0
        except Exception as error:
            self.callback_error = str(error)
            return -1

    def _snapshot(self, phase):
        # Each phase independently checks overlapping reads. Other CPUs/firmware
        # may still mutate non-overlapping fields; this is a candidate capture,
        # not proof of globally atomic state. Native progress may also modify
        # the graph between pre-init and later mailbox messages.
        self.reads, self.read_bytes, self.callback_error = [], 0, None
        captured = Capture()
        code = self.library.g16s_capture_bridge(C.byref(self.reader), self.table, self.root_va, C.byref(captured))
        self.output.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.output, 0o700)
        directory = self.output / phase
        directory.mkdir(parents=True, exist_ok=False, mode=0o700)
        os.chmod(directory, 0o700)
        manifest = {"phase": phase, "capture_error": code, "callback_error": self.callback_error,
                    "hardware_job_pass": False, "safe_to_publish_init": False,
                    "root_va": hex(self.root_va), "messages": list(self.messages),
                    "qualification": self.qualification, "capture_library_sha256": self.library_sha256,
                    "native_table": hex(self.table), "ram_ranges": [{"start": hex(r.start), "size": r.size} for r in self.ranges], "read_bytes": self.read_bytes, "reads": []}
        for index, (address, data) in enumerate(self.reads):
            name = f"read-{index:03d}.bin"
            path = directory / name
            path.write_bytes(data); os.chmod(path, 0o600)
            manifest["reads"].append({"physical": hex(address), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "file": name})
        if not code:
            for name in ["root", "main_header", "first_body", "main"]:
                path = directory / (name + ".bin")
                path.write_bytes(bytes(getattr(captured, name))); os.chmod(path, 0o600)
            manifest.update(main_va=hex(captured.main_va), first_body_va=hex(captured.first_body_va))
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        os.chmod(directory / "manifest.json", 0o600)
        self.phases.add(phase)
        if code:
            self.disabled = True
        return manifest

    def feed(self, address, data, width=3):
        if self.disabled:
            return None
        if width != 3 or address not in (ASC_BASE + 0x8800, ASC_BASE + 0x8808) or not isinstance(data, int) or not 0 <= data < 1 << 64:
            self.disabled = True
            raise ValueError("Unqualified mailbox access shape")
        if address == ASC_BASE + 0x8800:
            if self.pending is not None:
                self.disabled = True
                raise ValueError("Payload overwritten before endpoint commit")
            self.pending = int(data)
            return None
        if self.pending is None:
            self.disabled = True
            raise ValueError("Endpoint write without observed payload")
        payload, self.pending = self.pending, None
        endpoint = int(data) & 0xff
        if endpoint not in (0x20, 0x21):
            return None
        if len(self.messages) >= 64:
            self.disabled = True
            return None
        self.messages.append({"endpoint": endpoint, "payload": hex(payload), "metadata": hex(int(data))})
        if self.root_va is None:
            if endpoint != 0x20 or payload & 0x00bf000000000000 != 0x0081000000000000:
                return None
            self.root_va = payload | 0xfffff00000000000
            if self.root_va & 7:
                self.disabled = True
                raise ValueError("Unaligned native INIT root")
            return self._snapshot("pre-first-init")
        # These are observations, not proof that an arbitrary message is a
        # compute kick. The83/84 label comes from Gravity's existing G16 caller.
        kind = (payload >> 48) & 0xff
        if endpoint == 0x21 and kind in (0x83, 0x84) and "gravity-kick-candidate" not in self.phases:
            return self._snapshot("gravity-kick-candidate")
        if "first-post-init-app-message" not in self.phases:
            return self._snapshot("first-post-init-app-message")
        return None

def attach(hv, *, ram_ranges, library, output, approved_guest_session=False):
    """Attach only to an already approved guest session; never launch or recover it.

    RAM ranges must have been independently qualified from this machine's ADT
    and excluded carveouts. This API does not infer permission from that flag.
    """
    if not approved_guest_session:
        raise ValueError("No approved guest session supplied")
    if hv.p.get_chipid() != 0x6040 or hv.adt.model != "Mac16,8":
        raise ValueError("Wrong physical target")
    chosen, asc, sgx = hv.adt["/chosen"], hv.adt["/arm-io/gfx-asc"], hv.adt["/arm-io/sgx"]
    if chosen.board_id != 4 or chosen.system_firmware_version != FW:
        raise ValueError("Wrong board or boot firmware")
    if asc.get_reg(0) != (ASC_BASE, 0x88000) or sgx.get_reg(0) != (0x288000000, 0x3758000):
        raise ValueError("Unexpected ADT register apertures")
    if sgx.gfx_shared_region_size != 0x40000:
        raise ValueError("Unqualified native UAT region")
    observer = Observer(hv.iface.readmem, ram_ranges, sgx.gfx_shared_region_base, library, output)
    observer.qualification = {"model": hv.adt.model, "chip_id": "0x6040", "board_id": chosen.board_id, "boot_firmware": chosen.system_firmware_version, "note": "ADT boot identifier and captured ABI are checked; no loaded firmware binary hash is inferred"}
    # Importing the capture module itself has no target/runtime dependencies.
    from m1n1.hv import TraceMode
    from m1n1.utils import irange
    def callback(event):
        try:
            if getattr(event.flags, "MULTI", 0):
                raise ValueError("Unqualified multiword mailbox access")
            observer.feed(int(event.addr), int(event.data), int(event.flags.WIDTH))
        except Exception as error:
            # No automatic reset, guest exit or firmware recovery on capture
            # failure. The controller receives the failure via this object.
            observer.callback_error = str(error)
            observer.disabled = True
    hv.add_tracer(irange(ASC_BASE + 0x8800, 0x10), "J614sEarlyCapture", mode=TraceMode.SYNC, write=callback)
    return observer
