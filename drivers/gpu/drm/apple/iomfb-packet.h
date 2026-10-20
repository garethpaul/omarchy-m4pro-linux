/* SPDX-License-Identifier: GPL-2.0-only OR MIT */
#ifndef __APPLE_IOMFB_PACKET_H__
#define __APPLE_IOMFB_PACKET_H__

#include <linux/types.h>

/* Each IOMFB context has a separate 32 KiB window in the shared buffer. */
#define IOMFB_CHANNEL_SIZE 0x8000U
#define IOMFB_PACKET_HEADER_SIZE 12U
#define IOMFB_PACKET_ALIGNMENT 0x40U

/* Check before reading the shared header. Include the aligned end because it
 * becomes the starting offset of a nested call. Subtractions avoid overflow.
 */
static inline bool iomfb_packet_bounds_valid(u32 offset, u32 length)
{
	u32 available;

	if (offset > IOMFB_CHANNEL_SIZE || length < IOMFB_PACKET_HEADER_SIZE)
		return false;

	available = IOMFB_CHANNEL_SIZE - offset;
	if (length > available)
		return false;

	return ((length + IOMFB_PACKET_ALIGNMENT - 1) &
		~(IOMFB_PACKET_ALIGNMENT - 1)) <= available;
}

/* The wire length includes the header, input and reserved output bytes.
 * This validates the envelope, not the callback-specific structure sizes.
 */
static inline bool iomfb_packet_lengths_valid(u32 length, u32 in_len, u32 out_len)
{
	if (length < IOMFB_PACKET_HEADER_SIZE ||
	    in_len > length - IOMFB_PACKET_HEADER_SIZE)
		return false;

	return out_len == length - IOMFB_PACKET_HEADER_SIZE - in_len;
}

#endif
