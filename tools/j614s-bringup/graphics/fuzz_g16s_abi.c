/* SPDX-License-Identifier: MIT */
#include "g16s_abi.h"
#include <string.h>

static int zeros(void *cookie, g16_u64 address, g16_u8 *out, size_t size)
{
	(void)cookie; (void)address;
	memset(out, 0, size);
	return 0;
}
int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
	struct g16s_root root;
	struct g16s_walk walk;
	struct g16s_range ram = {0x10000, 1ull << 42};
	struct g16s_reader reader = {zeros, NULL, &ram, 1};
	g16_u64 address;

	(void)g16s_decode_root(data, size, &root);
	if (size >= 12)
		(void)g16s_init_address(g16s_le32(data), g16s_le64(data+4), &address);
	if (size >= sizeof(root)) {
		memcpy(&root, data, sizeof(root));
		(void)g16s_walk_page(&reader, &root, 0x10000, 0, &walk);
	}
	return 0;
}
