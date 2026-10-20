/* Freestanding AArch64 test: pinned processes share an atomic counter in RAM. */
typedef unsigned long u64;
static long sys(long n,long a,long b,long c,long d,long e,long f) {
 register long x0 __asm__("x0")=a,x1 __asm__("x1")=b,x2 __asm__("x2")=c;
 register long x3 __asm__("x3")=d,x4 __asm__("x4")=e,x5 __asm__("x5")=f,x8 __asm__("x8")=n;
 __asm__ volatile("svc #0":"+r"(x0):"r"(x1),"r"(x2),"r"(x3),"r"(x4),"r"(x5),"r"(x8):"memory","cc");return x0;
}
static void text(const char *s) {u64 n=0;while(s[n])n++;sys(64,1,(long)s,n,0,0,0);}
static void number(u64 n) {char s[24];unsigned i=24;do{s[--i]='0'+n%10;n/=10;}while(n);sys(64,1,(long)(s+i),24-i,0,0,0);}
__attribute__((noreturn)) static void finish(int n){sys(93,n,0,0,0,0,0);for(;;);}
extern long simd_sleep(u64 *);
struct shared {u64 counter;u64 results[12];};
__attribute__((noreturn)) void smptest(void) {
 struct shared *s=(void*)sys(222,0,16384,3,0x21,-1,0);
 if((long)s<0){text("MMAP_FAIL\n");finish(1);}
 long pids[12];int failed=0;
 for(int cpu=0;cpu<12;cpu++){
  long pid=sys(220,17,0,0,0,0,0);
  if(pid<0){text("CLONE_FAIL\n");finish(2);}
  if(!pid){
   u64 mask=1UL<<cpu;
#ifndef HOST_VALIDATION
   if(sys(122,0,sizeof(mask),(long)&mask,0,0,0)){text("AFFINITY_FAIL\n");finish(3);}
#endif
   u64 regs[64] __attribute__((aligned(16)));
   for(unsigned iter=0;iter<1000;iter++){
    for(unsigned n=0;n<64;n++)regs[n]=0x1020304050607080UL^((u64)cpu<<16)^(n/2);
    if(simd_sleep(regs)){text("NANOSLEEP_FAIL\n");finish(4);}
    for(unsigned n=0;n<64;n++)if(regs[n]!=(0x1020304050607080UL^((u64)cpu<<16)^(n/2))){
     text("SIMD_MISMATCH CPU ");number(cpu);text(" ITER ");number(iter);text(" LANE ");number(n);text("\n");finish(5);
    }
   }
   s->results[cpu]=0xc0ffee0000UL+cpu;
   finish(0);
  }
  pids[cpu]=pid;
 }
 for(int cpu=0;cpu<12;cpu++){
  int status=-1;long pid=sys(260,pids[cpu],(long)&status,0,0,0,0);
  if(pid!=pids[cpu]||status||s->results[cpu]!=0xc0ffee0000UL+cpu)failed=1;
  text("CHILD ");number(cpu);text(" STATUS ");number((unsigned)status);text("\n");
 }
 text(failed?"SIMD_CONTEXT_FAIL\n":"SIMD_CONTEXT_PASS 12_CPUS 1000_SLEEPS_EACH 32_VECTOR_REGISTERS\n");finish(failed);
}
