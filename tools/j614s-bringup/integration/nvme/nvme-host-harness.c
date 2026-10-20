/* SPDX-License-Identifier: MIT */
/* Actual inherited ANS predicates/callbacks run against fake registers/DMA. */
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;typedef uint64_t phys_addr_t;typedef uint64_t dma_addr_t;
#define READ_ONCE(x) (x)
#define GFP_KERNEL 0
#define MEMREMAP_WB 1
#define DMA_FROM_DEVICE 1
#define DMA_ATTR_SKIP_CPU_SYNC 1
#define IORESOURCE_SYSTEM_RAM 1
#define IORES_DESC_NONE 0
#define REGION_INTERSECTS 1
#define IS_ALIGNED(x,n) (((x)&((n)-1))==0)
#define PHYS_PFN(x) ((x)>>14)
#define check_add_overflow(a,b,c) __builtin_add_overflow((a),(b),(c))
#define dev_err(...) ((void)0)
#define APPLE_ANS_LINEAR_SQ_CTRL 0x24908
#define APPLE_ANS_LINEAR_SQ_EN 1
#define APPLE_ANS_COPROC_CPU_CONTROL 0x44
#define APPLE_ANS_COPROC_CPU_CONTROL_RUN 0x10
#define APPLE_ANS_BOOT_STATUS 0x1300
#define APPLE_ANS_BOOT_STATUS_OK 0xde71ce55
#define NVME_REG_CC 0x14
#define NVME_REG_CSTS 0x1c
#define NVME_CC_ENABLE 1
#define NVME_CSTS_RDY 1
#define NVME_CSTS_CFS 2
#define PAGE_SIZE 16384
#define BASE 0x10000ULL
struct device_node { int property_result;const char *handoff; };
struct device { struct device_node *of_node;unsigned refs; };
struct apple_sart { bool inherited; };
struct apple_nvme_hw { bool needs_ioq_register,j614s_diagnostic; };
struct apple_nvme {
    struct device *dev;struct apple_sart *sart;struct apple_nvme_hw *hw;
    void *mmio_coproc,*mmio_nvme;
    bool inherited_rtkit,handoff_disabled,quarantined,removing;
};
struct apple_rtkit_shmem {
    void *buffer,*iomem;size_t size;dma_addr_t iova;
    bool is_mapped,needs_dma_sync;void *private;
};
struct page { bool valid,reserved,highmem,linear; };
static struct page pages[4];
static unsigned char storage[4*PAGE_SIZE];
static u32 asc[0x2000/4], nvme[0x30000/4];
static struct device_node node;
static struct device dev;
static struct apple_sart sart;
static struct apple_nvme_hw hw;
static struct apple_nvme anv;
static unsigned mmio_reads,sart_queries,page_checks,remaps,maps,unmaps,unmap_attrs,device_syncs;
static unsigned objects,device_gets,device_puts,coherent_allocs,coherent_frees,add_regions,remove_regions;
static int ram_coverage=REGION_INTERSECTS;
static bool fail_object,fail_remap,fail_dma,bounce,fail_coherent,fail_add;
static unsigned cache_alignment=128;
static u32 readl(const void *p) {
    uintptr_t v=(uintptr_t)p;
    assert((v>=(uintptr_t)asc && v<(uintptr_t)(asc+sizeof(asc)/sizeof(*asc)))
        || (v>=(uintptr_t)nvme && v<(uintptr_t)(nvme+sizeof(nvme)/sizeof(*nvme))));
    mmio_reads++;return *(const u32 *)p;
}
static int of_property_read_string(struct device_node *n,const char *name,const char **value) {
    assert(!strcmp(name,"apple,rtkit-handoff"));if(n->property_result)return n->property_result;
    *value=n->handoff;return 0;
}
static unsigned dma_get_cache_alignment(void) { return cache_alignment; }
static bool apple_sart_is_inherited_region(struct apple_sart *s,phys_addr_t p,size_t n) {
    (void)p;(void)n;sart_queries++;return s->inherited;
}
static int region_intersects(phys_addr_t a,size_t n,unsigned flags,unsigned desc) {
    (void)a;(void)n;assert(flags==IORESOURCE_SYSTEM_RAM && desc==IORES_DESC_NONE);return ram_coverage;
}
static bool pfn_valid(unsigned long pfn) {
    page_checks++;return pfn>=PHYS_PFN(BASE) && pfn<PHYS_PFN(BASE)+4 && pages[pfn-PHYS_PFN(BASE)].valid;
}
static struct page *pfn_to_page(unsigned long pfn) { assert(pfn>=PHYS_PFN(BASE) && pfn<PHYS_PFN(BASE)+4);return &pages[pfn-PHYS_PFN(BASE)]; }
#define PageReserved(p) ((p)->reserved)
#define PageHighMem(p) ((p)->highmem)
static void *page_to_virt(struct page *p) { return storage+(p-pages)*PAGE_SIZE; }
static bool virt_addr_valid(const void *p) { size_t off=(const unsigned char *)p-storage;return off<sizeof(storage) && pages[off/PAGE_SIZE].linear; }
static void *allocate_object(size_t n) { if(fail_object)return NULL;objects++;return calloc(1,n); }
#define kzalloc_obj(obj,...) allocate_object(sizeof(obj))
static void kfree(void *p) { if(p){assert(objects);objects--;free(p);} }
static void *memremap(phys_addr_t a,size_t n,unsigned mode) {
    assert(mode==MEMREMAP_WB);assert(a>=BASE && n<=sizeof(storage) && a-BASE<=sizeof(storage)-n);
    remaps++;return fail_remap?NULL:storage+(a-BASE);
}
static void memunmap(void *p) { (void)p;assert(remaps);unmaps++; }
static dma_addr_t dma_map_single_attrs(struct device *d,void *p,size_t n,int direction,unsigned attrs) {
    (void)d;(void)n;assert(direction==DMA_FROM_DEVICE && attrs==DMA_ATTR_SKIP_CPU_SYNC);maps++;
    if(fail_dma)return UINT64_MAX;
    return BASE+((unsigned char *)p-storage)+(bounce?PAGE_SIZE:0);
}
static bool dma_mapping_error(struct device *d,dma_addr_t a) { (void)d;return a==UINT64_MAX; }
static void dma_unmap_single_attrs(struct device *d,dma_addr_t a,size_t n,int direction,unsigned attrs) {
    (void)d;(void)a;(void)n;assert(direction==DMA_FROM_DEVICE && attrs==DMA_ATTR_SKIP_CPU_SYNC);unmap_attrs++;
}
static void dma_sync_single_for_device(struct device *d,dma_addr_t a,size_t n,int direction) {
    (void)d;(void)a;(void)n;assert(direction==DMA_FROM_DEVICE);device_syncs++;
}
static struct device *get_device(struct device *d) { d->refs++;device_gets++;return d; }
static void put_device(struct device *d) { assert(d->refs>1);d->refs--;device_puts++; }
static void dma_unmap_single(struct device *d,dma_addr_t a,size_t n,int direction) {
    (void)d;(void)a;(void)n;assert(direction==DMA_FROM_DEVICE);unmaps++;
}
static void *dma_alloc_coherent(struct device *d,size_t n,dma_addr_t *a,int flags) {
    (void)d;(void)flags;coherent_allocs++;if(fail_coherent)return NULL;assert(n<=sizeof(storage));*a=BASE;return storage;
}
static void dma_free_coherent(struct device *d,size_t n,void *p,dma_addr_t a) { (void)d;(void)n;(void)p;(void)a;coherent_frees++; }
static int apple_sart_add_allowed_region(struct apple_sart *s,dma_addr_t a,size_t n) { (void)s;(void)a;(void)n;add_regions++;return fail_add?-EINVAL:0; }
static void apple_sart_remove_allowed_region(struct apple_sart *s,dma_addr_t a,size_t n) { (void)s;(void)a;(void)n;remove_regions++; }
#include "nvme-functions-under-test.c"
static unsigned checks;
#define CHECK(c) do { checks++;if(!(c)){fprintf(stderr,"FAIL check%u at line%d: %s\n",checks,__LINE__,#c);exit(1);} } while(0)
static void reset(void) {
    assert(!objects);memset(asc,0,sizeof(asc));memset(nvme,0,sizeof(nvme));memset(storage,0xa5,sizeof(storage));
    for(unsigned i=0;i<4;i++)pages[i]=(struct page){true,true,false,true};
    node=(struct device_node){-EINVAL,NULL};dev=(struct device){&node,1};sart=(struct apple_sart){true};hw=(struct apple_nvme_hw){.needs_ioq_register=true};
    anv=(struct apple_nvme){.dev=&dev,.sart=&sart,.hw=&hw,.mmio_coproc=asc,.mmio_nvme=nvme,.inherited_rtkit=true};
    asc[APPLE_ANS_COPROC_CPU_CONTROL/4]=APPLE_ANS_COPROC_CPU_CONTROL_RUN;
    nvme[APPLE_ANS_BOOT_STATUS/4]=APPLE_ANS_BOOT_STATUS_OK;nvme[NVME_REG_CC/4]=1;nvme[NVME_REG_CSTS/4]=1;
    mmio_reads=sart_queries=page_checks=remaps=maps=unmaps=unmap_attrs=device_syncs=device_gets=device_puts=coherent_allocs=coherent_frees=add_regions=remove_regions=0;
    fail_object=fail_remap=fail_dma=bounce=fail_coherent=fail_add=false;ram_coverage=REGION_INTERSECTS;
}
static struct apple_rtkit_shmem borrowed(void) { return (struct apple_rtkit_shmem){.size=PAGE_SIZE*2,.iova=BASE}; }
static void refuse_buffer(void) {
    struct apple_rtkit_shmem b=borrowed();CHECK(apple_nvme_sart_dma_setup(&anv,&b)==-EINVAL);
    CHECK(!remaps && !maps && !device_syncs && !device_gets && !objects && !b.buffer && !b.private);
}
int main(void) {
    reset();CHECK(apple_nvme_can_adopt_rtkit(&anv));CHECK(mmio_reads>0);CHECK(apple_nvme_read_handoff(&anv)==0 && !anv.handoff_disabled);
    hw.needs_ioq_register=false;CHECK(!apple_nvme_can_adopt_rtkit(&anv));hw.needs_ioq_register=true;
    asc[APPLE_ANS_COPROC_CPU_CONTROL/4]=0;CHECK(!apple_nvme_can_adopt_rtkit(&anv));asc[APPLE_ANS_COPROC_CPU_CONTROL/4]=0x10;
    nvme[APPLE_ANS_BOOT_STATUS/4]=0;CHECK(!apple_nvme_can_adopt_rtkit(&anv));nvme[APPLE_ANS_BOOT_STATUS/4]=APPLE_ANS_BOOT_STATUS_OK;
    for(unsigned cc=0;cc<2;cc++)for(unsigned csts=0;csts<4;csts++)for(unsigned disabled=0;disabled<2;disabled++) {
        nvme[NVME_REG_CC/4]=cc;nvme[NVME_REG_CSTS/4]=csts;anv.handoff_disabled=disabled;
        bool wanted=(cc==1 && csts==1 && disabled==0) || (cc==0 && csts==0 && disabled==1);
        CHECK(apple_nvme_can_adopt_rtkit(&anv)==wanted);
    }
    reset();node.property_result=0;node.handoff="wrong";CHECK(apple_nvme_read_handoff(&anv)==-EINVAL);
    node.handoff="nvme-disabled-v1";CHECK(apple_nvme_read_handoff(&anv)==-EIO);
    nvme[NVME_REG_CC/4]=nvme[NVME_REG_CSTS/4]=0;CHECK(apple_nvme_read_handoff(&anv)==0 && anv.handoff_disabled);
    reset();anv.inherited_rtkit=false;refuse_buffer();reset();sart.inherited=false;refuse_buffer();
    for(unsigned state=0;state<3;state++) {
        reset();ram_coverage=(int)state;if(state!=REGION_INTERSECTS)refuse_buffer();
    }
    for(unsigned property=0;property<4;property++) {
        reset();if(property==0)pages[1].valid=false;if(property==1)pages[1].reserved=false;
        if(property==2)pages[1].highmem=true;if(property==3)pages[1].linear=false;refuse_buffer();CHECK(page_checks>=2);
    }
    reset();struct apple_rtkit_shmem b=borrowed();b.iova=BASE+64;CHECK(!apple_nvme_in_inherited_rtkit_range(&anv,&b) && !sart_queries);
    b=borrowed();b.size=PAGE_SIZE+1;CHECK(!apple_nvme_in_inherited_rtkit_range(&anv,&b));
    b=borrowed();b.size=0;CHECK(!apple_nvme_in_inherited_rtkit_range(&anv,&b));
    b=borrowed();b.iova=UINT64_MAX-127;b.size=256;CHECK(!apple_nvme_in_inherited_rtkit_range(&anv,&b));
    reset();fail_object=true;b=borrowed();CHECK(apple_nvme_sart_dma_setup(&anv,&b)==-ENOMEM && !remaps && !objects);
    reset();fail_remap=true;b=borrowed();CHECK(apple_nvme_sart_dma_setup(&anv,&b)==-ENOMEM && !maps && !objects);
    reset();fail_dma=true;b=borrowed();CHECK(apple_nvme_sart_dma_setup(&anv,&b)==-ENOMEM && unmaps==1 && !unmap_attrs && !device_syncs && !device_gets && !objects);
    reset();bounce=true;b=borrowed();CHECK(apple_nvme_sart_dma_setup(&anv,&b)==-EINVAL && unmap_attrs==1 && unmaps==1 && !device_syncs && !device_gets && !objects);
    for(size_t i=0;i<sizeof(storage);i++)CHECK(storage[i]==0xa5);
    reset();b=borrowed();CHECK(apple_nvme_sart_dma_setup(&anv,&b)==0);
    CHECK(b.is_mapped && b.needs_dma_sync && b.private && dev.refs==2 && device_gets==1 && device_syncs==1 && !add_regions);
    apple_nvme_sart_dma_destroy(NULL,&b);CHECK(dev.refs==1 && device_puts==1 && !objects && unmaps==2 && !remove_regions);
    reset();anv.removing=true;b=borrowed();CHECK(apple_nvme_sart_dma_setup(&anv,&b)==-ESHUTDOWN && !sart_queries && !maps);
    reset();anv.quarantined=true;b=borrowed();CHECK(apple_nvme_sart_dma_setup(&anv,&b)==-ESHUTDOWN && !sart_queries && !maps);
    reset();b=(struct apple_rtkit_shmem){.size=PAGE_SIZE};CHECK(apple_nvme_sart_dma_setup(&anv,&b)==0 && coherent_allocs==1 && add_regions==1);
    apple_nvme_sart_dma_destroy(&anv,&b);CHECK(coherent_frees==1 && remove_regions==1);
    reset();fail_add=true;b=(struct apple_rtkit_shmem){.size=PAGE_SIZE};CHECK(apple_nvme_sart_dma_setup(&anv,&b)==-ENOMEM && coherent_frees==1 && !b.buffer);
    printf("PASS: %u actual NVMe admission/borrowed-buffer host checks; no controller writes; hardware UNTESTED\n",checks);
    return 0;
}
