J614s test56 source archive
==========================

This branch archives the exact formerly uncommitted diagnostic source used by
the qualified J614s RAM tests. It is an experimental reproduction checkpoint,
not a production kernel or permission to boot another machine. The parent
commit alone does not contain these diagnostic changes.

The original source checkout remains unchanged. The source files were copied
from the retained isolated build snapshot and matched byte-for-byte against the
original dirty checkout. The adjacent JSON manifest records their hashes.
The independently built kernel uses the exact configuration from the task's
m4-gpu-bootstrap artifacts and the qualified corrected bindgen 0.73.2.

Important limitations
---------------------

The archive deliberately retains fixed-address early framebuffer writes in
head.S and j614s_earlyfb.c, including an unconditional early_initcall. Those
addresses are valid only for the captured test session. Do not boot this archive
on another machine or assume firmware allocations are stable after a restart.
A separate candidate removes that instrumentation before further qualification.

The USB2 host diagnostic is board/resource/state gated and must not be loaded
automatically. The NVMe diagnostic preserves an inherited powered ANS link and
requires the matching guarded RAM loader. The SMC battery driver must use its
read_only mode for bring-up; module presence is not permission to change charge
policy. Trackpad GPIO reset is limited to the measured four-byte gp1c command.
No speaker, clock, voltage or persistent boot-policy qualification is implied.

Prior test scope
----------------

CPU tests established all twelve cores and the M4 wait-state handling. Tests55
and56 established G16S RTKit transport and shutdown, with read-only SSD and RAM
overlays. They did not establish GPU rendering, DCP modesetting, suspend or a
persistent default installation. This source archive changes no installed boot
object, protected volume, partition or Apple security policy.
