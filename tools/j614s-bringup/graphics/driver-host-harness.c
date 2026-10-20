/* SPDX-License-Identifier: MIT */
/* Host regression harness: compile the actual kernel driver, not a state model.
 * Generated Linux include stubs contain no logic; this TU supplies fake host
 * facilities. None of these fake functions are a hardware qualification. */
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>

typedef uint32_t u32;
typedef uint64_t resource_size_t;
#define __iomem
#define BIT(n) (1U << (n))
#define GFP_KERNEL 0
#define IORESOURCE_MEM 0
#define SZ_16M (16U * 1024U * 1024U)
#define SZ_16K (16U * 1024U)
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x, value) ((x) = (value))
#define IS_ERR(ptr) ((uintptr_t)(ptr) >= (uintptr_t)-4095)
#define PTR_ERR(ptr) ((int)(intptr_t)(ptr))
typedef struct { atomic_int counter; } atomic_t;
static inline __attribute__((unused)) void atomic_set(atomic_t *v, int n) { atomic_store(&v->counter,n); }
static inline __attribute__((unused)) int atomic_read(const atomic_t *v) { return atomic_load(&v->counter); }
static inline __attribute__((unused)) int atomic_cmpxchg(atomic_t *v, int old, int next)
{
	atomic_compare_exchange_strong(&v->counter,&old,next); return old;
}

struct device { void *of_node, *driver_data; };
struct platform_device { struct device dev; };
struct resource { resource_size_t start, end; const char *name; };
struct attribute { int unused; };
struct device_attribute { struct attribute attr; };
struct of_device_id { const char *compatible; };
struct platform_driver {
	int (*probe)(struct platform_device *);
	void (*remove)(struct platform_device *), (*shutdown)(struct platform_device *);
	struct { const char *name; const void *of_match_table, *dev_groups; } driver;
};
#define DEVICE_ATTR_RO(name) struct device_attribute dev_attr_##name
#define ATTRIBUTE_GROUPS(name) static const void *name##_groups[] = {name##_attrs,NULL}
#define MODULE_DEVICE_TABLE(type,table)
#define module_platform_driver(driver) static void *keep_driver __attribute__((unused)) = &(driver)
#define MODULE_DESCRIPTION(description)
#define MODULE_LICENSE(license)

struct apple_rtkit_shmem { size_t size; uint64_t iova; void *iomem; bool is_mapped; };
struct apple_rtkit_ops {
	int (*shmem_setup)(void *,struct apple_rtkit_shmem *);
	void (*shmem_destroy)(void *,struct apple_rtkit_shmem *);
	void (*crashed)(void *,const void *,size_t);
};
struct apple_rtkit { const struct apple_rtkit_ops *ops; void *cookie; bool running, crashed; unsigned int version; };

static struct resource resources[3];
static unsigned char *asc_memory,*sgx_memory,*data_memory;
static struct apple_rtkit fake_rtkit;
static void *allocation;
static bool board_ok=true, crash_inside_wake, crash_during_running_check, fail_quiesce;
static const char *firmware="26.6.2-25G83-g16s-b000";
static unsigned int wake_calls, run_writes, quiesce_calls;

