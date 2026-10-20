/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#define NVME_CTRL_VWC_PRESENT 1
#define BLK_FEAT_WRITE_CACHE 1
#define BLK_FEAT_FUA 2
#define BLK_FEAT_ROTATIONAL 4
#define BLK_FLAG_WRITE_CACHE_DISABLED 1
#define REQ_PREFLUSH 1
#define REQ_FUA 2
#define REQ_SYNC 4
#define RQF_FLUSH_SEQ 1
#define HZ 100
#define WARN_ON_ONCE(c) assert(!(c))
#define BUG_ON(c) assert(!(c))
#define BUG() assert(0)
#define likely(c) (c)
typedef unsigned blk_status_t;typedef unsigned blk_opf_t;
struct nvme_ctrl { unsigned vwc,quirks; };
struct nvme_ns { struct nvme_ctrl *ctrl; };
struct info { bool no_vwc,is_rotational; };
struct queue_limits { unsigned features,flags; };
struct list_head { struct list_head *next,*prev; };
struct request_queue { struct queue_limits limits;unsigned requeue_lock;struct list_head requeue_list; };
struct blk_flush_queue { unsigned mq_flush_lock,flush_data_in_flight,flush_pending_idx;unsigned long flush_pending_since;struct list_head flush_queue[2]; };
struct request {
    struct request_queue *q;struct blk_flush_queue *mq_ctx;void *bio,*biotail;
    unsigned cmd_flags,rq_flags,sectors;struct { unsigned seq;void (*saved_end_io)(void); } flush;
    void (*end_io)(void);struct list_head queuelist;
};
static unsigned kicks,ended,restored,requeued;static unsigned long jiffies=123;
static void list_init(struct list_head *h) { h->next=h->prev=h; }
static bool list_empty(struct list_head *h) { return h->next==h; }
static void list_add_tail(struct list_head *n,struct list_head *h) { n->next=h;n->prev=h->prev;h->prev->next=n;h->prev=n; }
static void list_del_init(struct list_head *n) { n->prev->next=n->next;n->next->prev=n->prev;list_init(n); }
static void list_move(struct list_head *n,struct list_head *h) { list_del_init(n);list_add_tail(n,h); }
static void spin_lock(unsigned *l) { assert(!*l);*l=1; }
static void spin_unlock(unsigned *l) { assert(*l);*l=0; }
#define spin_lock_irq spin_lock
#define spin_unlock_irq spin_unlock
static unsigned ffz(unsigned x) { return __builtin_ctz(~x); }
static struct blk_flush_queue *blk_get_flush_queue(struct blk_flush_queue *ctx) { return ctx; }
static unsigned blk_rq_sectors(struct request *r) { return r->sectors; }
static void blk_mq_end_request(struct request *r,blk_status_t s) { (void)r;assert(!s);ended++; }
static void blk_flush_restore_request(struct request *r) { (void)r;restored++; }
static void blk_mq_kick_requeue_list(struct request_queue *q) { (void)q;requeued++; }
static void blk_kick_flush(struct request_queue *q,struct blk_flush_queue *f,blk_opf_t flags) { (void)q;(void)f;(void)flags;kicks++; }
static void mq_flush_data_end_io(void) { }
#include "fua-source-under-test.c"
int main(void) {
    const struct { unsigned vwc;bool no_vwc;unsigned quirks,expected; } cases[]={
        {0,false,0,0},{0,false,NVME_QUIRK_BROKEN_FUA,0},
        {1,false,0,3},{1,false,NVME_QUIRK_BROKEN_FUA,1},
        {1,true,0,0},{1,true,NVME_QUIRK_BROKEN_FUA,0},
        {0,true,NVME_QUIRK_BROKEN_FUA,0},{1,false,NVME_QUIRK_ADMIN_PAGE_ALIGN,3}
    };
    assert(NVME_QUIRK_BROKEN_FUA==(1U<<24));assert(!strcmp(nvme_quirk_name(NVME_QUIRK_BROKEN_FUA),"broken_fua"));
    for(unsigned i=0;i<sizeof(cases)/sizeof(*cases);i++)for(unsigned rotational=0;rotational<2;rotational++) {
        struct nvme_ctrl c={cases[i].vwc,cases[i].quirks};struct nvme_ns ns={&c};
        struct info info={cases[i].no_vwc,rotational};struct queue_limits limits={.features=0x80|BLK_FEAT_WRITE_CACHE|BLK_FEAT_FUA};
        set_limits(&ns,&info,&limits);unsigned expected=cases[i].expected;
#ifdef EXPECT_FUA_RETAINED_BUG
        if(i==3)expected=3;
#endif
        assert(limits.features==(0x80|expected|(rotational?4:0)));
    }
    struct nvme_ctrl c={1,NVME_QUIRK_BROKEN_FUA};struct nvme_ns ns={&c};struct info info={0};
    struct request_queue q={0};set_limits(&ns,&info,&q.limits);
    struct blk_flush_queue fq={0};list_init(&q.requeue_list);list_init(&fq.flush_queue[0]);list_init(&fq.flush_queue[1]);
    struct request rq={.q=&q,.mq_ctx=&fq,.cmd_flags=REQ_FUA,.sectors=8};list_init(&rq.queuelist);
    bool consumed=blk_insert_flush(&rq);assert(!consumed);
#ifdef EXPECT_FUA_RETAINED_BUG
    assert(q.limits.features==3 && (rq.cmd_flags&REQ_FUA) && !fq.flush_data_in_flight && !rq.rq_flags);
    assert(!kicks&&!ended&&!restored&&!requeued);
    puts("REPRODUCED: old namespace fragment retains FUA and block layer skips explicit postflush");
#else
    assert(q.limits.features==1 && !(rq.cmd_flags&REQ_FUA) && (rq.cmd_flags&REQ_SYNC));
    assert(rq.rq_flags==RQF_FLUSH_SEQ && rq.flush.seq==REQ_FSEQ_PREFLUSH && fq.flush_data_in_flight==1);
    /* Complete the DATA phase through the actual sequence function. */
    spin_lock(&fq.mq_flush_lock);blk_flush_complete_seq(&rq,&fq,REQ_FSEQ_DATA,0);spin_unlock(&fq.mq_flush_lock);
    assert(blk_flush_cur_seq(&rq)==REQ_FSEQ_POSTFLUSH && !list_empty(&fq.flush_queue[0]) && kicks==1 && !ended && !restored && !requeued);
    assert(fq.flush_pending_since==123);
    puts("PASS 16 literal queue-limit scenarios; FUA cleared/cache retained; actual block DATA completion queues POSTFLUSH");
#endif
    return 0;
}
