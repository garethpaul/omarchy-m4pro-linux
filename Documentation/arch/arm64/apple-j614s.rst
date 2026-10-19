.. SPDX-License-Identifier: GPL-2.0-only

Apple J614s native RAM checkpoint
================================

A one-CPU, RAM-only Linux diagnostic on J614s (M4 Pro, board 4) reaches
BusyBox PID 1 and returns a nonce-bound root command through USB1 generic
serial. The command reports AArch64, advancing timer interrupts, zero
interrupt errors, zero DART fault interrupts and only RAM/pseudo filesystems.
This is not a persistent installation or desktop/peripheral qualification.

The debug transport must identify its controller with P_IODEV_WHOAMI before
building the device tree. In this test it reports USB1, not USB0. USB1 uses
DWC3 at 0x38a280000 with interrupt 1651, DART banks at 0x38af00000 and
0x38af80000 with shared fault interrupt 1655, and the inherited USB2 PHY/PIPE
apertures admitted by the PHY driver.

Both DART banks must be transferred after bounded controller retirement.
The native test gives both providers the low 32-bit DMA window and references
SID 0 of bank 0 and SID 1 of bank 1. The caller checks current bank state,
retains the initialized PHY clocks, and arms an independent recovery watchdog.
A device-tree assertion alone does not transfer ownership.

The USB1 consumer is peripheral-only, high-speed, and uses both
``snps,dis_u2_susphy_quirk`` and ``snps,dis_enblslpm_quirk``. This tested pair
retains the bootloader's working USB2 low-power settings. Its individual
requirements have not been isolated. The gadget uses generic serial bulk
endpoints; normal CDC notifications, host mode and SuperSpeed remain
unqualified. Root input/output and the original watchdog recovery were
observed on the real machine. Storage, SMP and an Omarchy desktop remain
unverified.
