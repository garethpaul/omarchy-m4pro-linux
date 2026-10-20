"""Wholly synthetic, non-bootable native-format fixtures; no candidate bundle."""
import gzip
import struct
import unittest
import zlib
import bundle
f=bundle.fmt


def synthetic():
    flat = (b'SYNTHETIC_LOADER_NOT_EXECUTABLE\0' * 9)[:256]
    symbols = b'_base T 1000 0\n_file_end D 1080 0\n_end D 1100 0\n_payload_start D 1100 0\n'
    layout = f.layout_from_nm(symbols, len(flat))
    image = bytearray(96); image[:8] = b'SYNTHET!'; image[56:60] = b'ARMd'; image[64:] = b'SYNTHETIC_NOT_BOOTABLE'.ljust(32, b'\0')
    struct.pack_into('<QQQ', image, 8, 0, 4096, 12)
    initrd = gzip.compress(b'SYNTHETIC_NOT_A_CPIO_ARCHIVE\n', mtime=0)
    dtb = struct.pack('>II', 0xd00dfeed, 64) + b'SYNTHETIC_NOT_A_VALIDATED_DTB'.ljust(56, b'\0')
    parts = {'image':bytes(image), 'initrd':initrd, 'dtb':dtb}
    expected = {k:f.sha(v) for k,v in parts.items()}
    return flat, layout, parts, expected


class NativeFormatTests(unittest.TestCase):
    def setUp(self):
        self.flat,self.layout,self.parts,self.expected=synthetic()
        self.blob=f.assemble(self.flat,self.layout,**self.parts,expected=self.expected)

    def parse(self, data):
        return f.parse(data,self.flat,self.layout,self.expected)

    def test_synthetic_roundtrip_only(self):
        self.assertEqual(self.parse(self.blob),self.parts)
        self.assertIn(b'SYNTHETIC',self.flat)
        self.assertIn(b'SYNTHETIC',self.parts['image'])
        self.assertIn(b'SYNTHETIC',self.parts['dtb'])
        self.assertEqual(f.HEADER.size,48)

    def test_all_truncated_prefixes_refused(self):
        for size in range(len(self.blob)):
            with self.assertRaises(f.Refused):self.parse(self.blob[:size])

    def test_trailing_byte_even_zero_refused(self):
        for tail in (b'\0',b'extra',self.blob):
            with self.assertRaises(f.Refused):self.parse(self.blob+tail)

    def test_flat_padding_must_be_preserved(self):
        mutated=bytearray(self.blob);mutated[self.layout.file_end_offset+1]^=1
        with self.assertRaisesRegex(f.Refused,'prefix or padding'):self.parse(mutated)

    def test_header_at_file_end_instead_of_payload_refused(self):
        wrong=self.flat[:self.layout.file_end_offset]+self.blob[self.layout.payload_offset:]
        with self.assertRaises(f.Refused):self.parse(wrong)

    def test_elf_offset_is_not_inferred_from_eof(self):
        with self.assertRaisesRegex(f.Refused,'extent'):
            f.layout_from_nm(b'_base T 0 0\n_file_end D 80 0\n_end D 80 0\n_payload_start D 80 0\n',256)

    def test_missing_duplicate_and_invalid_symbol_refused(self):
        good=b'_base T 1000 0\n_file_end D 1080 0\n_end D 1100 0\n_payload_start D 1100 0\n'
        for bad in (good.replace(b'_payload_start',b'other'),good+b'_base T 1000 0\n',good.replace(b'1100',b'ZZZZ'),good.replace(b'_base T',b'_base U')):
            with self.assertRaises(f.Refused):f.layout_from_nm(bad,256)

    def test_magic_version_reserved_rejected(self):
        for index,value in [(0,b'BAD_MAGIC'.ljust(16,b'\0')),(1,2),(8,1)]:
            fields=list(f.HEADER.unpack_from(self.blob,self.layout.payload_offset));fields[index]=value
            bad=bytearray(self.blob);f.HEADER.pack_into(bad,self.layout.payload_offset,*fields)
            with self.assertRaises(f.Refused):self.parse(bad)

    def test_declared_component_size_bounds(self):
        for index,value in [(2,0),(2,63),(2,f.IMAGE_LIMIT),(3,0),(3,f.INITRD_LIMIT),(4,39),(4,f.FDT_LIMIT+1),(2,0xffffffff)]:
            fields=list(f.HEADER.unpack_from(self.blob,self.layout.payload_offset));fields[index]=value
            bad=bytearray(self.blob);f.HEADER.pack_into(bad,self.layout.payload_offset,*fields)
            with self.assertRaises(f.Refused):self.parse(bad)

    def test_each_crc_mismatch_refused(self):
        for index in (5,6,7):
            fields=list(f.HEADER.unpack_from(self.blob,self.layout.payload_offset));fields[index]^=1
            bad=bytearray(self.blob);f.HEADER.pack_into(bad,self.layout.payload_offset,*fields)
            with self.assertRaisesRegex(f.Refused,'CRC32'):self.parse(bad)

    def test_body_mutation_refused(self):
        start=self.layout.payload_offset+48
        for offset in (start,start+len(self.parts['image']),len(self.blob)-1):
            bad=bytearray(self.blob);bad[offset]^=1
            with self.assertRaises(f.Refused):self.parse(bad)

    def test_each_pin_mismatch_refused(self):
        for name in self.expected:
            pins={**self.expected,name:'0'*64}
            with self.assertRaisesRegex(f.Refused,'pin differs'):f.parse(self.blob,self.flat,self.layout,pins)

    def test_arm_magic_offset_memory_and_flags(self):
        for offset,value,fmt in [(56,b'bad!','4s'),(8,4096,'Q'),(16,63,'Q'),(16,f.IMAGE_LIMIT,'Q'),(24,13,'Q'),(24,0,'Q')]:
            image=bytearray(self.parts['image']);struct.pack_into('<'+fmt,image,offset,value)
            with self.assertRaises(f.Refused):f.image_contract(image)

    def test_fdt_envelope_only_not_generic_validation(self):
        for offset,value in [(0,0),(4,65)]:
            dtb=bytearray(self.parts['dtb']);struct.pack_into('>I',dtb,offset,value)
            with self.assertRaises(f.Refused):f.parts_contract(self.parts['image'],self.parts['initrd'],dtb)

    def test_crc_standard_vector(self):
        self.assertEqual(zlib.crc32(b'123456789'),0xcbf43926)


if __name__=='__main__':unittest.main(verbosity=2)
