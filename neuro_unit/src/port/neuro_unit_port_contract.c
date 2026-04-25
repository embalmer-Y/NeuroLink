#include <errno.h>
#include <stddef.h>

#include "neuro_unit_port.h"

#define NEURO_UNIT_PORT_DEFAULT_APPS_DIR "/apps"
#define NEURO_UNIT_PORT_DEFAULT_SEED_PATH "/recovery.seed"

static const struct neuro_unit_port_fs_ops g_empty_fs_ops;
static const struct neuro_unit_port_network_ops g_empty_network_ops;

static const struct neuro_unit_port_fs_ops *g_fs_ops = &g_empty_fs_ops;
static const struct neuro_unit_port_network_ops *g_network_ops =
	&g_empty_network_ops;
static const char *g_apps_dir = NEURO_UNIT_PORT_DEFAULT_APPS_DIR;
static const char *g_seed_path = NEURO_UNIT_PORT_DEFAULT_SEED_PATH;

int neuro_unit_port_set_fs_ops(const struct neuro_unit_port_fs_ops *ops)
{
	g_fs_ops = (ops != NULL) ? ops : &g_empty_fs_ops;
	return 0;
}

const struct neuro_unit_port_fs_ops *neuro_unit_port_get_fs_ops(void)
{
	return g_fs_ops;
}

int neuro_unit_port_set_network_ops(
	const struct neuro_unit_port_network_ops *ops)
{
	g_network_ops = (ops != NULL) ? ops : &g_empty_network_ops;
	return 0;
}

const struct neuro_unit_port_network_ops *neuro_unit_port_get_network_ops(void)
{
	return g_network_ops;
}

int neuro_unit_port_set_paths(const char *apps_dir, const char *seed_path)
{
	if (apps_dir == NULL || apps_dir[0] == '\0' || seed_path == NULL ||
		seed_path[0] == '\0') {
		return -EINVAL;
	}

	g_apps_dir = apps_dir;
	g_seed_path = seed_path;
	return 0;
}

const char *neuro_unit_port_apps_dir(void) { return g_apps_dir; }

const char *neuro_unit_port_seed_path(void) { return g_seed_path; }
