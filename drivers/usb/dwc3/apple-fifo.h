/* SPDX-License-Identifier: GPL-2.0 */
#ifndef __DWC3_APPLE_FIFO_H
#define __DWC3_APPLE_FIFO_H

/* FIFO0 is reserved for EP0; a zero result means no safe assignment. */
static inline unsigned int
dwc3_apple_tx_fifo_select(unsigned int eligible, unsigned int busy,
			  unsigned int preferred, unsigned int owned)
{
	unsigned int fifo;

	eligible &= ~busy & 0xfffeU;
	if (owned)
		return owned < 16 && (eligible & (1U << owned)) ? owned : 0;
	if (preferred < 16 && (eligible & (1U << preferred)))
		return preferred;
	for (fifo = 1; fifo < 16; fifo++)
		if (eligible & (1U << fifo))
			return fifo;
	return 0;
}

#endif
