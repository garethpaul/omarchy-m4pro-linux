# J614s RAM-only NVMe probe — prepared offline

**PARTIAL:** a concrete initramfs is packaged and validated offline for the exact combined source `8f2f3d13600aacadd93d577855b7e212b8ae57ff`, config `6c5aba77…56516`, release `7.1.13-j614s-gravity-candidate+`. This is preparation for primary review and a future supervised test. It grants no boot, USB, watchdog, reset, loader, disk, partition or boot-policy authority.

**UNTESTED:** this init has never run. The new CDC-ACM function, console routing, serial reconnect, asynchronous module-load control, read-only guardian and all kernel/hardware behavior remain unqualified. Kernel build/reproducibility evidence is independent of hardware correctness. Root's previously qualified loader, old test52/56 and existing build outputs were not changed.

## Inputs and validation

`pins.json` locks the full build02 manifest, build contract, exact source, clean-source state, config, Image and both module hashes. `build_probe.py` first verifies the manifest/contract/helper digests, then compiles and executes exactly those hash-verified verifier source bytes in a fresh module, bypassing cached bytecode and creating no cache beside the read-only helper. That verifier checks every original artifact, AArch64 Image magic/16KiB flags, embedded IKCONFIG and all module ELF/vermagic. This operation only reads the bundle; its private build log is never copied into the initramfs. Additional checks enforce built-in gadget/pseudo-filesystem support, modular NVMe and exact module dependencies.

Only these kernel modules are packaged:

| Module | SHA256 | Dependency |
| --- | --- | --- |
| `nvme-core.ko` | `b4cfc0d9e84e34cc12f89f85fd01a3fa02b7e34223455825799bf9bc72993a51` | none |
| `nvme-apple.ko` | `8bf6fc6b1369bcbeadefbcbeb0197376803090c6b4776d230be36b039d53bcef` | `nvme-core` |

The static ARM64 BusyBox is Debian `busybox-static` version `1:1.38.0-3+b1`, binary SHA256 `f10ec6f1c3b41b6015cc0f15c11a4ce4e06fff158e20bdbe9a527a3ed3ea752a`. `busybox-provenance.json` records the official HTTPS key bootstrap, exact primary fingerprints, both valid archive signatures, signed index and package hashes, and extraction provenance. Public keys were used; no signing key or host package installation was created. The bootstrap trusts Debian's official HTTPS key distribution plus pinned fingerprints, rather than claiming a separately provisioned trust root. The signed metadata is retained historical evidence, not a future repository-freshness claim.

