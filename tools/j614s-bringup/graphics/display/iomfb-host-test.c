// SPDX-License-Identifier: GPL-2.0-only OR MIT
/* The driver function bodies/declarations are extracted unchanged by the runner.
 * Only the Linux logging, DMA barriers and callback boundary are replaced. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
#define __packed __attribute__((packed))
#define BIT_ULL(n) (1ULL << (n))
#define GENMASK_ULL(h, l) ((~0ULL >> (63 - (h))) & (~0ULL << (l)))
#define FIELD_GET(mask, x) (((x) & (mask)) >> __builtin_ctzll(mask))
#define ALIGN(x, a) (((x) + ((a) - 1)) & ~((a) - 1))
static unsigned warnings, callbacks, completions, read_barriers;
static unsigned barrier_before_ack;
#define WARN_ON(x) ((x) ? (++warnings, true) : false)
#define dev_warn(dev, ...) ((void)(dev), (void)++warnings)
#define dma_rmb() ((void)++read_barriers)
struct device { int unused; };
struct apple_dcp;
typedef void (*dcp_callback_t)(struct apple_dcp *, void *, void *);
#include "iomfb-declarations.inc"
struct apple_dcp {
 struct device *dev;
 void *shmem;
 struct dcp_channel ch_cb, ch_cmd, ch_oobcb, ch_oobcmd, ch_async, ch_oobasync;
 const struct iomfb_cb_contract *cb_contracts;
 bool (**cb_handlers)(struct apple_dcp *, int, void *, void *);
};
static void dcp_ack(struct apple_dcp *dcp, enum dcp_context_id context);
#include "iomfb-functions.inc"
static void dcp_ack(struct apple_dcp *dcp, enum dcp_context_id context)
{ /* Callback return is false in these tests; unexpected ACK is observable. */
 (void)dcp; (void)context; ++warnings;
}
static bool callback(struct apple_dcp *dcp, int tag, void *out, void *in)
{ (void)dcp; (void)tag; (void)out; (void)in; ++callbacks; return false; }
static void *expected_output;
static void completion(struct apple_dcp *dcp, void *out, void *cookie)
{ (void)dcp; if (out != expected_output || cookie != (void *)0x1234 ||
                         read_barriers <= barrier_before_ack) {
 fputs("FAIL: ACK did not use the saved output and cookie\n", stderr); exit(1);
 } ++completions; }
static void require(bool yes, const char *message)
{ if (!yes) { fprintf(stderr, "FAIL: %s\n", message); exit(1); } }
static u64 msg(unsigned context, unsigned offset, u32 length, bool ack)
{ return 2 | ((u64)context << 8) | ((u64)offset << 16) |
         ((u64)length << 32) | (ack ? 64 : 0); }
int main(int argc, char **argv)
{
 bool baseline = argc == 2 && !strcmp(argv[1], "--expect-baseline-bug");
 bool (*handlers[1000])(struct apple_dcp *, int, void *, void *) = { [1] = callback };
 struct device dev = { 0 };
 struct apple_dcp dcp = { .dev = &dev, .cb_handlers = handlers };
 dcp.shmem = malloc(DCP_SHMEM_SIZE);
 require(dcp.shmem != NULL, "allocation");
 memset(dcp.shmem, 0xa5, DCP_SHMEM_SIZE);
 struct dcp_packet_header header = { .tag = {'1','0','0','D'}, .in_len = 0,
                                     .out_len = 0x8000 };
 memcpy((u8 *)dcp.shmem + 0x60000, &header, sizeof(header));
 dcpep_got_msg(&dcp, msg(DCP_CONTEXT_CB, 0, 12, false));
 if (baseline) {
  require(callbacks == 1 && ((u8 *)dcp.shmem)[0x68000] == 0,
          "baseline malformed callback must cross its channel boundary");
  puts("REPRODUCED: actual driver invokes malformed callback and clears beyond its 32KiB channel");
  free(dcp.shmem); return 0;
 }
 require(callbacks == 0 && ((u8 *)dcp.shmem)[0x68000] == 0xa5,
         "malformed callback must be rejected before output clearing or dispatch");
 require(dcp.ch_cb.depth == 0, "rejection changes no stack state");
 /* Short wire header, channel overrun, sum overflow, mismatched lengths, depth. */
 const struct { u16 off; u32 len, in, out; u8 depth; } bad[] = {
  {0, 0, 0, 0, 0}, {0, 11, 0, 0, 0}, {0x8000, 12, 0, 0, 0},
  {0x7fc0, 65, 0, 53, 0}, {0, 12, UINT32_MAX, 1, 0},
  {0, 16, 0, 0, 0}, {0, 12, 0, 0, DCP_MAX_CALL_DEPTH}
 };
 for (unsigned i=0; i<sizeof(bad)/sizeof(bad[0]); ++i) {
  header.in_len=bad[i].in; header.out_len=bad[i].out;
  if (bad[i].off < 0x8000)
   memcpy((u8 *)dcp.shmem+0x60000+bad[i].off, &header, sizeof(header));
  dcp.ch_cb.depth=bad[i].depth;
  dcpep_got_msg(&dcp, msg(DCP_CONTEXT_CB,bad[i].off,bad[i].len,false));
  require(!callbacks && dcp.ch_cb.depth==bad[i].depth, "invalid callback mutated state");
 }
 dcp.ch_cb.depth=0;
 /* Exact header+in+out length and last aligned channel slot are valid. */
 header.in_len=4; header.out_len=48;
 memcpy((u8 *)dcp.shmem+0x67fc0,&header,sizeof(header));
 dcpep_got_msg(&dcp,msg(DCP_CONTEXT_CB,0x7fc0,64,false));
 require(callbacks==1 && dcp.ch_cb.depth==1 && dcp.ch_cb.end[0]==0x8000,
         "valid boundary callback must dispatch and retain nesting state");
 /* Zero-length ACK has no packet header. Saved host output is authoritative. */
 expected_output=(u8 *)dcp.shmem+0x1234;
 dcp.ch_cmd.depth=1; dcp.ch_cmd.callbacks[0]=completion;
 dcp.ch_cmd.cookies[0]=(void *)0x1234; dcp.ch_cmd.output[0]=expected_output;
 barrier_before_ack=read_barriers;
 dcpep_got_msg(&dcp,msg(DCP_CONTEXT_CMD,0,0,true));
 require(completions==1 && !dcp.ch_cmd.depth && !dcp.ch_cmd.callbacks[0], "valid ACK completion");
 dcpep_got_msg(&dcp,msg(DCP_CONTEXT_CMD,0,0,true));
 require(completions==1 && !dcp.ch_cmd.depth, "unsolicited ACK must not underflow");
 dcpep_got_msg(&dcp,msg(1,0,12,false));
 puts("PASS: actual receive functions reject malformed bounds/depth and preserve valid callback/ACK behavior");
 require(warnings != 0, "negative cases must report rejection");
 free(dcp.shmem); return 0;
}
