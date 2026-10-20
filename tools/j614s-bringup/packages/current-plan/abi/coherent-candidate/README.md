# Separate frozen candidate: Qt, SONAMEs and native formatters

**PARTIAL.** Attempt03 resolves the original 117 transaction's24 newly
introduced bounded ELF dependency issues. Its151 exact signed packages pass
payload identity, retained-keyring PGP and signed `.PKGINFO` comparison. Normal
libalpm preparation accepts those 151 exact targets and the same four explicitly
hypothetical removals. The removal-aware filesystem model reports zero newly introduced
issues across 14734 direct dependency edges and 310 untouched reverse consumers.
This does not establish runtime ABI or installation safety. No package was
installed, no package payload/hook was executed and no target was accessed.

## Scope and attempts

The original 117 proposal, payload qualification and all 986 baseline descriptions
remain unchanged. All 20 protected installed pins and four held requests remain
unchanged. This is an additional candidate, never a broad system upgrade.

| Evidence | Result |
| --- | --- |
| `evidence/proposal.json` and `attempt-01-failure.json` | BLOCKED: first closure needs an exact coupled update of `gnome-desktop-4` alongside `gnome-desktop-common`. Resolver failure retained. |
| `attempt-02/` | PARTIAL:145 signed packages, normal145-target/four-removal preparation; six residual static edges. |
| `attempt-03/` | PARTIAL:151 signed packages, normal151-target/four-removal preparation; zero new bounded static edges. |

The first additions address the actual Qt private-symbol failures, missing
incoming SONAME providers, and native `shfmt`/`stylua` dependencies for the
separately authorized source candidate. Actual preparation/ELF evidence then
requires seven exact coupled updates/providers beyond that first request set:
`gnome-desktop-4`, `openjph`, `opencv`, `libtiff`, `unixodbc`, `freetds`, `assimp`.
Transitive resolution adds only rows selected from the same six frozen databases
in the original repository order. All original 117 selected rows are retained
byte-for-byte; final selection adds 34 rows and changes/removes none of those117.
Every new explicit request and its reason is in `extra_canonical_requests`.

Attempt02's six residuals are preserved rather than hidden:

| Actual consumer | Missing dependency | Attempt03 action |
| --- | --- | --- |
| new OpenEXRCore | `libopenjph.so.0.32` | exact `openjph` provider |
| retained OpenCV image codecs | old `libOpenEXR-3_4.so.33` | coupled `opencv` rebuild requiring new `libOpenEXR-3_5.so.34` |
| retained libtiff | old `libjbig.so.2.1` | coupled `libtiff` rebuild requiring new `libjbig.so.2.2` |
| new Qt5 optional ODBC SQL plugin | `libodbc.so.2` | exact `unixodbc` provider |
| new Qt5 optional TDS SQL plugin | `libsybdb.so.5` | exact `freetds` provider |
| new Qt6 optional Assimp asset plugin | `libassimp.so.6` | exact `assimp` provider |

`crosscheck_closure.py` independently reads twelve actual AArch64 ELF files with
GNU readelf, comparing machine, NEEDED, SONAME and version nodes against our
parser. This includes before/after OpenCV and libtiff files, exact signed archive
members for the providers and the two new optional plugin consumers. The twelve
real-file hashes and contracts are retained in `attempt-03/readelf-crosscheck.json`.
A one-byte mutation of a reused extracted OpenCV file is rejected by the actual
CLI before readelf; exact original bytes are restored in `finally`.

## Exact authority and provenance

`propose_candidate.py` uses the unchanged pinned original resolver/parser source,
the current117 qualified inputs, same frozen repository bytes and original
protected predicate. It independently verifies the fixed full986-description
baseline. It never refreshes repositories or sources a PKGBUILD. It records its
own SHA and the exact unsigned nvim source commit/PKGBUILD SHA.

The unchanged `qualify_payloads.py` qualifies each separate candidate's entire
selected set. Attempt03's qualification records151/151 successful exact size,
SHA, PGP and signed metadata checks, against only retained image trust anchors.
It reuses145 prior exact content-addressed payloads and retrieves six additional
signed payloads. Metadata database authentication/freshness remains explicitly
unproven as in the original audit; individual payload signatures and identities
are verified. No new trust key or signature bypass is used.

