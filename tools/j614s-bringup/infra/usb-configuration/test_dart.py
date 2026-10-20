#!/usr/bin/env python3
"""Actual-source DART command/exception controls with mock register memory only."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import types

HERE=Path(__file__).resolve().parent
m=types.ModuleType('port_source_helpers');exec(compile((HERE/'port.py').read_bytes(),'port.py','exec'),m.__dict__)
PREFIX=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
typedef uint32_t u32;typedef uint16_t u16;typedef uint8_t u8;typedef unsigned long long u64;
typedef int irqreturn_t;
#define IRQ_NONE 0
#define IRQ_HANDLED 1
#define BIT(n) (1U<<(n))
#define U32_MAX UINT32_MAX
#define GENMASK(h,l) ((UINT32_MAX>>(31-(h))) & (UINT32_MAX<<(l)))
#define FIELD_PREP(mask,v) (((v)<<__builtin_ctz(mask))&(mask))
#define FIELD_GET(mask,v) (((v)&(mask))>>__builtin_ctz(mask))
#define BITS_TO_U32(n) ((int)(((n)+31)/32))
#define DIV_ROUND_UP(n,d) (((n)+(d)-1)/(d))
#define for_each_set_bit(n,p,max) for ((n)=0;(n)<(__typeof__(n))(max);(n)++) if ((p)[(n)/64]&(1UL<<((n)%64)))
#define __set_bit(n,p) ((p)[(n)/64]|=1UL<<((n)%64))
#define spin_lock_irqsave(p,f) do {(void)(p);(f)=0;} while (0)
#define spin_unlock_irqrestore(p,f) do {(void)(p);(void)(f);} while (0)
static unsigned barriers;
#define dma_wmb() do {barriers++;} while (0)
#define dsb(x) do {barriers++;} while (0)
static void log_mock(const char *format,...) {(void)format;}
#define dev_err(dev,...) do {(void)(dev);log_mock(__VA_ARGS__);} while (0)
#define dev_dbg(dev,...) do {(void)(dev);log_mock(__VA_ARGS__);} while (0)
#define dev_err_ratelimited(dev,...) do {(void)(irq);(void)(dev);log_mock(__VA_ARGS__);} while (0)
#define DART_T8110 2
struct apple_dart_hw {int type;};
struct apple_dart {void *dev;void *regs;unsigned num_streams;u16 version;int lock;const struct apple_dart_hw *hw;};
struct apple_dart_stream_map {struct apple_dart *dart;unsigned long sidmap[4];};
static u32 mmio[0xc000/4];static u32 commands[1024];static unsigned command_count;
static unsigned pending_reads,post_reads;static bool issued;
static u32 readl(void *ptr) {
 size_t off=(unsigned char *)ptr-(unsigned char *)mmio;assert(off<sizeof(mmio) && !(off%4));
 if (off==0x80) {
  if (!issued && pending_reads) {pending_reads--;return BIT(31);}
  if (issued && post_reads) {post_reads--;return BIT(31);}
  return 0;
 }
 return mmio[off/4];
}
static void writel(u32 value,void *ptr) {
 size_t off=(unsigned char *)ptr-(unsigned char *)mmio;assert(off<sizeof(mmio) && !(off%4));
 if (off==0x80) {
  assert(command_count<1024);commands[command_count++]=value;issued=true;
  if (((value>>8)&7)==4) mmio[0x210/4]&=~BIT(1);
 } else if (off>=0x4000 && off<0x4020) mmio[off/4]&=~value;
 else if (off==0x704) mmio[off/4]&=~value;
 else mmio[off/4]=value;
}
#define readl_poll_timeout_atomic(addr,value,condition,delay,timeout) ({ \
 int _ret=-110;unsigned _max=(timeout)/(delay)+1; \
 for (unsigned _i=0;_i<_max;_i++) {(value)=readl(addr);if (condition) {_ret=0;break;}} _ret;})
static void reset_mock(void) {memset(mmio,0,sizeof(mmio));command_count=0;pending_reads=0;post_reads=0;issued=false;barriers=0;}
'''
MAIN=r'''
int main(int argc,char **argv) {
 struct apple_dart_hw hw={.type=DART_T8110};
 struct apple_dart dart={.regs=mmio,.num_streams=256,.version=0x0202,.hw=&hw};
 struct apple_dart_stream_map map={.dart=&dart};
 if (argc==2 && !strcmp(argv[1],"command")) {
  __set_bit(0,map.sidmap);reset_mock();
  if (apple_dart_t8110_hw_tlb_command(&map,1) || command_count!=1 || commands[0]!=0x8100) return 17;
  assert(barriers<=8);return 0;
 }
 if (argc==2 && !strcmp(argv[1],"irq")) {
  reset_mock();mmio[0x4000/4]=BIT(1);mmio[(0x8000+0x40)/4]=3;
  if (apple_dart_t8110_irq(0,&dart)!=IRQ_HANDLED || mmio[0x4000/4]) return 18;
  return 0;
 }
#ifndef CANDIDATE
 return 19;
#else
 const unsigned versions[]={0x0100,0x0200,0x0201,0x0202,0x0203};
 const unsigned sids[]={0,1,31,32,255};
 for (unsigned v=0;v<5;v++) for (unsigned s=0;s<5;s++) {
  dart.version=versions[v];memset(map.sidmap,0,sizeof(map.sidmap));__set_bit(sids[s],map.sidmap);
  reset_mock();assert(!apple_dart_t8110_hw_tlb_command(&map,1));
  assert(command_count==1 && commands[0]==(0x100|sids[s]|(dart.version>=0x202?0x8000:0)));
 }
 dart.version=0x202;memset(map.sidmap,0,sizeof(map.sidmap));__set_bit(1,map.sidmap);
 reset_mock();pending_reads=2200;assert(apple_dart_t8110_hw_tlb_command(&map,1)==-110 && !command_count);
 reset_mock();pending_reads=500;assert(!apple_dart_t8110_hw_tlb_command(&map,1) && command_count==1);
 reset_mock();post_reads=2200;assert(apple_dart_t8110_hw_tlb_command(&map,1)==-110 && command_count==1);
 reset_mock();assert(!apple_dart_t8110_v2_unlock(&dart) && !command_count);
 mmio[0x210/4]=BIT(1);assert(!apple_dart_t8110_v2_unlock(&dart) && commands[0]==0x400 && !mmio[0x210/4]);
 reset_mock();dart.num_streams=64;mmio[0x4000/4]=BIT(1);mmio[0x4004/4]=BIT(31);mmio[0x210/4]=BIT(1);
 assert(apple_dart_t8110_irq(0,&dart)==IRQ_HANDLED && !mmio[0x4000/4] && !mmio[0x4004/4] && commands[0]==0x400);
 reset_mock();mmio[0x4000/4]=BIT(1);apple_dart_drain_stale_exceptions(&dart);assert(!mmio[0x4000/4]);
 reset_mock();dart.version=0x0201;mmio[0x100/4]=BIT(31)|BIT(3);
 assert(apple_dart_t8110_irq(0,&dart)==IRQ_HANDLED && !command_count);
 assert(barriers<=8);
 puts("PASS25 version/SID combinations; prebusy/postbusy/unlock/v2IRQ/stale/legacy controls");
 return 0;
#endif
}
'''


def translation_unit(source,candidate):
    # Exact source definitions; no command expression is reimplemented here.
    lines=source.splitlines();definitions=[];i=0
    while i<len(lines):
        if lines[i].startswith('#define DART_'):
            definitions.append(lines[i])
            while lines[i].endswith('\\'):
                i+=1;definitions.append(lines[i])
        i+=1
    defines='\n'.join(definitions)
    names=['apple_dart_t8110_hw_tlb_command']
    if candidate:names+=['apple_dart_t8110_v2_fault_name','apple_dart_drain_stale_exceptions','apple_dart_t8110_v2_unlock','apple_dart_t8110_legacy_irq','apple_dart_t8110_v2_block_pending','apple_dart_t8110_v2_irq']
    names+=['apple_dart_t8110_irq']
    return PREFIX+'\n'+defines+'\n'+'\n\n'.join(m.function(source,n) for n in names)+'\n'+MAIN


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--baseline',type=Path,required=True);ap.add_argument('--candidate',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();results=[]
    with tempfile.TemporaryDirectory(prefix='dart-v22-host-') as temp:
        root=Path(temp)
        for cc in ('gcc','clang'):
            for candidate,path in ((False,a.baseline),(True,a.candidate)):
                text=path.read_text();src=root/'host.c';binary=root/'host';src.write_text(translation_unit(text,candidate))
                flags=['-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all']
                build=subprocess.run([cc,*flags,*(['-DCANDIDATE'] if candidate else []),str(src),'-o',str(binary)],capture_output=True,text=True)
                if build.returncode:
                    diagnostic=build.stderr.replace(str(root),'host-test')
                    a.output.with_suffix('.compile-failure.json').write_text(json.dumps(dict(compiler=cc,candidate=candidate,diagnostic=diagnostic),indent=2)+'\n')
                    raise ValueError(diagnostic)
                runs=[]
                for case in (['command','irq','full'] if candidate else ['command','irq']):
                    run=subprocess.run([str(binary),*([case] if case!='full' else [])],capture_output=True,text=True)
                    expected=0 if candidate else (17 if case=='command' else 18)
                    if run.returncode!=expected or run.stderr:raise ValueError('Unexpected host result '+repr((cc,candidate,case,run.returncode,run.stderr)))
                    runs.append(dict(case=case,exit=run.returncode,stdout=run.stdout.strip(),stderr_bytes=0))
                results.append(dict(compiler=cc,compiler_version=subprocess.check_output([cc,'--version'],text=True).splitlines()[0],candidate=candidate,flags=flags,runs=runs,source_sha256=hashlib.sha256(text.encode()).hexdigest()))
    a.output.write_text(json.dumps(dict(status='PASS (mocked actual-source controls)',hardware='UNTESTED',runs=results),indent=2,sort_keys=True)+'\n');print('PASS baseline command/IRQ causal failures + candidate controls on GCC/Clang fatal sanitizers')
