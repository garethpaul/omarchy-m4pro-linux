# Gravity Mesa first compute job

This lane uses the user's requested Gravity stack. Its default `main` branch contains the Apple9 compiler and M4 CI tooling; exact base and matching kernel commits are recorded in `evidence/source-and-tests.json`. The [project article](https://codyho.dev/blog/gpu-driver/) links [Gravity Mesa](https://github.com/GravityLinux/mesa) and its [kernel](https://github.com/GravityLinux/linux/tree/gravity-m4). This lane does not reproduce the article's hardware results on J614s.

| Item | Status | Evidence |
| --- | --- | --- |
| Matching Mesa/kernel UAPI | WORKS for source comparison | Headers byte-identical, SHA256 `eb9f39e87dfe448dc044f54ab2d11b7493bf1359faca8fb76ece5f3583469015` |
| Apple9 compiler and packet encoder build | WORKS on x86_64 host | `evidence/source-and-tests.json`; compiled normal Gallium `libasahi.a` as well as tools |
| Compiler / launcher / geometry / new fixture tests | WORKS on host | 387 gtest cases across five suites; six additional Python cases, including corrupted artifacts and false hardware claims |
| Minimal compute payload | WORKS for source-built artifact generation | `evidence/fixture-validation.json`; repeated generation byte-identical |
| G16S identity geometry projection | PARTIAL | `evidence/g16s-geometry-candidate.json`, derived from actual saved identity/geometry measurement |
| G16S shader/job execution | UNTESTED | No real render node or qualified complete firmware/job path yet |
| Full G16S Mesa runtime | BLOCKED on kernel bring-up and hardware qualification | Production G16G-only device and compute guards remain unchanged |

## Source and reuse contract

Isolated source checkout: sibling `overnight-gravity-mesa`, branch `agent/j614s-compute`. Base `main` is `87ac51d411f0e58a9433567ec2666f457be89e1d`; source change is recorded by its complete commit SHA in the evidence JSON. `patches/0001-offline-compute-fixture.patch` carries the change as a zero-context diff; apply only against the recorded base with `git apply --unidiff-zero`. The source commit remains the preferred review/history reference. No edits were made to Aurora Mesa or the original running system's Mesa.

The kernel consumer is Gravity `gravity-m4` commit `4fc326f6c25ccceb7515e2635c22e01fde5d3bac`. The existing Asahi UAPI is reused without changes: ordinary VM/BO bindings, compute queue, `drm_asahi_cmd_compute`, submit/fence ownership. The runtime now explicitly rejects unqualified Apple9 models before allocation, so release builds also reject G16S. Original gen16/17 assertions remain; `agx_apple9_compute_enabled` still returns true only for G16G. NDEBUG unit tests exercise the rejection. The new host tool does not call runtime initialization, spoof device parameters, open a render node or issue ioctl.

The real measured G16S ID is `0x0a031100`, count word `0x11020a`, packed enabled-core mask `0xf6fdb`. Splitting the measured two physical ten-core clusters yields `0x3db / 0x3db`, eight enabled cores each. Only those known fields are projected into candidate UAPI geometry. VM limits, fragment geometry, firmware/power state and actual USC execution remain unqualified. No full G16G profile alias is added.

## Built fixture

The new source tool compiles a NIR shader that stores constant 42 into one SSBO at `global_id.x * 4`, with one 256x1x1 workgroup. Gravity's actual encoders produce:

- A 42-byte compiler-generated shader; no trace replay or vendor executable bytes.
- The normal 0x340 entry header plus one 0xc0 entry block, including source-built branch/helper encoding.
- One 0x100-byte resource record, group-count pointer plus one SSBO pointer, inline group counts at offset 0xc0.
- A 0x400-byte source-built launch program.
- A 0x2c-byte direct CDM record and eight-byte terminator. UAPI end is base+0x30, mirroring the existing `agx_flush_compute` first-terminator-word convention. The allocation/file contains all 0x34 bytes.
- A reference file of exactly 256 little-endian u32 words equal to 42 and the exact compiler profile in JSON.

The helper accepts explicit virtual addresses for rebuilding immutable records after allocation. The checked-in JSON uses unallocated template VAs, including the branch's existing 1-TiB USC aperture. It is deliberately marked `hardware_execution=UNTESTED`. The ordinary runtime header initializer now shares a pure helper with the fixture builder; initialization bytes are unchanged. Review reproduced two shader-containment holes in the first helper. The API now carries the actual shader byte length and rejects complete known shader/resource/launch overlaps, including reverse containment and USC-end overflow. Profile, alignment and range checks remain enabled, with rejection leaving the destination unchanged. Complete VM/CDM mapping validation remains the caller's responsibility.

Generated binaries are retained under `evidence/compute-fixture/` for the primary and ignored by Git. Metadata and SHA256s are committed. Regenerate them from the committed source before running the Python artifact tests in a fresh checkout.

## Reproduce the build

Build in an isolated source tree using Meson 1.9.2, Ninja 1.13.0, Mako 1.3.10, packaging 25.0 and PyYAML 6.0.3. This host uses GCC 16.2.1 and LLVM/Clang 23.1.3. The initially missing SPIR-V translator was extracted into a private build prefix from `spirv-llvm-translator-23.1.2-1-x86_64.pkg.tar.zst`, verified against SHA256 `5851c9464da258d38b94b5210cf0f5ca43e855e8c63cf1ecf0c78a032fbd127c` from local package metadata. No host package was installed. Its pkg-config prefix was relocated locally; use matching `PKG_CONFIG_PATH` and runtime library path when reproducing.

