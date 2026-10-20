# J614s Omarchy integration layer

This experimental layer qualifies an **M4 Pro J614s/T6040** native renderer and
produces a review manifest. It has no installer, package mutation, boot-policy,
partition, reboot, modeset or existing user-configuration operations. It does
not publish M4 support or modify either Omarchy source checkout.

| Item | Status | Evidence |
| --- | --- | --- |
| Native and ARM64 EGL probe builds | WORKS (compilation) | `evidence/build.json` |
| Preflight and package-audit regression tests | WORKS (host tests) | `evidence/unit-tests.txt` |
| Reject nonexistent render node | WORKS (host negative test) | `make check`; exits 1 |
| Existing image Asahi package set | WORKS (metadata comparison) | All 163 requests installed; `evidence/package-audit.json` |
| Live M4 Pro accelerated EGL probe | UNTESTED | Primary hardware operator must run on a qualified experimental kernel |
| DCP/KMS, Hyprland acceleration and physical input | UNTESTED by this layer | Existing framebuffer desktop is not GPU acceleration |
| Persistent installation, update and recovery | BLOCKED | Not authorized here; needs hardware-qualified kernel/display, thermal protection and independently tested rollback |

The previously boot-tested GPU bootstrap reports
`RTKIT_READY protocol=12 rendering=unimplemented`. That is transport evidence
and cannot satisfy this profile. Merely finding `/dev/dri/renderD128` also
cannot pass: vgem can create that node without a native GPU.

## Build and qualify

Dependencies: Python 3.8+, C compiler, pkg-config, EGL and GLES2 development
headers/libraries. Run from this directory:

```sh
make check
python3 j614s_preflight.py --probe evidence/render_probe --capture fresh-evidence.json
```

Run the preflight as the desktop user on the target through the primary
operator. No root is needed; DRM render-node access is needed. It reads root
DT compatibles and CPU sysfs, enumerates DRM render nodes and follows their
kernel driver links. It requires `aarch64`, both `apple,j614s` and `apple,t6040`,
and present/online CPU sets exactly `0-11`. It does not infer the SoC from a
marketing name. Identity, topology and environment guards run **before** the
EGL subprocess: an Asahi-bound node on another board does not authorize GPU
work. Fixture tests mock subprocess execution and assert it is never called
for rejected hardware, missing CPUs, render overrides or inappropriate nodes.

For exactly one `asahi` character render node, the C probe selects the matching
`EGL_EXT_device_drm_render_node` device, creates its own GLES2 pbuffer context,
clears 16 pixels and verifies readback. The result must report Mesa and an
Apple M4 Pro renderer. Missing EGL device support, permission errors, firmware
bootstrap-only drivers, software/virtual renderers, mismatched node identity,
failed readback and rendering overrides all block qualification. No fallback
to a default EGL display is attempted. A clear/readback pass establishes this
small workload only; it does not establish shader, Vulkan, compositor or
display reliability. Rendering overrides are rejected so an earlier llvmpipe
test environment cannot accidentally qualify a later hardware profile.

After a live pass, a **new** review folder can be staged:

```sh
python3 j614s_preflight.py --probe evidence/render_probe --stage profile-review
```

This reruns live collection and writes only `evidence.json` and `profile.json`
inside that new folder, with an evidence digest, exact render node, no actions,
and `release_authorized: false`. It does not change the desktop. Existing
folders are rejected. `--snapshot FILE` evaluates archived fixtures but cannot
stage. The supported fixture is prospective synthetic test data, not an M4
hardware pass. Successful preflight explicitly leaves compositor acceleration
and persistent installation `UNTESTED`.

An ARM64 binary was additionally linked against the existing image sysroot:

```sh
clang --target=aarch64-linux-gnu --sysroot="$SYSROOT" --ld-path="$LD_LLD" \
  -std=c11 -Wall -Wextra -Werror render_probe.c -lEGL -lGLESv2 \
  -o evidence/render_probe-aarch64
```

