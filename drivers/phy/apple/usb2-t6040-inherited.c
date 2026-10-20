// SPDX-License-Identifier: GPL-2.0-only OR MIT
/*
 * J614s/J616s RAM-only inherited USB2 PHY admission.
 *
 * The bootloader owns PHY power, clock, calibration and PIPE setup for the
 * entire experiment. This driver only verifies the device-mode state left by
 * m1n1 usb_phy_bringup() at fd360ef69054e42724b975d7a4c61e0242b6b341,
 * with the exact post-init SIG readback captured on source-checked recovery
 * ea52da04a1fa0e7f648812de23ac5cd8f5000ab3 on 2026-10-09 at 14:52 UTC.
 * The difference from the initialization write has no inferred bit meaning.
 * J614s USB1 was checked against the same SIG readback on 2026-10-19,
 * through the exact board-4 m1n1 8e0cf28 proxy. Other J614s ports are not
 * admitted by this experimental profile.
 * It performs no PHY/PIPE writes and cannot provide host, hotplug, suspend or
 * SuperSpeed support. Controller/DART retirement and watchdog recovery belong
 * to the caller; the inherited-handoff property does not perform a handoff.
 */
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/phy/phy.h>
#include <linux/platform_device.h>

#define USB2PHY_USBCTL		0x00
#define USB2PHY_USBCTL_MODE	GENMASK(2, 0)
#define USB2PHY_USBCTL_RUN	2
#define USB2PHY_CTL		0x04
#define USB2PHY_CTL_STOPPED	(BIT(0) | BIT(1) | BIT(3))
#define USB2PHY_SIG		0x08
#define USB2PHY_SIG_INHERITED	0x01c0000f
#define USB2PHY_MISCTUNE		0x1c
#define USB2PHY_MISCTUNE_INHERITED	0x008c0813
#define PIPE_MUX_CTRL		0x0c
#define PIPE_MUX_CTRL_MASK	GENMASK(5, 0)
#define PIPE_MUX_CTRL_DUMMY	0x22
#define PIPE_AON_GEN		0x1c
#define PIPE_AON_GEN_MASK	(BIT(4) | BIT(0))
#define PIPE_AON_GEN_RESET_N	BIT(0)
#define PIPE_NONSELECTED_OVERRIDE	0x20
#define PIPE_NONSELECTED_INHERITED	0x9332

struct apple_t6040_usb2 {
	struct device *dev;
	void __iomem *usb2;
	void __iomem *pipe;
};

static int apple_t6040_usb2_check(struct phy *phy)
{
	struct apple_t6040_usb2 *usb2 = phy_get_drvdata(phy);

	u32 ctl = readl(usb2->usb2 + USB2PHY_USBCTL);
	u32 stop = readl(usb2->usb2 + USB2PHY_CTL);
	u32 sig = readl(usb2->usb2 + USB2PHY_SIG);
	u32 tune = readl(usb2->usb2 + USB2PHY_MISCTUNE);
	u32 mux = readl(usb2->pipe + PIPE_MUX_CTRL);
	u32 aon = readl(usb2->pipe + PIPE_AON_GEN);
	u32 override = readl(usb2->pipe + PIPE_NONSELECTED_OVERRIDE);

	if ((ctl & USB2PHY_USBCTL_MODE) != USB2PHY_USBCTL_RUN ||
	    stop & USB2PHY_CTL_STOPPED || sig != USB2PHY_SIG_INHERITED ||
	    tune != USB2PHY_MISCTUNE_INHERITED ||
	    (mux & PIPE_MUX_CTRL_MASK) != PIPE_MUX_CTRL_DUMMY ||
	    (aon & PIPE_AON_GEN_MASK) != PIPE_AON_GEN_RESET_N ||
	    override != PIPE_NONSELECTED_INHERITED) {
		dev_err(usb2->dev, "Inherited USB2 state mismatch: ctl=%#x stop=%#x sig=%#x tune=%#x mux=%#x aon=%#x override=%#x\n",
			ctl, stop, sig, tune, mux, aon, override);
		return -EIO;
	}

	return 0;
}

static int apple_t6040_usb2_set_mode(struct phy *phy, enum phy_mode mode, int submode)
{
	/* No T6040 host-role mask or transition is inferred from T8132. */
	if (mode != PHY_MODE_USB_DEVICE || submode)
		return -EOPNOTSUPP;

	return apple_t6040_usb2_check(phy);
}

static const struct phy_ops apple_t6040_usb2_ops = {
	.owner = THIS_MODULE,
	.init = apple_t6040_usb2_check,
	.power_on = apple_t6040_usb2_check,
	.set_mode = apple_t6040_usb2_set_mode,
};

static int apple_t6040_usb2_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct apple_t6040_usb2 *usb2;
	struct phy_provider *provider;
	struct resource *res;
	struct phy *phy;

	if ((!of_machine_is_compatible("apple,j616s") &&
	     !of_machine_is_compatible("apple,j614s")) ||
	    !of_property_read_bool(dev->of_node, "apple,inherited-handoff"))
		return -EOPNOTSUPP;

	usb2 = devm_kzalloc(dev, sizeof(*usb2), GFP_KERNEL);
	if (!usb2)
		return -ENOMEM;
	usb2->dev = dev;

	res = platform_get_resource_byname(pdev, IORESOURCE_MEM, "usb2phy");
	if (!res || resource_size(res) < USB2PHY_MISCTUNE + sizeof(u32) ||
	    (of_machine_is_compatible("apple,j614s") &&
	     (res->start != 0x38aa90000ULL || resource_size(res) != 0x4000)))
		return -EINVAL;
	usb2->usb2 = devm_ioremap_resource(dev, res);
	if (IS_ERR(usb2->usb2))
		return PTR_ERR(usb2->usb2);
	res = platform_get_resource_byname(pdev, IORESOURCE_MEM, "pipehandler");
	if (!res || resource_size(res) < PIPE_NONSELECTED_OVERRIDE + sizeof(u32) ||
	    (of_machine_is_compatible("apple,j614s") &&
	     (res->start != 0x38aa84000ULL || resource_size(res) != 0x4000)))
		return -EINVAL;
	usb2->pipe = devm_ioremap_resource(dev, res);
	if (IS_ERR(usb2->pipe))
		return PTR_ERR(usb2->pipe);

	phy = devm_phy_create(dev, NULL, &apple_t6040_usb2_ops);
	if (IS_ERR(phy))
		return PTR_ERR(phy);
	phy_set_drvdata(phy, usb2);
	provider = devm_of_phy_provider_register(dev, of_phy_simple_xlate);
	return PTR_ERR_OR_ZERO(provider);
}

static const struct of_device_id apple_t6040_usb2_match[] = {
	{ .compatible = "apple,t6040-usb2-inherited" },
	{}
};
MODULE_DEVICE_TABLE(of, apple_t6040_usb2_match);

static struct platform_driver apple_t6040_usb2_driver = {
	.probe = apple_t6040_usb2_probe,
	.driver = {
		.name = "apple-t6040-usb2-inherited",
		.of_match_table = apple_t6040_usb2_match,
	},
};
module_platform_driver(apple_t6040_usb2_driver);

MODULE_DESCRIPTION("J614s/J616s RAM-only inherited USB2 PHY admission");
MODULE_LICENSE("Dual MIT/GPL");
