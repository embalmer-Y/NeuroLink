#ifndef NEURO_UNIT_PORT_MEMORY_H
#define NEURO_UNIT_PORT_MEMORY_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

struct neuro_unit_port_memory_ops {
	const char *provider;
	void *(*alloc_external)(size_t size, size_t align);
	void (*free_external)(void *ptr);
};

#ifdef __cplusplus
}
#endif

#endif
