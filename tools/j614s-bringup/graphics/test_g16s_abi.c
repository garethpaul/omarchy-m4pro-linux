/* SPDX-License-Identifier: MIT */
#include "test-fixture.h"
int main(int argc, char **argv)
{
	g16_u8 bytes[G16S_ROOT_SIZE], saved[G16S_ROOT_SIZE];
	struct g16s_root root, sentinel;
	struct g16s_range ranges[]={{0x10000,0x10000}};
	struct g16s_reader reader={read_memory, NULL, ranges, 1};
	struct g16s_walk result;
	g16_u64 address, va=0xfffffc2000100037ull;
	unsigned int i;
	fixture(bytes); memcpy(saved, bytes, sizeof(bytes));
	if (argc == 2 && !strcmp(argv[1], "--emit-fixture"))
		return fwrite(bytes, 1, sizeof(bytes), stdout) == sizeof(bytes) ? 0 : 1;
	assert(g16s_init_address(0x20,0x00810c2000100000ull,&address)==G16S_OK);
	assert(address==0xfffffc2000100000ull);
	assert(g16s_init_address(0x21,0x00810c2000100000ull,&address)==G16S_MESSAGE);
	assert(g16s_init_address(0x20,0x00820c2000100000ull,&address)==G16S_MESSAGE);
	assert(g16s_init_address(0x20,0x00810c2000100001ull,&address)==G16S_ALIGNMENT);
	assert(g16s_decode_root(bytes,sizeof(bytes),&root)==G16S_OK);
	assert(root.ias==42 && root.oas==42 && root.level[0].entries==64);
	assert(root.opaque_b8==0x0123456789abcdefull && root.opaque_c0==0xfedcba9876543210ull);
	memset(&sentinel,0xa5,sizeof(sentinel)); root=sentinel;
	bytes[0]^=1;
	assert(g16s_decode_root(bytes,sizeof(bytes),&root)==G16S_VERSION);
	assert(memcmp(&root,&sentinel,sizeof(root))==0);
	memcpy(bytes,saved,sizeof(bytes)); put64(bytes,0x0c89c357839204b8ull);
	assert(g16s_decode_root(bytes,sizeof(bytes),&root)==G16S_VERSION); /* Gravity mismatch */
	memcpy(bytes,saved,sizeof(bytes)); put32(bytes+0x2c,0);
	assert(g16s_decode_root(bytes,sizeof(bytes),&root)==G16S_UNMAPPED);
	assert(g16s_decode_root(bytes,0xb8,&root)==G16S_SIZE); /* G17 primary is too short */
	for(i=0;i<3;i++) {
		memcpy(bytes,saved,sizeof(bytes)); bytes[0x34+i*0x20+3]++;
		assert(g16s_decode_root(bytes,sizeof(bytes),&root)==G16S_GEOMETRY);
		memcpy(bytes,saved,sizeof(bytes)); put64(bytes+0x34+i*0x20+16,0x3fffffec000ull);
		assert(g16s_decode_root(bytes,sizeof(bytes),&root)==G16S_GEOMETRY);
	}
	memcpy(bytes,saved,sizeof(bytes)); put64(bytes+0x34+24,0);
	assert(g16s_decode_root(bytes,sizeof(bytes),&root)==G16S_GEOMETRY);
	memcpy(bytes,saved,sizeof(bytes));
	assert(g16s_decode_root(bytes,sizeof(bytes),&root)==G16S_OK);
	mapping(va); assert(g16s_walk_page(&reader,&root,0x10000,va,&result)==G16S_OK);
	assert(result.physical==0x1c037 && read_count==3);
	mapping(va); assert(g16s_walk_page(&reader,&root,0x10000,va&0x3ffffffffffull,&result)==G16S_OK);
	assert(g16s_walk_page(&reader,&root,0x10001,va,&result)==G16S_ALIGNMENT);
	read_count=0; assert(g16s_walk_page(&reader,&root,0x30000,va,&result)==G16S_RANGE);
	assert(read_count==0); /* Not one unauthorized physical read. */
	assert(g16s_walk_page(&reader,&root,0x10000,0x8000000000000000ull,&result)==G16S_ADDRESS);
	mapping(va); put64(memory+((va>>36)&63)*8,0x14001);
	assert(g16s_walk_page(&reader,&root,0x10000,va,&result)==G16S_BLOCK_PTE);
	mapping(va); put64(memory+0x4000+((va>>25)&2047)*8,0);
	assert(g16s_walk_page(&reader,&root,0x10000,va,&result)==G16S_INVALID_PTE);
	mapping(va); fail_read=1;
	assert(g16s_walk_page(&reader,&root,0x10000,va,&result)==G16S_READ); fail_read=0;
	mapping(va); root.level[0].shift=255; read_count=0;
	assert(g16s_walk_page(&reader,&root,0x10000,va,&result)==G16S_GEOMETRY);
	assert(read_count==0);
	assert(!g16s_in_range(&reader,G16S_MAX_U64-4,8));
	ranges[0]=(struct g16s_range){G16S_MAX_U64-4,8};
	assert(!g16s_in_range(&reader,G16S_MAX_U64-4,1));
	puts("PASS: synthetic G16S envelope, mismatch rejection, bounded read-only page walk");
	return 0;
}
