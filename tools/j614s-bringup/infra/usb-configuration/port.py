#!/usr/bin/env python3
"""Offline narrow source port; never imports target code."""
from pathlib import Path
import argparse
import hashlib
import re


def function(source,name):
    pattern=r'^static [^;{}]*\b'+re.escape(name)+r'\([^;{}]*\)\s*\{'
    match=re.search(pattern,source,re.M)
    if not match:raise ValueError('function not found: '+name)
    depth=1;end=match.end()
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[match.start():end]


def port(old,new):
    expected_old='e3befe0b737fafd5f46c9b38a286b9dbf79e6ce1730c11f8740af3305126e11d'
    expected_base='c3cae72eacf30c5a0592bda4490a6f6e5e850aca7342b2a93f3a68e0cb37d4c5'
    if hashlib.sha256(old.encode()).hexdigest()!=expected_old or hashlib.sha256(new.encode()).hexdigest()!=expected_base:
        raise ValueError('Pinned old/base DART source differs; refuse mutation')
    new=new.replace('#define DART_T8110_TLB_CMD_OP_FLUSH_SID 1',
        '#define DART_T8110_TLB_CMD_OP_FLUSH_SID 1\n#define DART_T8110_TLB_CMD_OP_FLUSH_UNLOCK 4\n#define DART_T8110_TLB_CMD_V2 BIT(15)\n#define DART_T8110_FLUSH_BUSY_TIMEOUT 2000')
    regs=old[old.index('#define DART_T8110_EXCEPTION(i)'):old.index('#define DART_T8110_PROTECT 0x200')]
    # Adjacent old definitions include only exception/status/diagnostic registers.
    new=new.replace('#define DART_T8110_PROTECT 0x200',regs+'#define DART_T8110_PROTECT 0x200')
    new=new.replace('#define DART_T8110_PROTECT_TTBR_TCR BIT(0)',
        '#define DART_T8110_PROTECT_TTBR_TCR BIT(0)\n#define DART_T8110_DIAG_LOCK 0x210\n#define DART_T8110_DIAG_LOCK_ON_ERR BIT(1)')
    new=new.replace('\tu32 num_streams;\n\tu32 supports_bypass', '\tu32 num_streams;\n\tu16 version;\n\tu32 supports_bypass')
    new=new.replace(' * @supports_bypass: indicates if this DART supports bypass mode',
        ' * @version: T8110 PARAMS3 hardware revision\n * @supports_bypass: indicates if this DART supports bypass mode')
    body=function(new,'apple_dart_t8110_hw_tlb_command')
    revised=body.replace('\tint sid;', '\tint sid;\n\tu32 timeout = dart->version >= 0x0202 ?\n\t\tDART_T8110_FLUSH_BUSY_TIMEOUT : DART_STREAM_COMMAND_BUSY_TIMEOUT;')
    revised=revised.replace('\t\twritel(val, dart->regs + DART_T8110_TLB_CMD);', '''\t\tif (dart->version >= 0x0202) {
\t\t\tu32 status;

\t\t\tret = readl_poll_timeout_atomic(dart->regs + DART_T8110_TLB_CMD,
\t\t\t\t\t\t\tstatus,
\t\t\t\t\t\t\t!(status & DART_T8110_TLB_CMD_BUSY),
\t\t\t\t\t\t\t1, timeout);
\t\t\tif (ret)
\t\t\t\tbreak;
\t\t\tif (command == DART_T8110_TLB_CMD_OP_FLUSH_SID)
\t\t\t\tval |= DART_T8110_TLB_CMD_V2;
\t\t}
\t\tdma_wmb();
\t\twritel(val, dart->regs + DART_T8110_TLB_CMD);''')
    # The barrier is harmless but retain the legacy command body byte-for-byte
    # except timeout expression: use it only on the new revision branch.
    revised=revised.replace('\t\t}\n\t\tdma_wmb();', '\t\t\tdma_wmb();\n\t\t}')
    revised=revised.replace('DART_STREAM_COMMAND_BUSY_TIMEOUT);','timeout);')
    new=new.replace(body,revised)
    helpers=function(old,'apple_dart_t8110_v2_fault_name')+'\n\n'+function(old,'apple_dart_drain_stale_exceptions')+'\n\n'+function(old,'apple_dart_t8110_v2_unlock')
    helpers=helpers.replace('apple_dart_t8110_hw_tlb_command_range(&stream_map,\n\t\t\t\t\t    DART_T8110_TLB_CMD_OP_FLUSH_UNLOCK,\n\t\t\t\t\t    false, 0, 0)', 'apple_dart_t8110_hw_tlb_command(&stream_map,\n\t\t\t\t\t    DART_T8110_TLB_CMD_OP_FLUSH_UNLOCK)')
    if 'hw_tlb_command_range' in helpers:raise ValueError('unlock adaptation failed')
    helpers=helpers.replace('\n\t\t\t\t "stale', '\n\t\t\t\t"stale').replace('\n\t\t\t "%u stale', '\n\t\t\t"%u stale')
    new=new.replace('static int apple_dart_hw_reset(struct apple_dart *dart)',helpers+'\n\nstatic int apple_dart_hw_reset(struct apple_dart *dart)')
    new=new.replace('''\t/* clear any pending errors before the interrupt is unmasked */
\twritel(readl(dart->regs + dart->hw->error), dart->regs + dart->hw->error);''','''\t/* v2 exceptions use per-stream W1C records and a lock-on-error latch. */
\tif (dart->hw->type == DART_T8110 && dart->version >= 0x0202) {
\t\tint ret;

\t\tapple_dart_drain_stale_exceptions(dart);
\t\tret = apple_dart_t8110_v2_unlock(dart);
\t\tif (ret)
\t\t\treturn ret;
\t} else {
\t\t/* Legacy status/acknowledgment semantics are unchanged. */
\t\twritel(readl(dart->regs + dart->hw->error),
\t\t       dart->regs + dart->hw->error);
\t}''')
    legacy=function(new,'apple_dart_t8110_irq')
    v2=function(old,'apple_dart_t8110_v2_block_pending')+'\n\n'+function(old,'apple_dart_t8110_v2_irq')
    wrapper='''static irqreturn_t apple_dart_t8110_irq(int irq, void *dev)
{
\tstruct apple_dart *dart = dev;

\tif (dart->version >= 0x0202)
\t\treturn apple_dart_t8110_v2_irq(irq, dev);

\treturn apple_dart_t8110_legacy_irq(irq, dev);
}'''
    new=new.replace(legacy,legacy.replace('apple_dart_t8110_irq','apple_dart_t8110_legacy_irq',1)+'\n\n'+v2+'\n\n'+wrapper)
    new=new.replace('\t\tdart->four_level = dart->ias > 36;\n', '\t\tdart->four_level = dart->ias > 36;\n\t\tdart->version = dart_params[2] & GENMASK(15, 0);\n')
    new=new.replace('\tret = request_irq(dart->irq, apple_dart_irq, IRQF_SHARED,', '\tif (dart->locked)\n\t\tapple_dart_drain_stale_exceptions(dart);\n\n\tret = request_irq(dart->irq, apple_dart_irq, IRQF_SHARED,')
    return new


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--old',type=Path,required=True);ap.add_argument('--new',type=Path,required=True);a=ap.parse_args()
    a.new.write_text(port(a.old.read_text(),a.new.read_text()))