`transaction/prepare.py` performs normal dependency/conflict/architecture checks
in a private metadata-only database with flags139264 (`NOLOCK|NEEDED`). It has no
transaction-commit call or payload-execution path. It verifies every copied
baseline description against the immutable full986 qualification before and
after preparation. The exact hypothetical removals are unchanged:
`dotnet-host`, `dotnet-runtime`, `mise`, `quickshell-git`. No protected item changes;
there are no download attempts or unexpected questions. These answers authorize
only the offline scenario, not real removals.

`transaction/model.py` independently validates the sealed actual image tree,
all 986 descriptions and complete preparation identity. It removes paths owned
by actual prepared removals and same-name replacements, then models incoming
files. Every payload byte hash is rechecked on cached replay. Final evidence has
zero incoming-file or retained-owner path collisions. This remains a virtual
model, not libalpm's install-time file-conflict test.

Reproduce from the task directory using the established paths:

```sh
python work/overnight-package-abi/packages/current-plan/abi/coherent-candidate/propose_candidate.py \
  --source work/overnight-omarchy/omarchy \
  --current work/overnight-cpu/packages/current-plan \
  --nvim-source work/overnight-omarchy-pkgs \
  --private work/overnight-package-abi/packages/current-plan/abi/.private/new-candidate \
  --output work/overnight-package-abi/packages/current-plan/abi/.private/new-candidate-evidence \
  --extra-canonical 'gnome-desktop-4=direct coupled reverse dependency on gnome-desktop-common exact version' \
  --extra-canonical 'openjph=new OpenEXRCore requires libopenjph.so.0.32' \
  --extra-canonical 'opencv=retained imagecodec requires replaced OpenEXR3_4 SONAME' \
  --extra-canonical 'libtiff=retained libtiff requires replaced JBIG2.1 SONAME' \
  --extra-canonical 'unixodbc=new Qt5 SQL plugin requires libodbc.so.2' \
  --extra-canonical 'freetds=new Qt5 SQL plugin requires libsybdb.so.5' \
  --extra-canonical 'assimp=new Qt6 assetimporter requires libassimp.so.6'
```

Fresh output/private directories are required. Qualify the resulting exact
proposal using the unchanged qualifier, then use the existing prepare/model
CLIs with the separate four-removal scenario. Evidence binds every argument's
input bytes. Intermediate malformed import-path/file-read invocations produced
no qualified result and are not counted as passes. Private full diagnostics and
all vendor bytes stay outside tracked files. `EVIDENCE.json` binds public files.

## Remaining gates

* **BLOCKED:** unsigned `omarchy-nvim2026.9.21-6` is only a source placeholder,
  pinned to commit `e8f5edeabdaa0efe30760f47bc5c93467ac45490` and PKGBUILD SHA
  `4a03f84d600c70e5b74893ee5d2ec461701ae9e07d470f97daaa4e59b13cd4c8`.
  It is not built/signed/released or substituted into the151 signed rows.
  Official signed `2026.9.21-5` remains, with the previously documented dormant
  x86_64 Mason asset. Native `shfmt3.14.1-1` and `stylua2.6.0-1` are signed
  AArch64 candidate dependencies; their presence does not remove that asset or
  migrate an existing user profile.
* **PARTIAL:** final 1582 incoming ELFs include 1581 AArch64 files and that one
  dormant x86_64 template resource. Final 9701 modeled ELFs retain 57 pre-existing
  issue edges. The expanded OpenCV/libtiff reverse-consumer scope exposes more
  baseline issues than the145 model's 37; all are preserved with before/after
  evidence. Optional plugin dependencies are not suppressed.
* **PARTIAL:**344 Guile VM ELF objects (machine0/OSABI255) remain parse gaps;
  they are not native AArch64 executable-format parser successes.
* **UNTESTED:** unversioned symbol completeness, structure/calling conventions,
  dlopen, scripts, CPU instruction support, inherited RPATH/global-loader scope,
  cache/hwcaps selection, and runtime behavior. Selected direct GNU versioned
  contracts passing cannot qualify full ABI.
* **BLOCKED:** real package removals, install-time file conflicts, removal-hook
  operation matching and hook/script execution. Incoming Plymouth still matches
  the recorded Limine lock and two initramfs generation hooks. None is disabled
  or executed. Removed packages have no stored local install script; this does
  not establish hook safety.
* **BLOCKED/UNTESTED:** original protected boot requests, tested recovery,
  hardware acceptance, actual installation and persistent native boot. This lane
  makes no target or boot-policy changes.

The next package gate is an isolated hook/file-conflict/runtime validation with
tested recovery and explicit target authority, plus a real signed nvim source
build. Zero new static edges is evidence for this candidate only.
