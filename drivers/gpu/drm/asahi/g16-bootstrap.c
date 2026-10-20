// SPDX-License-Identifier: GPL-2.0-only OR MIT
/* J614s G16S bootstrap qualification. No render node or application INIT. */
#include <linux/atomic.h>
#include <linux/bitfield.h>
#include <linux/device.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/soc/apple/rtkit.h>
#include <linux/sizes.h>

#define CPU_CONTROL 0x44
#define CPU_RUN BIT(4)
#define G16_ID 0x0a031100
#define FW_DATA_SIZE 0x138000
#define CRASH_OFFSET 0xa0000
#define CRASH_SIZE 0x8000

enum j614s_gfx_state {
	J614S_GFX_NOT_READY,
	J614S_GFX_READY,
	J614S_GFX_CRASHED,
};

struct j614s_gfx {
	struct device *dev;
	void __iomem *asc, *sgx, *data;
	struct resource *data_res;
	struct apple_rtkit *rtk;
	atomic_t state;
};

static int j614s_gfx_shmem_setup(void *cookie, struct apple_rtkit_shmem *buf)
{
	struct j614s_gfx *gfx = cookie;

	/* The exact-build B-silicon firmware supplies a physical buffer in its DATA.
	 * Refuse Linux allocations and every other address/size rather than assuming
	 * that an unqualified G16 UAT mapping or an A18 fixed VA is valid.
	 */
	if (buf->size != CRASH_SIZE ||
	    buf->iova != gfx->data_res->start + CRASH_OFFSET)
		return -ERANGE;
	buf->iomem = gfx->data + CRASH_OFFSET;
	buf->is_mapped = true;
	dev_info(gfx->dev, "firmware crash buffer %pad size %#zx mapped within ADT DATA\n",
		 &buf->iova, buf->size);
	return 0;
}

static void j614s_gfx_shmem_destroy(void *cookie, struct apple_rtkit_shmem *buf)
{
	/* Firmware owns this memory. The enclosing devres mapping owns the view. */
}

static void j614s_gfx_crashed(void *cookie, const void *log, size_t size)
{
	struct j614s_gfx *gfx = cookie;

	atomic_set(&gfx->state, J614S_GFX_CRASHED);
	dev_err(gfx->dev, "G16 firmware crashed; RTKit captured %#zx bytes\n", size);
}

static const struct apple_rtkit_ops j614s_gfx_ops = {
	.shmem_setup = j614s_gfx_shmem_setup,
	.shmem_destroy = j614s_gfx_shmem_destroy,
	.crashed = j614s_gfx_crashed,
};

static ssize_t bootstrap_state_show(struct device *dev,
				    struct device_attribute *attr, char *buf)
{
	struct j614s_gfx *gfx = dev_get_drvdata(dev);
	int state = atomic_read(&gfx->state);
	const char *name;

	if (state == J614S_GFX_CRASHED || apple_rtkit_is_crashed(gfx->rtk))
		name = "CRASHED";
	else if (state == J614S_GFX_READY && apple_rtkit_is_running(gfx->rtk))
		name = "RTKIT_READY";
	else
		name = "NOT_READY";
	return sysfs_emit(buf, "%s protocol=%u rendering=unimplemented\n",
		name,
		apple_rtkit_protocol_version(gfx->rtk));
}
static DEVICE_ATTR_RO(bootstrap_state);
static struct attribute *j614s_gfx_attrs[] = { &dev_attr_bootstrap_state.attr, NULL };
ATTRIBUTE_GROUPS(j614s_gfx);

static void j614s_gfx_stop(struct j614s_gfx *gfx)
{
	u32 value;

	/* A later stop must not erase the latched crash diagnosis. */
	atomic_cmpxchg(&gfx->state, J614S_GFX_READY, J614S_GFX_NOT_READY);
	value = readl(gfx->asc + CPU_CONTROL);
	writel(value & ~CPU_RUN, gfx->asc + CPU_CONTROL);
	value = readl(gfx->asc + CPU_CONTROL);
	if (value & CPU_RUN)
		dev_err(gfx->dev, "G16 CPU RUN did not clear: %#x\n", value);
	else
		dev_info(gfx->dev, "G16 CPU RUN cleared, control=%#x\n", value);
}

