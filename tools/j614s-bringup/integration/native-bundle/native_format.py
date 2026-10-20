"""Bounded native container format only. Does not qualify FDT or hardware.

Production callers must first verify pinned loader/ELF and D's DT evidence.
Synthetic tests use wholly invented, explicitly non-bootable component bytes.
"""
from dataclasses import dataclass
import hashlib
import struct
import zlib

HEADER = struct.Struct('<16s8I')
MAGIC = b'J614S_NATIVE_V1\0'
IMAGE_LIMIT = 32 << 20
INITRD_LIMIT = 4 << 20
FDT_LIMIT = 0x10000
LOADER_LIMIT = 8 << 20
PAYLOAD_LIMIT = 64 << 20
BUNDLE_LIMIT = LOADER_LIMIT + HEADER.size + IMAGE_LIMIT + INITRD_LIMIT + FDT_LIMIT


class Refused(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Refused(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Layout:
    payload_offset: int
    file_end_offset: int


def layout_from_nm(raw, flat_size):
    require(len(raw) <= 2 << 20, 'Symbol listing exceeds bound')
    wanted = {b'_base', b'_file_end', b'_end', b'_payload_start'}
    symbols = {}
    for line in raw.splitlines():
        words = line.split()
        if not words or words[0] not in wanted:
            continue
        require(len(words) == 4 and words[1] in (b'T', b'D', b'A'), 'Unexpected required symbol schema')
        name = words[0]
        require(name not in symbols, 'Duplicate required symbol')
        try:
            value, size = int(words[2], 16), int(words[3], 16)
        except ValueError as error:
            raise Refused('Invalid required symbol integer') from error
        require(0 <= value < 1 << 64 and size == 0, 'Required symbol value/size differs')
        symbols[name] = value
    require(set(symbols) == wanted, 'Missing required ELF symbol')
    base, file_end, end, payload = (symbols[n] for n in (b'_base', b'_file_end', b'_end', b'_payload_start'))
    require(base < file_end <= end == payload, 'Loader symbol ordering differs')
    offset = payload - base
    require(0 < offset <= LOADER_LIMIT and flat_size == offset, 'Flat extent differs from ELF payload offset')
    return Layout(offset, file_end - base)


def image_contract(image):
    require(64 <= len(image) < IMAGE_LIMIT, 'Image size violates native header contract')
    require(image[56:60] == b'ARMd', 'Image AArch64 magic differs')
    text_offset, memory_size, flags = struct.unpack_from('<QQQ', image, 8)
    require(text_offset == 0 and len(image) <= memory_size < IMAGE_LIMIT, 'Image load/memory extent violates native consumer')
    require(flags & 1 == 0 and ((flags >> 1) & 3) == 2, 'Image must be little-endian with 16 KiB pages')
    return memory_size


def parts_contract(image, initrd, dtb):
    image_contract(image)
    require(0 < len(initrd) < INITRD_LIMIT, 'Initrd size violates native header contract')
    require(40 <= len(dtb) <= FDT_LIMIT, 'FDT size violates native header contract')
    require(struct.unpack_from('>II', dtb) == (0xd00dfeed, len(dtb)), 'FDT envelope magic/total size differs')
    # Full FDT structure/properties/provenance are checked by D's pinned validator,
    # never by treating this two-word envelope check as an FDT validation pass.


def verify_hashes(parts, expected):
    require(set(expected) == {'image', 'initrd', 'dtb'}, 'Exact component hash set required')
    for name, data in parts.items():
        require(sha(data) == expected[name], 'Component pin differs: ' + name)


def assemble(flat, layout, image, initrd, dtb, expected):
    require(len(flat) == layout.payload_offset <= LOADER_LIMIT, 'Loader extent/header placement differs')
    require(0 < layout.file_end_offset <= layout.payload_offset, 'Invalid loader file-end extent')
    parts = {'image': image, 'initrd': initrd, 'dtb': dtb}
    parts_contract(image, initrd, dtb); verify_hashes(parts, expected)
    sizes = [len(image), len(initrd), len(dtb)]
    crcs = [zlib.crc32(part) for part in (image, initrd, dtb)]
    require(HEADER.size + sum(sizes) <= PAYLOAD_LIMIT, 'Payload exceeds loader capacity')
    header = HEADER.pack(MAGIC, 1, *sizes, *crcs, 0)
    result = flat + header + image + initrd + dtb
    parse(result, flat, layout, expected)
    return result


def parse(blob, flat, layout, expected):
    require(len(blob) <= BUNDLE_LIMIT, 'Container exceeds bounded format size')
    require(len(flat) == layout.payload_offset <= LOADER_LIMIT and
            0 < layout.file_end_offset <= layout.payload_offset, 'Invalid paired loader layout')
    offset = layout.payload_offset
    require(len(blob) >= offset + HEADER.size, 'Truncated loader/native header')
    require(blob[:offset] == flat, 'Flat loader prefix or padding differs')
    magic, version, image_size, initrd_size, dtb_size, image_crc, initrd_crc, dtb_crc, reserved = HEADER.unpack_from(blob, offset)
    require(magic == MAGIC and version == 1 and reserved == 0, 'Native magic/version/reserved differs')
    require(64 <= image_size < IMAGE_LIMIT and 0 < initrd_size < INITRD_LIMIT and 40 <= dtb_size <= FDT_LIMIT,
            'Declared component sizes violate native contract')
    payload_size = HEADER.size + image_size + initrd_size + dtb_size
    require(payload_size <= PAYLOAD_LIMIT and offset + payload_size == len(blob), 'Truncation/trailing bytes or inconsistent total size')
    start = offset + HEADER.size
    parts = {}
    for name, size, crc in [('image', image_size, image_crc), ('initrd', initrd_size, initrd_crc), ('dtb', dtb_size, dtb_crc)]:
        data = blob[start:start + size]
        require(zlib.crc32(data) == crc, 'CRC32 differs: ' + name)
        parts[name] = data; start += size
    parts_contract(parts['image'], parts['initrd'], parts['dtb'])
    verify_hashes(parts, expected)
    return parts
