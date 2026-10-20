#!/bin/sh
# Cross-build the unchanged, freestanding AArch64 qualification workloads.
set -eu
cd "$(dirname "$0")"
: "${CLANG:=clang}"
: "${LD_LLD:=ld.lld}"
mkdir -p build
for source in coherency simd-context; do
    "$CLANG" --target=aarch64-linux-gnu -march=armv8-a -O2 -ffreestanding -fno-stack-protector -fno-builtin -c "src/$source.c" -o "build/$source.o"
done
"$CLANG" --target=aarch64-linux-gnu -c src/coherency-start.S -o build/start.o
"$CLANG" --target=aarch64-linux-gnu -c src/simd-sleep.S -o build/simd-sleep.o
"$LD_LLD" -m aarch64elf -static -e _start build/start.o build/coherency.o -o build/coherency
"$LD_LLD" -m aarch64elf -static -e _start build/start.o build/simd-context.o build/simd-sleep.o -o build/simd-context
sha256sum build/coherency build/simd-context > build/SHA256SUMS