`verify_busybox_provenance.py` rechecks the retained public evidence offline with isolated temporary public keyring storage. It verifies InRelease signatures, the signed Packages.xz digest, exact native package paragraph, .deb digest and extracted regular BusyBox bytes without extracting arbitrary archive paths. Sources: [Debian archive keys](https://ftp-master.debian.org/keys.html), [signed sid metadata](https://deb.debian.org/debian/dists/sid/InRelease), [native package](https://deb.debian.org/debian/pool/main/b/busybox/busybox-static_1.38.0-3+b1_arm64.deb).

The builder runs only that qualified BusyBox's `--list` and `sh -n init`, under an explicitly supplied existing emulator. It never runs init or chroots. A deterministic gzip/newc archive is parsed back with bounded entries and compared byte-for-byte with the expected payload map. It rejects escapes, duplicate/unexpected entries, set-ID files, extra modules, arbitrary links and all device nodes except the exact console/null pair. Those nodes exist only in archive headers; no host `mknod` occurs.

## Prepared runtime sequence (not executed)

1. Mount only devtmpfs, proc, sysfs, tmpfs and configfs; log to the inherited console and bounded RAM filesystem. No storage filesystem is mounted, even read-only.
2. Check AArch64, exact release/config, and exact J614s + T6040 compatible strings before gadget setup. Require the single previously observed UDC `38a280000.usb`. Create one ACM function using the built-in gadget code. This function differs from old gserial diagnostics and is **UNTESTED**.
3. Wait for USB host state `configured`, open ACM, then accept only literal commands: `help`, `status`, `before`, `after`, `logs`, `dmesg`, `probe`. No shell, eval, arbitrary executable command, network function or daemon is exposed. Send LF-terminated command lines; the parser bounds input to 64 characters.
4. Only an explicit physical serial `probe` request can start the single NVMe attempt. Recheck exact platform/config, all 12 present/online CPUs, empty loaded-module contents and absence of any existing NVMe block device. A failed guard leaves serial diagnostics available.
5. Save CPU/module/dmesg/block-counter baseline. Start the RO guardian and wait for its first completed-scan acknowledgement plus process liveness before loading either module. Missing acknowledgement or any sticky failure prevents module loading. Load `nvme-core`, then `nvme-apple`, in a separate process so a blocked module initialization does not directly block the command dispatcher. No further load attempt, unload, detach, reset or reprobe command exists.
6. The guardian polls every 50ms, including partition block devices, applies `blockdev --setro` and verifies both the ioctl result and sysfs RO bit. The kernel has `UEVENT_HELPER` disabled. **This is not atomic RO protection from the instant of device creation.** There are no userspace disk consumers, mount helpers, storage workloads or arbitrary shell commands in this init. Kernel enumeration can itself issue discovery/metadata reads; software RO is not a claim that controller/firmware activity cannot change media.
7. Latch all observed RO enforcement failures permanently, retain first/latest details and cumulative count, and expose them in status/logs. A later clean iteration cannot erase failure or produce a successful RO classification. Guardian process loss also latches failure. Record current RO assertions and an after-snapshot. Zero devices is a partial/refused result, never a storage pass. `status` includes CPU masks, loaded modules, USB state, per-block RO/counters, read-only watchdog observations and dmesg (including ownership/admission refusal). `before`/`after` preserve the snapshots in RAM. Reports also go to the inherited console; visibility on KVM depends on the separate loader/console handoff.
8. Snapshot existing watchdog `identity`, `state`, `timeout`, `timeleft`, `nowayout`, `bootstatus` attributes and actual `/sys/module/watchdog/parameters/{handle_boot_enabled,open_timeout}` values. Missing devices/fields are explicitly `ABSENT`; failed reads are `UNREADABLE`. No watchdog device handle is opened and no watchdog sysfs field is written. The exact config has `APPLE_WATCHDOG=y`, `WATCHDOG_NOWAYOUT=y`, boot handling disabled by default, and open timeout 15; module parameters can override defaults. The selected kernel driver observes an inherited running watchdog and resets its counter/applies the configured/DT timeout in probe. This init does not arm/feed watchdogs; predecessor/kernel state can still cause reset, and recovery remains unverified. Keep PID1 and diagnostic dispatcher alive. Do not open or feed watchdog devices, reboot automatically, change power policy, or assume recovery. A kernel failure may still remove USB entirely. If initial mounts/platform/gadget setup fail, only the inherited console may remain; USB control cannot be guaranteed before it has actually been established. A disconnected host can reconnect to the bounded command interface if the gadget/kernel remains healthy. Failed/EOF serial reads back off 100ms even if UDC remains configured. This is untested, not a recovery guarantee.

No user-data read diagnostic is included. GPU/DCP/SMC/CPU_FREQ modules, firmware, raw ADT, disk tools, package hooks, desktop files and services are absent. The Image is verified as an external input and is not packed inside the initramfs.

## Reproduction without a target

Run from this lane's repository. These commands read the existing bundle and write only a new ignored directory:

```sh
python3 integration/boot-probe/verify_busybox_provenance.py --cache integration/boot-probe/.private
python3 integration/boot-probe/build_probe.py \
  --bundle ../overnight-infra-gravity-combined-build-02 \
  --verifier ../overnight-infra/infra/kernel_build.py \
  --busybox integration/boot-probe/.private/busybox \
  --emulator /usr/bin/qemu-aarch64-static \
  --output integration/boot-probe/.private/new-build
J614S_KERNEL_BUNDLE=../overnight-infra-gravity-combined-build-02 \
J614S_KERNEL_VERIFIER=../overnight-infra/infra/kernel_build.py \
  python3 integration/boot-probe/test_probe.py
sh -n integration/boot-probe/init
```

The cache and generated initrd are deliberately ignored. Retain the historical signed metadata and package locally to rerun provenance verification; the current moving sid URL may later contain different metadata. A changed input requires a separately reviewed new pin set, not an override or skipped check. Build output must be a fresh directory; it cannot be placed inside the kernel bundle. Tests use copies of artifact inputs, never modify the original bundle and never run init. Without the two environment paths, the portable archive tests run and real-bundle input tests explicitly skip.

`evidence.json` and `artifact-manifest.json` record the actual offline results: 36 tests (the previous32 archive/ELF/classification/input controls plus4 watchdog source/fixture controls). The pure classification helper and extracted actual read-only file helper are executed only against isolated host fixtures. The init body is only parsed; real sysfs and device nodes are never accessed by tests. Guardian scheduling/acknowledgement and serial EOF behavior remain runtime UNTESTED. No DT freshness, loader/boot entry, firmware state, inherited memory/cache ownership, durable storage, live USB control, target recovery or permission to boot is provided. The strict kernel ownership predicates may refuse a session whose boot handoff does not satisfy them; this package does not weaken them.

The watchdog-report revision produces a separate `fresh-03`/`fresh-04` private archive pair. The earlier `frozen-01`/`frozen-02` pair remains byte-for-byte preserved at SHA256 `a3a01204b0310877dd41fd24c6f6ce803344cb48c4e9ef49a9bc4c994f1c39e8`. Neither version has been booted or run.

## Framed host collection — offline prepared, hardware UNTESTED

`collect_probe.py` supplies the host half. It is not run against a physical device by this lane. Importing it, running its tests or requesting `--help` does not discover USB devices or open serial ports. The primary exclusively owns any later physical invocation.

The new init accepts only `J614S_REQ_V1 <32 lowercase hex nonce> <literal command>` followed by LF. Bare commands, CRLF, extra fields and unknown commands are rejected. The longest valid request is 53 bytes including LF, within the existing 64-character read bound. The host creates one random nonce per request; it never automatically sends `probe` or retries an incomplete request.

Before responding, init copies a bounded source into a stable RAM file, computes its length/SHA256, and assembles a complete frame into a second RAM file. One cancellable `cat` writes that file to ACM. The frame contains the nonce, command, byte length and SHA256, the exact payload bytes, then a nonce-tagged completion footer. A timed-out write cannot be mistaken for a complete response. Payloads above 2 MiB become an explicit refusal; missing sources also produce refusal data. There are no unsolicited greeting frames. Status/before/after/dmesg snapshots publish via `.next` then rename, so an in-progress file cannot be framed as a finished snapshot. A failed baseline snapshot refuses module loading; fresh status/dmesg failures do not return an old file.

The host rejects stale buffered bytes before sending, mismatched nonce/command, malformed/oversized headers or payloads, bad digest/footer, truncation, disconnected channels, and extra bytes/frames observed during its bounded 200 ms post-frame window. It does not resynchronize past bad data, flush away stale input, retry, reset, reboot, feed a watchdog or rebind devices. Partial I/O continues one request rather than resending it. No finite quiet window proves that later unexpected bytes can never arrive.

The caller must supply an exact physical USB port such as `1-3.2`; there is no vendor-only or arbitrary-tty fallback. The matcher requires device `1d6b:0104`, the exact product/serial configured by init, control interface 00, COMM/ACM/protocol 01, the exact ACM control string and the `cdc_acm` host driver. It rejects ambiguity and the old sourcehelper/m1n1/gserial identities. It rereads paths/inodes/busnum/devnum immediately before open, requires the opened node's character-device major/minor to match, and rereads identity before termios/serial I/O. `transport-contract.json` records exact descriptor source SHA/line evidence from 8f2; these are source expectations, not a measured runtime match. Device strings are matching criteria, not cryptographic authentication.

An explicit future `collect` invocation defaults to one read-only `status` request. Its only other choices are `before`, `after`, `logs`, `dmesg`, `help`. The separate `probe-once` subcommand requires an exact primary-invocation gate; the transport API enforces that gate too. This path was not invoked, including in fake transport tests. A pure command-selection test checks the gate without transmitting a probe. Opening/configuring ACM can assert modem-control lines; it is not equivalent to authorizing the NVMe command.

A new evidence directory is created mode 0700; raw `rx.bin`, actual `tx.bin`, validated `payload.bin` and `result.json` are mode 0600. Raw bytes remain available after rejection; payload is stored only after framing and quiet-window validation. `FRAME_VALIDATED` describes transport completeness/correlation only. The collector always leaves hardware/boot `UNTESTED` and recovery `UNVERIFIED`, regardless of payload text or USB enumeration. Raw evidence stays private and is not a publishable hardware report.

Offline checks (no physical collector invocation):

```sh
J614S_BUSYBOX=integration/boot-probe/.private/busybox \
J614S_QEMU=/usr/bin/qemu-aarch64-static \
  python3 integration/boot-probe/test_transport.py
python3 integration/boot-probe/collect_probe.py --help
sh -n integration/boot-probe/probe-frame.sh
```

There are 75 checks across the two suites: previous 36, one verifier-cache integrity regression, plus 38 parser, fake-transport/sysfs and shell-framer controls. They exercise every split point and truncated prefix, one-byte reads, oversized/bad-SHA/stale/extra frames, ambiguity and identity changes before open, private raw retention, literal request grammar/CRLF rejection, frozen RAM payloads, refusal bounds and qualified native BusyBox applets. The init body, physical USB discovery/tty opens, actual collector and explicit probe remain unexecuted. Runtime behavior and recovery remain unverified.

The framing revision uses private `framed-07`/`framed-08` outputs. Earlier framed05/06 outputs are also preserved and byte-identical; the final packager additionally bypasses helper bytecode caches. Both the older a3a012 frozen pair and d9fac watchdog-report pair remain unchanged; their recorded byte hashes are preserved in `evidence.json`. No kernel/config/loader/firmware/DT or existing artifact was modified.

A controlled copied-helper regression showed that a timestamp-valid unverified `.pyc` could bypass the source hash under the old import mechanism. The new packager compiles the verified source bytes directly; the same actual copied-bundle regression now passes without consulting or modifying that cache. No other lane helper/source file was changed.
