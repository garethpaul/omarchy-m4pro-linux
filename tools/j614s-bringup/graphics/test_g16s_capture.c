/* SPDX-License-Identifier: MIT */
#include "g16s_capture.h"
#include "test-fixture.h"
int main(void)
{
	g16_u8 bytes[G16S_ROOT_SIZE];
	struct g16s_capture captured;
	struct g16s_range ranges[]={{0x10000,0x10000}};
	struct g16s_reader reader={read_memory,NULL,ranges,1};
	g16_u64 va=0xfffffc2000100000ull;
	unsigned int i;
	fixture(bytes); put64(bytes+0x18,va+0x400);
	mapping(va); memcpy(memory+0xc000,bytes,sizeof(bytes));
	put64(memory+0xc400,va+0x800); put32(memory+0xd690,0x6040);
	assert(g16s_capture_collect(&reader,0x10000,va,&captured)==G16S_OK);
	assert(captured.main_va==va+0x400 && captured.first_body_va==va+0x1690);
	assert(g16s_le32(captured.first_body)==0x6040);
	put32(memory+0xd690,0x8132);
	assert(g16s_capture_collect(&reader,0x10000,va,&captured)==G16S_CHIP);
	put32(memory+0xd690,0x6040);
	memory[0xc000]^=1; read_count=0;
	assert(g16s_capture_collect(&reader,0x10000,va,&captured)==G16S_VERSION);
	assert(read_count==4); memory[0xc000]^=1;
	put16(memory+0xc000+0x38,128); put64(memory+0xc000+0x4c,127ull<<36);
	assert(g16s_capture_collect(&reader,0x10000,va,&captured)==G16S_GEOMETRY);
	memcpy(memory+0xc000,bytes,sizeof(bytes));
	for(i=0;i<3;i++) put64(memory+0xc000+0x44+i*0x20,0xffffffc000ull);
	assert(g16s_capture_collect(&reader,0x10000,va,&captured)==G16S_GEOMETRY);
	memcpy(memory+0xc000,bytes,sizeof(bytes));
	ranges[0]=(struct g16s_range){0x14000,0xc000}; read_count=0;
	assert(g16s_capture_collect(&reader,0x10000,va,&captured)==G16S_RANGE);
	assert(read_count==0);
	puts("PASS: shared capture collector uses exact root/body identity and bounded read-only UAT");
	return 0;
}
