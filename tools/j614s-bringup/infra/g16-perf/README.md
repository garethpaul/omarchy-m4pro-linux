# T6040 performance decoder crate qualification

The decoder records both16-state banks without reordering indices. It is an ADT input decoder, with no firmware serializer or runtime caller. Compilation does not establish GPU initialization, performance control or hardware operation.

The immutable decoder commit `eb40b68bcdca7bf66f79b045b96c5599adb720ab` is applied as `5628d35c32649341516db300b1a7939fe5753334` to the reproduced combined kernel `8f2f3d13600aacadd93d577855b7e212b8ae57ff`. Only the new `g16_perf.rs` and one module declaration differ. All combined-source fixes, including checked runtime MMIO and layout assertions, remain present. Original source and qualified build are preserved. The two unsuccessful orchestration/preflight attempts are retained separately in `attempts.json`; neither is a decoder compilation result.

Reproduce in a fresh output directory using this tooling repository and the workspace's `work/` layout:

```sh
python3 infra/qualify_gravity.py \
  --source ../overnight-infra-gravity-perf-source-02 \
  --commit 5628d35c32649341516db300b1a7939fe5753334 \
  --config ../overnight-integration/integration/configs/j614s-gravity-candidate.config \
  --config-sha256 6c5aba7745d918c528300c5a395fcd7db0c2b718acda7d1467af2816a8d56516 \
  --localversion=-j614s-gravity-candidate \
  --bindgen ../toolchains/aurora-bindgen-qualified/rust-bindgen-0.73.2/target/release/bindgen \
  --tool-dir ../build-tools --tool-contract infra/baseline-contract.json \
  --output ../gravity-perf-next-fresh-build --jobs 8
```

This builds the actual AArch64 `asahi_m4.o` crate and generated prerequisites only. It does not perform a full kernel build, module link, deployment or target operation. No lints or assertions are suppressed for this qualification. Warnings are retained in the result; unused decoder items are expected because runtime wiring is deliberately absent. Raw build logs remain private because they contain host paths.

**WORKS (compile only):** the complete AArch64 crate compiles with zero config normalization drift. All3174 generated layout blocks and16413 field-offset checks remain enabled; no unresolved Rust build assertion remains. `result.json` records object/source/tree/tool/helper hashes and byte-identical patch provenance. The existing combined build's manifest artifacts remain unchanged. **UNTESTED:** module linking, firmware behavior, runtime inputs and hardware operation.

Twelve compiler warnings are retained: three existing G16 firmware items are unused, five decoder items are unused, and four decoder `pub` items are unreachable outside their private module. Bindgen also reports three nonfatal missing-rustfmt notices. These are recorded without lint suppression or toolchain changes. No warning-free claim is made. The preserved successful output is the private `overnight-infra-gravity-perf-build-02` directory; no compiled binary is committed here.
