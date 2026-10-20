# Host-only supervised preparation

`prepare_supervised.py` replaces the manual fresh-capture packaging steps. **WORKS within host unit scope:** the guard and phase controls pass. **WORKS in a separate root replay:** the complete actual-input generator/assemble/verify/plan succeeds;15 controls and two additional full-CLI negative cases pass. See [root evidence](../../qualification/preparation-root-04.json). **UNTESTED:** live freshness, supervision, recovery, allocation and boot. No target interface or target mode is exposed by this wrapper.

Supply an explicitly SHA-bound reviewed seed context, an explicitly SHA-bound fresh CPU capture, a staging capture directory with `capture.json`, `bootargs.bin` and `adt.bin`, its exact capture SHA, and a new private output directory. All required files must already exist except the output. The output's parent must exist. The output must be outside the input/source/evidence directories, including the CPU capture's parent. A sibling under a broad capture parent is still forbidden. Existing output directories are refused and preserved; each attempt needs a new path.

```sh
python3 recovery/preparation/prepare_supervised.py \
  --seed "$SEED_CONTEXT" --expected-seed-sha256 "$SEED_SHA256" \
  --cpu-capture "$CPU_CAPTURE" --expected-cpu-sha256 "$CPU_SHA256" \
  --staging-directory "$STAGING_DIRECTORY" \
  --expected-staging-sha256 "$STAGING_CAPTURE_SHA256" \
  --output "$NEW_PRIVATE_WORK_DIRECTORY"
```

The seed's `bundle_inputs.storage_diagnostic` must be the JSON boolean `true`, explicitly present. Missing/false/nonboolean values refuse before creating output. The old session fields and old generated artifact paths in the seed are not reused as current evidence. Its reviewed static source/artifact paths and physical-port identity are retained; all session fields, nonce, DT, bundle, context and plan are rebuilt for the supplied fresh captures. The pinned existing generator and bundler still validate the unchanged hardware candidate `5cbc8c64748b480f7da4dac87b92450b80124594` and all original tool, firmware-interface and diagnostic guards.

SHA checks precede JSON decoding. Duplicate JSON keys refuse. The exact frozen bundle, pinset, format helper, generator/profile, reservation helper, geometry helper, kernel verifier and stager source bytes are checked. Verified Python bytes are compiled directly; timestamp-valid bytecode caches are not consulted. Kernel/loader/resident checks remain those required by the existing validators. Unrelated edits elsewhere in the tooling tree do not require cleanup and are not touched. `/dev`, `/sys` and `/proc` input paths, including resolved symlink targets, are refused before file reads. No proxy/serial/USB module is imported by this wrapper.

Preflight checks the available shared CPU/staging USB session, BootArgs/ADT hashes, source identity, resident extent, usable/physical RAM, video, exact release pointers and CPU/WFE readiness summaries. Original BootArgs/ADT bytes must match both captures and their metadata lengths; BootArgs revision, original top and RAM fields are checked directly. The frozen staging schema contains no full raw-slot digest. Consequently byte-identical raw slot snapshots **cannot be proved across the two files**. The CPU capture's slot hash is retained as its own evidence only. The separate stage/vector paired-ELF live double reads remain the authoritative slot gate. File timestamps and matching files do not establish liveness.

Only after preflight passes does the wrapper create its mode0700 private work directory. It copies original inputs exactly, renders the canonical DT with the storage flag, runs the pinned assemble and verify entry points, and writes a fresh context plus `context.sha256`. It invokes the pinned stager with literal **`plan` only**. Its required `--operator-present` option is used solely to enter that existing host-plan path: the wrapper does not establish an operator's presence, supervision or boot authorization. A strict phase allowlist accepts only generate-DT, assemble, verify and plan. No seed/CLI value selects stage/vector. Only `.plan.json` and the host lock may be emitted by the stager; `stage-state.json` is expressly forbidden.

The original `inputs/bootargs.bin` remains byte-identical. A separate private `final-bootargs.bin` is produced for review: only the eight-byte `top_of_kernel_data` field changes to the proposed child end, with the hash checked against the pinned plan. The canonical plan remains geometry only. The final preparation report explicitly denies boot permission and deployment authority. Root must separately review every output, recheck the live session/ownership/recovery gates, and handle the unanswered health-clear authorization before any hardware action.

Phase stdout/stderr, including inherited host-tool file-descriptor output, are retained privately. If a phase raises, `FAILED.traceback.txt` records the private reason/trace and captured exception streams with mode0600; `FAILED.json` records refusal. Partial outputs are not removed or reused. Preflight refusal creates no work directory; its sanitized CLI refusal must be retained by the caller as that attempt's evidence. Private captures, binaries, traces and generated ASLR-bearing artifacts must never be committed or published. Curated evidence contains only source hashes, test outcomes and limitations.

Run host controls:

```sh
python3 recovery/preparation/test_preparation.py
```

The initial missing/false-storage controls failed with “ValueError not raised” before implementation. Fifteen final tests cover the packaging errors, identity/refusal conditions, exact helper hashes, output separation, original/patched BootArgs padding, phase allowlist, forbidden target-mode/input paths, and private failure retention. Shared-field positive fixtures are wholly synthetic and never submitted as real observations. A fake host phase tests log/trace capture; it is not a real generator/bundle/stager replay. The pure BootArgs control executes only AST-selected functions from the pinned stager. This lane did not run the complete real-input preparation or touch the physical target.
