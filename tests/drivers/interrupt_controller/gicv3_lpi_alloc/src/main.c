/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 Process Mission
 * SPDX-License-Identifier: Apache-2.0
 */

#include <zephyr/device.h>
#include <zephyr/drivers/interrupt_controller/gicv3_its.h>
#include <zephyr/fatal.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

static bool failure_injected;

void *__real_k_aligned_alloc(size_t align, size_t size);

void *__wrap_k_aligned_alloc(size_t align, size_t size)
{
	uint32_t cpu = arch_curr_cpu()->id;
	bool property = CONFIG_TEST_LPI_ALLOCATION_FAILURE == 1 && align == KB(4) && size == KB(64);
	bool pending = CONFIG_TEST_LPI_ALLOCATION_FAILURE == 2 && align == KB(64) && size == KB(64);

	if ((property || pending) && cpu == CONFIG_TEST_LPI_ALLOCATION_FAILURE_CPU) {
		failure_injected = true;
		return NULL;
	}
	return __real_k_aligned_alloc(align, size);
}

void k_sys_fatal_error_handler(unsigned int reason, const struct arch_esf *esf)
{
	ARG_UNUSED(esf);

	if (failure_injected && reason == K_ERR_KERNEL_PANIC) {
		printk("GIC_LPI_ALLOC_TEST_PASS\n");
	} else {
		printk("Unexpected fatal error: %u\n", reason);
		printk("PROJECT EXECUTION FAILED\n");
	}
	k_fatal_halt(reason);
}

static void lpi_handler(const void *arg)
{
	k_sem_give((struct k_sem *)arg);
}

int main(void)
{
	static K_SEM_DEFINE(delivered, 0, 1);
	const struct device *its = DEVICE_DT_GET(DT_COMPAT_GET_ANY_STATUS_OKAY(arm_gic_v3_its));
	int intid;
	int ret;

	if (CONFIG_TEST_LPI_ALLOCATION_FAILURE != 0) {
		printk("Expected LPI allocation failure was not triggered\n");
		goto failed;
	}
	if (!device_is_ready(its)) {
		printk("ITS device is not ready\n");
		goto failed;
	}
	ret = its_setup_deviceid(its, 0U, 1U);
	if (ret != 0) {
		printk("ITS device table allocation failed: %d\n", ret);
		goto failed;
	}
	intid = its_alloc_intid(its);
	if (intid < 8192 || intid >= CONFIG_NUM_IRQS) {
		goto failed;
	}
	ret = irq_connect_dynamic(intid, 0U, lpi_handler, &delivered, 0U);
	if (ret != intid) {
		goto failed;
	}
	irq_enable(intid);
	ret = its_map_intid(its, 0U, 0U, intid);
	if (ret != 0) {
		goto failed;
	}
	ret = its_send_int(its, 0U, 0U);
	if (ret != 0 || k_sem_take(&delivered, K_SECONDS(1)) != 0) {
		goto failed;
	}
	printk("GIC_LPI_ALLOC_TEST_PASS\n");
	return 0;
failed:
	printk("PROJECT EXECUTION FAILED\n");
	return -EIO;
}
