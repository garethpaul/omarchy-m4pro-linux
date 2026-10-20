/* SPDX-License-Identifier: GPL-2.0-only OR MIT */
#include <stdbool.h>
#include <stdint.h>
typedef uint32_t u32;
#include "iomfb-packet.h"
int display_packet_valid(uint32_t offset, uint32_t length,
                         uint32_t in_len, uint32_t out_len)
{
 return iomfb_packet_bounds_valid(offset,length) &&
        iomfb_packet_lengths_valid(length,in_len,out_len);
}
