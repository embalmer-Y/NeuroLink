#ifndef APP_RUNTIME_ELF_STAGING_H
#define APP_RUNTIME_ELF_STAGING_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum app_runtime_elf_buffer_source {
	APP_RUNTIME_ELF_BUFFER_MALLOC = 0,
	APP_RUNTIME_ELF_BUFFER_STATIC,
	APP_RUNTIME_ELF_BUFFER_EXTERNAL,
	APP_RUNTIME_ELF_BUFFER_PSRAM = APP_RUNTIME_ELF_BUFFER_EXTERNAL,
};

const char *app_runtime_elf_buffer_source_str(
	enum app_runtime_elf_buffer_source source);
const char *app_runtime_elf_staging_provider_str(void);
uint8_t *app_runtime_elf_staging_alloc(
	size_t size, enum app_runtime_elf_buffer_source *source);
void app_runtime_elf_staging_release(
	uint8_t *buf, enum app_runtime_elf_buffer_source source);

#ifdef CONFIG_ZTEST
bool app_runtime_elf_staging_static_in_use(void);
#endif

#ifdef __cplusplus
}
#endif

#endif