static int of_machine_is_compatible(const char *name) { return board_ok && !strcmp(name,"apple,j614s"); }
static int of_property_read_string(void *node,const char *key,const char **value)
{
	(void)node; assert(!strcmp(key,"apple,bootstrap-firmware")); *value=firmware; return 0;
}
static void *devm_kzalloc(struct device *dev,size_t size,int flags)
{
	(void)dev; (void)flags; assert(!allocation); allocation=calloc(1,size); assert(allocation); return allocation;
}
static struct resource *platform_get_resource_byname(struct platform_device *pdev,int kind,const char *name)
{
	(void)pdev; (void)kind;
	for(unsigned int i=0;i<3;i++) if(!strcmp(name,resources[i].name)) return &resources[i];
	return NULL;
}
static resource_size_t resource_size(const struct resource *res) { return res->end-res->start+1; }
static void *devm_ioremap_resource(struct device *dev,struct resource *res)
{
	(void)dev;
	if(res->start==resources[0].start) return asc_memory;
	if(res->start==resources[1].start) { assert(resource_size(res)==SZ_16M); return sgx_memory; }
	if(res->start==resources[2].start) return data_memory;
	abort();
}
static u32 readl(const void *address) { return *(const u32 *)address; }
static void writel(u32 value,void *address)
{
	if(address==asc_memory+0x44 && (value & BIT(4))) run_writes++;
	*(u32 *)address=value;
}
static void platform_set_drvdata(struct platform_device *pdev,void *data) { pdev->dev.driver_data=data; }
static void *platform_get_drvdata(struct platform_device *pdev) { return pdev->dev.driver_data; }
static void *dev_get_drvdata(struct device *dev) { return dev->driver_data; }
static void dev_info(struct device *dev,const char *format,...) { (void)dev; (void)format; }
static void dev_err(struct device *dev,const char *format,...) { (void)dev; (void)format; }
static int dev_err_probe(struct device *dev,int error,const char *format,...)
{
	(void)dev; (void)format; return error;
}
static ssize_t sysfs_emit(char *buffer,const char *format,...)
{
	int result; va_list args; va_start(args,format); result=vsnprintf(buffer,4096,format,args); va_end(args); return result;
}
static struct apple_rtkit *devm_apple_rtkit_init(struct device *dev,void *cookie,void *unused,int index,const struct apple_rtkit_ops *ops)
{
	(void)dev; (void)unused; (void)index; fake_rtkit.cookie=cookie; fake_rtkit.ops=ops; return &fake_rtkit;
}
static int apple_rtkit_wake(struct apple_rtkit *rtk)
{
	wake_calls++; rtk->version=12; rtk->running=true;
	if(crash_inside_wake) {
		/* The real driver callback runs at the exact causal point: after
		 * protocol negotiation and before wake returns success. */
		rtk->crashed=true; rtk->running=false;
		rtk->ops->crashed(rtk->cookie,NULL,0x8000);
	}
	return 0;
}
static unsigned int apple_rtkit_protocol_version(struct apple_rtkit *rtk) { return rtk->version; }
static bool apple_rtkit_is_running(struct apple_rtkit *rtk)
{
	bool observed=rtk->running && !rtk->crashed;
	if(crash_during_running_check) {
		/* Deterministic concurrency interleaving: report the just-observed
		 * value while a crash occurs before caller publication/cmpxchg. */
		crash_during_running_check=false;
		rtk->crashed=true; rtk->running=false;
		rtk->ops->crashed(rtk->cookie,NULL,0x8000);
	}
	return observed;
}
static inline __attribute__((unused)) bool apple_rtkit_is_crashed(struct apple_rtkit *rtk) { return rtk->crashed; }
static int apple_rtkit_quiesce(struct apple_rtkit *rtk)
{
	quiesce_calls++; if(fail_quiesce) return -EIO; rtk->running=false; return 0;
}

#include "g16-bootstrap-under-test.c"

