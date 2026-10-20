# Normal dependency/conflict preparation, without installation

**WORKS within metadata preparation:** the exact signed 117-package set can be
prepared by the installed host libalpm 16.0.1 with dependency and package-conflict
checks enabled, under an explicit hypothetical four-removal scenario. The
private cloned local DB remains byte-identical, all 20 installed protected pins
and four original held requests remain unchanged, no fetch occurs, and the
helper never imports or calls transaction commit, system upgrade or payload
loading. No package code, hooks, scripts or services run.

**BLOCKED as a real installation:** Qt's twelve missing private imports across
eight untouched consumers and 16 unresolved direct SONAME edges remain. The
prepared-removal filesystem model checks 12,596 direct edges, 1256 incoming ELF
files and 327 untouched reverse consumers. Removing the four superseded package
names eliminates every retained-owner path collision in the scanned ownership
metadata. It leaves the same 24 new/incoming static issue edges and 52 pre-existing
issue edges. The dormant x86_64 Mason asset also remains in the signed original
package. File-conflict preparation at commit time, removal-hook matching,
runtime ABI and the original boot/hook/recovery gates remain unqualified.

## Full baseline binding

The original preparation captures checked 20 protected descriptions and only
proved their entire private DB stayed unchanged during preparation. They did
not establish that every initial non-held description matched the image.
Those captures remain as the weaker initial scope; they are not discarded.

The current wrapper pins the original baseline qualification's SHA
`d63559fc4cad4c7e3974cbc71acaee9ddfc9d1b4b6d67b6eff13e44a17d16eb7`
and checks all 986 directory-name/description-byte identities before copying,
after copying, and after preparation. Its description digest must be
`05592373e5f03cfcfeb32ea3dcf0fb835b307e9e1eae75540e670db36e5e1e7e`.
The model independently recomputes that digest from the actual sealed image
and compares it with the preparation report, including qualification/helper
hashes. This binds dependency/conflict input to the immutable image, beyond
the protected subset.

An actual archived `d6e57f7` wrapper replay accepted a separate copied baseline
whose non-held Neovim description was changed. The current CLI refuses that
same copy before creating its private transaction directory or compiling the
helper. The current model also refuses a changed reported baseline digest.
Three focused actual-file regressions failed before guard implementation and
now pass. Original source/image bytes remain unchanged.

`current117-preparation-04-baseline-bound.json` and
`current117-filesystem-model-baseline-bound.json` are the stronger captures.
They reproduce all 117 adds, four hypothetical removals, and the same 24 new
link issues with no retained-owner path collisions. The earlier preparation
01–03/model files remain historical captures from source `d6e57f7` and have
weaker initial input binding. `baseline-before-fix.json`,
`baseline-mutation-refusal.json` and `model-baseline-mutation-refusal.json`
record the actual before/after controls.

## Why the print proposal omitted removals

The [official pacman 7.1.0 source](https://gitlab.archlinux.org/pacman/pacman/-/blob/5683f8477a0afcc6b331766175a83445b2dcfe89/src/pacman/pacman.c#L1293)
sets NOCONFLICTS and NOLOCK for print mode. The unchanged earlier C resolver
uses that mode safely as a metadata selection, so its successful print does
not establish accepted package removals. `pacman-print-source.json` records the
exact official Git tag/commit and source-file hashes. The installed binary's
version agrees; byte identity with upstream's source is not asserted.

The separate own helper uses only NEEDED and NOLOCK. It calls
[libalpm transaction preparation](https://man.archlinux.org/man/core/pacman/libalpm_trans.3.en),
then releases the transaction. It uses the same Required DatabaseOptional
policy and frozen repository order; signed payload qualification is external
hash-bound evidence, and no payload load or key import occurs. Dependency,
version and conflict checks remain enabled. A download callback refuses any
fetch. Exact repository/name/version inputs are bound to the qualified plan.

The first three-answer scenario fails normally: after the hypothetical
`dotnet-host-bin`/`dotnet-host` answer, libalpm finds the additional signed
`dotnet-runtime-10.0` conflict. The retained `dotnet-runtime` provides that alias.
This is a package conflict even without overlapping versioned file paths.
The failed result and exact input are retained separately. The four-answer
scenario subsequently prepares these exact removals:

| Incoming package | Hypothetical retained removal |
| --- | --- |
| dotnet-host-bin | dotnet-host 10.0.11.sdk400-1 |
| dotnet-runtime-bin | dotnet-runtime 10.0.11.sdk400-1 |
| mise-bin | mise 2026.9.4-1 |
| quickshell | quickshell-git 0.3.0.r20.g28771c7-2 |

Every removal answer is restricted to its explicit new/old pair, requires a
signed conflict against the retained name/provides, and refuses protected
names. Libalpm still applies the full dependency/version semantics. Unknown
provider/key/ignore/skip questions block qualification. These are hypothetical
model answers; they grant no real removal authority.

`current117-preparation.json` is the failed first scenario;
`scenario-current117-01.json` matches its exact input hash.
`current117-preparation-02.json` is the first four-answer success;
`current117-preparation-03.json` repeats it after using Python's keyword-only
`maxsplit` form, preserving its failure-free source hash.
`current117-filesystem-model.json` binds preparation 03 and removes all files
owned by its four exact package names before applying incoming packages.
The earlier same-name-only audit is retained as a distinct scope.

All four removed packages have no stored local install script in the sealed
image metadata. This does not qualify removal hooks. The prior incoming
Plymouth initramfs effects and held boot/graphics requests remain blockers.

## Verification

Six tests use the actual installed libalpm and disposable metadata fixtures:
authorized exact conflict removal, refusal of an unlisted removal, refusal of
a protected removal, refusal of a broken untouched reverse dependency, and
refusal of wrong architecture, and absence of commit/sysupgrade/pkg_load imports. All six pass with ordinary
strict compilation and ASan+UBSan. The real 117 preparation also confirms its
local metadata DB stays unchanged. No check-disabling flag is used.

The initial helper stub failed its real prepare contract before implementation.
Strict compilation caught misleading indentation during implementation; a
real fixture also exposed borrowed callback names becoming invalid after
libalpm cleanup. The helper now owns callback name copies and frees its
allocations. Sanitized runs retain no reported errors.

## Reproduce

Use a new private preparation directory. Existing captures must stay intact.

```sh
python3 packages/current-plan/abi/transaction/prepare.py \
  --source ../overnight-omarchy/omarchy \
  --proposal ../overnight-cpu/packages/current-plan/evidence/configured-current-proposal.json \
  --qualification ../overnight-cpu/packages/current-plan/evidence/configured-current-payload-qualification.json \
  --repositories ../overnight-cpu/packages/current-plan/.private/capture-01/configured-current/repositories \
  --scenario packages/current-plan/abi/transaction/scenario-current117-aliases.json \
  --private packages/current-plan/abi/.private/new-prepare-capture \
  --output packages/current-plan/abi/.private/new-preparation.json
python3 -m unittest discover -s packages/current-plan/abi/tests -p test_prepare.py -v
ABI_PREPARE_SANITIZERS=1 python3 -m unittest discover -s packages/current-plan/abi/tests -p test_prepare.py -v
```

`model.py --help` lists the exact sealed image, qualified plan, preparation and
payload-cache inputs. It uses the existing audited data parser plus its own
hash-bound overlay model and data-only cache, rehashing the sealed image/tree
and every payload. It cannot accept an unsigned source candidate in place of
an official signed row. No mount or installation happens.
