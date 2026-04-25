#ifndef NEURO_UNIT_PORT_H
#define NEURO_UNIT_PORT_H

#include "neuro_unit_port_fs.h"
#include "neuro_unit_port_network.h"

#ifdef __cplusplus
extern "C" {
#endif

struct neuro_unit_port_provider {
	const char *name;
	int (*init)(void);
};

int neuro_unit_port_init(void);
const char *neuro_unit_port_name(void);

int neuro_unit_port_set_fs_ops(const struct neuro_unit_port_fs_ops *ops);
const struct neuro_unit_port_fs_ops *neuro_unit_port_get_fs_ops(void);

int neuro_unit_port_set_network_ops(
	const struct neuro_unit_port_network_ops *ops);
const struct neuro_unit_port_network_ops *neuro_unit_port_get_network_ops(void);

int neuro_unit_port_set_paths(const char *apps_dir, const char *seed_path);
const char *neuro_unit_port_apps_dir(void);
const char *neuro_unit_port_seed_path(void);

const struct neuro_unit_port_provider *neuro_unit_port_provider_generic(void);

#ifdef __cplusplus
}
#endif

#endif
