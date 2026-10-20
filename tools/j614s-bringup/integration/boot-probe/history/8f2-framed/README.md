# Historical 8f2 / 8fd6 probe evidence

These JSON files are exact copies from commit
`944f64386f527f074808405322a986eec44b0317`, before the DART-kernel transition.
`history.json` records their original digests. They are retained historical
evidence, not the current packaging pins or a current hardware-status report.

The original private `framed-07` and `framed-08` archives remain unchanged at
SHA256 `8fd6f861c42e4585156ff747ef657fbdba04b8bc307d0f4a0c2c226b20d16be1`,
1,098,565 bytes. Prior a3a012 and d9fac pairs also remain preserved. No binary
or private captured log is committed here.

The primary subsequently reported a supervised boot reaching init with a USB
SET_CONFIGURATION timeout (-110). That report does not revise the historical
offline checks or establish working USB, framing, NVMe, recovery or storage.
This lane does not access the target; hardware evidence remains with the
primary. Use the original source commit and its recorded pins to reproduce the
old packaging, without overwriting an old output directory.