static struct platform_device fresh_device(void)
{
	struct platform_device pdev={0};
	free(allocation); allocation=NULL;
	memset(asc_memory,0,0x4000); memset(sgx_memory,0,SZ_16M); memset(data_memory,0,0x138000);
	fake_rtkit=(struct apple_rtkit){0};
	board_ok=true; crash_inside_wake=false; crash_during_running_check=false; fail_quiesce=false;
	firmware="26.6.2-25G83-g16s-b000";
	wake_calls=run_writes=quiesce_calls=0;
	*(u32 *)(sgx_memory+0xe80100)=0xff; *(u32 *)(sgx_memory+0xe80110)=0xff;
	*(u32 *)(sgx_memory+0xd04000)=0x0a031100;
	*(u32 *)(sgx_memory+0xe01500)=0xf6fdb;
	return pdev;
}
static void assert_state(struct platform_device *pdev,const char *expected)
{
	char buffer[4096];
	assert(bootstrap_state_show(&pdev->dev,NULL,buffer)>0);
	assert(strstr(buffer,expected)==buffer);
}
int main(int argc,char **argv)
{
	struct platform_device pdev;
	bool expect_bug = argc==2 && !strcmp(argv[1],"--expect-baseline-bug");
	int ret;
	asc_memory=calloc(1,0x4000); sgx_memory=calloc(1,SZ_16M); data_memory=calloc(1,0x138000);
	assert(asc_memory && sgx_memory && data_memory);
	resources[0]=(struct resource){0x28a600000ULL,0x28a603fffULL,"asc"};
	resources[1]=(struct resource){0x288000000ULL,0x28b757fffULL,"sgx"};
	resources[2]=(struct resource){0x10001d34000ULL,0x10001e6bfffULL,"firmware-data"};

	pdev=fresh_device();
	assert(j614s_gfx_probe(&pdev)==0); assert(wake_calls==1 && run_writes==1);
	assert_state(&pdev,"RTKIT_READY ");
	j614s_gfx_remove(&pdev);
	assert(quiesce_calls==1 && !(readl(asc_memory+0x44)&BIT(4)));
	assert_state(&pdev,"NOT_READY ");

	pdev=fresh_device(); crash_inside_wake=true;
	ret=j614s_gfx_probe(&pdev);
	assert(wake_calls==1);
	if(expect_bug) {
		assert(ret==0); assert_state(&pdev,"RTKIT_READY ");
		assert(!apple_rtkit_is_running(&fake_rtkit));
		puts("REPRODUCED: baseline publishes RTKIT_READY after actual crash callback during wake");
	} else {
		if(ret!=-EIO) {
			char buffer[4096];
			bootstrap_state_show(&pdev.dev,NULL,buffer);
			fprintf(stderr,"FAIL: probe returned %d after crash; observed %s",ret,buffer);
			free(allocation); free(asc_memory); free(sgx_memory); free(data_memory);
			return 1;
		}
		assert(ret==-EIO); assert_state(&pdev,"CRASHED ");
		assert(!(readl(asc_memory+0x44)&BIT(4)));
		puts("PASS: candidate rejects crash-during-wake and preserves CRASHED diagnosis");
	}

	pdev=fresh_device(); *(u32 *)(sgx_memory+0xd04000)=0x0a021100;
	assert(j614s_gfx_probe(&pdev)==-ENODEV); assert(wake_calls==0 && run_writes==0);
	pdev=fresh_device(); firmware="unqualified";
	assert(j614s_gfx_probe(&pdev)==-ENODEV); assert(wake_calls==0 && run_writes==0);
	pdev=fresh_device(); board_ok=false;
	assert(j614s_gfx_probe(&pdev)==-ENODEV); assert(wake_calls==0 && run_writes==0);
	pdev=fresh_device(); *(u32 *)(sgx_memory+0xe80110)=0;
	assert(j614s_gfx_probe(&pdev)==-EBUSY); assert(wake_calls==0 && run_writes==0);
	if(!expect_bug) {
		pdev=fresh_device(); crash_during_running_check=true;
		assert(j614s_gfx_probe(&pdev)==-EIO);
		assert_state(&pdev,"CRASHED ");
		assert(!(readl(asc_memory+0x44)&BIT(4)));
		puts("PASS: actual callback between running observation and readiness publication defeats cmpxchg");
		pdev=fresh_device(); assert(j614s_gfx_probe(&pdev)==0);
		fake_rtkit.crashed=true; fake_rtkit.running=false;
		fake_rtkit.ops->crashed(fake_rtkit.cookie,NULL,0x8000);
		assert_state(&pdev,"CRASHED "); j614s_gfx_remove(&pdev);
		assert_state(&pdev,"CRASHED "); assert(quiesce_calls==0);
		assert(!(readl(asc_memory+0x44)&BIT(4)));
	}
	free(allocation); free(asc_memory); free(sgx_memory); free(data_memory);
	puts("PASS: actual driver normal ready/quiesce and board/firmware/GPU/power guards");
	return 0;
}
