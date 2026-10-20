/* SPDX-License-Identifier: MIT */
#ifndef G16S_ABI_H
#define G16S_ABI_H

/* Read-only G16S interface decoder. This does not construct or publish INIT. */
#ifdef __KERNEL__
#include <linux/types.h>
typedef u8 g16_u8;
typedef u16 g16_u16;
typedef u32 g16_u32;
typedef u64 g16_u64;
#else
#include <stddef.h>
#include <stdint.h>
typedef uint8_t g16_u8;
typedef uint16_t g16_u16;
typedef uint32_t g16_u32;
typedef uint64_t g16_u64;
#endif

#define G16S_ROOT_SIZE 0xc8u
#define G16S_PAGE_SIZE 0x4000u
#define G16S_MAX_U64 ((g16_u64)~(g16_u64)0)

enum g16s_error {
	G16S_OK = 0, G16S_SIZE, G16S_MESSAGE, G16S_ALIGNMENT,
	G16S_VERSION, G16S_UNMAPPED, G16S_GEOMETRY, G16S_ADDRESS,
	G16S_RANGE, G16S_READ, G16S_INVALID_PTE, G16S_BLOCK_PTE, G16S_CHIP,
};

struct g16s_level {
	g16_u8 shift;
	g16_u16 entries;
	g16_u64 phys_mask, index_mask;
};
struct g16s_root {
	g16_u64 region_a, opaque_10, main_config, region_c;
	g16_u32 opaque_28, mapped_marker;
	struct g16s_level level[3];
	g16_u8 ias, oas;
	g16_u64 status_a, status_b, opaque_b8, opaque_c0;
};
struct g16s_range { g16_u64 start, size; };
/* The callback must return zero and exactly fill destination on success.
 * Reads are approved against ranges before invoking it. Supply RAM ranges,
 * never MMIO. No callback for writes exists. */
struct g16s_reader {
	int (*read)(void *cookie, g16_u64 address, g16_u8 *out, size_t size);
	void *cookie;
	const struct g16s_range *ranges;
	size_t range_count;
};
struct g16s_walk {
	g16_u64 physical;
	g16_u64 pte_address[3], pte[3];
};

static inline g16_u16 g16s_le16(const g16_u8 *p)
{
	return (g16_u16)p[0] | (g16_u16)((g16_u16)p[1] << 8);
}
static inline g16_u32 g16s_le32(const g16_u8 *p)
{
	return (g16_u32)g16s_le16(p) | ((g16_u32)g16s_le16(p + 2) << 16);
}
static inline g16_u64 g16s_le64(const g16_u8 *p)
{
	return (g16_u64)g16s_le32(p) | ((g16_u64)g16s_le32(p + 4) << 32);
}
static inline int g16s_power2(g16_u64 n) { return n && !(n & (n - 1)); }

/* Exact endpoint/type predicate and address reconstruction seen in 25G83
 * G16S b000 at VM address 0xfffffc000002f204. Unknown flag bits are retained
 * by the caller's original message; they are not assigned invented meanings. */
static inline enum g16s_error g16s_init_address(g16_u32 endpoint,
	g16_u64 message, g16_u64 *address)
{
	if (!address || endpoint != 0x20 ||
	    (message & 0x00bf000000000000ull) != 0x0081000000000000ull)
		return G16S_MESSAGE;
	*address = message | 0xfffff00000000000ull;
	return (*address & 7) ? G16S_ALIGNMENT : G16S_OK;
}

/* Decode only the measured root envelope. Opaque fields intentionally have
 * no G17 secondary-role names. The shared interface version does not imply
 * that G17 hardware-data, channels or dual-coprocessor profile is usable. */
static inline enum g16s_error g16s_decode_root(const g16_u8 *p, size_t size,
	struct g16s_root *out)
{
	static const g16_u16 version[4] = {0x04c0, 0x0396, 0xa322, 0x0c8a};
	g16_u64 mask, all_phys = 0;
	unsigned int i, bits;
	struct g16s_root root = {0};

