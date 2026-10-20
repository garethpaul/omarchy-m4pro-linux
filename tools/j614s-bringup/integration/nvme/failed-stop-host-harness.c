/* SPDX-License-Identifier: MIT */
/* Driver's exact cleanup function; fake RTKit APIs expose metadata retirement. */
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#define READ_ONCE(x) (x)
struct mutex { bool locked; };
typedef unsigned spinlock_t;
struct apple_rtkit { unsigned marker;bool stopped; };
struct apple_nvme { bool reset_ready,quarantined,inherited_rtkit;struct mutex disable_lock;spinlock_t event_lock;struct apple_rtkit *rtk; };
static unsigned freed,quiesced;
static void mutex_unlock(struct mutex *m) { assert(m->locked);m->locked=false; }
static struct mutex *acquire_guard(struct mutex *m) { assert(!m->locked);m->locked=true;return m; }
static void release_guard(struct mutex **m) { mutex_unlock(*m); }
#define guard(type) struct mutex *lock_guard __attribute__((cleanup(release_guard))) = acquire_guard
#define spin_lock_irqsave(l,f) do { assert(!*(l));*(l)=1;(f)=0; } while(0)
#define spin_unlock_irqrestore(l,f) do { (void)(f);assert(*(l));*(l)=0; } while(0)
static void apple_rtkit_free(struct apple_rtkit *r) { freed++;free(r); }
static void apple_rtkit_free_retaining_buffers(struct apple_rtkit *r) { apple_rtkit_free(r); }
static void apple_rtkit_quiesce_retaining_state(struct apple_rtkit *r) { quiesced++;r->stopped=true; }
#include "failed-stop-functions-under-test.c"
int main(void) {
    (void)apple_rtkit_quiesce_retaining_state;
    struct apple_nvme a={.reset_ready=true,.quarantined=true,.inherited_rtkit=true};
    a.rtk=calloc(1,sizeof(*a.rtk));assert(a.rtk);a.rtk->marker=0x6145a55a;
    struct apple_rtkit *paused_reader=a.rtk;
    apple_nvme_free_rtkit(&a);
#ifdef EXPECT_METADATA_FREE_BUG
    assert(freed==1&&!a.rtk&&!quiesced);puts("REPRODUCED: failed-stop cleanup retires metadata still referenced by paused reader");
    (void)paused_reader;
#else
    if(freed || a.rtk!=paused_reader || quiesced!=1){fputs("FAIL: failed-stop cleanup retired paused-reader metadata\n",stderr);return 1;}
    assert(paused_reader->marker==0x6145a55a&&paused_reader->stopped&&!a.reset_ready&&!a.disable_lock.locked);
    /* Test-only release after retained-state assertions; never a real live-DMA operation. */
    apple_rtkit_free_retaining_buffers(a.rtk);a.rtk=NULL;
    puts("PASS: failed-stop cleanup retains metadata for paused reader after RX quiescence");
#endif
    return 0;
}
