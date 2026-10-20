# Offline package ELF/ABI audit

**PARTIAL. The separate signed117-package proposal is not safe to install.**
This lane reads exact signed payload bytes and the immutable986-package image,
constructs a virtual package-file overlay, and checks ELF contracts without
installing, loading or executing those files. Package signatures remain the
separate current-plan audit's evidence; this auditor rechecks every payload's
size/SHA and binds that qualification's hash, without inventing new trust.

The scan covers1256 incoming ELFs (1255 AArch64, one dormant x86_64),
9308 parsed baseline ELFs and328 untouched reverse consumers across12,596
direct edges. It finds24 new/incoming issue edges (eight Qt private-symbol
contracts plus16 unresolved direct SONAME edges), with52 pre-existing issue
edges retained separately.344 Guile VM ELF gaps are classified explicitly.

The concrete blocker is partial Qt replacement. Selected Qt6.12.0 removes
`Qt_6_PRIVATE_API` symbols required by eight untouched6.11.2 consumers owned by
`qt6-networkauth`, `qt6-positioning`, `qt6-speech`, `qt6-webchannel` and
`qt6-multimedia-ffmpeg`. Independent GNU readelf confirms each required UND
symbol exists in the retained provider and is absent from the new provider.
This is static evidence of incompatible symbol contracts in the modeled
filesystem, not a claim that a particular hardware/runtime path was run.

The incoming packages also require newer SONAMEs than retained dependencies:
for example Evince needs `libgnome-desktop-3.so.21` rather than retained20,
`gvfsd-nfs` needs `libnfs.so.17` rather than retained16.2.0, and libvips needs
OpenEXR3_5.so.34 rather than retained3_4.so.33. Other unresolved edges belong to
plugins or optional features; the report records every exact consumer and does
not infer that every entry point in each package fails.

The architecture=any `omarchy-nvim` archive embeds a single x86_64 shfmt ELF
under `/etc/skel`, its Mason symlink and an amd64 receipt. Its stored mode is
0644. This is dormant new-home template data, not evidence that an existing
account runs foreign code. It remains an ARM compatibility defect candidate.

## Method and boundaries

The provenance repair re-extracted a fresh restore after review found the
initial cache key omitted restore identities and auditor source. An actual
archived-code replay reproduced a stale cached SHA after modifying a separate
restore copy. The current CLI refuses a one-byte mutation in its own sealed
QtCore file; restoring the exact original bytes and replaying gives a
byte-identical static report. A changed reused Qt provider is also refused
before generating proof. See `cache-before-fix.json`,
`cache-mutation-refusal.json`, `cache-replay.json` and
`provider-mutation-refusal.json` in evidence.

The image SHA is
`f6ceb11ef79914eaa10cc07637c929a99afe5982d216d8b89905c86e863b2491`,
14344519680bytes, Btrfs root256. `btrfs restore` reads only `usr/bin`, `usr/lib`,
`usr/libexec`, `opt`, loader configuration and pacman metadata into a new
ignored directory. No mount occurs. Archive members are never extracted by
`extractall`: only ELF regular-file data is parsed, and links are interpreted
inside an in-memory virtual filesystem. Traversal, loops and special package
entries fail closed. All package files owned by selected baseline packages
are removed from the virtual overlay before incoming files are applied.
This first model removes same-name packages only. Name-changing conflicts
(`dotnet-host-bin`/`dotnet-host`, `mise-bin`/`mise`,
`quickshell`/`quickshell-git`) are explicitly unresolved in the classification.
The overlay is not the final intended transaction filesystem; actual removal
semantics still require separate preparation. The exact untouched Qt proof
does not depend on these aliases.