The binary is a build artifact and is not committed. Its SHA and interpreter
are recorded in `evidence/build.json`. It has not run on the target.

## Actual ARM64 package results

Sources reviewed: official Omarchy commit
`81fd2d23ca6e3462183a4dc8360de3113fa8d80c` and the existing Mac fork/image
commit `72f1906722fd042a54f1e1973610f62dd019531f`. The latter fork is feature
frozen and directs new work to `omacom/omarchy-mac`; it was read as baseline
evidence and not modified.

The immutable September OS image has **986 installed packages**, and all
**163** entries in its `omarchy-base-asahi.packages` are installed under native
ARM64 or architecture-independent metadata, including Hyprland 0.56.2-3,
Mesa 26.2.2-1, and quickshell-git 0.3.0.r20.g28771c7-2. This measures package
presence, not working hardware. Image identity is recorded in
`evidence/image-provenance.json`; the package inventory was extracted from
`/var/lib/pacman/local` with read-only `btrfs restore`, without mounting or
changing the image. Public package keyrings were separately re-extracted for
the signature verification below.

Compared with current official source, the image lacks 18 of 162 base entries,
`zram-generator` from the 2-entry ARM addition, and 4 of 7 Apple additions:
`omarchy-mac`, `avd-fw`, `libva-v4l2_request-avd`, `wf-recorder`.
These are source/image version differences. The captured official Apple ARM64
edge repository metadata has ARM-compatible candidates for all 18 missing base
entries and all five missing architecture/platform entries.

Editor requests now have signed payload evidence:

| Request | Captured ARM64 metadata | Integration action |
| --- | --- | --- |
| `nvim` | Native `neovim` 0.12.6-1 provides `nvim`, confirmed in both the split repository `depends` record and signed `.PKGINFO`; archive contains the native executable. | Review overlay requests canonical `neovim` with exact version/filename/SHA256 and matching signed payload proof. |
| `vi` | Official `extra/ex-vi-compat` 3-1 (`any`) owns executable `usr/bin/vi`, provides `vi`, and depends on Bash/native Vim. Signed wrapper and actual invocation were verified. | Resolve explicitly to `ex-vi-compat` only with matching signed ownership/provider and invocation evidence; Vim package presence alone still fails. |

The earlier desc-only audit missed ALARM's separate `depends` archive member,
where `PROVIDES` and dependencies are stored. The parser now merges both forms
and has a regression fixture. This corrects the earlier apparent `nvim`
repository gap. One unrelated `findnewest-0.3-4/depends` record has no identity
record in the captured extra database: it is explicitly reported and excluded
from candidate resolution. It cannot satisfy a package request.

Further provider inspection corrected the earlier unresolved-`vi` conclusion:
`vim`/`vim-runtime` do lack that path, but the separate official
`ex-vi-compat` package supplies it. The shared index also now searches exact
package names before virtual providers, matching actual pacman print behavior;
for example, `gvim` advertising `vim` cannot shadow the real `vim` package.
Regression tests cover both repositories and the package-plan consumer.

Both editor archives, `vim-runtime`, and `ex-vi-compat` matched repository sizes/SHA256 and
verified with ALARM signer
`68B3537F39A313B3E574D06777193F152BDBE6A6`. The public keyring was re-extracted
from the verified image and matched the existing sysroot byte-for-byte
(SHA256 `6ce771e853f04a38a5b533cb33e61f877b9b06b58b6db051eb8a15d737a2332f`).
The keyring is armored; verification converts it into a binary keyring only
inside disposable inspection storage. No host keyring was imported or changed.
See the extended `evidence/editor-verification-with-vi.json`.

