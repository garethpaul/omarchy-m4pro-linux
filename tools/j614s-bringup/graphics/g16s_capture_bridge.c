/* SPDX-License-Identifier: MIT */
#include "g16s_capture.h"
int g16s_capture_bridge(const struct g16s_reader *reader, g16_u64 table,
	g16_u64 root_va, struct g16s_capture *capture)
{
	return (int)g16s_capture_collect(reader, table, root_va, capture);
}

size_t g16s_capture_size(void) { return sizeof(struct g16s_capture); }
