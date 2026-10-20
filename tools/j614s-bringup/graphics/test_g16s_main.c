/* SPDX-License-Identifier: MIT */
#include "g16s_main.h"
#include "test-fixture.h"

int main(int argc, char **argv)
{
	g16_u8 root_bytes[G16S_ROOT_SIZE], bytes[G16S_MAIN_CAPTURE_SIZE], output[32];
	struct g16s_root root;
	struct g16s_main main, sentinel;
	struct g16s_request request;
	struct g16s_range ranges[] = {{0x10000, 0x10000}};
	struct g16s_reader reader = {read_memory, NULL, ranges, 1};
	unsigned int offset;
	g16_u64 va = 0xfffffc2000100000ull;

	fixture(root_bytes);
	assert(g16s_decode_root(root_bytes, sizeof(root_bytes), &root) == G16S_OK);
	assert(g16s_main_header_request(&root, &request) == G16S_OK);
	assert(request.address == root.main_config && request.size == 8);
	put64(bytes, va);
	assert(g16s_hwdata_first_request(&root, bytes, 8, &request) == G16S_OK);
	assert(request.address == va + 0xe90 && request.size == 16);
	put64(bytes, G16S_MAX_U64 - 7);
	assert(g16s_hwdata_first_request(&root, bytes, 8, &request) == G16S_ADDRESS);
	put64(bytes, 0);
	assert(g16s_hwdata_first_request(&root, bytes, 8, &request) == G16S_ADDRESS);
	assert(g16s_hwdata_first_request(&root, bytes, 7, &request) == G16S_SIZE);

	memset(bytes, 0, sizeof(bytes));
	put64(bytes, va);
	put64(bytes+0x1a0, va+0x100); put64(bytes+0x1a8, va+0x110);
	put64(bytes+0x1b0, va+0x120); put64(bytes+0x1b8, va+0x200);
	put64(bytes+0x2e0, va+0x300); put64(bytes+0x2f0, va+0x400);
	put64(bytes+0x471, va+0x500); put32(bytes+0x250, 7);
	if (argc == 2 && !strcmp(argv[1], "--emit-fixture"))
		return fwrite(bytes, 1, sizeof(bytes), stdout) == sizeof(bytes) ? 0 : 1;
	assert(g16s_decode_main(bytes, sizeof(bytes), &main) == G16S_OK);
	assert(main.log_enable == 7 && main.power_471 == va+0x500);
	assert(g16s_check_main_pointers(&root, &main, &offset) == G16S_OK);
	main.descriptor_2f0 = 0;
	assert(g16s_check_main_pointers(&root, &main, &offset) == G16S_ADDRESS && offset == 0x2f0);
	assert(g16s_decode_main(bytes, sizeof(bytes), &main) == G16S_OK);
	main.power_471 = 1;
	assert(g16s_check_main_pointers(&root, &main, &offset) == G16S_ADDRESS && offset == 0x471);
	memset(&sentinel, 0xa5, sizeof(sentinel)); main = sentinel;
	assert(g16s_decode_main(bytes, 0x478, &main) == G16S_SIZE);
	assert(!memcmp(&main, &sentinel, sizeof(main)));

	mapping(va);
	for (offset=0; offset<16; offset++) memory[0xce90+offset] = (g16_u8)offset;
	assert(g16s_read_virtual(&reader,&root,0x10000,va+0xe90,output,16) == G16S_OK);
	for (offset=0; offset<16; offset++) assert(output[offset] == offset);
	assert(read_count == 4); /* Three table reads plus exact16-byte data read. */
	assert(g16s_read_virtual(&reader,&root,0x10000,va,output,0) == G16S_SIZE);
	assert(g16s_read_virtual(&reader,&root,0x10000,va,output,0x4001) == G16S_SIZE);

	/* A two-page request is split; its second page is independently checked. */
	mapping(va);
	put64(memory+0x8000+(((va>>14)&2047)+1)*8, 0x1c403);
	memory[0xfff8]=0x55; memory[0xc000]=0xaa;
	assert(g16s_read_virtual(&reader,&root,0x10000,va+0x3ff8,output,16) == G16S_OK);
	assert(output[0] == 0x55 && output[8] == 0xaa && read_count == 8);
	mapping(va); read_count=0;
	assert(g16s_read_virtual(&reader,&root,0x10000,va+0x3ff8,output,16) == G16S_INVALID_PTE);
	assert(read_count == 7); /* No data read occurs for the absent second page. */
	puts("PASS: G16S known MainConfig fields and staged bounded first-body capture");
	return 0;
}