The verified native Vim and Neovim executables both passed `--version` and
scratch-file write/read round trips under the already installed, hash-pinned
`qemu-user-static` 11.1.2-1. `pacman -Qkk` reported 45 files, 0 altered files.
The runner re-verifies archive signatures before extracting only the exact
executable and uses an isolated home and loader prefix; no archive hooks run.
This proves ARM userspace execution under emulation, **not** target hardware
operation or a working `vi` command. See `evidence/editor-execution.json`.

`exercise_vi_provider.py` then invoked the **unchanged signed `/usr/bin/vi`
script** in an isolated user/mount/network namespace. Its hardcoded
`/usr/bin/vim` was mapped only inside that namespace to a QEMU dispatch shim
for the signed native ARM Vim binary. No host executable was installed or
replaced. The wrapper's actual version invocation, `compatible=1`, file
roundtrip, HOME `.exrc`, `EXINIT` precedence and edit/save all passed. It reads
only the fixture files and exposed library roots, with writes confined to its
own scratch bind. The official provider has no install script and explicitly
declares `provides=vi`, `conflict=vi`, `replaces=vi`, and `depends=bash,vim`.
Its archive SHA256 is
`7d5d99f383a190485a868e61bf6522611f0148f805ab7d7f3cd55c17dc6ce8e5`.
This validates the existing provider, without creating a replacement package
or signing key. Target-native invocation remains untested. See
`evidence/vi-execution.json`.

```sh
python3 verify_editor_packages.py --include-vi-provider --database fresh-repositories/extra.db \
  --keyring EXTRACTED/usr/share/pacman/keyrings/archlinuxarm.gpg \
  --output editor-inspection
python3 exercise_editor_payloads.py --payloads editor-inspection \
  --sysroot "$SYSROOT" --output editor-emulation
python3 exercise_vi_provider.py --payloads editor-inspection \
  --sysroot "$SYSROOT" --output vi-emulation
```

`arm_package_plan.py` provides a clean request-resolution overlay without
editing either upstream package list. Its captured plan has **167 exact
ARM-compatible request candidates**, **4 held requests**, **0 unresolved requests** and
**20 protected installed-image package pins**. Every candidate includes its
repository, version, architecture, exact payload filename and SHA256. Unknown
requests stay explicit failures; unverified or stale editor proof cannot
resolve `nvim` or `vi`. Non-executable wrapper metadata, mismatched backend
hashes, missing actual invocation evidence or failed compatibility checks
cannot resolve `vi`. Tests cover protected provider aliases and exact names.

Kernel/header, firmware, m1n1/aura, U-Boot, bootloader/hooks, system identity and
graphics ABI packages are held. The current held source requests are
`omarchy-mac`, `omarchy-mac-boot`, `asahi-bless` and `avd-fw`. Existing package
versions and local-description digests are preserved in the plan. These are
**image** pins, not claims about the active experimental kernel or current
target state. Protected dependencies and reverse dependencies still need a
real isolated dependency/conflict/hook review before any deployment.

```sh
python3 arm_package_plan.py --database EXTRACTED/var/lib/pacman/local \
  --editor-proof editor-inspection/inspection.json \
  --vi-execution vi-emulation/vi-execution.json \
  --repository omarchy=fresh-repositories/omarchy.db \
  --repository asahi-alarm=fresh-repositories/asahi-alarm.db \
  --repository core=fresh-repositories/core.db \
  --repository extra=fresh-repositories/extra.db \
  --repository alarm=fresh-repositories/alarm.db \
  --repository aur=fresh-repositories/aur.db \
  SOURCE/install/omarchy-base.packages SOURCE/install/omarchy-aarch64.packages \
  SOURCE/install/omarchy-aarch64-apple.packages
```

`evidence/arm-package-plan.json` deliberately remains `BLOCKED`,
`deployable: false`, with no actions or install command. It is an exact request
review plan, **not a solved pacman transaction**. Full dependency closure,
conflicts, complete package signatures, live hardware baseline and update-hook
behavior remain unverified. It authorizes neither a full upgrade nor a reboot.

### Isolated pacman print resolution

