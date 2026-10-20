/* SPDX-License-Identifier: MIT */
#ifndef G16S_MAIN_H
#define G16S_MAIN_H
#include "g16s_abi.h"

/* Only the last known field sets this capture extent. It is not a claim
 * about the allocation size or a complete firmware initialization graph. */
#define G16S_MAIN_CAPTURE_SIZE 0x479u
#define G16S_CHANNELS 17u
#define G16S_CONTROL_CHANNEL 12u

struct g16s_channel { g16_u64 state[3], ring; };
struct g16s_main {
	g16_u64 hwdata, opaque_8, opaque_10, opaque_18;
	struct g16s_channel channel[G16S_CHANNELS];
	g16_u32 log_enable;
	g16_u64 view[5];
	g16_u64 descriptor_2e0, descriptor_2f0, power_471;
};
struct g16s_request { g16_u64 address; size_t size; };

static inline int g16s_canonical(const struct g16s_root *root, g16_u64 address)
{
	g16_u64 mask;
	if (!root || root->ias < 36 || root->ias > 47)
		return 0;
	mask = ((g16_u64)1 << root->ias) - 1;
	return !(address & ~mask) || (address & ~mask) == ~mask;
}

/* Parse known fields only. No role, power-state or clock profile is inferred.
 * Counter/ring meanings are established for control channel 12 in this exact
 * consumer; work/event channel publication remains unqualified. */
static inline enum g16s_error g16s_decode_main(const g16_u8 *p, size_t size,
	struct g16s_main *out)
{
	struct g16s_main main = {0};
	unsigned int i, j;
	if (!p || !out || size < G16S_MAIN_CAPTURE_SIZE)
		return G16S_SIZE;
	main.hwdata = g16s_le64(p);
	main.opaque_8 = g16s_le64(p + 8);
	main.opaque_10 = g16s_le64(p + 0x10);
	main.opaque_18 = g16s_le64(p + 0x18);
	for (i = 0; i < G16S_CHANNELS; i++) {
		const g16_u8 *channel = p + 0x20 + i * 0x20;
		for (j = 0; j < 3; j++)
			main.channel[i].state[j] = g16s_le64(channel + j * 8);
		main.channel[i].ring = g16s_le64(channel + 24);
	}
	main.log_enable = g16s_le32(p + 0x250);
	for (i = 0; i < 5; i++)
		main.view[i] = g16s_le64(p + 0x254 + i * 8);
	main.descriptor_2e0 = g16s_le64(p + 0x2e0);
	main.descriptor_2f0 = g16s_le64(p + 0x2f0);
	main.power_471 = g16s_le64(p + 0x471);
	*out = main;
	return G16S_OK;
}

/* Check only pointers the measured consumer uses. Success means plausible
 * addresses, never safe-to-publish: mapped extents and object contents still
 * require captures, and the rest of the graph is explicitly unknown. */
static inline enum g16s_error g16s_check_main_pointers(const struct g16s_root *root,
	const struct g16s_main *main, unsigned int *bad_offset)
{
	g16_u64 values[7];
	static const unsigned int offsets[7] = {0, 0x1a0, 0x1a8, 0x1b0, 0x1b8, 0x2e0, 0x2f0};
	unsigned int i;
	if (!root || !main || !bad_offset)
		return G16S_SIZE;
	values[0] = main->hwdata;
	for (i = 0; i < 3; i++)
		values[i + 1] = main->channel[G16S_CONTROL_CHANNEL].state[i];
	values[4] = main->channel[G16S_CONTROL_CHANNEL].ring;
	values[5] = main->descriptor_2e0;
	values[6] = main->descriptor_2f0;
	for (i = 0; i < 7; i++) {
		if (!values[i] || (values[i] & ((i >= 1 && i <= 3) ? 3u : 7u)) ||
		    !g16s_canonical(root, values[i])) {
			*bad_offset = offsets[i];
			return G16S_ADDRESS;
		}
	}
	if (!main->power_471 || (main->power_471 & 7) || !g16s_canonical(root, main->power_471)) {
		*bad_offset = 0x471;
		return G16S_ADDRESS;
	}
	return G16S_OK;
}

/* Stage 1: request exactly the pointer used by the first unsupported
 * consumer dereference after root +0x18. No capture is executed here. */
static inline enum g16s_error g16s_main_header_request(const struct g16s_root *root,
	struct g16s_request *request)
{
	if (!root || !request || !root->main_config || (root->main_config & 7) ||
	    !g16s_canonical(root, root->main_config))
		return G16S_ADDRESS;
	request->address = root->main_config;
	request->size = 8;
	return G16S_OK;
}

/* Stage 2: exact25G83 first body read is 16 bytes at hwdata +0xe90,
 * consumer VM PC0xfffffc000002f318. Its semantics remain opaque. */
static inline enum g16s_error g16s_hwdata_first_request(const struct g16s_root *root,
	const g16_u8 *main_header, size_t size, struct g16s_request *request)
{
	g16_u64 hwdata;
	if (!root || !main_header || !request || size != 8)
		return G16S_SIZE;
	hwdata = g16s_le64(main_header);
	if (!hwdata || (hwdata & 7) || !g16s_canonical(root, hwdata) ||
	    hwdata > G16S_MAX_U64 - 0xe9f || !g16s_canonical(root, hwdata + 0xe9f))
		return G16S_ADDRESS;
	request->address = hwdata + 0xe90;
	request->size = 16;
	return G16S_OK;
}

/* Read a bounded virtual capture through the explicitly selected UAT root.
 * It shares the physical RAM allowlist; no MMIO or write path is added. */
static inline enum g16s_error g16s_read_virtual(const struct g16s_reader *reader,
	const struct g16s_root *root, g16_u64 table, g16_u64 address,
	g16_u8 *destination, size_t size)
{
	struct g16s_walk walk;
	enum g16s_error error;
	size_t chunk, done = 0;
	if (!destination || !size || size > G16S_PAGE_SIZE || size - 1 > G16S_MAX_U64 - address)
		return G16S_SIZE;
	while (done < size) {
		error = g16s_walk_page(reader, root, table, address + done, &walk);
		if (error != G16S_OK)
			return error;
		chunk = G16S_PAGE_SIZE - (size_t)(walk.physical & (G16S_PAGE_SIZE - 1));
		if (chunk > size - done)
			chunk = size - done;
		if (!g16s_in_range(reader, walk.physical, chunk))
			return G16S_RANGE;
		if (reader->read(reader->cookie, walk.physical, destination + done, chunk))
			return G16S_READ;
		done += chunk;
	}
	return G16S_OK;
}
#endif
