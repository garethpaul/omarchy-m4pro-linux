#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build
xcrun --sdk macosx clang -arch arm64 -mmacosx-version-min=13.0 \
  -std=c11 -O2 -Wall -Wextra -Werror -fobjc-arc -fblocks \
  -framework Metal -framework Foundation compute_trigger.m -o build/compute-trigger
shasum -a 256 compute_trigger.m build/compute-trigger
