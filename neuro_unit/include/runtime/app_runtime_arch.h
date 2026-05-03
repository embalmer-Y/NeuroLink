#ifndef APP_RUNTIME_ARCH_H
#define APP_RUNTIME_ARCH_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

#if defined(CONFIG_XTENSA) && defined(CONFIG_SOC_SERIES_ESP32S3)
#define APP_RT_EXEC_ALIAS_FROM_START 0x3FC88000U
#define APP_RT_EXEC_ALIAS_FROM_END 0x3FCF0000U
#define APP_RT_EXEC_ALIAS_OFFSET 0x006F0000U
#endif

#if defined(APP_RT_EXEC_ALIAS_FROM_START) &&                                   \
	defined(APP_RT_EXEC_ALIAS_FROM_END) &&                                 \
	defined(APP_RT_EXEC_ALIAS_OFFSET)
#define APP_RT_EXEC_ADDR_FIXUP(addr)                                           \
	((((uintptr_t)(addr) >= (uintptr_t)APP_RT_EXEC_ALIAS_FROM_START) &&    \
		 ((uintptr_t)(addr) < (uintptr_t)APP_RT_EXEC_ALIAS_FROM_END))  \
			? ((uintptr_t)(addr) +                                 \
				  (uintptr_t)APP_RT_EXEC_ALIAS_OFFSET)         \
			: (uintptr_t)(addr))

static inline bool app_runtime_exec_addr_has_alias(const void *addr)
{
	uintptr_t value = (uintptr_t)addr;

	return value >= (uintptr_t)APP_RT_EXEC_ALIAS_FROM_START &&
	       value < (uintptr_t)APP_RT_EXEC_ALIAS_FROM_END;
}

static inline bool app_runtime_exec_range_has_alias(
	const void *addr, size_t len)
{
	uintptr_t start = (uintptr_t)addr;
	uintptr_t end = start + (uintptr_t)len;

	return len > 0U && start >= (uintptr_t)APP_RT_EXEC_ALIAS_FROM_START &&
	       end >= start && end <= (uintptr_t)APP_RT_EXEC_ALIAS_FROM_END;
}
#else
#define APP_RT_EXEC_ADDR_FIXUP(addr) ((uintptr_t)(addr))

static inline bool app_runtime_exec_addr_has_alias(const void *addr)
{
	ARG_UNUSED(addr);
	return false;
}

static inline bool app_runtime_exec_range_has_alias(
	const void *addr, size_t len)
{
	ARG_UNUSED(addr);
	ARG_UNUSED(len);
	return false;
}
#endif

#endif
