# Minimal Metal compute trigger for a later M4 Pro trace

This CLI prepares one small workload for the primary operator's authorized
XNU/hypervisor capture. It does not capture or decode firmware itself.
The source, compiled ARM64 Mach-O and development-Mac validation are ready.
**It has not run on the M4 Pro target.**

| Item | Status | Evidence |
| --- | --- | --- |
| ARM64 build/link, SDK availability and executable verification | WORKS on development Mac | `evidence/build.json` |
| Guarded one-job public Metal workload | WORKS on M1 Pro builder | `evidence/builder-validation/one-job.jsonl` |
| Separately gated second job/readback | WORKS on M1 Pro builder | `evidence/builder-validation/two-jobs.jsonl` |
| Wrong-model, START refusal/EOF and commit refusal | WORKS on builder | `evidence/builder-validation/result.json` |
| Transcript corruption rejection | WORKS as host tests | `evidence/unit-tests.txt` |
| M4 Pro execution, APP INIT or first firmware kick capture | UNTESTED | Requires primary-operator session and authorization |
| GPU firmware replay, shader submission from Linux, accelerated Omarchy | UNTESTED by this helper | Builder Metal success does not establish these features |

## Published work reused

The public [Gravity write-up](https://codyho.dev/blog/gpu-driver/) identifies
early, small compute captures as the useful starting point. Its reported
single-user/early-launch setup is context; this change installs no daemon and
changes no boot configuration.

The workload adapts the existing public-API
[`iohello_compute.m`](https://github.com/ADevWithAnIdea/agx-re/blob/c677ff970ca9d5ab98770100e790f8a62c60a2a0/experiments/EXP-M4-03-cmdstream-pipeline/work/iohello_compute.m),
with the [Niklas experiment](https://github.com/niklassheth/agx-re/blob/e25433b1d348a809ab86484ce149ff7d459e8cdf/experiments/EXP-0058-m4-compute-render-transition-fixed/harness/probe.m)
reviewed as a second reference. Exact revisions and source digests are in
`upstream.json`; the source carries GPL-3.0 attribution and the license is
included. We use a newly supplied XOR shader, not copied vendor shaders.
This helper makes no provenance claim about the project's separate
vendor-derived firmware decoder or other reverse-engineering artifacts.

## Workload and coordination protocol

There is one shared Metal buffer: **16 uint32 words / 64 bytes**, initialized
to `0..15`. The shader applies `word[i] ^= 0x6145a55a`. It submits one compute
command buffer by default, with no textures, render passes, windows, capture
interposer or file-data inputs. It logs its own GPU buffer address in hex and
little-endian form. Readback checks every word against the CPU expectation;
the separate transcript validator uses a literal expected vector.

`--run` is required. Default expectations are `Mac16,8` and `Apple M4 Pro`.
Model and native-architecture guards precede this process's first Metal API
call. Builder overrides were explicit, and `validate_builder.py` refuses to
run its GPU tests on the target model.

1. `WAIT_START` waits for exactly `START` on stdin, before
   `MTLCreateSystemDefaultDevice`. The primary tracer must already be armed
   before releasing this gate. APP INIT may occur during kernel/device boot
   before this program starts: capture it by tracing from guest entry, not by
   assuming this stdin gate can recover an earlier initialization event.
2. Markers identify device creation, library/pipeline creation, buffer and
   queue allocation, and encoding. `WAIT_COMMIT` waits for `COMMIT0`, after
   encoding and before the first command-buffer commit.
3. `BEFORE_COMMIT`, `COMMAND_COMPLETED`, `READBACK` and `DONE` identify actual
   submission, completion status and independent output verification.
4. Only `--second` enables another job. It requires both `SECOND` and
   `COMMIT1`; the same buffer is reused and the second XOR restores `0..15`.

All markers are JSONL with monotonic nanoseconds. EOF or a wrong gate string
fails closed. `GATE_ACCEPTED` is emitted only after the exact input matched,
before the corresponding device creation or command-buffer commit. The
validator checks both wait and acceptance markers in causal order, as well as
the actual completed command status and independently expected readback.
A failed command, timeout or incorrect output cannot produce
success. The completion timeout defaults to 10 seconds (maximum 30 seconds).
On timeout, the program reports failure; it cannot guarantee an in-flight
driver operation is cancelled or recover crashed firmware.

These barriers cover **our process's API calls and submitted jobs**. Dynamic
framework loading and other macOS processes are outside that claim. A
running GUI may already have initialized the GPU or submitted render work;
the helper cannot prove its job is the first global firmware job. The primary
operator must establish the early/no-render boot context separately.

## Build and validation

On a Mac with the SDK installed:

```sh
./build.sh
./build/compute-trigger --dry-run
python3 -m unittest discover -s . -v
```

This is a command-line executable, not an application bundle. The build
script only compiles and prints source/binary digests; it never launches work.
The prepared binary is `build/compute-trigger` (ignored build artifact),
SHA256 `a64db4ed42291db0b8829ffd1655099aa1c71f5aea8928b45edd74c01d4cf871`.
It compiled with Apple clang 21.0.0 and SDK 26.5, deployment target macOS 13.0.
The builder was an M1 Pro running macOS 26.5.2. The final validation run submitted
three own compute jobs across one-job and two-job cases; all 16 words passed.

For that known development Mac only:

```sh
python3 validate_builder.py --binary build/compute-trigger --output NEW_EVIDENCE_DIRECTORY
```

The runner checks the builder model before launching the executable. It tests
dry-run and rejected gate/model paths, then explicit builder overrides for
one and two submissions. It writes only its selected evidence directory;
Metal/macOS may additionally write normal driver/compiler caches and logs.
No services, agents, boot settings or package installations were changed.

## Future target run: exact scope requiring primary approval

This is a prepared command for a later explicitly authorized target session;
it is **not executed by building or testing this change**:

```sh
./compute-trigger --run
```

Copying the executable or saving a transcript onto a macOS volume also needs
an explicitly approved staging path under the protected-volume rule; use a
primary-operator RAM staging area where available. No target staging was
performed here.

Keep stdin interactive: release `START` only when the primary tracer is ready,
then release `COMMIT0` when the first-kick capture is armed. Do not pipe these
tokens automatically into an unqualified target boot. Optional post-start
investigation uses `--second` and its two additional gates.

The proposed action loads public Metal, compiles our small shader, initializes
the macOS GPU driver/firmware, allocates its own buffer/queue/pipeline and
submits one tiny compute job. Metal/macOS can update shader caches and logs.
It does not read arbitrary application data or perform filesystem, firmware,
partition, security-policy, bootloader or LaunchDaemon installation writes.
Starting macOS/XNU itself has broader side effects and requires a separate
primary-operator decision under the protected-volume rule. Have independently
verified recovery and the known-good fallback before any experimental boot.

The graphics lane's required capture is endpoint `0x20` APP INIT type `0x81`,
its root pointer, `root+0x18 -> main`, `main+0 -> hardware data`, and the earliest
compute-kick shared state. The helper exposes stage boundaries and its own
known data; the hypervisor tracer must capture/validate those firmware objects.
Record initialization and first-kick state before trying replay. No later GUI
capture or builder success substitutes for that target evidence.