static int j614s_gfx_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct j614s_gfx *gfx;
	struct resource *res, core_regs;
	const char *firmware;
	u32 id, masks;
	int ret;

	if (!of_machine_is_compatible("apple,j614s") ||
	    of_property_read_string(dev->of_node, "apple,bootstrap-firmware", &firmware) ||
	    strcmp(firmware, "26.6.2-25G83-g16s-b000"))
		return -ENODEV;
	gfx = devm_kzalloc(dev, sizeof(*gfx), GFP_KERNEL);
	if (!gfx)
		return -ENOMEM;
	gfx->dev = dev;
	atomic_set(&gfx->state, J614S_GFX_NOT_READY);
	res = platform_get_resource_byname(pdev, IORESOURCE_MEM, "asc");
	if (!res || res->start != 0x28a600000ULL || resource_size(res) != 0x4000)
		return -EINVAL;
	gfx->asc = devm_ioremap_resource(dev, res);
	if (IS_ERR(gfx->asc))
		return PTR_ERR(gfx->asc);
	res = platform_get_resource_byname(pdev, IORESOURCE_MEM, "sgx");
	if (!res || res->start != 0x288000000ULL || resource_size(res) != 0x3758000)
		return -EINVAL;
	/* The ADT SGX aperture contains the ASC mailbox further up. Reserve only
	 * the first 16 MiB used by these ID/mask/PMGR reads, as the existing
	 * AGX register layer does; never claim another driver's mailbox window.
	 */
	core_regs = *res;
	core_regs.end = core_regs.start + SZ_16M - 1;
	gfx->sgx = devm_ioremap_resource(dev, &core_regs);
	if (IS_ERR(gfx->sgx))
		return PTR_ERR(gfx->sgx);
	gfx->data_res = platform_get_resource_byname(pdev, IORESOURCE_MEM, "firmware-data");
	if (!gfx->data_res || resource_size(gfx->data_res) != FW_DATA_SIZE ||
	    (gfx->data_res->start & (SZ_16K - 1)))
		return -EINVAL;
	gfx->data = devm_ioremap_resource(dev, gfx->data_res);
	if (IS_ERR(gfx->data))
		return PTR_ERR(gfx->data);
	/* The RAM test bootloader owns power for now. Do not reuse an A18 PMGR
	 * profile, alter clocks, or start firmware if either real domain is off.
	 */
	if ((readl(gfx->sgx + 0xe80100) & 0xff) != 0xff ||
	    (readl(gfx->sgx + 0xe80110) & 0xff) != 0xff ||
	    readl(gfx->asc + CPU_CONTROL) & CPU_RUN)
		return dev_err_probe(dev, -EBUSY, "requires cold firmware and powered AFR/GFX domains\n");
	id = readl(gfx->sgx + 0xd04000);
	masks = readl(gfx->sgx + 0xe01500);
	if (id != G16_ID || masks != 0xf6fdb ||
	    readl(gfx->sgx + 0xe01504) || readl(gfx->sgx + 0xe01508))
		return dev_err_probe(dev, -ENODEV, "unqualified GPU identity %#x masks %#x\n", id, masks);
	platform_set_drvdata(pdev, gfx);
	gfx->rtk = devm_apple_rtkit_init(dev, gfx, NULL, 0, &j614s_gfx_ops);
	if (IS_ERR(gfx->rtk))
		return dev_err_probe(dev, PTR_ERR(gfx->rtk), "RTKit transport setup failed\n");
	writel(readl(gfx->asc + CPU_CONTROL) | CPU_RUN, gfx->asc + CPU_CONTROL);
	ret = apple_rtkit_wake(gfx->rtk);
	if (ret || apple_rtkit_protocol_version(gfx->rtk) != 12) {
		j614s_gfx_stop(gfx);
		return dev_err_probe(dev, ret ?: -EPROTONOSUPPORT, "G16 bootstrap failed\n");
	}
	/* The crash callback may run as wake completes. Publish readiness only
	 * if it has not already latched a crash; later crashes remain terminal.
	 */
	if (!apple_rtkit_is_running(gfx->rtk) ||
	    atomic_cmpxchg(&gfx->state, J614S_GFX_NOT_READY,
			   J614S_GFX_READY) != J614S_GFX_NOT_READY) {
		j614s_gfx_stop(gfx);
		return dev_err_probe(dev, -EIO, "G16 firmware stopped during bootstrap\n");
	}
	dev_info(dev, "G16S B1 RTKit ready, protocol 12; 16 cores; application INIT not sent\n");
	return 0;
}

static void j614s_gfx_remove(struct platform_device *pdev)
{
	struct j614s_gfx *gfx = platform_get_drvdata(pdev);
	int ret;

	if (apple_rtkit_is_running(gfx->rtk)) {
		ret = apple_rtkit_quiesce(gfx->rtk);
		if (ret)
			dev_err(gfx->dev, "G16 RTKit quiesce failed: %d\n", ret);
		else
			dev_info(gfx->dev, "G16 RTKit quiesced\n");
	}
	j614s_gfx_stop(gfx);
}

static const struct of_device_id j614s_gfx_match[] = {
	{ .compatible = "apple,j614s-gfx-bootstrap" }, {}
};
MODULE_DEVICE_TABLE(of, j614s_gfx_match);
static struct platform_driver j614s_gfx_driver = {
	.probe = j614s_gfx_probe,
	.remove = j614s_gfx_remove,
	.shutdown = j614s_gfx_remove,
	.driver = {
		.name = "j614s-gfx-bootstrap",
		.of_match_table = j614s_gfx_match,
		.dev_groups = j614s_gfx_groups,
	},
};
module_platform_driver(j614s_gfx_driver);
MODULE_DESCRIPTION("J614s G16S RTKit bootstrap qualification (no rendering)");
MODULE_LICENSE("Dual MIT/GPL");
