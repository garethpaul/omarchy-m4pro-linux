/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

typedef uint8_t u8; typedef uint32_t u32; typedef uint64_t u64;
typedef uint64_t dma_addr_t;
#define __iomem
#define EXPORT_SYMBOL_GPL(x)
#define GFP_KERNEL 0
#define WQ_HIGHPRI 1
#define WQ_MEM_RECLAIM 2
#define DMA_FROM_DEVICE 1
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define DECLARE_BITMAP(name, n) unsigned long name[((n)+63)/64]
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define WARN_ON_ONCE(x) (!!(x))
#define FIELD_GET(mask,value) (((value)&(mask)) >> __builtin_ctzll(mask))
#define FIELD_PREP(mask,value) (((u64)(value) << __builtin_ctzll(mask))&(mask))
#define BIT_ULL(n) (1ULL << (n))
#define GENMASK_ULL(hi,lo) ((UINT64_MAX >> (63-(hi))) & (UINT64_MAX << (lo)))
#define dev_err(...) ((void)0)
#define dev_dbg(...) ((void)0)
#define dev_warn(...) ((void)0)
#define dev_info(...) ((void)0)
#define ERR_PTR(n) ((void *)(intptr_t)(n))
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define spin_lock_irqsave(lock,flags) do { (void)(lock); (flags)=0; } while(0)
#define spin_unlock_irqrestore(lock,flags) do { (void)(lock); (void)(flags); } while(0)
struct device { int unused; };
struct completion { int done; };
struct workqueue_struct { int unused; };
struct apple_mbox_msg { u64 msg0; u32 msg1; };
struct apple_mbox {
    unsigned rx_lock;
    void (*rx)(struct apple_mbox *, struct apple_mbox_msg, void *);
    void *cookie;
};
#include "rtkit-types-under-test.h"
#include "rtkit-constants-under-test.h"
static struct apple_mbox mailbox;
static struct device device;
static unsigned allocations, workqueues, sends, setups, destroys, stopped;
static unsigned bad_early_state, sync_cpu, sync_device, starts;
static bool fail_alloc, fail_wq, fail_start, fail_get, inject_log, mapped = true, setup_failure;
static u8 last_ep;
static u64 last_message;
static unsigned char shared[16384];
static void *alloc_object(size_t size) {
    if (fail_alloc) return NULL;
    allocations++;
    return calloc(1, size);
}
#define kzalloc_obj(obj,...) alloc_object(sizeof(obj))
static void tracked_free(void *ptr) { if(ptr) { assert(allocations); allocations--; free(ptr); } }
#define kfree tracked_free
static void init_completion(struct completion *c) { c->done=0; }
static void bitmap_zero(unsigned long *b, unsigned count) { memset(b,0,(count+7)/8); }
static void set_bit(unsigned bit, unsigned long *b) { b[bit/64] |= 1UL<<(bit%64); }
static bool test_bit(unsigned bit, const unsigned long *b) { return (b[bit/64]>>(bit%64))&1; }
static const char *dev_name(struct device *d) { (void)d; return "fake"; }
static struct apple_mbox *apple_mbox_get(struct device *d, int index) {
    (void)d; (void)index; return fail_get ? ERR_PTR(-ENODEV) : &mailbox;
}
static struct apple_mbox *apple_mbox_get_byname(struct device *d, const char *name) {
    (void)name; return apple_mbox_get(d,0);
}
static struct workqueue_struct *alloc_ordered_workqueue(const char *fmt, unsigned flags, const char *name) {
    (void)fmt; (void)flags; (void)name;
    if(fail_wq) return NULL;
    workqueues++; return calloc(1,sizeof(struct workqueue_struct));
}
static void destroy_workqueue(struct workqueue_struct *w) { assert(workqueues); workqueues--; free(w); }
static void apple_mbox_stop(struct apple_mbox *m) { (void)m; stopped++; }
static void apple_rtkit_rx(struct apple_mbox *, struct apple_mbox_msg, void *);
static int apple_mbox_start(struct apple_mbox *m) {
    starts++;
    if (inject_log) m->rx(m,(struct apple_mbox_msg){FIELD_PREP(APPLE_RTKIT_SYSLOG_TYPE,APPLE_RTKIT_SYSLOG_LOG),APPLE_RTKIT_EP_SYSLOG},m->cookie);
    return fail_start ? -EIO : 0;
}
static int apple_rtkit_send_message(struct apple_rtkit *r, u8 ep, u64 msg, void *completion, bool atomic) {
    (void)r; (void)completion; (void)atomic; sends++; last_ep=ep; last_message=msg; return 0;
}
static void *dma_alloc_coherent(struct device *d,size_t n,dma_addr_t *address,int flags) {
    (void)d;(void)flags; setups++; if(n>sizeof(shared)) return NULL; *address=0x4000; return shared;
}
static void dma_free_coherent(struct device *d,size_t n,void *p,dma_addr_t a) {
    (void)d;(void)n;(void)p;(void)a;destroys++;
}
static void dma_sync_single_range_for_cpu(struct device *d,dma_addr_t a,size_t o,size_t n,int dir) {
    (void)d;(void)a;(void)o;(void)n;(void)dir;sync_cpu++;
}
static void dma_sync_single_range_for_device(struct device *d,dma_addr_t a,size_t o,size_t n,int dir) {
    (void)d;(void)a;(void)o;(void)n;(void)dir;sync_device++;
}
#define memcpy_fromio memcpy
static int shmem_setup(void *cookie,struct apple_rtkit_shmem *b) {
    (void)cookie; setups++;
    if(setup_failure) return -EIO;
    b->buffer=shared;b->is_mapped=mapped;b->private=(void *)0x614;
    if(!b->iova)b->iova=0x4000;
    return 0;
}
static void shmem_destroy(void *cookie,struct apple_rtkit_shmem *b) { (void)cookie;(void)b;destroys++; }
static struct apple_rtkit_ops ops = {.shmem_setup=shmem_setup,.shmem_destroy=shmem_destroy};
#include "rtkit-functions-under-test.c"
static void apple_rtkit_rx(struct apple_mbox *m,struct apple_mbox_msg msg,void *cookie) {
    (void)m;
#ifdef BASELINE
    (void)msg;(void)cookie;
#else
    struct apple_rtkit *r=cookie;
    if (!r->syslog_inherited || !r->crashlog_inherited || !test_bit(APPLE_RTKIT_EP_SYSLOG,r->endpoints)
        || r->iop_power_state!=APPLE_RTKIT_PWR_STATE_ON || r->ap_power_state!=APPLE_RTKIT_PWR_STATE_ON)bad_early_state++;
    /* Any attempt to parse these deliberately unusable pointers faults. */
    r->syslog_msg_buffer=(char *)1;r->syslog_buffer.buffer=(void *)1;r->syslog_buffer.size=4096;
    apple_rtkit_syslog_rx_log(r,msg.msg0);
    r->syslog_msg_buffer=NULL;r->syslog_buffer=(struct apple_rtkit_shmem){0};
#endif
}
static u64 request(size_t n,u64 address) {
    return FIELD_PREP(APPLE_RTKIT_SYSLOG_TYPE,APPLE_RTKIT_BUFFER_REQUEST)
        | FIELD_PREP(APPLE_RTKIT_BUFFER_REQUEST_SIZE,n>>12)
        | FIELD_PREP(APPLE_RTKIT_BUFFER_REQUEST_IOVA,address);
}
static void reset(void) {
    assert(!allocations && !workqueues);memset(&mailbox,0,sizeof(mailbox));
    sends=setups=destroys=stopped=bad_early_state=sync_cpu=sync_device=starts=0;
    fail_alloc=fail_wq=fail_start=fail_get=inject_log=setup_failure=false;mapped=true;
}
int main(int argc, char **argv) {
    (void)argc;(void)argv;
    reset();
    struct apple_rtkit r={.dev=&device,.ops=&ops};
    struct apple_rtkit_shmem b={0};
    assert(apple_rtkit_common_rx_get_buffer(&r,&b,APPLE_RTKIT_EP_IOREPORT,request(4096,0x8000))==0);
    struct apple_rtkit_shmem saved=b;
    int changed=apple_rtkit_common_rx_get_buffer(&r,&b,APPLE_RTKIT_EP_IOREPORT,request(8192,0x8000));
#ifdef BASELINE
    /* Fake APIs used only by the candidate's actual initializer/free paths. */
    (void)saved;(void)alloc_object;(void)tracked_free;(void)init_completion;
    (void)bitmap_zero;(void)set_bit;(void)test_bit;(void)dev_name;
    (void)apple_mbox_get_byname;(void)alloc_ordered_workqueue;(void)destroy_workqueue;
    (void)apple_mbox_stop;(void)apple_mbox_start;(void)apple_rtkit_rx;
    (void)dma_free_coherent;(void)dma_sync_single_range_for_cpu;(void)dma_sync_single_range_for_device;
    if(changed!=0 || setups!=2 || b.size!=8192 || sends || last_ep || last_message) return 1;
    if(argc==2 && !strcmp(argv[1],"--expect-baseline-bug")) {
        puts("REPRODUCED: changed live RTKit request calls setup again and replaces descriptor");
        return 0;
    }
    fputs("FAIL: changed live RTKit request replaced descriptor instead of -EBUSY\n",stderr);
    return 1;
#else
    assert(changed==-EBUSY && setups==1 && memcmp(&b,&saved,sizeof(b))==0);
    assert(apple_rtkit_common_rx_get_buffer(&r,&b,APPLE_RTKIT_EP_IOREPORT,request(4096,0x9000))==-EBUSY);
    assert(apple_rtkit_common_rx_get_buffer(&r,&b,APPLE_RTKIT_EP_IOREPORT,request(4096,0x8000))==0 && setups==1);
    assert(apple_rtkit_common_rx_get_buffer(&r,&b,APPLE_RTKIT_EP_IOREPORT,request(0,0))==-EINVAL && b.size==4096);
    r.early_crashlog=true;b=(struct apple_rtkit_shmem){0};
    u64 crash=request(4096,0x8000);
    assert(apple_rtkit_common_rx_get_buffer(&r,&b,APPLE_RTKIT_EP_CRASHLOG,crash)==0);
    assert(last_ep==APPLE_RTKIT_EP_CRASHLOG && last_message==crash);
    r.early_crashlog=false;
    b=(struct apple_rtkit_shmem){0};setup_failure=true;
    assert(apple_rtkit_common_rx_get_buffer(&r,&b,APPLE_RTKIT_EP_IOREPORT,request(4096,0x8000))==-EIO && !b.size && !b.buffer);
    setup_failure=false;mapped=false;b=(struct apple_rtkit_shmem){0};
    assert(apple_rtkit_common_rx_get_buffer(&r,&b,APPLE_RTKIT_EP_UNKNOWN7,request(4096,0))==0);
    assert(last_ep==APPLE_RTKIT_EP_UNKNOWN7 && FIELD_GET(APPLE_RTKIT_SYSLOG_TYPE,last_message)==5);
    unsigned once=setups;
    assert(apple_rtkit_common_rx_get_buffer(&r,&b,APPLE_RTKIT_EP_UNKNOWN7,request(4096,0))==0 && setups==once);
    b.needs_dma_sync=true;memset(shared,0x61,16);char copied[16];
    apple_rtkit_memcpy(&r,copied,&b,0,16);
    assert(!memcmp(copied,shared,16) && sync_cpu==1 && sync_device==1);
    apple_rtkit_free_buffer(&r,&b);assert(destroys==1 && !b.size && !b.private && !b.needs_dma_sync);
    reset();inject_log=true;
    struct apple_rtkit *adopted=apple_rtkit_init_adopted(&device,NULL,NULL,0,&ops);
    assert(!IS_ERR(adopted) && !bad_early_state && sends==1 && last_ep==APPLE_RTKIT_EP_SYSLOG);
    assert(adopted->version==0); /* No fabricated HELLO/protocol measurement. */
    adopted->ioreport_buffer=(struct apple_rtkit_shmem){.size=4096,.buffer=shared};
    apple_rtkit_free_retaining_buffers(adopted);
    assert(stopped==1 && !destroys && !mailbox.cookie && !mailbox.rx && !allocations && !workqueues);
    reset();
    struct apple_rtkit *cold=apple_rtkit_init(&device,NULL,NULL,0,&ops);
    assert(!IS_ERR(cold) && !cold->syslog_inherited && cold->boot_ap_power && !sends);
    cold->ioreport_buffer=(struct apple_rtkit_shmem){.size=4096,.buffer=shared};
    apple_rtkit_free(cold);assert(destroys==1 && !mailbox.cookie && !mailbox.rx);
    reset();assert(PTR_ERR(apple_rtkit_init_adopted(&device,NULL,NULL,0,NULL))==-EINVAL && !allocations);
    reset();fail_alloc=true;assert(PTR_ERR(apple_rtkit_init_adopted(&device,NULL,NULL,0,&ops))==-ENOMEM);
    reset();fail_get=true;assert(PTR_ERR(apple_rtkit_init_adopted(&device,NULL,NULL,0,&ops))==-ENODEV && !allocations);
    reset();fail_wq=true;assert(PTR_ERR(apple_rtkit_init_adopted(&device,NULL,NULL,0,&ops))==-ENOMEM && !mailbox.cookie && !mailbox.rx && !allocations);
    reset();mailbox.cookie=(void *)0xabc;mailbox.rx=apple_rtkit_rx;
    assert(PTR_ERR(apple_rtkit_init_adopted(&device,NULL,NULL,0,&ops))==-EBUSY);
    assert(mailbox.cookie==(void *)0xabc && mailbox.rx==apple_rtkit_rx && !stopped && !starts && !allocations && !workqueues);
    reset();fail_start=true;
    assert(PTR_ERR(apple_rtkit_init_adopted(&device,NULL,NULL,0,&ops))==-EIO);
    assert(stopped==1 && !mailbox.cookie && !mailbox.rx && !allocations && !workqueues);
    puts("PASS: actual RTKit buffer identity, inherited pre-RX, ownership, teardown and failure-path host invariants");
    return 0;
#endif
}
