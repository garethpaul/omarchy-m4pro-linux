# Pinned transaction payload and hook audit

This lane inspects the 117-package, print-only transaction from C commit
`4941c67dbab65ec9bd903c337863c10a51741542` (central integration `46294f6`).
It never installs packages, invokes payloads or hooks, starts services, mounts an
image, changes a disk, or accesses the M4 target. The four previously qualified
editors are reverified together with the remaining 113 packages.

The auditor refuses changed parser/plan bytes, changed repository DB identities,
protected boot/system/graphics package selections, identity/architecture drift,
unsafe paths, SHA/size mismatches, bad/expired/revoked signatures and retained
revocations. Missing public keys and missing trust evidence remain failures.
Public keys are taken from the checksum-qualified retained OS image. `gpgv`
cryptographic success is recorded separately from membership in the image's
explicit `-trusted` anchors: no host trust database, keyserver retrieval, newly
invented local signing, or single-signer assumption is used. This does not
recreate the live target's pacman trust database.

All package payloads, signatures and restored image data remain in ignored
`.private/`. Embedded signatures come from exact pinned repository DBs; where
PGPSIG is absent, the detached `.sig` is fetched from the pinned payload URL and
verified against that payload. Repository payload SHA is required independently
of PGP. Failure does not silently select a different package/version/repository.

## Reproduce on the development host

Run from this worktree root, with C's namespace present and unchanged. The
snapshot output must be a new disposable directory; choose a fresh path when
repeating extraction, then pass that same path to the auditor:

```sh
python3 packages/prepare_image.py \
  --image ../omarchy-arm-payload/root.img \
  --output packages/.private/image-snapshot
python3 packages/audit_transaction.py \
  --source ../overnight-omarchy/omarchy \
  --cache packages/.private \
  --image-hooks packages/.private/image-snapshot \
  --output packages/evidence/transaction-audit.json
python3 -m unittest discover -s packages/tests -v
python3 packages/qualify_pinned_plan_guards.py \
  --source ../overnight-omarchy/omarchy \
  --output packages/evidence/pinned-plan-negative-tests.json
python3 packages/qualify_real_signature_failures.py \
  --source ../overnight-omarchy/omarchy \
  --cache packages/.private \
  --audit packages/evidence/transaction-audit.json \
  --output packages/evidence/real-signature-negative-tests.json
```

`prepare_image.py` verifies the full retained image's fixed size/SHA256, then uses
read-only `btrfs restore -r256` with narrow path selection. It extracts hook and
public keyring data plus first `Exec` argv files solely for static inspection.
The audit verifies the restored manifest and that C's keyrings equal the actual
image extraction. Shell text is never interpreted. First-argv inspection is not
a recursive call graph: shell commands, binary behavior and downstream helpers
remain unqualified. Image identity comes from C's signature-qualified source
catalog and ZIP provenance, retained in `omarchy/evidence/image-provenance.json`.
This baseline is an immutable September image, not live target metadata.

## Recorded result

PARTIAL: **115/117** payloads pass exact pinned size/SHA, signed identity and
retained-anchor verification, including the four editors; **111/113** newly
requested payloads qualify. Signers differ: 80 use ALARM
`68B3537F39A313B3E574D06777193F152BDBE6A6`; 35 use Omarchy
`40DFB630FF42BCFFB047046CF0134EE680CAC571`. The exact marisa 0.3.1-1 and
graphicsmagick 1.3.49-2 URLs return 404. The bounded alternate official-mirror
check fails TLS hostname validation; checks were preserved.

Static data inspection covers 16 `.INSTALL` files, five packaged hooks and
60 baseline hooks (59 effective after the `/etc` override). Plymouth's incoming
`usr/lib/initcpio/install/plymouth` and `plymouth-shutdown` paths match both
`/etc/pacman.d/hooks/90-mkinitcpio-install.hook` (limine-mkinitcpio-install) and
`91-omarchy-mac-boot-initramfs.hook` (mkinitcpio install). The package-name guard
alone does not contain boot effects. No hook was executed or disabled.