	if (!p || !out || size != G16S_ROOT_SIZE)
		return G16S_SIZE;
	for (i = 0; i < 4; i++)
		if (g16s_le16(p + i * 2) != version[i])
			return G16S_VERSION;
	root.region_a = g16s_le64(p + 8);
	root.opaque_10 = g16s_le64(p + 0x10);
	root.main_config = g16s_le64(p + 0x18);
	root.region_c = g16s_le64(p + 0x20);
	root.opaque_28 = g16s_le32(p + 0x28);
	root.mapped_marker = g16s_le32(p + 0x2c);
	if (!root.mapped_marker)
		return G16S_UNMAPPED;
	if (g16s_le16(p + 0x30) != G16S_PAGE_SIZE || p[0x32] != 14 || p[0x33] != 3)
		return G16S_GEOMETRY;
	for (i = 0; i < 3; i++) {
		const g16_u8 *d = p + 0x34 + i * 0x20;
		struct g16s_level *level = &root.level[i];

		level->shift = d[3];
		level->entries = g16s_le16(d + 4);
		level->phys_mask = g16s_le64(d + 16);
		level->index_mask = g16s_le64(d + 24);
		if (d[0] != 8 || d[1] != 14 || d[2] != 14 ||
		    level->shift != 36 - i * 11 ||
		    !g16s_power2(level->entries) || level->entries > 2048 ||
		    (i && level->entries != 2048) ||
		    g16s_le16(d + 6) != G16S_PAGE_SIZE || g16s_le64(d + 8) != 1 ||
		    level->index_mask != ((g16_u64)level->entries - 1) << level->shift)
			return G16S_GEOMETRY;
		mask = level->phys_mask;
		if (mask & (G16S_PAGE_SIZE - 1) || !mask)
			return G16S_GEOMETRY;
		mask |= G16S_PAGE_SIZE - 1;
		if (!g16s_power2(mask + 1) || mask >= ((g16_u64)1 << 48))
			return G16S_GEOMETRY;
		if (i && level->phys_mask != all_phys)
			return G16S_GEOMETRY;
		all_phys = level->phys_mask;
	}
	for (bits = 0, mask = root.level[0].entries; mask > 1; mask >>= 1)
		bits++;
	root.ias = (g16_u8)(36 + bits);
	for (bits = 0, mask = all_phys; mask; mask >>= 1)
		bits++;
	root.oas = (g16_u8)bits;
	root.status_a = g16s_le64(p + 0xa8);
	root.status_b = g16s_le64(p + 0xb0);
	root.opaque_b8 = g16s_le64(p + 0xb8);
	root.opaque_c0 = g16s_le64(p + 0xc0);
	*out = root;
	return G16S_OK;
}

static inline int g16s_in_range(const struct g16s_reader *reader,
	g16_u64 address, g16_u64 size)
{
	size_t i;

	if (!reader || !reader->ranges || !size || size - 1 > G16S_MAX_U64 - address)
		return 0;
	for (i = 0; i < reader->range_count; i++) {
		const struct g16s_range *r = &reader->ranges[i];
		if (r->size && r->size - 1 <= G16S_MAX_U64 - r->start &&
		    address >= r->start && size <= r->size && address - r->start <= r->size - size)
			return 1;
	}
	return 0;
}

/* Root selection is explicit: never infer a TTBR or overwrite a published
 * root. Geometry must come from a successfully decoded root. Only 16-KiB
 * page mappings are supported; block mappings fail rather than guessing. */
static inline enum g16s_error g16s_walk_page(const struct g16s_reader *reader,
	const struct g16s_root *root, g16_u64 table, g16_u64 virtual_address,
	struct g16s_walk *out)
{
	struct g16s_walk walk = {0};
	g16_u64 lowmask, base, pte;
	g16_u8 bytes[8];
	unsigned int i, bits;

	if (!reader || !reader->read || !root || !out || root->ias < 36 || root->ias > 47)
		return G16S_GEOMETRY;
	/* Recheck externally visible structs before shifts or physical reads. */
	for (i = 0; i < 3; i++) {
		const struct g16s_level *level = &root->level[i];
		g16_u64 mask = level->phys_mask | (G16S_PAGE_SIZE - 1);
		if (level->shift != 36 - i * 11 ||
		    !g16s_power2(level->entries) || level->entries > 2048 ||
		    (i && level->entries != 2048) ||
		    level->index_mask != ((g16_u64)level->entries - 1) << level->shift ||
		    !level->phys_mask || (level->phys_mask & (G16S_PAGE_SIZE - 1)) ||
		    mask >= ((g16_u64)1 << 48) || !g16s_power2(mask + 1) ||
		    level->phys_mask != root->level[0].phys_mask)
			return G16S_GEOMETRY;
	}
	for (bits = 0, base = root->level[0].entries; base > 1; base >>= 1)
		bits++;
	if (root->ias != 36 + bits)
		return G16S_GEOMETRY;
	lowmask = ((g16_u64)1 << root->ias) - 1;
	if ((virtual_address & ~lowmask) && (virtual_address & ~lowmask) != ~lowmask)
		return G16S_ADDRESS;
	for (i = 0; i < 3; i++) {
		if (table & (G16S_PAGE_SIZE - 1))
			return G16S_ALIGNMENT;
		if (table & ~root->level[i].phys_mask)
			return G16S_ADDRESS;
		if (!g16s_in_range(reader, table, G16S_PAGE_SIZE))
			return G16S_RANGE;
		walk.pte_address[i] = table + ((virtual_address & root->level[i].index_mask) >> root->level[i].shift) * 8;
		if (reader->read(reader->cookie, walk.pte_address[i], bytes, sizeof(bytes)))
			return G16S_READ;
		pte = walk.pte[i] = g16s_le64(bytes);
		if (!(pte & 1))
			return G16S_INVALID_PTE;
		if (!(pte & 2))
			return G16S_BLOCK_PTE;
		if (pte & 0x0000ffffffffc000ull & ~root->level[i].phys_mask)
			return G16S_ADDRESS;
		base = pte & root->level[i].phys_mask;
		table = base;
	}
	walk.physical = base | (virtual_address & (G16S_PAGE_SIZE - 1));
	if (!g16s_in_range(reader, walk.physical, 1))
		return G16S_RANGE;
	*out = walk;
	return G16S_OK;
}
#endif
