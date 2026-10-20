# J614s native Omarchy bring-up tools

Experimental tools for Mac16,8 / T6040. The installed boot object and protected
volumes are not modified by these tools. Native GPU rendering and persistent
default boot remain incomplete. Read PROGRESS.md before running any experiment.

- cpu/: guarded12-core qualification, performance evidence and read-only power-layout decoding.
- graphics/: exact-build G16S initialization capture decoders, bounded UAT reads and actual-driver crash regression. These do not construct or send INIT.
- omarchy/: native renderer qualification, signed ARM package inspection and print-only dependency planning. No package installation or desktop changes.
- mesa/: source-built first-compute fixture, architecture comparison and explicit unqualified-model rejection. No GPU submission.
- packages/: pinned payload signature and boot-hook audit, including unavailable-pin evidence. Actual static ELF audit plus normal libalpm dependency/conflict preparation against all986 frozen package descriptions; only explicit hypothetical removals, no transaction commit or installation.
- integration/: immutable consolidated J614s source/config ledgers and patch replay evidence. Strict ANS admission/lifetime source, host regressions and a pinned offline USB/read-only initramfs probe; init has never run, and real hardware/cache ownership remain unqualified.
- omarchy-packages/: architecture-independent Neovim seed repair with actual packaging fixtures; signed build/runtime remain untested.
- infra/: isolated kernel builds with tool/source/config/artifact integrity checks.
- capture/: gated minimal Metal workload, validated on a separate M1 Pro builder; M4 capture remains untested.
- qualification/: all-phase status matrix and selected captured hardware evidence.
- recovery/: USB/webcam observation and PMU counter read without counter or watchdog changes.

Run component commands from this directory, with explicit external source/build
paths for this workspace. Examples showing sibling development trees describe
the original layout; adapt those arguments to retained qualified sources.

Host tests, cross-compilation, firmware transport, actual acceleration and
persistent boot are separate evidence levels. Synthetic fixtures are labeled
and never establish hardware support. Raw ADTs, vendor firmware, credentials
and private screen captures are excluded. WORKSPACE-SOURCE.json fingerprints
the integrated source checkpoint. New experimental builds must not replace
the last qualified payload or bypass the independently verified recovery gate.
