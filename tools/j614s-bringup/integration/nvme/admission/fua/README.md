# FUA core dependency repair

The first full AArch64 build found that the Gravity core lacked the FUA quirk
referenced by the staged driver. Source `dd3f608d60ed503b87a9400255286d1c8fe5ac2d`
on separate branch `agent/gravity-j614s-fua` adds the exact f93 dependency:
bit24 and its name, plus clearing only BLK_FEAT_FUA after the existing namespace
cache-feature setup. The 9-line delta leaves the prior frozen 05af source intact.

The actual enum reproduces the missing-quirk compile failure. The old namespace
fragment, run with the candidate enum solely to isolate behavior, retains native
FUA and therefore skips explicit postflush. It fails the corrected invariant.
The candidate passes 16 literal queue-limit scenarios, preserving write cache
and unrelated profiles. Its actual `blk_insert_flush` initializes the flush
sequence; after simulated data completion, the actual `blk_flush_complete_seq`
queues POSTFLUSH. Queue scheduling/physical I/O remain faked boundaries.

The repair has host execution evidence; original full-build verification remains
pending the build lane. Hardware and storage durability are UNTESTED. No target,
known boot object, firmware, macOS/Recovery or configuration was changed.

Use `test_fua_source.py --source KERNEL --commit dd3f608d60ed503b87a9400255286d1c8fe5ac2d --output NEW_OUTPUT`.
For the original baseline use 05af and `--expect-missing-quirk`. For the isolated
old feature behavior use 05af with `--header-commit dd3f608d60ed503b87a9400255286d1c8fe5ac2d --expect-fua-retained-bug`.
Omit the last flag to require the corrected behavior and observe baseline failure.
All fixtures retain actual enum/core/flush functions and fatal ASan/UBSan.
