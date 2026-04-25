#ifndef BOARD_RUNTIME_PORT_H
#define BOARD_RUNTIME_PORT_H

#include "neuro_unit_port.h"

#ifdef __cplusplus
extern "C" {
#endif

static inline int board_runtime_port_init(void)
{
	return neuro_unit_port_init();
}

#ifdef __cplusplus
}
#endif

#endif
