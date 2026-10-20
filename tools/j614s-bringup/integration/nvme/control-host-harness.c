/* SPDX-License-Identifier: MIT */
/* Actual driver control functions; deterministic fakes do not model concurrency. */
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;typedef uint64_t u64;typedef uint64_t dma_addr_t;
#define __iomem
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define smp_store_release(p,v) (*(p)=(v))
#define container_of(p,t,f) ((t *)((char *)(p)-offsetof(t,f)))
static void log_fake(void *dev,const char *format,...) { (void)dev;(void)format; }
#define dev_crit log_fake
#define dev_warn log_fake
#define dev_err log_fake
#define dev_dbg log_fake
#define NVME_CTRL_FROZEN 0
#define NVME_IO_TIMEOUT 1
#define NVME_REG_CAP 0
#define NVME_REG_CC 0x14
#define NVME_REG_CSTS 0x1c
#define NVME_REG_AQA 0x24
#define NVME_REG_ASQ 0x28
#define NVME_REG_ACQ 0x30
#define NVME_CC_ENABLE 1
#define NVME_CSTS_RDY 1
#define NVME_CSTS_CFS 2
#define APPLE_ANS_COPROC_CPU_CONTROL 0x44
#define APPLE_ANS_COPROC_CPU_CONTROL_RUN 0x10
#define APPLE_ANS_BOOT_STATUS 0x1300
#define APPLE_ANS_BOOT_STATUS_OK 0xde71ce55
#define APPLE_ANS_LINEAR_SQ_CTRL 0x24908
#define APPLE_ANS_LINEAR_SQ_EN 1
#define APPLE_ANS_T8103_MAX_PEND_CMDS_CTRL 0x1210
#define APPLE_ANS_T8132_IOQ_CQES 0x1208
#define APPLE_ANS_T8132_IOQ_CMDS 0x1200
#define APPLE_NVMMU_NUM_TCBS 0x28100
#define APPLE_NVMMU_ASQ_TCB_BASE 0x28108
#define APPLE_NVMMU_IOSQ_TCB_BASE 0x28110
#define APPLE_NVME_AQ_DEPTH 2
#define APPLE_ANS_BOOT_TIMEOUT 1
#define APPLE_NVME_RECOVERY_PENDING 0
#define USEC_PER_MSEC 1
#define NVME_MAX_KB_SZ 1024
#define NVME_MAX_SEGS 128
#define NVME_REQ_CANCELLED 1
#define THIS_MODULE ((void *)1)
#define min_t(t,a,b) ((t)(a)<(t)(b)?(t)(a):(t)(b))
#define test_bit(n,p) ((*(p)>>(n))&1)
#define clear_bit(n,p) (*(p)&=~(1UL<<(n)))
static bool test_and_set_bit(unsigned n,unsigned long *p) { bool b=!!test_bit(n,p);*p|=1UL<<n;return b; }
struct work_struct { unsigned id; };
struct device { unsigned id; };
struct mutex { bool locked; };
struct list_head { unsigned unused; };
typedef unsigned spinlock_t;
enum nvme_ctrl_state { NVME_CTRL_LIVE,NVME_CTRL_RESETTING,NVME_CTRL_CONNECTING,NVME_CTRL_DELETING,NVME_CTRL_DELETING_NOIO };
enum blk_eh_timer_return { BLK_EH_DONE,BLK_EH_RESET_TIMER };
struct nvme_ctrl {
    struct work_struct reset_work;enum nvme_ctrl_state state;
    unsigned long flags;u64 cap;u32 ctrl_config;unsigned max_hw_sectors,max_segments,sqsize,queue_count;
    struct device *device;
};
struct apple_rtkit { bool crashed,running; };
struct apple_nvme_hw { bool needs_ioq_register,j614s_diagnostic,has_lsq_nvmmu;unsigned max_queue_depth; };
struct apple_nvme_queue { bool is_adminq,enabled;dma_addr_t sq_dma_addr,cq_dma_addr,tcb_dma_addr; };
struct blk_mq_tag_set { unsigned unused; };
struct apple_nvme {
    struct device *dev;struct mutex disable_lock;spinlock_t event_lock,lock;
    bool reset_ready,quarantined,removing,detached,abort_reset,recover_to_live,suspended,owns_rtkit,inherited_rtkit,handoff_disabled;
    unsigned long recovery_flags;int irq,pd_count;struct device **pd_dev;
    struct list_head quarantine_node;void *mmio_coproc,*mmio_nvme;
    struct apple_nvme_hw *hw;struct apple_rtkit *rtk;struct nvme_ctrl ctrl;
    struct work_struct recovery_work,remove_work;struct apple_nvme_queue adminq,ioq;
    struct blk_mq_tag_set tagset;
};
struct apple_nvme_iod { struct apple_nvme_queue *q; };
enum { MQ_RQ_IDLE, MQ_RQ_IN_FLIGHT, MQ_RQ_COMPLETE };
struct request { struct apple_nvme_iod iod;unsigned state;int tag;unsigned flags; };
struct blk_mq_hw_ctx { void *driver_data; };struct io_comp_batch { unsigned unused; };
static struct mutex apple_nvme_quarantine_lock;
static struct list_head apple_nvme_quarantines;
static void *system_unbound_wq=(void *)2,*nvme_wq=(void *)3;
static u32 registers[0x30000/4],asc[0x4000/4];
static unsigned reads,writes,paired,native64,disable_calls,cancels,drains,quiesces,module_pins,irq_disabled,pd_pins,held;
static unsigned legacy_calls,scheduled,restarts,started,creates,removed_queues,ctrl_refs,dead;
static bool inject_quarantine_at_lock;
static bool fail_disable,fail_enable,fail_finish,fail_create,complete_poll,fail_state,abort_finish;
static struct request *current_request;
static unsigned poll_outcome=MQ_RQ_COMPLETE;
static struct apple_nvme *current;
static void mutex_lock(struct mutex *m) { assert(!m->locked);m->locked=true; }
static void mutex_unlock(struct mutex *m) { assert(m->locked);m->locked=false; }
#define lockdep_assert_held(m) assert((m)->locked)
#define spin_lock_irqsave(l,f) do { assert(!*(l));*(l)=1;(f)=0;if(inject_quarantine_at_lock && (l)==&current->lock){current->quarantined=true;inject_quarantine_at_lock=false;} } while(0)
#define spin_unlock_irqrestore(l,f) do { (void)(f);assert(*(l));*(l)=0; } while(0)
static u32 readl(const void *p) { reads++;return *(const u32 *)p; }
static u64 readq(const void *p) { reads++;u64 v;memcpy(&v,p,8);return v; }
static void writel(u32 v,void *p) { assert(!current->quarantined && !current->detached);writes++;*(u32 *)p=v; }
static void writeq(u64 v,void *p) { native64++;memcpy(p,&v,8); }
static void lo_hi_writeq(u64 v,void *p) { assert(!(registers[NVME_REG_CC/4]&1)||(creates==2&&(((char *)p-(char *)registers==0x1200)||((char *)p-(char *)registers==0x1208))));paired++;writel((u32)v,p);writel(v>>32,(char *)p+4); }
#define readl_poll_timeout(addr,val,condition,delay,timeout) ((void)(delay),(void)(timeout),(val)=readl(addr),(condition)?0:-ETIMEDOUT)
static enum nvme_ctrl_state nvme_ctrl_state(struct nvme_ctrl *c) { return c->state; }
static bool nvme_change_ctrl_state(struct nvme_ctrl *c,enum nvme_ctrl_state state) { if(fail_state)return false;if(c->state==NVME_CTRL_CONNECTING&&state==NVME_CTRL_RESETTING)return false;c->state=state;return true; }
static bool apple_rtkit_is_crashed(struct apple_rtkit *r) { return r->crashed; }
static bool apple_rtkit_is_running(struct apple_rtkit *r) { return r->running; }
static void nvme_start_freeze(struct nvme_ctrl *c) { c->flags|=1; }
static bool nvme_wait_freeze_timeout(struct nvme_ctrl *c,unsigned t) { (void)c;(void)t;return true; }
static void nvme_quiesce_io_queues(struct nvme_ctrl *c) { (void)c;quiesces++; }
static void nvme_quiesce_admin_queue(struct nvme_ctrl *c) { (void)c;quiesces++; }
static void nvme_unquiesce_io_queues(struct nvme_ctrl *c) { (void)c; }
static void nvme_unquiesce_admin_queue(struct nvme_ctrl *c) { (void)c; }
static int nvme_disable_ctrl(struct nvme_ctrl *c,bool shn) { assert(!shn);disable_calls++;if(fail_disable)return -ETIMEDOUT;registers[NVME_REG_CC/4]=registers[NVME_REG_CSTS/4]=0;c->ctrl_config=0;return 0; }
static bool apple_nvme_handle_cq(struct apple_nvme_queue *q,bool force) { (void)q;if(force){assert(!registers[NVME_REG_CC/4]);drains++;}if(complete_poll&&current_request)current_request->state=poll_outcome;return complete_poll; }
static void nvme_cancel_tagset(struct nvme_ctrl *c) { (void)c;assert(!registers[NVME_REG_CC/4]);cancels++; }
static void nvme_cancel_admin_tagset(struct nvme_ctrl *c) { nvme_cancel_tagset(c); }
static void __module_get(void *m) { assert(m==THIS_MODULE);module_pins++; }
static void disable_irq(int irq) { assert(irq==5);irq_disabled++; }
static void pm_runtime_get_noresume(struct device *d) { (void)d;pd_pins++; }
static void list_add_tail(struct list_head *n,struct list_head *l) { (void)n;(void)l;held++; }
static void nvme_mark_namespaces_dead(struct nvme_ctrl *c) { (void)c;dead++; }
static void apple_nvme_disable_legacy(struct apple_nvme *a,bool shutdown) { (void)a;(void)shutdown;legacy_calls++; }
static void nvme_try_sched_reset(struct nvme_ctrl *c) { (void)c;restarts++; }
static void *blk_mq_rq_to_pdu(struct request *r) { return &r->iod; }
static struct apple_nvme *queue_to_apple_nvme(struct apple_nvme_queue *q) { return q->is_adminq?container_of(q,struct apple_nvme,adminq):container_of(q,struct apple_nvme,ioq); }
static unsigned blk_mq_rq_state(struct request *r) { return r->state; }
static bool blk_mq_request_completed(struct request *r) { return r->state==MQ_RQ_COMPLETE; }
#define nvme_req(r) (r)
static bool queue_work(void *q,struct work_struct *w) { (void)q;(void)w;scheduled++;return true; }
static enum blk_eh_timer_return apple_nvme_timeout_legacy(struct request *r) { (void)r;legacy_calls++;return BLK_EH_DONE; }
static bool apple_nvme_poll_cq(struct apple_nvme_queue *q,struct io_comp_batch *b) { (void)q;(void)b;drains++;return true; }
static void apple_nvme_reset_legacy_work(struct work_struct *w) { (void)w;legacy_calls++; }
static size_t dma_max_mapping_size(struct device *d) { (void)d;return 1<<20; }
static void dma_set_max_seg_size(struct device *d,u32 n) { (void)d;(void)n; }
static int nvme_enable_ctrl(struct nvme_ctrl *c) { if(fail_enable)return -EIO;registers[NVME_REG_CC/4]=registers[NVME_REG_CSTS/4]=1;c->ctrl_config=1;return 0; }
static void apple_nvme_init_queue(struct apple_nvme_queue *q) { q->enabled=true; }
static int nvme_init_ctrl_finish(struct nvme_ctrl *c,bool b) { (void)c;(void)b;assert(!current->disable_lock.locked);if(abort_finish)current->abort_reset=true;return fail_finish?-EIO:0; }
static int apple_nvme_create_cq(struct apple_nvme *a) { assert(!a->disable_lock.locked);creates++;return fail_create?-EIO:0; }
static int apple_nvme_create_sq(struct apple_nvme *a) { return apple_nvme_create_cq(a); }
static void apple_nvme_remove_sq(struct apple_nvme *a) { (void)a;removed_queues++; }
static void apple_nvme_remove_cq(struct apple_nvme *a) { (void)a;removed_queues++; }
static void nvme_wait_freeze(struct nvme_ctrl *c) { (void)c; }
static void blk_mq_update_nr_hw_queues(struct blk_mq_tag_set *s,unsigned n) { (void)s;assert(n==1); }
static void nvme_unfreeze(struct nvme_ctrl *c) { c->flags=0; }
static void nvme_start_ctrl(struct nvme_ctrl *c) { (void)c;assert(!current->disable_lock.locked);started++; }
static void nvme_get_ctrl(struct nvme_ctrl *c) { (void)c;ctrl_refs++; }
static void nvme_put_ctrl(struct nvme_ctrl *c) { (void)c;assert(ctrl_refs);ctrl_refs--; }
#include "control-functions-under-test.c"
static unsigned checks,scenarios;
#define CHECK(c) do { checks++;if(!(c)){fprintf(stderr,"FAIL %d: %s\n",__LINE__,#c);exit(1);} } while(0)
static struct apple_nvme a;static struct apple_nvme_hw hw;static struct apple_rtkit rtk;static struct device dev;
static void reset(void) {
    scenarios++;memset(&a,0,sizeof(a));memset(registers,0,sizeof(registers));memset(asc,0,sizeof(asc));
    hw=(struct apple_nvme_hw){true,true,true,64};rtk=(struct apple_rtkit){false,true};
    a=(struct apple_nvme){.dev=&dev,.hw=&hw,.rtk=&rtk,.inherited_rtkit=true,.irq=5,.mmio_nvme=registers,.mmio_coproc=asc};
    a.ctrl.state=NVME_CTRL_RESETTING;a.adminq.is_adminq=true;
    a.adminq.sq_dma_addr=0x100001000ULL;a.adminq.cq_dma_addr=0x100002000ULL;
    a.adminq.tcb_dma_addr=0x100003000ULL;a.ioq.tcb_dma_addr=0x100004000ULL;
    a.ioq.cq_dma_addr=0x100005000ULL;a.ioq.sq_dma_addr=0x100006000ULL;
    registers[NVME_REG_CC/4]=registers[NVME_REG_CSTS/4]=1;
    registers[APPLE_ANS_BOOT_STATUS/4]=APPLE_ANS_BOOT_STATUS_OK;registers[APPLE_ANS_LINEAR_SQ_CTRL/4]=1;
    asc[APPLE_ANS_COPROC_CPU_CONTROL/4]=0x10;current=&a;current_request=NULL;
    reads=writes=paired=native64=disable_calls=cancels=drains=quiesces=module_pins=irq_disabled=pd_pins=held=0;
    legacy_calls=scheduled=restarts=started=creates=removed_queues=ctrl_refs=dead=0;
    fail_disable=fail_enable=fail_finish=fail_create=complete_poll=fail_state=abort_finish=inject_quarantine_at_lock=false;
}
int main(void) {
    (void)apple_nvme_remove_sq;(void)apple_nvme_remove_cq;
    reset();apple_nvme_reset_work(&a.ctrl.reset_work);CHECK(started==1&&a.ctrl.state==NVME_CTRL_LIVE&&a.ctrl.queue_count==2);
    CHECK(a.owns_rtkit&&disable_calls==1&&paired==6&&!native64&&creates==2&&!removed_queues&&!legacy_calls);
    CHECK(registers[0x1210/4]==0x003f003f&&registers[0x24908/4]==1);
    CHECK(registers[0x28/4]==0x1000&&registers[0x2c/4]==1&&registers[0x1208/4]==0x5000&&registers[0x120c/4]==1);
    CHECK(!a.disable_lock.locked);
    reset();a.inherited_rtkit=false;apple_nvme_reset_work(&a.ctrl.reset_work);CHECK(legacy_calls==1&&!reads&&!writes);
    for(unsigned mode=0;mode<2;mode++){reset();a.quarantined=!mode;a.removing=mode;apple_nvme_reset_work(&a.ctrl.reset_work);CHECK(!reads&&!writes&&!disable_calls&&!a.disable_lock.locked);}
    reset();fail_disable=true;apple_nvme_reset_work(&a.ctrl.reset_work);CHECK(a.quarantined&&module_pins==1&&held==1&&irq_disabled==1&&!writes&&!cancels&&!drains&&!scheduled);
    unsigned saved=disable_calls;CHECK(apple_nvme_disable(&a,false)==-EIO&&disable_calls==saved&&held==1);
    for(unsigned mode=0;mode<4;mode++){reset();fail_finish=mode==0;fail_enable=mode==1;fail_create=mode==2;abort_finish=mode==3;apple_nvme_reset_work(&a.ctrl.reset_work);CHECK(!started&&!removed_queues&&!a.disable_lock.locked&&scheduled==1&&cancels==2);}
    reset();a.owns_rtkit=true;apple_nvme_reset_work(&a.ctrl.reset_work);CHECK(started==1&&disable_calls==1&&cancels==2&&paired==6);
    CHECK(blk_mq_request_completed(&(struct request){.state=MQ_RQ_COMPLETE}));
    CHECK(blk_mq_rq_state(&(struct request){.state=MQ_RQ_IDLE})==MQ_RQ_IDLE);
    struct request req={0};struct io_comp_batch batch={0};struct blk_mq_hw_ctx hctx={&a.adminq};
    for(unsigned mode=0;mode<2;mode++){reset();a.quarantined=!mode;a.detached=mode;req=(struct request){.iod={&a.adminq},.state=MQ_RQ_IN_FLIGHT};CHECK(apple_nvme_timeout(&req)==BLK_EH_RESET_TIMER&&!reads);CHECK(!apple_nvme_poll(&hctx,&batch)&&!drains);}
    reset();a.ctrl.state=NVME_CTRL_CONNECTING;req=(struct request){.iod={&a.adminq},.state=MQ_RQ_IN_FLIGHT};current_request=&req;complete_poll=true;CHECK(apple_nvme_timeout(&req)==BLK_EH_DONE&&!scheduled&&!disable_calls);
    reset();a.ctrl.state=NVME_CTRL_CONNECTING;req=(struct request){.iod={&a.adminq},.state=MQ_RQ_IN_FLIGHT};CHECK(apple_nvme_timeout(&req)==BLK_EH_RESET_TIMER&&a.abort_reset&&scheduled==1&&!disable_calls);apple_nvme_recovery_work(&a.recovery_work);CHECK(cancels==2&&!restarts&&!a.recovery_flags);
    reset();a.ctrl.state=NVME_CTRL_LIVE;req=(struct request){.iod={&a.adminq},.state=MQ_RQ_IN_FLIGHT};CHECK(apple_nvme_timeout(&req)==BLK_EH_RESET_TIMER&&a.recover_to_live&&scheduled==1&&!disable_calls);apple_nvme_recovery_work(&a.recovery_work);CHECK(cancels==2&&restarts==1&&!a.recovery_flags);
    reset();a.ctrl.state=NVME_CTRL_LIVE;req=(struct request){.iod={&a.adminq},.state=MQ_RQ_IN_FLIGHT};fail_disable=true;CHECK(apple_nvme_timeout(&req)==BLK_EH_RESET_TIMER);apple_nvme_recovery_work(&a.recovery_work);CHECK(a.quarantined&&!cancels&&!drains&&!restarts&&held==1);
    reset();a.quarantined=true;apple_nvme_recovery_work(&a.recovery_work);CHECK(!reads&&!disable_calls&&!cancels);
    reset();CHECK(apple_nvme_poll(&hctx,&batch)==1&&drains==1);
    for(unsigned outcome=MQ_RQ_IDLE;outcome<=MQ_RQ_COMPLETE;outcome+=2) {
        reset();a.ctrl.state=NVME_CTRL_LIVE;req=(struct request){.iod={&a.adminq},.state=MQ_RQ_IN_FLIGHT};current_request=&req;complete_poll=true;poll_outcome=outcome;
        enum blk_eh_timer_return ret=apple_nvme_timeout(&req);
#ifdef EXPECT_TIMEOUT_IDLE_BUG
        if(outcome==MQ_RQ_IDLE){CHECK(ret==BLK_EH_RESET_TIMER&&scheduled==1);puts("REPRODUCED: IDLE completion incorrectly schedules recovery");}
        else CHECK(ret==BLK_EH_DONE&&!scheduled);
#else
        CHECK(ret==BLK_EH_DONE&&!scheduled&&!disable_calls);
#endif
    }
    reset();inject_quarantine_at_lock=true;int polled=apple_nvme_poll(&hctx,&batch);
#ifdef EXPECT_POLL_GATE_BUG
    CHECK(polled==1&&drains==1&&a.quarantined);puts("REPRODUCED: pre-lock poll gate accesses CQ after quarantine publication");
#else
    CHECK(!polled&&!drains&&a.quarantined);
#endif
    printf("PASS %u actual ANS control checks across %u scenarios\n",checks,scenarios);return 0;
}
