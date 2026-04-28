#include <zephyr/logging/log.h>

#include <stdlib.h>

#include "app_runtime_elf_staging.h"
#include "neuro_unit_port.h"

LOG_MODULE_REGISTER(app_runtime_elf_staging, LOG_LEVEL_INF);

#if defined(CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE) &&                    \
	CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE > 0
static bool g_static_elf_buf_in_use;
static union {
	uint32_t align;
	uint8_t bytes[CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE];
} g_static_elf_buf;
#endif

const char *app_runtime_elf_buffer_source_str(
	enum app_runtime_elf_buffer_source source)
{
	switch (source) {
	case APP_RUNTIME_ELF_BUFFER_EXTERNAL:
		return "external";
	case APP_RUNTIME_ELF_BUFFER_STATIC:
		return "static";
	case APP_RUNTIME_ELF_BUFFER_MALLOC:
	default:
		return "malloc";
	}
}

const char *app_runtime_elf_staging_provider_str(void)
{
	const struct neuro_unit_port_memory_ops *memory_ops =
		neuro_unit_port_get_memory_ops();

	if (memory_ops == NULL || memory_ops->provider == NULL) {
		return "none";
	}

	return memory_ops->provider;
}

uint8_t *app_runtime_elf_staging_alloc(
	size_t size, enum app_runtime_elf_buffer_source *source)
{
	if (source == NULL) {
		return NULL;
	}

	*source = APP_RUNTIME_ELF_BUFFER_MALLOC;
#if defined(CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER) &&                \
	CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER
	const struct neuro_unit_port_memory_ops *memory_ops;
	uint8_t *buf = NULL;

	memory_ops = neuro_unit_port_get_memory_ops();
	if (memory_ops->alloc_external != NULL) {
		buf = memory_ops->alloc_external(size, 32);
	}
	if (buf != NULL) {
		*source = APP_RUNTIME_ELF_BUFFER_EXTERNAL;
		return buf;
	}
	LOG_WRN("LLEXT ELF external staging alloc failed: provider=%s bytes=%zu",
		memory_ops->provider != NULL ? memory_ops->provider : "none",
		size);
#endif
#if defined(CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE) &&                    \
	CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE > 0
	if (!g_static_elf_buf_in_use &&
		size <= sizeof(g_static_elf_buf.bytes)) {
		g_static_elf_buf_in_use = true;
		*source = APP_RUNTIME_ELF_BUFFER_STATIC;
		return g_static_elf_buf.bytes;
	}
#endif

	return malloc(size);
}

void app_runtime_elf_staging_release(
	uint8_t *buf, enum app_runtime_elf_buffer_source source)
{
	if (buf == NULL) {
		return;
	}

	if (source == APP_RUNTIME_ELF_BUFFER_EXTERNAL) {
#if defined(CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER) &&                \
	CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER
		const struct neuro_unit_port_memory_ops *memory_ops =
			neuro_unit_port_get_memory_ops();

		if (memory_ops->free_external != NULL) {
			memory_ops->free_external(buf);
		}
#endif
		return;
	}

	if (source == APP_RUNTIME_ELF_BUFFER_STATIC) {
#if defined(CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE) &&                    \
	CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE > 0
		if (buf == g_static_elf_buf.bytes) {
			g_static_elf_buf_in_use = false;
		}
#endif
		return;
	}

	free(buf);
}

#ifdef CONFIG_ZTEST
bool app_runtime_elf_staging_static_in_use(void)
{
#if defined(CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE) &&                    \
	CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE > 0
	return g_static_elf_buf_in_use;
#else
	return false;
#endif
}
#endif