The ELF64 little-endian parser checks architecture, direct DT_NEEDED/SONAME,
local RPATH/RUNPATH, version definitions, required version nodes and versioned
strong imports. Symbol lookup includes the recursively resolved dependency
closure. This matters because modern glibc's libc exports symbols originally
version-bound to its libpthread/libdl compatibility libraries. A direct-provider
check alone produces false failures; a real compiled ELF regression covers
this case. Names removed from old providers are also retained as review candidates.
That name-only intersection can include versioned imports already checked
above; unversioned imports do not encode their provider provenance.

This is **not full dynamic-loader emulation or runtime ABI qualification**.
It omits inherited RPATH, ld.so.cache/hwcaps, preloads/environment, application
global namespaces, relocations/interpreter validation, dlopen/plugin selection,
calling conventions, structures, CPU instructions and semantic changes. All
incoming ELF regular files are scanned; untouched baseline files outside the
restored directories are outside scope. Guile machine0/OSABI255 VM ELF objects
use unsupported dynamic metadata and are explicitly classified as unqualified
VM data, rather than passed as native binaries. BPF and other non-host ELF data
are not treated as native ARM applications.

**BLOCKED:** actual installation, unchanged initramfs-generating hooks, protected
boot/system/graphics holds, live hardware, known-good recovery and runtime ABI.
All evidence retains `deployable:false`, `execution_ready:false`, `actions:[]`.
No target, KVM, USB, SSH, watchdog, services, hooks, install scripts, package
programs, ld.so, ldd or QEMU are used.

## Evidence

- `evidence/static-abi.json`: hash-bound overlay, counts, all new/incoming and preserved direct-edge issues, exact versions, parse/resolution gaps.
- `evidence/qt-private-abi.json`: eight exact before/after consumer/provider readelf proofs.
- `evidence/readelf-crosscheck.json`:13 actual AArch64 shared libraries from the four changed pins and retained baseline; parser/readelf agree on machine, SONAME, dependencies and version nodes.
- `evidence/classification.json`: Guile VM gaps, dormant x86_64 asset, signed dependencies and optional dependencies for unresolved direct edges.
- `evidence/tests.log`: real compiled fixture and virtual-root guard regressions. Raw red-phase traces and all image/payload bytes stay private.

## Reproduce

Use the existing frozen current-plan qualification and payload cache. The paths
below are relative to this lane worktree and name sibling read-only evidence.
The restore destination must be new; do not overwrite a retained snapshot.
An old unsealed restore is deliberately refused. The extractor seals every
regular file byte identity, directory and link with its source/helper hashes.
Each replay rehashes that actual tree and the original image. Parse caches
are data-only gzip JSON with independent integrity checks; immutable keys
bind parser, auditor, sealed manifest, tree and qualification identities.

```sh
python3 packages/current-plan/abi/restore_image.py \
  --image ../omarchy-arm-payload/root.img \
  --output packages/current-plan/abi/.private/image-verified-01
python3 packages/current-plan/abi/audit_plan.py \
  --image ../omarchy-arm-payload/root.img \
  --restore packages/current-plan/abi/.private/image-verified-01 \
  --qualification ../overnight-cpu/packages/current-plan/evidence/configured-current-payload-qualification.json \
  --payload-cache ../overnight-cpu/packages/current-plan/.private/payload-cache \
  --private packages/current-plan/abi/.private \
  --output packages/current-plan/abi/evidence
python3 -m unittest discover -s packages/current-plan/abi/tests -v
```

The optional independent `crosscheck_readelf.py`, `prove_qt_break.py` and
`classify_findings.py` CLIs accept the same private restore/cache and public
evidence inputs (`--help` describes paths). They only run the trusted host's
readelf against data files. No package code is executed. Cached parser data
stays ignored and cannot be silently overwritten. Sidecar SHA checks run
before JSON decoding. Baseline and incoming cache keys include auditor and
parser hashes; the baseline also binds the validated sealed restore. The
original image, actual restore contents and all payload bytes are checked on
replay. This detects accidental changes while the recorded seal is retained;
it is not an authenticated defense against someone replacing both data and
all local provenance records.
