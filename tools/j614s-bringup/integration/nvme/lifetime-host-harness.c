/* SPDX-License-Identifier: MIT */
/* Selected actual driver functions; host fakes do not model DMA or concurrency. */
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <errno.h>
#include <string.h>
#define __iomem
#define IORESOURCE_MEM 1
#define IORESOURCE_MEM_NONPOSTED 2
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define GFP_KERNEL 0
#define APPLE_NVME_IOSQES 6
#define container_of(p,t,f) ((t *)((char *)(p)-offsetof(t,f)))
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define IS_ERR(p) ((uintptr_t)(p)>(uintptr_t)-4096)
typedef uint64_t resource_size_t;
typedef uint64_t dma_addr_t;
struct device { unsigned refs; };
struct resource { resource_size_t start,size;unsigned flags; };
struct platform_device { struct resource resource; };
struct kref { unsigned count; };
struct mutex { unsigned dummy; };
typedef unsigned spinlock_t;
struct list_head { struct list_head *next,*prev; };
struct nvme_ctrl { unsigned unused; };
struct nvme_command { char bytes[64]; };
struct nvme_completion { char bytes[16]; };
struct apple_nvmmu_tcb { char bytes[128]; };
struct apple_nvme_hw { bool has_lsq_nvmmu; unsigned max_queue_depth; };
struct apple_nvme_queue {
    bool is_adminq; unsigned cq_phase; void *cqes,*sqes,*tcbs;
    dma_addr_t cq_dma_addr,sq_dma_addr,tcb_dma_addr;
};
struct apple_nvme_mmio { struct apple_nvme *owner;resource_size_t start,size;void *base;bool reserved; };
struct apple_nvme {
    struct device *dev;struct apple_nvme_mmio retained_mmio[2];struct kref ref;struct mutex disable_lock;
    spinlock_t event_lock; bool reset_ready,detached,quarantined;
    struct list_head quarantine_node;resource_size_t controller_start;
    struct nvme_ctrl ctrl;struct apple_nvme_queue adminq,ioq;
    struct apple_nvme_hw *hw;void *iod_mempool,*prp_small_pool,*prp_page_pool;
};
struct blk_mq_tag_set { void *driver_data; };
static struct mutex apple_nvme_quarantine_lock;
static struct list_head apple_nvme_quarantines;
#define list_for_each_entry(pos,head,member) for(struct list_head *node=(head)->next; node!=(head) && ((pos)=container_of(node,typeof(*(pos)),member),1);node=node->next)
static unsigned allocated,allocations,frees,dma_count,dma_frees,tag_frees,pool_frees,mempool_frees;
static unsigned regions,map_calls;static bool fail_region,fail_map;
static unsigned fail_alloc_at,fail_action_at,action_calls;
struct action { void (*fn)(void *);void *data; };
static struct action actions[16];static unsigned action_count;
static void *allocate(size_t n) { allocations++;if(allocations==fail_alloc_at)return NULL;allocated++;return calloc(1,n); }
#define kzalloc_obj(x) allocate(sizeof(x))
static void kfree(void *p) { assert(p && allocated);allocated--;frees++;free(p); }
static struct device *get_device(struct device *d) { d->refs++;return d; }
static void put_device(struct device *d) { assert(d->refs>1);d->refs--; }
static void kref_init(struct kref *r) { r->count=1; }
static void kref_get(struct kref *r) { assert(r->count);r->count++; }
static void kref_put(struct kref *r,void(*release)(struct kref *)) { assert(r->count);if(!--r->count)release(r); }
static void mutex_init(struct mutex *m) { m->dummy=0; }
static void mutex_lock(struct mutex *m) { assert(!m->dummy);m->dummy=1; }
static void mutex_unlock(struct mutex *m) { assert(m->dummy);m->dummy=0; }
static void spin_lock_init(spinlock_t *l) { *l=0; }
#define spin_lock_irqsave(l,f) do { assert(!*(l));*(l)=1;(f)=0; } while(0)
#define spin_unlock_irqrestore(l,f) do { (void)(f);assert(*(l));*(l)=0; } while(0)
#define INIT_LIST_HEAD(h) do { (h)->next=(h);(h)->prev=(h); } while(0)
static int devm_add_action_or_reset(struct device *d,void(*fn)(void *),void *p) {
    (void)d;action_calls++;if(action_calls==fail_action_at){fn(p);return -ENOMEM;}
    assert(action_count<16);actions[action_count++]=(struct action){fn,p};return 0;
}
static struct apple_nvme *ctrl_to_apple_nvme(struct nvme_ctrl *c) { return container_of(c,struct apple_nvme,ctrl); }
static struct apple_nvme *queue_to_apple_nvme(struct apple_nvme_queue *q) {
    return q->is_adminq?container_of(q,struct apple_nvme,adminq):container_of(q,struct apple_nvme,ioq);
}
static unsigned apple_nvme_queue_depth(struct apple_nvme_queue *q) { return q->is_adminq?2:queue_to_apple_nvme(q)->hw->max_queue_depth; }
static void blk_mq_free_tag_set(struct blk_mq_tag_set *s) { (void)s;tag_frees++; }
static void mempool_destroy(void *p) { if(p)mempool_frees++; }
static void dma_pool_destroy(void *p) { if(p)pool_frees++; }
static void *dma_alloc_coherent(struct device *d,size_t n,dma_addr_t *a,int flags) {
    (void)d;(void)flags;void *p=allocate(n);if(p){dma_count++;*a=(uintptr_t)p;}return p;
}
static void dma_free_coherent(struct device *d,size_t n,void *p,dma_addr_t a) {
    (void)d;assert(n && p && a==(uintptr_t)p && dma_count);dma_count--;dma_frees++;kfree(p);
}
static struct resource *platform_get_resource_byname(struct platform_device *p,int type,const char *name) { assert(type==IORESOURCE_MEM&&!strcmp(name,"ans"));return &p->resource; }
static resource_size_t resource_size(const struct resource *r) { return r->size; }
static const char *dev_name(struct device *d) { (void)d;return "test"; }
static void *request_mem_region(resource_size_t a,resource_size_t n,const char *name) { (void)a;(void)n;(void)name;if(fail_region)return NULL;regions++;return (void *)1; }
static void release_mem_region(resource_size_t a,resource_size_t n) { (void)a;(void)n;assert(regions);regions--; }
static void *ioremap(resource_size_t a,resource_size_t n) { (void)a;map_calls++;return fail_map?NULL:allocate(n); }
static void *ioremap_np(resource_size_t a,resource_size_t n) { return ioremap(a,n); }
static void iounmap(void *p) { kfree(p); }
#include "lifetime-functions-under-test.c"
static unsigned checks,scenarios;
#define CHECK(c) do { checks++;if(!(c)){fprintf(stderr,"FAIL %d: %s\n",__LINE__,#c);exit(1);} } while(0)
static void cleanup(void) { while(action_count){struct action a=actions[--action_count];a.fn(a.data);} }
static void reset(void) {
    CHECK(!allocated && !action_count && !dma_count && !regions);scenarios++;
    fail_region=fail_map=false;map_calls=0;
    allocations=frees=dma_frees=tag_frees=pool_frees=mempool_frees=action_calls=0;
    fail_alloc_at=fail_action_at=0;
}
int main(void) {
    INIT_LIST_HEAD(&apple_nvme_quarantines);
    struct device dev={1};struct apple_nvme *a;struct apple_nvme_hw hw={true,4};
    reset();fail_alloc_at=1;a=apple_nvme_alloc_owner(&dev,0x40000);CHECK(IS_ERR(a) && dev.refs==1 && !action_count);
    reset();fail_action_at=1;a=apple_nvme_alloc_owner(&dev,0x40000);CHECK(IS_ERR(a) && dev.refs==1 && !allocated && frees==1);
    for(unsigned order=0;order<2;order++) {
        reset();a=apple_nvme_alloc_owner(&dev,0x40000);CHECK(!IS_ERR(a) && a->ref.count==1 && dev.refs==2);
        CHECK(a->controller_start==0x40000 && a->quarantine_node.next==&a->quarantine_node);
        kref_get(&a->ref);apple_nvme_set_reset_ready(a,true);CHECK(a->reset_ready);
        if(order){cleanup();CHECK(a->detached && a->ref.count==1);apple_nvme_free_ctrl(&a->ctrl);}
        else {apple_nvme_free_ctrl(&a->ctrl);CHECK(a->ref.count==1);cleanup();}
        CHECK(!allocated && dev.refs==1 && frees==1);
    }
    /* Action registration precedes every allocation; unwind each partial queue. */
    for(unsigned lsq=0;lsq<2;lsq++)for(unsigned fail=0;fail<5;fail++) {
        reset();a=apple_nvme_alloc_owner(&dev,0);a->hw=&hw;hw.has_lsq_nvmmu=lsq;a->adminq.is_adminq=true;
        fail_alloc_at=fail?allocations+fail:0;
        int ret=apple_nvme_queue_alloc(a,&a->adminq);
        unsigned expected=lsq?3:2;
        CHECK(ret==((fail && fail<=expected)?-ENOMEM:0));cleanup();CHECK(!allocated && dev.refs==1);
    }
    reset();a=apple_nvme_alloc_owner(&dev,0);a->hw=&hw;a->adminq.is_adminq=true;
    fail_action_at=action_calls+1;CHECK(apple_nvme_queue_alloc(a,&a->adminq)==-ENOMEM);CHECK(!dma_count);cleanup();
    for(unsigned held=0;held<2;held++) {
        reset();a=apple_nvme_alloc_owner(&dev,0);a->hw=&hw;a->adminq.is_adminq=true;
        CHECK(!apple_nvme_queue_alloc(a,&a->adminq));
        a->iod_mempool=(void *)1;a->prp_small_pool=(void *)2;a->prp_page_pool=(void *)3;
        struct blk_mq_tag_set tags={&a->adminq};a->quarantined=held;
        apple_nvme_free_pools(a);devm_apple_nvme_put_tag_set(&tags);
        CHECK(mempool_frees==!held && pool_frees==2*!held && tag_frees==!held);
        if(held){
            cleanup();CHECK(allocated==4 && dma_count==3 && a->detached && a->ref.count==1 && dev.refs==2);
            /* Test-only release after proving retained state, simulating a platform reset. */
            a->quarantined=false;apple_nvme_free_queue(&a->adminq);kref_put(&a->ref,apple_nvme_release);
        }else cleanup();
        CHECK(!allocated && !dma_count && dev.refs==1);
    }
    reset();a=apple_nvme_alloc_owner(&dev,0x40000);
    CHECK(!apple_nvme_controller_quarantined(0x40000));
    apple_nvme_quarantines.next=apple_nvme_quarantines.prev=&a->quarantine_node;
    a->quarantine_node.next=a->quarantine_node.prev=&apple_nvme_quarantines;
    CHECK(apple_nvme_controller_quarantined(0x40000));CHECK(!apple_nvme_controller_quarantined(0x80000));
    INIT_LIST_HEAD(&apple_nvme_quarantines);cleanup();CHECK(!apple_nvme_quarantine_lock.dummy);
    struct platform_device pdev={.resource={0x409600000ULL,0x4000,IORESOURCE_MEM}};
    for(unsigned failure=0;failure<3;failure++) {
        reset();a=apple_nvme_alloc_owner(&dev,0);fail_region=failure==0;fail_map=failure==1;if(failure==2)fail_action_at=action_calls+1;
        CHECK(IS_ERR(apple_nvme_map_retained_mmio(&pdev,a,0,"ans")));cleanup();CHECK(!allocated&&!regions&&dev.refs==1);
    }
    for(unsigned retained=0;retained<2;retained++) {
        reset();a=apple_nvme_alloc_owner(&dev,0);void *base=apple_nvme_map_retained_mmio(&pdev,a,0,"ans");
        CHECK(!IS_ERR(base)&&regions==1&&map_calls==1);*(unsigned *)base=0x6145a55a;a->quarantined=retained;cleanup();
        if(retained){CHECK(allocated==2&&regions==1&&a->detached&&*(unsigned *)base==0x6145a55a);a->quarantined=false;apple_nvme_free_retained_mmio(&a->retained_mmio[0]);kref_put(&a->ref,apple_nvme_release);}
        CHECK(!allocated&&!regions&&dev.refs==1);
    }
    printf("PASS %u actual ownership/cleanup checks across %u scenarios\n",checks,scenarios);return 0;
}
