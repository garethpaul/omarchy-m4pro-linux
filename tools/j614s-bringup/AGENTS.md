# M4 Pro bring-up workspace

The physical target is Mac16,8 / J614s / T6040. The primary agent exclusively owns KVM, SSH, USB proxy, watchdog and all target operations. Subagents must not access the physical target.

Preserve macOS, Recovery, 1TR policy, partitions and the last qualified boot object. No unattended reboot until independent remote recovery is verified. Do not publish vendor firmware, raw ADTs (they contain keys), credentials, private host details or unredacted logs.

Keep WORKS, PARTIAL, BLOCKED and UNTESTED separate. Compilation does not establish hardware functionality. Every hardware claim must cite captured evidence. M4 is bring-up; reuse M2/M3 code only after measured comparisons. Do not disable validation or compatibility guards.

Use separate branches/worktrees and explicit file staging. PROGRESS.md is maintained by the primary agent. Each lane maintains its own README and test results. No aggregate work limits. Continue until the lane acceptance is met or only evidenced external blockers remain.
