/* SPDX-License-Identifier: MIT */
#include "g16s_abi.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static void put16(g16_u8 *p, g16_u16 v) { p[0] = (g16_u8)v; p[1] = (g16_u8)(v >> 8); }
static void put32(g16_u8 *p, g16_u32 v) { put16(p, (g16_u16)v); put16(p+2, (g16_u16)(v >> 16)); }
static void put64(g16_u8 *p, g16_u64 v) { put32(p, (g16_u32)v); put32(p+4, (g16_u32)(v >> 32)); }
/* Fully synthetic graph, never a vendor binary or captured process memory. */
static void fixture(g16_u8 bytes[G16S_ROOT_SIZE])
{
	unsigned int i;
	memset(bytes, 0, G16S_ROOT_SIZE);
	put64(bytes, 0x0c8aa322039604c0ull);
	put64(bytes+8, 0xfffffc2000108000ull);
	put64(bytes+0x18, 0xfffffc20c04f5a40ull);
	put32(bytes+0x2c, 1);
	put16(bytes+0x30, 0x4000); bytes[0x32]=14; bytes[0x33]=3;
	for (i=0; i<3; i++) {
		g16_u8 *d=bytes+0x34+i*0x20;
		unsigned int shift=36-i*11, entries=i?2048:64;
		d[0]=8; d[1]=d[2]=14; d[3]=(g16_u8)shift;
		put16(d+4, (g16_u16)entries); put16(d+6, 0x4000); put64(d+8, 1);
		put64(d+16, 0x3ffffffc000ull);
		put64(d+24, (g16_u64)(entries-1)<<shift);
	}
	put64(bytes+0xb8, 0x0123456789abcdefull);
	put64(bytes+0xc0, 0xfedcba9876543210ull);
}
static g16_u8 memory[0x10000];
static unsigned int read_count;
static int fail_read;
static int read_memory(void *cookie, g16_u64 address, g16_u8 *out, size_t size)
{
	(void)cookie;
	read_count++;
	assert(address >= 0x10000 && address+size <= 0x20000);
	if (fail_read) return -1;
	memcpy(out, memory+(address-0x10000), size); return 0;
}
static void mapping(g16_u64 va)
{
	memset(memory, 0, sizeof(memory));
	put64(memory+((va>>36)&63)*8, 0x14003);
	put64(memory+0x4000+((va>>25)&2047)*8, 0x18003);
	put64(memory+0x8000+((va>>14)&2047)*8, 0x1c403);
	read_count=0;
}
