/* SPDX-License-Identifier: MIT */
#include "g16s_main.h"
#include <inttypes.h>
#include <stdio.h>

static size_t read_capture(const char *path, g16_u8 *out, size_t size)
{
	FILE *file = fopen(path, "rb");
	size_t count;
	if (!file) return 0;
	count = fread(out, 1, size, file);
	if (ferror(file)) count = 0;
	fclose(file);
	return count;
}
int main(int argc, char **argv)
{
	g16_u8 root_bytes[G16S_ROOT_SIZE+1], main_bytes[G16S_PAGE_SIZE+1];
	struct g16s_root root;
	struct g16s_main main;
	enum g16s_error error;
	unsigned int bad_offset = 0;
	size_t size;
	if (argc != 3) {
		fprintf(stderr,"usage: %s captured-root.bin captured-main.bin\n",argv[0]);
		return 2;
	}
	size = read_capture(argv[1],root_bytes,sizeof(root_bytes));
	error = g16s_decode_root(root_bytes,size,&root);
	if (error != G16S_OK) {
		fprintf(stderr,"root rejected: error=%d\n",(int)error); return 1;
	}
	size = read_capture(argv[2],main_bytes,sizeof(main_bytes));
	if (size > G16S_PAGE_SIZE) {
		fprintf(stderr,"main capture exceeds one page\n"); return 1;
	}
	error = g16s_decode_main(main_bytes,size,&main);
	if (error != G16S_OK) {
		fprintf(stderr,"main rejected: error=%d\n",(int)error); return 1;
	}
	error = g16s_check_main_pointers(&root,&main,&bad_offset);
	printf("{\"hardware_validated\":false,\"safe_to_publish_init\":false,"
	       "\"pointer_check_error\":%d,\"first_bad_offset\":%u,"
	       "\"hwdata\":\"0x%016" PRIx64 "\",\"log_enable\":%u,"
	       "\"descriptor_2e0\":\"0x%016" PRIx64 "\","
	       "\"descriptor_2f0\":\"0x%016" PRIx64 "\","
	       "\"power_471\":\"0x%016" PRIx64 "\"}\n",
	       (int)error,bad_offset,main.hwdata,(unsigned int)main.log_enable,
	       main.descriptor_2e0,main.descriptor_2f0,main.power_471);
	return error == G16S_OK ? 0 : 1;
}
