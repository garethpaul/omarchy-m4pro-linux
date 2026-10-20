/* SPDX-License-Identifier: MIT */
#ifndef G16S_CAPTURE_H
#define G16S_CAPTURE_H
#include "g16s_main.h"

/* The initial read uses the source-supported42/42 bootstrap geometry. The
 * captured root must confirm it before any pointer is followed. No fallback
 * geometry is guessed on a mismatch. Physical RAM bounds remain independent. */
struct g16s_capture {
	g16_u64 root_va, main_va, first_body_va;
	g16_u8 root[G16S_ROOT_SIZE];
	g16_u8 main_header[8], first_body[16], main[G16S_MAIN_CAPTURE_SIZE];
};
static inline enum g16s_error g16s_capture_collect(const struct g16s_reader *reader,
	g16_u64 table, g16_u64 root_va, struct g16s_capture *capture)
{
	struct g16s_root geometry = {.ias = 42, .oas = 42}, root;
	struct g16s_request request;
	enum g16s_error error;
	unsigned int i;
	if (!capture) return G16S_SIZE;
	for (i = 0; i < 3; i++) {
		geometry.level[i].shift = (g16_u8)(36 - i * 11);
		geometry.level[i].entries = (g16_u16)(i ? 2048 : 64);
		geometry.level[i].phys_mask = 0x3ffffffc000ull;
		geometry.level[i].index_mask = ((g16_u64)geometry.level[i].entries - 1) << geometry.level[i].shift;
	}
	capture->root_va = root_va;
	error = g16s_read_virtual(reader, &geometry, table, root_va, capture->root, sizeof(capture->root));
	if (error) return error;
	error = g16s_decode_root(capture->root, sizeof(capture->root), &root);
	if (error) return error;
	if (root.ias != 42 || root.oas != 42) return G16S_GEOMETRY;
	error = g16s_main_header_request(&root, &request);
	if (error) return error;
	capture->main_va = request.address;
	error = g16s_read_virtual(reader, &root, table, request.address, capture->main_header, request.size);
	if (error) return error;
	error = g16s_hwdata_first_request(&root, capture->main_header, sizeof(capture->main_header), &request);
	if (error) return error;
	capture->first_body_va = request.address;
	error = g16s_read_virtual(reader, &root, table, request.address, capture->first_body, request.size);
	if (error) return error;
	/* Source correspondences identify the first word as chip ID. Refuse an
	 * unexpected chip rather than interpreting the remaining words as a profile. */
	if (g16s_le32(capture->first_body) != 0x6040) return G16S_CHIP;
	return g16s_read_virtual(reader, &root, table, capture->main_va, capture->main, sizeof(capture->main));
}
#endif
