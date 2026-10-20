# J614s early APP INIT capture, without replay

**PARTIAL: capture adapter compiled and synthetic replay tested. Physical J614s
capture, XNU tracing and a completed GPU job remain UNTESTED.**

This adapts the mailbox observation pattern from the published
[G17 pre-init capture](https://github.com/ADevWithAnIdea/m1n1/blob/7f42520f39c55eedbb47d990d8eab7bf5569829c/proxyclient/hv/capture_agx_g17p_pre_initdata.py).
Its payload/endpoint pairing is reused. Its dual-ASC constants, broad phase-state
capture and automatic timeout are not carried over. The selected published
script imports a phase-state helper absent from the pinned tree; this adapter
uses the already tested bounded C root/UAT reader instead of depending on it.

## Default behavior and prerequisites

Importing either Python file or applying the source patch only defines functions.
Nothing attaches to a target by default. The adapter contains no GPU writes,
application INIT send, memory replay, UAT constructor, power operation, watchdog
change, reset, boot command or persistent installation.

Live installation is exclusively for the primary controller in a separately
approved guest session, with independently verified remote recovery. Protected
macOS/Recovery boot restrictions continue to apply. `approved_guest_session=True`
is an API prerequisite, not a source of authorization. This checkpoint did not
connect to the Mac, install a tracer or start XNU.

Before any tracer is installed, `attach()` checks:

- proxy chip ID 0x6040, ADT model Mac16,8 and board ID 4;
- exact ADT boot firmware identifier mBoot-18000.161.10;
- live ASC and SGX apertures against the already measured J614s addresses/sizes;
- the native shared-root region size 0x40000 and 16-KiB root alignment;
- a caller-supplied physical RAM allowlist established independently from the
  live ADT and carveouts. No guest-readable-MMIO range belongs in this allowlist.

The first root read uses source-supported IAS/OAS42 geometry. The captured root
must then confirm that exact geometry and current interface before any pointer
is followed. An unexpected version/geometry fails rather than trying guessed
alternatives. The first hardware-data word must identify T6040. The rest of
that prefix remains opaque. A boot identifier is not a cryptographic loaded
firmware match: the manifest explicitly avoids claiming a loaded-image hash.
Retain the primary lane's separate exact-image qualification evidence.

## What is observed

The tracer covers only ASC INBOX0/INBOX1 at +0x8800/+0x8808. Those offsets were
already exercised by J614s's real RTKit bootstrap; they are not inferred from
G17 alone. It requires single 64-bit stores and rejects missing/reordered/
overwritten payload pairs or multiword stores.

Immediately **before** the native endpoint word commits a first endpoint-0x20
INIT of the checked type, it captures:

1. Root: exactly 0xc8 bytes.
2. Main header: the eight-byte pointer at root.main.
3. First hardware-data body read: 16 bytes at that pointer +0xe90.
4. The known main prefix: 0x479 bytes, without following its other pointers.

Every translation uses the C bounds/descriptor checks. Each read is limited to
one checked physical RAM interval. A page crossing gets another translation.
Short reads, differing overlapping bytes and exceeded capture bounds disable
the observer; no recovery or firmware action is attempted. Matching overlapping
reads establish only observed consistency. Stopping one vCPU does not prove an
atomic snapshot against other CPUs or firmware, or cache/publication coherence.
Those properties require separate qualification before interpreting a graph as
a coherent native publication. Per-phase bounds
are 256 physical reads and 64KiB of returned data, not a session work budget.

Subsequent application messages are recorded as raw observations. The first
post-INIT application message receives its own snapshot. An endpoint-0x21
message of type83/84 is labeled **gravity-kick-candidate**, based on Gravity's
existing caller. It is not declared a T6040 compute kick merely because its
number matches. Correlate it with the independent trigger's COMMIT0 marker and
later completion/readback; a captured message is never a job pass.

The SYNC tracer observes a guest store before m1n1 forwards that store normally.
The adapter does not manufacture or alter it. Installing the trace changes the
hypervisor's trap mappings and timing; it is not passive hardware sniffing.
The existing m1n1 SYNC mechanism's forwarding is part of the separately approved
guest session, not an extra GPU write made by this adapter.

## Build and offline tests

```sh
make -C graphics all test
python3 graphics/test_early_capture.py -v
```

C collector tests also pass with Clang AddressSanitizer/fatal UBSan through the
existing `BUILD=build-clang` test invocation. Python tests use synthetic ADT,
mailbox and RAM inputs. They verify native-INIT collection, candidate-message
labeling, wrong chip/version, absent RAM approval, short/changed reads, strict
mailbox width/order, default refusal, exact attach guards and offline file-hash
rejection. A fake tracer registration is exercised without any target access.

The source patch `m1n1-j614s-capture-installer.patch` adds only
`proxyclient/hv/capture_agx_j614s_early.py` to the selected m1n1 tree. It defines
an explicit installer using the separately supplied module and built library.
No default script invocation attaches. The module itself is
`g16s_early_capture.py`; the library is built from `g16s_capture_bridge.c` and
the same read-only headers used by replay tests.

## Later approved session runbook

This is preparation, not an instruction to boot the protected Mac unattended.

1. Independently qualify remote recovery and the intended XNU session. Arm the
   observer **before guest entry**, since APP INIT may precede a user-space
   helper or its START gate. Do not discover that boundary by installing a
   LaunchDaemon or changing startup policy here.
2. Pass the already created/qualified HV object, live-ADT RAM ranges, explicit
   module/library paths and a new private output directory to `install_capture`.
   Keep it in a variable so capture errors and phase state remain inspectable.
3. The primary controller starts the separately approved guest. This adapter
   never calls HV.start. Follow the public-Metal trigger's START and COMMIT0
   gates only when the observer is armed. Its source-owned XOR/constant output
   provides an independent oracle.
4. Inspect `observer.disabled`, `callback_error` and saved manifests. A capture
   failure remains a failure. Do not automatically reset, replay memory or send
   an INIT to make another attempt. The controller owns recovery decisions.
5. Replay a completed phase entirely offline:

```sh
python3 graphics/replay_early_capture.py /private/capture/pre-first-init --output graphics/build/replayed --library graphics/build/g16s_capture.so
```

Replay verifies filenames, lengths, hashes and overlapping bytes, then executes
the same C traversal against captured data only. It never connects to a target.

Private output directories use 0700; raw captures use 0600. Files may contain
sensitive live memory and must remain private. Publish only derived interface
facts and redacted diagnostics. The metadata always says
`hardware_job_pass=false` and `safe_to_publish_init=false`.

The primary also exercised the attach guards offline with this machine's real
captured ADT and a fake tracer registration: `early-capture-real-adt-guard.json`.
No physical read, target connection, output directory or guest execution occurred.
The RAM allowlist in that guard test was synthetic and grants no live permission.
