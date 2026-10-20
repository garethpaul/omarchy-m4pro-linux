# Gravity stack port: first compute job

The target remains one source-built compute job with an independently checked
output buffer on J614s. A renderer or desktop is a later acceptance step.
This checkpoint adapts the descriptor envelope in Gravity's existing driver;
it does not replace its VM, scheduler, DRM UAPI or compute submission stack.

## Implemented and compiled

Gravity kernel base: `4fc326f6c25ccceb7515e2635c22e01fde5d3bac`.
Candidate kernel commit: `db9f2f8f00986e3ef03fddbdaad55a861e793123`, branch
`agent/t6040-g16s-abi`. Only `drivers/gpu/drm/asahi/g16_fw.rs` changes.

- `RootPointers::encode_interface` explicitly selects the current 25G83 root
  interface. Existing `encode()` retains its original output byte for byte.
- `MainConfig::encode_g16s_26_6_2` reuses Gravity's established header/channel
  serialization, then writes the measured G16S main offsets from explicit
  caller-supplied pointers. No defaults pretend that a legacy hardware bundle
  is a valid T6040 bundle. The opening record remains at its existing boundary;
  a blind eight-byte shift of the complete object would move it incorrectly.
- No runtime caller selects the new methods. GPU identification, firmware,
  platform and compatibility checks remain unchanged. Hardware-data and power
  contents are still unqualified. This is an envelope port, not an enabled
  T6040 hardware profile or a sendable initialization graph.

`run-gravity-port-replay.py` compiles the actual old and candidate Rust source,
not a duplicate model. It verifies bit-identical legacy root/main output and
passes the new envelope output through the existing C decoders. The pointer
fixture is synthetic; both inspector outputs explicitly reject a hardware
qualification or permission to publish INIT. `gravity-port-result.json` records
source hashes and results. The complete `asahi_m4` AArch64 crate also compiled in the isolated build lane;
`gravity-crate-result.json` records the object and all layout checks. Its source
snapshot removes the upstream `--no-layout-tests` flag, retaining 3,170 layout
blocks and 16,284 field-offset checks with qualified bindgen. The three unused
candidate-method warnings correctly reflect that runtime callers remain closed;
no warning suppression was added to that kernel build. Module linking, firmware
execution and target boot remain UNTESTED.

```sh
make -C graphics all test
python3 graphics/run-gravity-port-replay.py --kernel-source /path/to/candidate-kernel --output graphics/build/gravity-port --root-inspector graphics/build/g16s-inspect --main-inspector graphics/build/g16s-main-inspect
```

`gravity-g16s-envelope.patch` exports the candidate source change with zero
context; use its recorded base or the actual kernel commit for integration.

## Corrected interpretation of the upstream mismatch

The exact same 25G83 restore contains G16G J700 and G16S J614s firmware. Both
G16G B1 (`b100`) and G16S (`b000`) require the current root interface
`[04c0, 0396, a322, 0c8a]`. The G16G B0 slice was also inspected and agrees.
Therefore the legacy Gravity serializer mismatch is **not evidence of a
G16G-versus-G16S root ABI difference**. It indicates source/firmware contract
drift in the inspected source path; it does not prove that every published
working stack or replay environment fails.

The actual kernel call path was checked: `g16_power::Platform::bundle()` uses
`MainConfig::bootstrap(...).encode()`, and `g16::Boot::new()` writes
`RootPointers::bootstrap().encode()` before the eventual endpoint-0x20 INIT.
No root-version override or firmware substitution was found in that direct
kernel path. The examined loader's T8132 handoff transfers firmware-reserved
regions and firmware metadata; it is not evidence of a substituted payload.
Other capture/replay worlds can have different retained state and must be
qualified by their own exact firmware and capture identity.

`compare-same-build-interfaces.py` checks the private same-build views and
exports only constants, component hashes and derived facts in
`same-build-interface-result.json`. Root ABI equality does not establish body,
power or GPU-job format equality across variants.

## Reused sources and capture boundaries

- [Gravity kernel](https://github.com/GravityLinux/linux/tree/4fc326f6c25ccceb7515e2635c22e01fde5d3bac): full G16 VM, compute and DRM implementation; this is the selected base.
- [Gravity Mesa](https://github.com/GravityLinux/mesa): the parallel userspace lane verifies matching UAPI and prepares a source-built shader/launcher/CDM fixture.
- [Niklas userspace experiments](https://github.com/niklassheth/agx-re/tree/e25433b1d348a809ab86484ce149ff7d459e8cdf): contains a documented T8132 25G83 Mesa/shim render checkpoint. That result is for T8132, not T6040, and does not supply a J614s initialization capture.
- [Published bring-up branch](https://github.com/ADevWithAnIdea/m1n1/tree/7f42520f39c55eedbb47d990d8eab7bf5569829c): early pre-init, pre-run and minimal-compute capture/replay tools. Its inspected examples target G17P; dual-coprocessor assumptions cannot be imported into G16S blindly.

No T6040/J614s firmware capture was located in the narrowly inspected public
bring-up paths. This is a bounded source-inspection result, not a claim that
none exists anywhere. The public userspace experiment repositories explicitly
separate their work from the firmware/kernel layer.

The capture plan should observe APP INIT and the earliest compute kick, with
one small buffer and a source-built constant/XOR shader. The integration lane
prepares explicit gates before device creation and before commit, independent
readback checks, and an optional second submission for later post-startup
handshake testing. Neither that trigger nor this port installs a daemon or
boots a protected volume.

## Remaining concrete gap

Before the first actual job, qualify T6040's initialization body and power
inputs, UAT publication and application handshake against the earliest coherent
capture. Reuse Gravity's existing compute path and matching Mesa job builder
once those inputs are established. Acknowledged work without changed output
is a failure; the acceptance evidence must include a completed fence/status,
exact output bytes and absence of unexpected writes to guarded regions.

Source provenance includes public open-source implementations **and private
vendor-firmware analysis performed in this project**. No clean-room provenance
is claimed for this port. Original source license and copyright notices remain
intact. Vendor firmware, raw ADTs and assembly listings are not included.
