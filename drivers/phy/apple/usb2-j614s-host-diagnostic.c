// SPDX-License-Identifier: GPL-2.0-only OR MIT
/*
 * Private J614s USB2 host experiment. This is not a general T6040 PHY driver.
 * Requires a caller-owned watchdog and a reboot after a failed experiment.
 * Only the host-role field used by Apple's upstream ATC USB2 set_mode path is
 * written; inherited power, clocks, tuning and PIPE state are left in place.
 * USB1, which carries the recovery/control channel, is never admitted here.
 */
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/phy/phy.h>
#include <linux/platform_device.h>

#define HOST_ROLE GENMASK(14, 12)
struct j614s_host_phy { struct device *dev; void __iomem *phy; void __iomem *pipe; };

static int j614s_host_check(struct phy *phy)
{
 struct j614s_host_phy *p = phy_get_drvdata(phy);
 u32 ctl = readl(p->phy), stop = readl(p->phy + 4);
 u32 sig = readl(p->phy + 8), tune = readl(p->phy + 0x1c);
 u32 mux = readl(p->pipe + 0xc), aon = readl(p->pipe + 0x1c);
 u32 override = readl(p->pipe + 0x20), base_sig = sig & ~HOST_ROLE;
 if (ctl != 0x102 || stop || (base_sig != 0x01c0000f && base_sig != 0x01d0000f) ||
     ((sig & HOST_ROLE) && (sig & HOST_ROLE) != HOST_ROLE) || tune != 0x008c0813 ||
     mux != 0x22 || aon != 1 || override != 0x9332) {
  dev_err(p->dev, "Host experiment refused: ctl=%#x stop=%#x sig=%#x tune=%#x mux=%#x aon=%#x override=%#x\n", ctl, stop, sig, tune, mux, aon, override);
  return -EIO;
 }
 return 0;
}

static int j614s_host_mode(struct phy *phy, enum phy_mode mode, int submode)
{
 struct j614s_host_phy *p = phy_get_drvdata(phy);
 u32 before, after;
 int ret;
 if (mode != PHY_MODE_USB_HOST || submode)
  return -EOPNOTSUPP;
 ret = j614s_host_check(phy);
 if (ret)
  return ret;
 before = readl(p->phy + 8);
 writel(before | HOST_ROLE, p->phy + 8);
 after = readl(p->phy + 8);
 dev_info(p->dev, "J614s USB2 host-role diagnostic: sig=%#x -> %#x\n", before, after);
 return after == (before | HOST_ROLE) ? 0 : -EIO;
}

static const struct phy_ops j614s_host_ops = {
 .owner = THIS_MODULE,
 .init = j614s_host_check,
 .power_on = j614s_host_check,
 .set_mode = j614s_host_mode,
};

static int j614s_host_probe(struct platform_device *pdev)
{
 struct device *dev = &pdev->dev;
 struct j614s_host_phy *p;
 struct resource *r;
 struct phy *phy;
 struct phy_provider *provider;
 resource_size_t phy_start;
 if (!of_machine_is_compatible("apple,j614s") ||
     !of_property_read_bool(dev->of_node, "apple,j614s-host-experiment"))
  return -EOPNOTSUPP;
 p = devm_kzalloc(dev, sizeof(*p), GFP_KERNEL);
 if (!p)
  return -ENOMEM;
 p->dev = dev;
 r = platform_get_resource_byname(pdev, IORESOURCE_MEM, "usb2phy");
 if (!r || resource_size(r) != 0x4000 ||
     (r->start != 0x382a90000ULL && r->start != 0x392a90000ULL))
  return -EINVAL;
 phy_start = r->start;
 p->phy = devm_ioremap_resource(dev, r);
 if (IS_ERR(p->phy))
  return PTR_ERR(p->phy);
 r = platform_get_resource_byname(pdev, IORESOURCE_MEM, "pipehandler");
 if (!r || resource_size(r) != 0x4000 || r->start != phy_start - 0xc000)
  return -EINVAL;
 p->pipe = devm_ioremap_resource(dev, r);
 if (IS_ERR(p->pipe))
  return PTR_ERR(p->pipe);
 phy = devm_phy_create(dev, NULL, &j614s_host_ops);
 if (IS_ERR(phy))
  return PTR_ERR(phy);
 phy_set_drvdata(phy, p);
 provider = devm_of_phy_provider_register(dev, of_phy_simple_xlate);
 return PTR_ERR_OR_ZERO(provider);
}

static const struct of_device_id j614s_host_match[] = {
 { .compatible = "apple,j614s-usb2-host-diagnostic" }, {}
};
MODULE_DEVICE_TABLE(of, j614s_host_match);
static struct platform_driver j614s_host_driver = {
 .probe = j614s_host_probe,
 .driver = { .name = "j614s-usb2-host-diagnostic", .of_match_table = j614s_host_match },
};
module_platform_driver(j614s_host_driver);
MODULE_DESCRIPTION("Private J614s inherited USB2 host experiment");
MODULE_LICENSE("Dual MIT/GPL");