The broad Omarchy Upgrade/* guard runs on upgrades, but its actual script rejects
`-Syu` specifically; it exits for ordinary package-only transactions. Its presence
is not an unconditional failure. Other scripts include real setcap and conditional
service-enablement operations; absence of boot keywords does not qualify them.

Evidence: [summary](evidence/summary.json), [complete audit](evidence/transaction-audit.json),
[17 unit tests](evidence/tests.log), [actual PGP negative controls](evidence/real-signature-negative-tests.json),
[actual pinned-plan controls](evidence/pinned-plan-negative-tests.json).

## Hook limitations and installation gate

`.INSTALL` and packaged hooks are read as bounded regular-file data from the
verified archives. Baseline hook directory overrides are applied by basename;
`/etc` wins and `/dev/null` masks are retained. Incoming selected package/path
trigger matches are reported, distinguishing Install from Upgrade using the
image local database. This is not libalpm transaction execution. Old removed
upgrade paths, runtime hook dependencies, ordering/failure effects and service
state are untested. Package-provided new hooks are inventoried, but not simulated
as an authoritative libalpm execution plan. A script with no suspicious text is
not certified safe.

The result always keeps `deployable:false`, `execution_ready:false` and `actions:[]`.
`boot_effects` records each matched effective hook SHA, Exec and incoming package
path; `execution_blockers` preserves those effects independently of name holds. Payload verification
cannot authorize protected boot selections, satisfy held requests, establish
recovery, or qualify the resulting system. Broad pretransaction guard hooks and
boot-generating hooks require independent transaction/recovery qualification.

## Attribution

Reuses C's `package_audit.repository_records` and `arm_package_plan.protected`
from the exact pinned commit, without copying or modifying those files. The
existing editor verifier provided the metadata/signature inspection pattern;
this audit adds per-signer anchor evidence, complete transaction pinning and
static hook inventory. Public package scripts/hooks in evidence retain their
original text and provenance; no vendor firmware or raw ADT is included.

The separate `check_official_mirrors.py` makes one bounded alternate check for
only the observed marisa/graphicsmagick failures, using the same pinned metadata,
SHA, architecture and signature rules. It preserves primary failures and never
refreshes metadata or selects a substitute. The alternate hostname is the
[official ALARM GeoIP mirror](https://archlinuxarm.org/about/mirrors); TLS
validation remains enabled. Reproduce after the main audit with:

```sh
python3 packages/check_official_mirrors.py \
  --source ../overnight-omarchy/omarchy \
  --audit packages/evidence/transaction-audit.json \
  --cache packages/.private/alternate \
  --output packages/evidence/official-mirror-checks.json
```

## Supplemental official-route exhaustion

`exhaust_official_mirrors.py` follows the [current official mirror page](https://archlinuxarm.org/about/mirrors),
its linked JavaScript and documented AJAX mirror list, and the HTTP Download
protocol published on the [marisa](https://archlinuxarm.org/packages/aarch64/marisa)
and [graphicsmagick](https://archlinuxarm.org/packages/aarch64/graphicsmagick)
pages. It checks the SAME two original filenames and hashes across all 12
published mirrors plus GeoIP. Current package pages still use `aarch64/extra`
and show newer release numbers; those new payloads are never requested.

**BLOCKED:** all 26 exact-file requests returned HTTP 404; no payload was
recovered. GeoIP HTTP works and redirects to the New Jersey mirror, so the
previous HTTPS certificate failure was not the only obstacle. There is no
evidence of category migration. The measured external blocker is absence of
these two exact immutable payloads at every currently documented mirror route.
An external archived copy satisfying BOTH original SHA and retained-key PGP
verification is required to complete this fixed plan. This does not establish
that no private or historical archive exists.

The supplemental result preserves hashes of the original audit/failure evidence;
it never changes that evidence or the plan. Every recovered candidate, if one
becomes available, must pass the original embedded signature, a freshly fetched
detached signature, signed architecture/identity and exact SHA/size checks.
HTTP is used as officially published transport with those checks intact; TLS
checks are never disabled. No installation, hooks, services or target access.

```sh
python3 packages/exhaust_official_mirrors.py \
  --source ../overnight-omarchy/omarchy \
  --cache packages/.private/exhaustive-mirrors \
  --output packages/evidence/exhaustive-official-mirror-checks.json
```

Evidence: [26 route outcomes](evidence/exhaustive-official-mirror-checks.json),
[20 passing tests](evidence/supplemental-mirror-tests.log), including real
loopback HTTP 404, oversized response and wrong-SHA refusal before PGP handling.