`resolve_package_review.py` additionally ran the real host pacman in
**print-only** mode against copies of the captured ARM repositories and
installed-image database, with its own root/cache/log/keyring directories and
non-routable repository URLs. It verifies repository hashes/order and every
protected baseline pin before invoking pacman. It never refreshes databases,
downloads packages, installs, runs hooks or requests a full upgrade.

The actual resolver exited **0** and produced **117 exact transaction
packages**, including **16 dependencies** beyond the requested candidate names;
**66 direct requests** were already installed at their reviewed version. Every
printed entry matched its repository/version/filename/SHA256. No protected
package was selected. Unknown/mismatched entries or a protected dependency
would reject the result. Changed repository or protected baseline metadata is
covered by tests asserting the pacman subprocess is never started.

```sh
python3 resolve_package_review.py --review REQUEST_REVIEW.json \
  --database EXTRACTED/var/lib/pacman/local \
  --repository omarchy=fresh-repositories/omarchy.db \
  --repository asahi-alarm=fresh-repositories/asahi-alarm.db \
  --repository core=fresh-repositories/core.db \
  --repository extra=fresh-repositories/extra.db \
  --repository alarm=fresh-repositories/alarm.db \
  --repository aur=fresh-repositories/aur.db --output print-review
```

This improves dependency evidence for the **non-protected subset** only. The
complete original request remains blocked: four boot/firmware requests were
held, not silently installed or removed. Package payload signatures for the
other 113 transaction packages, installed hooks, live target compatibility
and recovery remain unverified. The four editor/provider payloads were
verified separately and are all in this proposed desktop transaction.
The print result therefore keeps `deployable: false`, no actions
and no install command. See `evidence/pacman-print-resolution.json`.

Other image differences have concrete native paths: current `mise-bin` now has
an ARM64 build and provides `mise`; current `quickshell` has a native package.
The historical package-parity document's blanket x86-only `mise-bin` claim is
outdated relative to this captured metadata. Its older "no Apple Limine"
statement also disagrees with the current Apple package list; current source
and exact image metadata take precedence.

**Do not run `omarchy update` or a general `pacman -Syu` as this bring-up's
integration step.** Current repository metadata supplies `linux-aurora`
7.2.10.aurora1-2 and `aura` as the `m1n1`/`m1n1-aurora` provider. That is not
evidence those binaries support this M4 Pro or preserve its known-good boot
object. `omarchy-mac`/`omarchy-mac-boot` also introduce boot dependencies and
hooks. Qualify exact artifacts and dependency transactions in an isolated
root before any deployment; boot-sensitive changes need the primary
operator's recovery gate and separate authorization. Audio packages alone do
not authorize enabling unqualified speakers.

To refresh analysis without installing anything:

```sh
python3 fetch_repository_metadata.py fresh-repositories
python3 package_audit.py --database EXTRACTED/var/lib/pacman/local \
  --repository omarchy=fresh-repositories/omarchy.db \
  --repository asahi-alarm=fresh-repositories/asahi-alarm.db \
  --repository core=fresh-repositories/core.db \
  --repository extra=fresh-repositories/extra.db \
  --repository alarm=fresh-repositories/alarm.db \
  --repository aur=fresh-repositories/aur.db SOURCE/install/omarchy-base.packages
```

Repository order matches the official `default/pacman/aarch64-apple/`
configuration. Databases were read over HTTPS and hashed; they are metadata
analysis, not verified package signatures or a resolved dependency transaction.
No current public package candidate proves the missing M4 driver support.

## Next executable integration action

After the primary operator has a recoverable Linux session with an actual
Asahi render node, copy only the ARM64 probe and Python preflight into RAM and
run the capture command above. Preserve a rejection as evidence; do not weaken
the checks to admit llvmpipe or the bootstrap module. A passing result allows
staging the review manifest, followed by compositor/DCP, thermal and input
qualification. Persistent boot remains a separate gate.
