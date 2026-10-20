J614s G16S bootstrap qualification
=================================

This is an experimental transport milestone, not an accelerated graphics driver.
``CONFIG_DRM_ASAHI_G16_BOOTSTRAP=m`` creates no DRM device and sends no application
INIT message. The qualified target is Mac16,8 / J614s, T6040, GPU ID 0x0a031100
(S variant, B1) with masks 0xf6fdb / 0 / 0. Firmware is the B-silicon slice of
G16S from macOS 26.6.2 build 25G83. Other boards, revisions and builds are refused.

The existing Apple mailbox and RTKit drivers handle the transport. The measured
M2 ASC wrapper is v4 and the M3/M4 wrapper is v6; their mailbox FIFO/control
registers have the same layout at wrapper offset 0x8000. On J614s the wrapper
aperture grew from the M3's 0x6c000 to 0x88000 and its second register aperture
changed from 8 bytes to 0x60000. This test does not interpret that second aperture.

Before loading the module, the test loader powers the real AFR/GFX PMGR domains
and keeps the coprocessor halted. The driver verifies those power states. Virtual
GFX-SGX/GFX-ASC PMGR aliases must not be treated as power-state register offsets.
All GPU firmware memory is excluded from the Linux RAM allocator by the test's
restricted RAM envelope. No clock, voltage, DCP or page-table changes are made.

The test DT supplies these named resources on ``apple,j614s-gfx-bootstrap``:

* ``asc``: 0x28a600000, size 0x4000.
* ``sgx``: the ADT aperture at 0x288000000, size 0x3758000. The driver requests
  only its first 16 MiB; the full aperture also contains the mailbox and ASC.
* ``firmware-data``: the current live ADT GFX DATA segment, size 0x138000.
  Never reuse another machine's physical address or treat it as a GPU VA.

``apple,bootstrap-firmware`` is ``26.6.2-25G83-g16s-b000``. ``mboxes`` names an
``apple,asc-mailbox-v4`` controller at 0x28a608000, size 0x4000, with AIC interrupt
numbers 1501/1502/1503/1504 named send-empty, send-not-empty, recv-empty, recv-not-empty.
These numbers were compared with the live ADT list 1502/1501/1504/1503 and tested
with the normal interrupt-driven mailbox driver.

The firmware supplies its own physical crash buffer at DATA + 0xa0000, size
0x8000. The driver refuses other geometries and host allocation requests. Its
RTKit mapping views only that firmware-owned storage; it never frees the storage.

Qualification on the actual target
----------------------------------

Two cold RAM boots completed RTKit startup with protocol 12. The receive mailbox
interrupt count rose from zero to six. All 12 Linux CPUs remained online; the
internal NVMe disk and every partition remained block read-only, with zero write
requests/sectors. The second boot also tested unbind: RTKit acknowledged quiesce
and the CPU control register read back 0 after clearing RUN. No kernel BUG,
WARNING, Oops or panic was observed in the captured logs.

Observed commands and results::

    modprobe g16_bootstrap
    cat /sys/bus/platform/devices/28a600000.gfx-bootstrap/bootstrap_state
    RTKIT_READY protocol=12 rendering=unimplemented

    drivers=/sys/bus/platform/drivers
    echo 28a600000.gfx-bootstrap > "$drivers/j614s-gfx-bootstrap/unbind"
    # dmesg: G16 RTKit quiesced
    # dmesg: G16 CPU RUN cleared, control=0x0

A fresh reboot is required before another cold-start test. A clear RUN bit is
not a GPU reset or proof of reusable firmware state. UAT ownership, application
initialization, job submission, rendering, GPU power management and accelerated
desktop use remain unimplemented by this module. The installed boot object and
macOS/recovery containers were not changed during these tests.
