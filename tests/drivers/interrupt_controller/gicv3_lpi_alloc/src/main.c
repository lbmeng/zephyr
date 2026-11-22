/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 Process Mission
 * SPDX-License-Identifier: Apache-2.0
 */

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
	}
	k_fatal_halt(reason);
}

int main(void)
{
	printk("Expected LPI allocation failure was not triggered\n");
	return 0;
}
