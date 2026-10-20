# USB configuration failure: narrow DART v2 port

**WORKS (offline):** USB DT equivalence, measured revision binding, actual-source regression controls, strict checkpatch, AArch64 DART object, and full Image/18-module linking pass. **PARTIAL:** a source-level regression is identified and a narrow candidate is compiled. **UNTESTED:** the candidate's ability to complete USB configuration on hardware. No lane target access or deployment occurred.

The supervised boot reached PID1 and USB descriptors, then the host's SET_CONFIGURATION request timed out. No probe or NVMe module had been loaded. Root subsequently captured both actual USB1 DART banks' PARAMS3 as `0x2a2a0202` (42-bit PA/VA, revision 2.2), with zero exceptions from that read-only measurement. The public evidence records its hash and only those static register facts; no private capture or raw ADT is included.

`comparison.json` proves every property of USB1, its inherited USB2 PHY, both DART banks and AIC matches the older compiled DT after normalizing phandle identities. This includes both suspend quirks, SID0/1 and the low 4 GiB DMA window. The PHY, DWC3 core/gadget, ACM, serial and configfs sources are byte-identical; ep0 differs only by braces around an existing branch and a blank line. The filtered USB/IOMMU/DMA config comparison differs only in three display DMA helpers. The known working older init used CDC-subset networking, while the failing init uses ACM: an old-kernel/same-ACM control is not established, so class choice remains a confound.

The old driver, unlike the combined 8f2 baseline, recognizes PARAMS3 revision 2.2, sets bit 15 on FLUSH_SID, waits for a prior command to finish and uses its v2 timeout. It also decodes and acknowledges the per-stream exception bitmap and releases the diagnostic lock-on-error latch. The baseline uses the legacy command and exception path for the measured2.2 hardware. These omissions are a concrete regression from the known working driver. They can explain failure when endpoint configuration creates new DMA mappings and encounters an unhandled fault/lock, but no failing-Linux DART trace proves which omitted operation caused this timeout.

Candidate source `5cbc8c64748b480f7da4dac87b92450b80124594`, branch `agent/j614s-usb-dart-v22`, is one file atop combined `8f2f3d13600aacadd93d577855b7e212b8ae57ff`. It ports only version detection, v2 command handling, stale exception acknowledgement/unlock and version-selected IRQ handling. The older handler's existing guarded 2.3 block-summary support is retained; actual measured hardware is 2.2. Ten mapping/domain/locked-root function bodies are byte-identical, as is the legacy IRQ body after restoring its name. DMA windows, SID bindings, page tables, retained mappings, display, and tunneled PCIe paths are untouched. No checks or compatibility gates are removed.

`test_dart.py` compiles selected **actual function bodies and register macros** with mocked MMIO. The baseline exits 17 for the missing `0x8100` command and 18 for unacknowledged v2 exception state. The candidate passes these controls, 25 version/SID combinations, pre/post-busy timeouts, conditional unlock, per-SID W1C handling, stale exception drain and legacy IRQ behavior under GCC and Clang with fatal ASan/UBSan and warnings as errors. The mocks establish emitted source behavior, not hardware semantics or successful transport. Reset ordering is checked as source wiring and through real kernel compilation; the whole reset function is not executed in the host harness. Host adapter compile failures and their corrections are retained; no warning flag was disabled. Checkpatch's initial style findings and final zero-findings result remain separate.

The fresh full build uses unchanged config SHA `6c5aba7745d918c528300c5a395fcd7db0c2b718acda7d1467af2816a8d56516`, pinned original toolchain and enabled layout assertions. DART object SHA is `8ea98a71459f3d466fe11b3e0a34d9ccbb2e3f94ab86f3bda34562b148799301`. Image SHA is `09a5242571bef87b5d7c4c64df6210a87571156430e7013d3f556b4db33db8e8` (14772232 bytes). All 18 modules are byte-identical to 8f2. Three inherited unused firmware warnings and three missing-rustfmt notices are retained; there are no DART compiler warnings. Two independent fresh same-host builds now reproduce Image, all18modules and seven supplemental artifacts byte-for-byte; see `reproducibility.json`. Root independently compared Image/config/contract/release/layout and all18modules, with distinct inodes and clean exact-source checkouts; see `../../qualification/usb-dart-reproduction-root.json`. The raw build logs differ but their path-normalized line multisets match. Original sources/builds are preserved.

From this tooling repository with the workspace's `work/` layout:

```sh
python3 infra/usb-configuration/test_dart.py \
  --baseline ../overnight-infra-gravity-combined-source-03/drivers/iommu/apple-dart.c \
  --candidate ../overnight-infra-gravity-usb-v22-source-01/drivers/iommu/apple-dart.c \
  --output "$FRESH_HOST_RESULT"
python3 infra/qualify_gravity.py \
  --source ../overnight-infra-gravity-usb-v22-source-01 \
  --commit 5cbc8c64748b480f7da4dac87b92450b80124594 \
  --config ../overnight-integration/integration/configs/j614s-gravity-candidate.config \
  --config-sha256 6c5aba7745d918c528300c5a395fcd7db0c2b718acda7d1467af2816a8d56516 \
  --localversion=-j614s-gravity-candidate --full-kernel --display \
  --object drivers/iommu/apple-dart.o \
  --bindgen ../toolchains/aurora-bindgen-qualified/rust-bindgen-0.73.2/target/release/bindgen \
  --tool-dir ../build-tools --tool-contract infra/baseline-contract.json \
  --output ../gravity-usb-v22-next-fresh-build --jobs 8
python3 infra/kernel_build.py verify --output ../gravity-usb-v22-next-fresh-build
```

`port.py` can recreate the exact one-file source change only when both old/base source hashes match; it refuses a second application. It edits only the explicit host source path supplied by its caller. `compare.py` reads static USB properties from existing DTBs and hashes source files. Neither script imports a target module. Build logs/binaries and DTBs remain private intermediates; `build-result.json` records reviewed hashes and limitations. Root separately owns probe metadata transition, permission, health-counter handling and any supervised hardware test.
