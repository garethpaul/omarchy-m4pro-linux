/* SPDX-License-Identifier: MIT */
/* Exact source metadata predicates against refcounted fake OF topology. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;
typedef uint64_t resource_size_t;
#define IORESOURCE_MEM 1
struct resource { resource_size_t start,end; };
struct device_node {
    const char *compatible;struct device_node *parent,*mbox,*sart;
    bool pd,reset,fail_address;unsigned refs;struct resource reg;
    int mbox_count,sart_count,cells_result;unsigned mbox_cells;
};
struct device { struct device_node *of_node; };
struct platform_device { struct device dev;struct resource reg[3];bool nvme,ans,extra; };
struct apple_nvme_hw { bool j614s_diagnostic; };
static bool board_j614s,board_t6040;
static unsigned gets,node_puts,checks,scenarios;
static struct device_node *of_node_get(struct device_node *n) { if(n){n->refs++;gets++;}return n; }
static void of_node_put(struct device_node *n) { if(n){assert(n->refs);n->refs--;node_puts++;} }
static struct device_node *of_get_next_parent(struct device_node *n) { struct device_node *p=n->parent;of_node_put(n);return of_node_get(p); }
static void *of_find_property(struct device_node *n,const char *name,void *len) { (void)len;assert(!strcmp(name,"power-domains")||!strcmp(name,"resets"));return (!strcmp(name,"resets")?n->reset:n->pd)?n:NULL; }
static bool of_device_is_compatible(struct device_node *n,const char *c) { return n && !strcmp(n->compatible,c); }
static bool of_machine_is_compatible(const char *c) { assert(!strcmp(c,"apple,j614s")||!strcmp(c,"apple,t6040"));return !strcmp(c,"apple,j614s")?board_j614s:board_t6040; }
static struct device_node *of_parse_phandle(struct device_node *n,const char *p,int index) { assert(!index);return of_node_get(!strcmp(p,"mboxes")?n->mbox:n->sart); }
static int of_property_read_u32(struct device_node *n,const char *name,unsigned *v) { assert(!strcmp(name,"#mbox-cells"));*v=n->mbox_cells;return n->cells_result; }
static int of_address_to_resource(struct device_node *n,int index,struct resource *r) { assert(!index);if(n->fail_address)return -EINVAL;*r=n->reg;return 0; }
static resource_size_t resource_size(const struct resource *r) { return r->end-r->start+1; }
static struct resource *platform_get_resource_byname(struct platform_device *d,int type,const char *name) { assert(type==IORESOURCE_MEM);if(!strcmp(name,"nvme"))return d->nvme?&d->reg[0]:NULL;assert(!strcmp(name,"ans"));return d->ans?&d->reg[1]:NULL; }
static struct resource *platform_get_resource(struct platform_device *d,int type,unsigned n) { assert(type==IORESOURCE_MEM && n==2);return d->extra?&d->reg[2]:NULL; }
static int of_count_phandle_with_args(struct device_node *n,const char *name,const char *cells) { if(!strcmp(name,"mboxes")){assert(!strcmp(cells,"#mbox-cells"));return n->mbox_count;}assert(!strcmp(name,"apple,sart")&&!cells);return n->sart_count; }
#include "topology-functions-under-test.c"
#define CHECK(c) do { checks++;if(!(c)){fprintf(stderr,"FAIL %d: %s\n",__LINE__,#c);exit(1);} } while(0)
static struct device_node root,consumer,mbox,sart;
static struct platform_device pdev;static struct apple_nvme_hw hw;
static struct resource resource(resource_size_t start,resource_size_t size) { return (struct resource){start,start+size-1}; }
static void reset(void) {
    CHECK(!root.refs&&!consumer.refs&&!mbox.refs&&!sart.refs);scenarios++;gets=node_puts=0;
    root=(struct device_node){.compatible="root"};
    mbox=(struct device_node){.compatible="apple,asc-mailbox-v4",.parent=&root,.reg=resource(0x409608000ULL,0x4000)};
    sart=(struct device_node){.compatible="apple,t6000-sart",.parent=&root,.reg=resource(0x40dc50000ULL,0xc000)};
    consumer=(struct device_node){.compatible="apple,j614s-nvme-diagnostic",.parent=&root,.mbox=&mbox,.sart=&sart,.mbox_count=1,.sart_count=1};
    pdev=(struct platform_device){.dev={&consumer},.reg={resource(0x44dcc0000ULL,0x30000),resource(0x409600000ULL,0x4000)},.nvme=true,.ans=true};
    hw=(struct apple_nvme_hw){true};board_j614s=board_t6040=true;
}
static void refuse(void) { CHECK(apple_nvme_check_j614s_resources(&pdev,&hw)<0);CHECK(gets==node_puts&&!root.refs&&!consumer.refs&&!mbox.refs&&!sart.refs); }
int main(void) {
    reset();CHECK(!apple_nvme_check_j614s_resources(&pdev,&hw)&&gets==node_puts);
    reset();CHECK(apple_nvme_check_j614s_resources(&pdev,NULL)==-ENODEV);
    reset();hw.j614s_diagnostic=false;refuse();board_j614s=false;CHECK(!apple_nvme_check_j614s_resources(&pdev,&hw));
    reset();board_j614s=false;refuse();reset();board_t6040=false;refuse();reset();consumer.compatible="apple,t8132-nvme-ans2";refuse();
    reset();pdev.nvme=false;refuse();reset();pdev.ans=false;refuse();reset();pdev.extra=true;refuse();
    for(unsigned reg=0;reg<2;reg++)for(unsigned part=0;part<2;part++){reset();if(part)pdev.reg[reg].end--;else pdev.reg[reg].start++;refuse();}
    for(unsigned provider=0;provider<2;provider++)for(unsigned mode=0;mode<7;mode++) {
        reset();struct device_node *n=provider?&sart:&mbox;
        if(mode==0)n->compatible="wrong";if(mode==1)n->reg.start++;if(mode==2)n->reg.end--;
        if(mode==3)n->fail_address=true;if(mode==4){if(provider)consumer.sart=NULL;else consumer.mbox=NULL;}
        if(mode==5){if(provider)consumer.sart_count=0;else consumer.mbox_count=0;}
        if(mode==6){if(provider)consumer.sart_count=2;else consumer.mbox_count=2;}
        refuse();
    }
    for(unsigned node=0;node<4;node++)for(unsigned property=0;property<2;property++) {
        reset();struct device_node *n=node==0?&consumer:node==1?&mbox:node==2?&sart:&root;
        if(property)n->reset=true;else n->pd=true;refuse();
    }
    reset();consumer.mbox_count=-EINVAL;refuse();reset();consumer.sart_count=-ENOENT;refuse();
    reset();mbox.mbox_cells=1;refuse();reset();mbox.cells_result=-EINVAL;refuse();
    printf("PASS %u actual topology checks across %u scenarios; all OF references balanced\n",checks,scenarios);return 0;
}
