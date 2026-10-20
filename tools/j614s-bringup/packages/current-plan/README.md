# Separate current ARM package proposal

This is a **new review proposal**, preserving the historical 117-row snapshot,
its two missing immutable pins and every prior failure unchanged. It takes the
same **167 recorded compatibility requests**, keeps their explicit canonical
mappings and protected boot holds, and uses C's unmodified parser/resolver from
commit `4941c67dbab65ec9bd903c337863c10a51741542`.

Both freshly frozen source variants print-resolve to **117 packages**. The
configured Omarchy HTTPS mirror and the official CA HTTPS mirror currently
provide byte-identical DBs and identical selections. There are four explicit
version changes, with no package/dependency-name additions or removals:

| Package | Historical pin | Separate current pin |
| --- | --- | --- |
| graphicsmagick | 1.3.49-2 | 1.3.49-3 |
| marisa | 0.3.1-1 | 0.3.1-2 |
| imagemagick | 7.1.2.34-1 | 7.1.2.34-2 |
| postgresql-libs | 18.6-2 | 18.6-4 |

All **117 current payloads** are obtainable and pass exact size/SHA, required
package PGP against frozen-image anchors, signed identity and `.PKGINFO`/DB
comparison. Signers: 82 ALARM, 35 Omarchy. Signed comparison covers dependencies,
optional dependencies, provides/conflicts/replaces, base, description, URL,
license, installed size, build date and packager. Marisa's dependencies change
from `gcc-libs` to `libgcc` + `libstdc++`; existing frozen-image dependencies
satisfy the metadata solve, which does not establish binary compatibility.
The three recorded aliases have signed provider evidence; `nvim`/`vi` also own
the required executable files. No payload was run.

## Distinct evidence and limits

The **retained immutable image** was SHA/size checked and only its pacman
configuration extracted as data. It uses `Required DatabaseOptional`, including
its repository overrides. This agrees with the reviewed [public Apple configuration](https://github.com/omacom/omarchy/blob/81fd2d23ca6e3462183a4dc8360de3113fa8d80c/default/pacman/aarch64-apple/pacman-edge.conf)
and [ALARM signing policy](https://archlinuxarm.org/about/package-signing).
Package signatures remain required. Missing DB signatures do not become a new
policy requiring signed DBs, and do not authenticate those DBs.

Asahi's DB signature verifies against retained anchor
`12CE6799A94A3F1B5DDFFE88F576553597FB8FEB`. The other five DB signatures return
404; those DBs remain **unsigned**. All proposal metadata URLs require HTTPS
with normal certificate verification. The [public mirror configuration](https://github.com/omacom/omarchy/blob/81fd2d23ca6e3462183a4dc8360de3113fa8d80c/default/pacman/aarch64-apple/mirrorlist-edge)
uses HTTPS because ALARM DBs are unsigned. The explicit CA alternative is also
in the retained image configuration and the published official mirror list.
TLS authenticates an origin connection; signatures authenticate individual
payload content. **Neither proves repository freshness, completeness or absence
of a rollback.** Signed redirects are recorded without transient URL queries.
No keys are imported, fetched or newly trusted; public rings are only read or
dearmored into disposable directories and compared with prior image evidence.

**This proposal is not installable qualification.** Plymouth still triggers the
two effective initramfs-generating hooks from the frozen image. Four source
boot requests and 20 installed boot/system/graphics pins remain held. More
broadly, mixing current packages with the untouched 986-package image can
produce a partial upgrade whose reverse dependencies have incompatible binary
ABIs. Metadata resolution and PGP do not prove those consumers still work.
A disposable full-image clone plus affected-library/symbol/consumer validation
is required before proposing any real install. This requirement does not
license `-Syu`, boot changes or a real installation.

Every artifact retains `deployable:false` and `execution_ready:false`; actions
are empty. There is no package installation, hook/script/service execution,
key/trust change, host system configuration mutation or target access.

## Evidence

- [Summary and claim ledger](evidence/summary.json)
- [Current proposal and old→new diff](evidence/configured-current-proposal.json)
- [Complete signed payload qualification](evidence/configured-current-payload-qualification.json)
- [Configured-source provenance](evidence/configured-current-repositories.json)
- [Official-source provenance](evidence/official-alarm-current-repositories.json)
- [Retained image policy](evidence/frozen-policy.json)
- [Actual C parser/resolver tests](evidence/current-tests.log)

The proposal files are metadata-only captures created before the separate
payload audit. Their payload gate must be read with the hash-bound completed
qualification and summary. Original historical evidence remains separate.
Complete frozen DBs, signatures, payloads and disposable resolver state remain
under ignored `.private/`; published JSON hashes/selected rows alone do not
reconstruct a complete repository index.

## Reproduce safely

From the evidence repository root, use the included hash-pinned `omarchy/`
sources and choose a **new private capture directory** to fetch
and freeze a new separate snapshot. Existing captures are never overwritten.
This does not silently update the recorded historical plan.

```sh
python3 packages/current-plan/propose.py \
  --source omarchy --public-source omarchy \
  --image ../omarchy-arm-payload/root.img \
  --private packages/current-plan/.private/capture-01 \
  --output packages/current-plan/evidence
python3 packages/current-plan/qualify_payloads.py \
  --source omarchy \
  --capture packages/current-plan/.private/capture-01 --variant configured-current \
  --evidence packages/current-plan/evidence \
  --cache packages/current-plan/.private/payload-cache --old-cache packages/.private \
  --image-hooks packages/.private/qualified-image-snapshot
python3 -m unittest discover -s packages/current-plan/tests -v
python3 packages/current-plan/summarize.py
```

Tests default to the included `omarchy/` sources; an explicit
`J614S_OMARCHY_SOURCE` override must still satisfy every existing source hash.
No sibling development checkout is needed.

Tests invoke the actual pinned C parser and actual host pacman's `--print -S`
inside disposable root/DB/cache/log directories. They include protected
secondary-dependency refusal, changed DB rejection, exact print identity,
provider-substitution refusal and signed dependency/provider mismatch. No
`-Syu`, refresh, package download or install occurs in those resolver tests.
The existing capture was also replayed through C's unchanged CLI and its
selected package rows matched exactly. The summary binds that saved replay.
