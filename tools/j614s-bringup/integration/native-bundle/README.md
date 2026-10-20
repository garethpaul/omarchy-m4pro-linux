# Offline J614s native container

This tool checks local files and can assemble an **unqualified** native-format
container only after the pinned capture and DT validators accept its inputs.
It has no target, USB, serial, staging, chainload, reboot or watchdog interface.

| Item | Status | Evidence / limit |
| --- | --- | --- |
| Pinned loader/paired ELF, Image and framed initrd identities | WORKS (file checks only) | Five actual-input controls included in the 30-test run; hashes in `pins.json` and `evidence.json` |
| Bounded format codec | PARTIAL | Synthetic non-bootable roundtrip and corruption controls; native C checksum comparison over six small vectors |
| Current capture03 full assembly | BLOCKED | Secondary flags are zero; idle/WFE conditions are false. Both API and CLI refuse before reading DT evidence or creating output/diagnostics |
| Future actual validated DT/container | UNTESTED | Current capture has no qualifying DT. No real candidate container was produced |
| Live placement, resident preservation, firmware handoff, recovery and boot | UNTESTED | No target operation; file validity grants no boot authority |

## Inputs and format

`pins.json` binds loader commit `6249e0ec`, kernel commit `8f2f3d13`, Image
`f9d7b637…`, framed initrd `8fd6f861…`, exact source helpers and host tools.
`bundle.py` pins the pinset itself, then compiles hash-verified helper bytes;
timestamp-valid Python caches cannot replace those helper bytes. Source and
pinset changes require review and deliberate digest updates.

The native header is 48 bytes, little-endian `<16s8I`: 16-byte
`J614S_NATIVE_V1\0`, version 1, Image/initrd/FDT lengths, their CRC32 values,
and reserved zero. It follows the complete flat loader at the paired ELF's
`_payload_start - _base`. The pinned symbols give `_file_end=0x140000` but
`_end=_payload_start=0x360000`; the complete 3,538,944-byte flat image includes
the zero-padded stack/BSS region. This tool verifies the ELF symbols and fresh
`llvm-objcopy` output rather than deriving placement from EOF or `_file_end`.
The pinned linker declares a 64 MiB maximum payload.

`native_format.py` checks bounded component sizes, Image header, exact prefix,
lengths, CRCs and SHA256 identities. Its FDT envelope check is **not** a DT
validation. Production validation executes the exact pinned
`infra/native-dt/generate.py` bytes from commit `66557cd6`. Its `verify_inputs`
binds the capture/session/observer/ADT/bootargs, sources and artifacts;
`verify_dtb` independently renders and compiles the canonical DT, compares
exact bytes, and performs its semantic checks. Compiler diagnostics are retained
privately on a future compilation failure. The current capture is refused
before those output paths are created.

The C bridge compiles only pinned `src/tinf/crc32.c` for this host and compares
six tiny checksum vectors with Python zlib. It does not exercise the native C
consumer, AArch64 instructions, relocation or handoff.

## Replay

Portable format/source controls run with:

```sh
python3 -m unittest discover -s integration/native-bundle -p 'test_*.py' -v
```

The five actual-input controls require a private JSON containing explicit
artifact/source paths and expected capture provenance. In this isolated
worktree the retained, ignored configuration is `.private/actual-inputs.json`:

```sh
J614S_NATIVE_INPUTS=integration/native-bundle/.private/actual-inputs.json \
  python3 -m unittest discover -s integration/native-bundle -p 'test_*.py' -v
```

That full run passes all 30 controls without skips. It independently checks
real component bytes, exercises the capture03 refusal through the API and CLI,
and confirms no container/diagnostics directory appears and the capture hash
is unchanged. Ordinary execution without the private configuration explicitly
skips the five actual-input controls; it cannot establish their result.
Positive codec fixtures contain invented `SYNTHETIC_*` markers, a fake Image,
non-cpio initrd text and an invalid synthetic DT envelope. They never combine
actual candidate component bytes into a positive bundle. The metadata-only
future-report fixture also establishes no validated DT.

## Separate live gate

There is no staging or placement qualification. In particular, the generic
pinned `proxyclient/tools/chainload.py` path uses the resident base and a copy
stub; it must not be inferred safe for preserved resident release pointers.
The primary's staging-source hazard record remains a separate gate. A child
loader's placement, exclusion from resident memory, fresh boot state, release
pointers and recovery need their own reviewed implementation and supervised
qualification. This tool neither imports nor invokes that chainloader and
does not implement a stager. Every result keeps `hardware=UNTESTED`,
`runtime_fdt=false`, `deployment_authorized=false`, and `boot_permission=false`.

No old loader, kernel, DT, initrd, test52/56 or capture artifact was changed.
Generated positive codec fixtures exist only in memory/temporary test files;
private paths and the preserved cache-regression failure remain ignored.
