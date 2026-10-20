// SPDX-License-Identifier: GPL-2.0-only OR MIT
/* Uses actual D006 struct declarations, handler, typed trampoline and receive
 * functions. Only the Linux boundaries are replaced, as in the envelope test. */
#include "iomfb-host-prefix.inc"
#define __maybe_unused __attribute__((unused))
#define trace_iomfb_callback(...) ((void)++callbacks)
#include "iomfb-typed-callback.inc"
#include "iomfb-functions.inc"
static void dcp_ack(struct apple_dcp *dcp, enum dcp_context_id context)
{ ++completions; --dcp_get_channel(dcp,context)->depth; }
static void require(bool yes,const char *reason)
{ if (!yes) { fprintf(stderr,"FAIL: %s\n",reason); exit(1); } }
static u64 typed_msg(u32 length) { return 2 | ((u64)length<<32); }
int main(int argc,char **argv)
{
 bool baseline=argc==2 && !strcmp(argv[1],"--expect-baseline-bug");
 bool (*handlers[1000])(struct apple_dcp*,int,void*,void*) = { [6]=trampoline_set_frame_sync_props };
 struct device dev={0};
 struct apple_dcp dcp={.dev=&dev,.cb_handlers=handlers};
#include "iomfb-typed-contract.inc"
 dcp.shmem=malloc(DCP_SHMEM_SIZE);require(dcp.shmem!=NULL,"allocation");
 /* Structurally valid input79/output80: D006 reads the80th byte from the
  * declared output span after memset has changed it. It must not dispatch. */
 struct dcp_packet_header header={.tag={'6','0','0','D'},.in_len=79,.out_len=80};
 memset(dcp.shmem,0xa5,DCP_SHMEM_SIZE);
 u8 *packet=(u8*)dcp.shmem+0x60000;
 memcpy(packet,&header,sizeof(header));memset(packet+12,0x55,79);
 dcpep_got_msg(&dcp,typed_msg(12+79+80));
 bool short_input_dispatched=callbacks==1 && completions==1 && packet[12+79+79]==0;
 if (!baseline) require(callbacks==0 && completions==0 && packet[12+79]==0xa5 && !dcp.ch_cb.depth,
                       "typed short input must reject before memset, depth change or dispatch");
 /* Full input84/output0: actual struct-return trampoline writes80 bytes
  * beyond the declared zero output, despite a structurally valid envelope. */
 header.in_len=84;header.out_len=0;callbacks=completions=0;
 memset(dcp.shmem,0xa5,DCP_SHMEM_SIZE);memcpy(packet,&header,sizeof(header));memset(packet+12,0x55,84);
 dcpep_got_msg(&dcp,typed_msg(12+84));
 bool short_output_overrun=callbacks==1 && completions==1 && packet[12+84]==0x55;
 if (baseline) {
  require(short_input_dispatched && short_output_overrun,"both typed baseline failures reproduced");
  puts("REPRODUCED: actual D006 handler/trampoline consumes undeclared input and writes80 bytes beyond declared output");
  free(dcp.shmem);return 0;
 }
 require(!callbacks && !completions && packet[12+84]==0xa5 && !dcp.ch_cb.depth,
         "typed short output must reject before memset, depth change or dispatch");
 /* A complete typed request succeeds and reproduces the actual callback's
  * copy-and-clear73..75 behavior; output suffix padding stays within the span. */
 header.out_len=80;callbacks=completions=0;
 memset(dcp.shmem,0xa5,DCP_SHMEM_SIZE);memcpy(packet,&header,sizeof(header));memset(packet+12,0x55,84);
 dcpep_got_msg(&dcp,typed_msg(12+84+80));
 require(callbacks==1 && completions==1 && !dcp.ch_cb.depth,"valid typed callback completion");
 for (unsigned i=0;i<80;i++) require(packet[12+84+i]==((i>=73 && i<=75)?0:0x55),"actual D006 output behavior");
 require(packet[12+84+80]==0xa5,"typed output sentinel");
 /* The bounds are minimum typed access extents; suffix bytes stay opaque. */
 header.in_len=85;header.out_len=81;callbacks=completions=0;
 memset(dcp.shmem,0xa5,DCP_SHMEM_SIZE);memcpy(packet,&header,sizeof(header));memset(packet+12,0x55,85);
 dcpep_got_msg(&dcp,typed_msg(12+85+81));
 require(callbacks==1 && completions==1 && packet[12+85+80]==0,
         "bounded opaque suffix remains accepted and zeroed as before");
 /* Older versions still use their unmodified handler-table path. */
 dcp.cb_contracts=NULL;header.in_len=79;header.out_len=80;callbacks=completions=0;
 memset(dcp.shmem,0xa5,DCP_SHMEM_SIZE);memcpy(packet,&header,sizeof(header));memset(packet+12,0x55,79);
 dcpep_got_msg(&dcp,typed_msg(12+79+80));
 require(callbacks==1 && completions==1,"legacy table dispatch path preserved");
 puts("PASS: typed short input/output rejected before mutation; complete D006, opaque suffix and legacy table path preserved");
 free(dcp.shmem);return 0;
}
