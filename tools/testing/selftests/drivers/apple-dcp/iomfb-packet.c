// SPDX-License-Identifier: GPL-2.0-only OR MIT
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
#include "iomfb-packet.h"

int main(void)
{
	assert(iomfb_packet_bounds_valid(0, 12));
	assert(iomfb_packet_bounds_valid(0x7fc0, 64));
	assert(!iomfb_packet_bounds_valid(0, 11));
	assert(!iomfb_packet_bounds_valid(0x8000, 12));
	assert(!iomfb_packet_bounds_valid(0x7fc0, 65));
	assert(!iomfb_packet_bounds_valid(UINT32_MAX, 12));
	assert(!iomfb_packet_bounds_valid(0, UINT32_MAX));
	assert(iomfb_packet_lengths_valid(12, 0, 0));
	assert(iomfb_packet_lengths_valid(64, 4, 48));
	assert(!iomfb_packet_lengths_valid(12, 0, 0x8000));
	assert(!iomfb_packet_lengths_valid(12, UINT32_MAX, 1));
	assert(!iomfb_packet_lengths_valid(11, 0, 0));
	assert(!iomfb_packet_lengths_valid(16, 0, 0));
	puts("IOMFB callback envelope boundaries passed");
	return 0;
}
