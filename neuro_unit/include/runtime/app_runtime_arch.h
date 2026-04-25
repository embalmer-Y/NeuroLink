#ifndef APP_RUNTIME_ARCH_H
#define APP_RUNTIME_ARCH_H

#include <stdint.h>

#if defined(CONFIG_XTENSA) && defined(CONFIG_SOC_SERIES_ESP32S3)
#define APP_RT_EXEC_ALIAS_FROM_START 0x3FC00000U
#define APP_RT_EXEC_ALIAS_FROM_END 0x40000000U
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
#else
#define APP_RT_EXEC_ADDR_FIXUP(addr) ((uintptr_t)(addr))
#endif

#endif
