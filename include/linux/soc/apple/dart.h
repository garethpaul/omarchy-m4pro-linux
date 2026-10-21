/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef _LINUX_SOC_APPLE_DART_H
#define _LINUX_SOC_APPLE_DART_H

#include <linux/kconfig.h>
#include <linux/types.h>

struct iommu_domain;

#if IS_REACHABLE(CONFIG_APPLE_DART)
bool apple_dart_has_atomic_iova_query(struct iommu_domain *domain);
#else
static inline bool apple_dart_has_atomic_iova_query(struct iommu_domain *domain)
{
	(void)domain;
	return false;
}
#endif

#endif
