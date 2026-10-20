#!/usr/bin/env python3
"""Fetch read-only metadata for the official aarch64-apple edge configuration.

This never installs packages or changes trust. Databases are for analysis;
package signatures and complete transactions must be checked before deployment.
"""
import argparse
import concurrent.futures
import datetime
import hashlib
import json
from pathlib import Path
import urllib.request

URLS = {
    "omarchy": "https://pkgs.omarchy.org/edge/aarch64/omarchy.db",
    "asahi-alarm": "https://github.com/asahi-alarm/asahi-alarm/releases/download/aarch64/asahi-alarm.db",
    **{name: f"https://arm-mirror.omarchy.org/aarch64/{name}/{name}.db"
       for name in ("core", "extra", "alarm", "aur")},
}


def fetch(item, directory):
    name, url = item
    try:
        with urllib.request.urlopen(url, timeout=40) as response:
            data = response.read(32 * 1024 * 1024 + 1)
        if len(data) > 32 * 1024 * 1024:
            raise ValueError("database exceeds analysis input size limit")
        with (directory / f"{name}.db").open("xb") as output:
            output.write(data)
        return name, {"url": url, "status": "retrieved", "bytes": len(data),
                      "sha256": hashlib.sha256(data).hexdigest(),
                      "retrieved_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    except (OSError, ValueError) as error:
        return name, {"url": url, "status": "unavailable", "error": str(error)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new directory; existing captures are never overwritten")
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        result = dict(pool.map(lambda item: fetch(item, args.output), URLS.items()))
    (args.output / "provenance.json").write_text(json.dumps(result, indent=2) + "\n")
    return 0 if all(row["status"] == "retrieved" for row in result.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