```sh
meson setup build-cpu MESA_SOURCE --buildtype=debugoptimized \
  -Dgallium-drivers=asahi -Dvulkan-drivers= -Dplatforms= \
  -Dglx=disabled -Degl=disabled -Dgbm=disabled -Dbuild-tests=true \
  -Dllvm=enabled -Dshared-llvm=enabled -Dtools=asahi \
  -Dvideo-codecs= -Dlibunwind=disabled
ninja -C build-cpu \
  src/asahi/compiler/agx_tests \
  src/asahi/compiler/agx_apple9_tiny_tool \
  src/gallium/drivers/asahi/agx_apple9_launcher_tests \
  src/gallium/drivers/asahi/agx_apple9_geometry_tests \
  src/gallium/drivers/asahi/agx_apple9_compute_fixture_tests \
  src/gallium/drivers/asahi/agx_apple9_runtime_model_tests \
  src/gallium/drivers/asahi/agx_apple9_compute_fixture_tool \
  src/gallium/drivers/asahi/libasahi.a
meson test -C build-cpu --no-rebuild agx_tests \
  agx_apple9_launcher_tests agx_apple9_geometry_tests \
  agx_apple9_compute_fixture_tests agx_apple9_runtime_model_tests
build-cpu/src/gallium/drivers/asahi/agx_apple9_compute_fixture_tool \
  --offline-template EVIDENCE/constant42
```

From this lane's root, after placing the output under `mesa/evidence/compute-fixture/`:

```sh
python3 mesa/verify_fixture.py \
  --prefix mesa/evidence/compute-fixture/constant42 \
  --output mesa/evidence/fixture-validation.json
python3 -m unittest discover -s mesa/tests -v
```

A clean build-tool PATH avoids this host's stale Python-version shims. Upstream compiler/Gallium warnings remain in local build logs; no error checks or compatibility guards were disabled to obtain passing tests. Host results are distinct from the AArch64 cross-build and emulated execution below; none establish physical GPU execution.

## Primary's next hardware integration

The graphics lane owns the missing current-firmware G16S root/MainConfig/profile work. Do not submit while that is incomplete. Once there is an independently qualified real Asahi render node with correct G16S parameters, allocate/bind real BOs through the unchanged UAPI, rebuild the records using those actual VAs, and retain every BO until completion. Validate full shader/entry/resource/launch/CDM/output ranges, permissions, disjoint mappings, command bounds and cache synchronization. The placeholder JSON grants no runtime permission and is not directly runnable.

The first test should issue one compute job with sampler/helper fields zero, wait for its real completion fence, verify all 256 words against 42, check untouched output/page canaries and kernel fault logs, then repeat after a fresh qualified boot. Preserve the known-good boot and rollback route. A host packet test, completed submission ioctl or retired firmware message alone is insufficient evidence of GPU execution.

## AArch64 qualification and review

The actual compiler, fixture tools, five gtest binaries, Gallium library and device library also cross-build for AArch64 using the existing saved ALARM sysroot. `evidence/aarch64-build.json` records ELF machine and hashes. Native x86_64 `mesa_clc`, `vtn_bindgen2` and `asahi_clc` perform build-time generation; the AGX compiler itself remains compiled into the AArch64 programs. Cross-building found an existing Clang C++ narrowing error in a compiler test; an explicit unsigned location cast fixes its type without disabling that diagnostic or any test.

`write_cross_file.py --sysroot SAVED_SYSROOT --linker LD_LLD --output CROSS.local.ini` generates local paths. Reuse the setup options above with `--cross-file CROSS.local.ini`, `-Dmesa-clc=system -Dprecomp-compiler=system -Dllvm=disabled -Dshared-llvm=disabled` and the native generator directories on PATH. `needs_exe_wrapper=true` prevents incidental execution of target programs during configuration.

A checksum-verified cached QEMU user-static 11.1.2 was extracted privately. Explicit user-mode runs pass all 387 AArch64 gtests, including the NDEBUG model gate; this is emulation on x86_64, not execution on the Mac. Its ELF interpreter prefix is the saved sysroot's `usr` directory because the copy has `usr/lib` without a root `lib` symlink. Use `qemu-aarch64-static -L SYSROOT/usr -E LD_LIBRARY_PATH=SYSROOT/usr/lib AARCH64_PROGRAM`. The target-architecture fixture tool emits exactly the same shader and every packet/reference/JSON byte as the x86_64 tool. See `evidence/aarch64-emulated-tests.json`.

`evidence/overlap-red.txt` retains the failing containment regression before the fix. Production model admission is now an explicit conditional that survives NDEBUG, with assertions retained as internal checks. All GPU runtime status remains UNTESTED.

The matched public Metal helper test contract is recorded separately in `evidence/compute-test-contract.json`: one 256-thread group, one 1024-byte SSBO initialized to 0xa5a5a5a5, and constant 42 stores indexed by global_id.x. Linux BO/page canaries and tracer checks are separate; the Metal helper must not read or write memory beyond its owned buffer.
