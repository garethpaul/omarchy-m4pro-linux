/* SPDX-License-Identifier: MIT */
/* Host fake compiles the actual kernel SART predicate; no MMIO is accessed. */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

typedef uint64_t phys_addr_t;
typedef uint8_t u8;
#define PHYS_ADDR_MAX UINT64_MAX
#define APPLE_SART_MAX_ENTRIES 16
#define EXPORT_SYMBOL_GPL(name)
struct apple_sart;
struct fake_entry { u8 flags; phys_addr_t base; size_t size; };
struct fake_ops {
    void (*get_entry)(struct apple_sart *, int, u8 *, phys_addr_t *, size_t *);
    u8 flags_allow;
};
struct apple_sart {
    unsigned long protected_entries;
    struct fake_ops *ops;
    struct fake_entry entries[APPLE_SART_MAX_ENTRIES];
    unsigned reads;
};
static bool test_bit(unsigned bit, const unsigned long *bits) {
    return (*bits & (1UL << bit)) != 0;
}
static void get_entry(struct apple_sart *sart, int index, u8 *flags,
                      phys_addr_t *base, size_t *size) {
    if (index < 0 || index >= APPLE_SART_MAX_ENTRIES) abort();
    sart->reads++;
    *flags = sart->entries[index].flags;
    *base = sart->entries[index].base;
    *size = sart->entries[index].size;
}
#include "sart-predicate-under-test.c"
static unsigned cases;
static void expect(struct apple_sart *sart, phys_addr_t address, size_t size,
                   bool wanted, const char *why) {
    bool actual = apple_sart_is_inherited_region(sart, address, size);
    cases++;
    if (actual != wanted) {
        fprintf(stderr, "FAIL case %u: %s\n", cases, why);
        exit(1);
    }
}
int main(void) {
    _Static_assert(sizeof(phys_addr_t) == 8 && sizeof(size_t) == 8, "64-bit contract");
    struct fake_ops ops = { .get_entry = get_entry, .flags_allow = 0xff };
    struct apple_sart sart = { .protected_entries = 1UL << 7, .ops = &ops };
    sart.entries[7] = (struct fake_entry){0xff, 0x1000, 0x1000};
    expect(&sart, 0x1000, 0x1000, true, "exact range");
    expect(&sart, 0x1000, 1, true, "first byte");
    expect(&sart, 0x1fff, 1, true, "last byte");
    expect(&sart, 0x1800, 0x800, true, "suffix");
    expect(&sart, 0x1000, 0, false, "empty");
    expect(&sart, 0xfff, 1, false, "before range");
    expect(&sart, 0xfff, 0x1001, false, "prefix outside");
    expect(&sart, 0x2000, 1, false, "end is exclusive");
    expect(&sart, 0x1fff, 2, false, "one-byte overrun");
    expect(&sart, 0x1000, 0x1001, false, "whole-entry overrun");
    expect(&sart, 0, SIZE_MAX, false, "oversize request");
    sart.reads = 0;
    expect(&sart, PHYS_ADDR_MAX, 2, false, "overflow must refuse before entry reads");
    if (sart.reads) return 2;
    sart.protected_entries = 0;
    expect(&sart, 0x1000, 0x1000, false, "ordinary allow entry is not inherited");
    sart.protected_entries = 1UL << 7;
    for (unsigned flags = 0; flags < 256; flags++) {
        sart.entries[7].flags = (u8)flags;
        expect(&sart, 0x1000, 1, flags == 0xff, "exact hardware allow flags");
    }
    sart.entries[7] = (struct fake_entry){0xff, 0x1000, 0x1000};
    sart.entries[8] = (struct fake_entry){0xff, 0x2000, 0x1000};
    sart.protected_entries |= 1UL << 8;
    expect(&sart, 0x1fff, 2, false, "adjacent entries do not establish one ownership range");
    sart.entries[7] = (struct fake_entry){0xff, UINT64_MAX - 15, 16};
    expect(&sart, UINT64_MAX, 1, true, "last physical byte without wrap");
    expect(&sart, UINT64_MAX - 15, 16, true, "highest complete range");
    expect(&sart, UINT64_MAX - 15, 17, false, "highest range overflow");
    sart.entries[7] = (struct fake_entry){0xff, 0x1000, 0};
    expect(&sart, 0x1000, 1, false, "empty inherited entry");
    printf("PASS: %u actual SART predicate cases; host fake only; hardware UNTESTED\n", cases);
    return 0;
}
