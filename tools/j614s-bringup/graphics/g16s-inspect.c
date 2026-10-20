/* SPDX-License-Identifier: MIT */
#include "g16s_abi.h"
#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>

/* An offline tool. Input is exactly one captured 0xc8-byte root. It does not
 * open /dev/mem, attach to m1n1, modify files or follow firmware pointers. */
int main(int argc, char **argv)
{
	g16_u8 bytes[G16S_ROOT_SIZE + 1];
	struct g16s_root root;
	FILE *file;
	size_t size;
	enum g16s_error error;

	if (argc != 2) {
		fprintf(stderr, "usage: %s captured-root.bin\n", argv[0]);
		return 2;
	}
	file = fopen(argv[1], "rb");
	if (!file) {
		perror("root input");
		return 2;
	}
	size = fread(bytes, 1, sizeof(bytes), file);
	if (ferror(file)) {
		fclose(file);
		fprintf(stderr, "root read failed\n");
		return 2;
	}
	fclose(file);
	error = g16s_decode_root(bytes, size, &root);
	if (error != G16S_OK) {
		fprintf(stderr, "G16S root rejected: error=%d\n", (int)error);
		return 1;
	}
	printf("{\"status\":\"DECODED_OFFLINE\",\"hardware_validated\":false,"
	       "\"root_size\":200,\"ias\":%u,\"oas\":%u,"
	       "\"main_config\":\"0x%016" PRIx64 "\","
	       "\"status_a\":\"0x%016" PRIx64 "\","
	       "\"status_b\":\"0x%016" PRIx64 "\","
	       "\"opaque_b8\":\"0x%016" PRIx64 "\","
	       "\"opaque_c0\":\"0x%016" PRIx64 "\"}\n",
	       (unsigned int)root.ias, (unsigned int)root.oas,
	       root.main_config, root.status_a, root.status_b, root.opaque_b8, root.opaque_c0);
	return 0;
}
