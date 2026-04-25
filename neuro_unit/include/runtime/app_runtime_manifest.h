#ifndef APP_RUNTIME_MANIFEST_H
#define APP_RUNTIME_MANIFEST_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define APP_RT_MANIFEST_ABI_MAJOR 1U
#define APP_RT_MANIFEST_ABI_MINOR 0U

#define APP_RT_MANIFEST_NAME_MAX_LEN 31
#define APP_RT_MANIFEST_DEPENDENCY_MAX_LEN 63

enum app_runtime_capability_flag {
	APP_RT_CAP_NONE = 0,
	APP_RT_CAP_STORAGE = (1U << 0),
	APP_RT_CAP_NETWORK = (1U << 1),
	APP_RT_CAP_SENSOR = (1U << 2),
	APP_RT_CAP_ACTUATOR = (1U << 3),
	APP_RT_CAP_UI = (1U << 4),
	APP_RT_CAP_CRYPTO = (1U << 5),
};

struct app_runtime_version {
	uint16_t major;
	uint16_t minor;
	uint16_t patch;
};

struct app_runtime_resource_budget {
	uint32_t ram_bytes;
	uint32_t stack_bytes;
	uint8_t cpu_budget_percent;
	uint8_t reserved[3];
};

struct app_runtime_manifest {
	uint16_t abi_major;
	uint16_t abi_minor;
	struct app_runtime_version version;
	uint32_t capability_flags;
	struct app_runtime_resource_budget resource;
	char app_name[APP_RT_MANIFEST_NAME_MAX_LEN + 1];
	char dependency[APP_RT_MANIFEST_DEPENDENCY_MAX_LEN + 1];
};

#ifdef __cplusplus
}
#endif

#endif
