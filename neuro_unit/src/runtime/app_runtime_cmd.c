#include <errno.h>
#include <string.h>

#include "app_runtime_cmd.h"
#include "neuro_unit_port.h"

#define APP_RT_DEFAULT_APPS_DIR "/apps"
#define APP_RT_DEFAULT_SEED_PATH "/recovery.seed"

static int app_runtime_cmd_normalize_error(const char *op, int ret)
{
	if (ret >= 0) {
		return ret;
	}

	if (app_rt_is_framework_error(ret)) {
		return ret;
	}

	return app_rt_raise_errno("cmd", op, ret);
}

/*
 * Default config keeps board-dependent command surfaces disabled until the
 * active port/provider publishes explicit capability and hook wiring.
 */
static const struct app_runtime_cmd_config g_default_cfg = {
	.support = {
		.storage = {
			.mount = false,
			.unmount = false,
		},
		.network = {
			.connect = false,
			.disconnect = false,
		},
	},
	.runtime_ops = {
		.load = app_runtime_load,
		.start = app_runtime_start,
		.suspend = app_runtime_suspend,
		.resume = app_runtime_resume,
		.stop = app_runtime_stop,
		.unload = app_runtime_unload,
		.get_status = app_runtime_get_status,
	},
	.apps_dir = APP_RT_DEFAULT_APPS_DIR,
	.seed_path = APP_RT_DEFAULT_SEED_PATH,
};

static struct app_runtime_cmd_config g_cfg;

static void app_runtime_cmd_fill_defaults(struct app_runtime_cmd_config *cfg)
{
	/*
	 * Port setup may provide only a partial config. Fill in framework-owned
	 * runtime defaults here, but never auto-enable capability bits.
	 */
	if (cfg->runtime_ops.load == NULL) {
		cfg->runtime_ops.load = g_default_cfg.runtime_ops.load;
	}

	if (cfg->runtime_ops.start == NULL) {
		cfg->runtime_ops.start = g_default_cfg.runtime_ops.start;
	}

	if (cfg->runtime_ops.suspend == NULL) {
		cfg->runtime_ops.suspend = g_default_cfg.runtime_ops.suspend;
	}

	if (cfg->runtime_ops.resume == NULL) {
		cfg->runtime_ops.resume = g_default_cfg.runtime_ops.resume;
	}

	if (cfg->runtime_ops.stop == NULL) {
		cfg->runtime_ops.stop = g_default_cfg.runtime_ops.stop;
	}

	if (cfg->runtime_ops.unload == NULL) {
		cfg->runtime_ops.unload = g_default_cfg.runtime_ops.unload;
	}

	if (cfg->runtime_ops.get_status == NULL) {
		cfg->runtime_ops.get_status =
			g_default_cfg.runtime_ops.get_status;
	}

	if (cfg->apps_dir == NULL || cfg->apps_dir[0] == '\0') {
		cfg->apps_dir = g_default_cfg.apps_dir;
	}

	if (cfg->seed_path == NULL || cfg->seed_path[0] == '\0') {
		cfg->seed_path = g_default_cfg.seed_path;
	}
}

int app_runtime_cmd_set_config(const struct app_runtime_cmd_config *cfg)
{
	if (cfg == NULL) {
		g_cfg = g_default_cfg;
		return 0;
	}

	g_cfg = *cfg;
	app_runtime_cmd_fill_defaults(&g_cfg);
	return 0;
}

const struct app_runtime_cmd_config *app_runtime_cmd_get_config(void)
{
	/* Defensive fallback for early callers before port init finishes. */
	if (g_cfg.apps_dir == NULL || g_cfg.seed_path == NULL) {
		g_cfg = g_default_cfg;
	}

	return &g_cfg;
}

int app_runtime_cmd_get_status(struct app_runtime_status *status)
{
	const struct app_runtime_cmd_config *cfg = app_runtime_cmd_get_config();

	if (status == NULL) {
		return app_rt_raise(
			"cmd", "status", APP_RT_EX_INVALID_ARGUMENT, -EINVAL);
	}

	if (cfg->runtime_ops.get_status == NULL) {
		return app_rt_raise(
			"cmd", "status", APP_RT_EX_NOT_SUPPORTED, -ENOTSUP);
	}

	memset(status, 0, sizeof(*status));
	cfg->runtime_ops.get_status(status);
	return 0;
}

int app_runtime_cmd_exec(
	enum app_runtime_cmd_id cmd, const char *arg1, const char *arg2)
{
	const struct app_runtime_cmd_config *cfg = app_runtime_cmd_get_config();

	/*
	 * Each dispatch branch validates both capability and hook presence
	 * first so callers get deterministic NOT_SUPPORTED instead of
	 * best-effort behavior.
	 */
	switch (cmd) {
	case APP_RT_CMD_STORAGE_MOUNT: {
		const struct neuro_unit_port_fs_ops *fs_ops =
			neuro_unit_port_get_fs_ops();

		if (!cfg->support.storage.mount || fs_ops == NULL ||
			fs_ops->mount == NULL) {
			return app_rt_raise("cmd", "storage_mount",
				APP_RT_EX_NOT_SUPPORTED, -ENOTSUP);
		}
		return app_runtime_cmd_normalize_error(
			"storage_mount", fs_ops->mount());
	}

	case APP_RT_CMD_STORAGE_UNMOUNT: {
		const struct neuro_unit_port_fs_ops *fs_ops =
			neuro_unit_port_get_fs_ops();

		if (!cfg->support.storage.unmount || fs_ops == NULL ||
			fs_ops->unmount == NULL) {
			return app_rt_raise("cmd", "storage_unmount",
				APP_RT_EX_NOT_SUPPORTED, -ENOTSUP);
		}
		return app_runtime_cmd_normalize_error(
			"storage_unmount", fs_ops->unmount());
	}

	case APP_RT_CMD_NETWORK_CONNECT: {
		const struct neuro_unit_port_network_ops *network_ops =
			neuro_unit_port_get_network_ops();
		struct neuro_unit_port_network_connect_params params = {
			.type = NEURO_UNIT_PORT_NETWORK_WIFI,
			.endpoint = arg1,
			.credential = arg2,
		};

		if (!cfg->support.network.connect || network_ops == NULL ||
			network_ops->connect == NULL) {
			return app_rt_raise("cmd", "network_connect",
				APP_RT_EX_NOT_SUPPORTED, -ENOTSUP);
		}
		if (arg1 == NULL || arg2 == NULL) {
			return app_rt_raise("cmd", "network_connect",
				APP_RT_EX_INVALID_ARGUMENT, -EINVAL);
		}
		return app_runtime_cmd_normalize_error(
			"network_connect", network_ops->connect(&params));
	}

	case APP_RT_CMD_NETWORK_DISCONNECT: {
		const struct neuro_unit_port_network_ops *network_ops =
			neuro_unit_port_get_network_ops();

		if (!cfg->support.network.disconnect || network_ops == NULL ||
			network_ops->disconnect == NULL) {
			return app_rt_raise("cmd", "network_disconnect",
				APP_RT_EX_NOT_SUPPORTED, -ENOTSUP);
		}
		return app_runtime_cmd_normalize_error(
			"network_disconnect", network_ops->disconnect());
	}

	case APP_RT_CMD_LOAD:
		if (cfg->runtime_ops.load == NULL) {
			return app_rt_raise("cmd", "load",
				APP_RT_EX_NOT_SUPPORTED, -ENOTSUP);
		}
		if (arg1 == NULL || arg2 == NULL) {
			return app_rt_raise("cmd", "load",
				APP_RT_EX_INVALID_ARGUMENT, -EINVAL);
		}
		return app_runtime_cmd_normalize_error(
			"load", cfg->runtime_ops.load(arg1, arg2));

	case APP_RT_CMD_START:
		if (cfg->runtime_ops.start == NULL) {
			return app_rt_raise("cmd", "start",
				APP_RT_EX_NOT_SUPPORTED, -ENOTSUP);
		}
		if (arg1 == NULL) {
			return app_rt_raise("cmd", "start",
				APP_RT_EX_INVALID_ARGUMENT, -EINVAL);
		}
		return app_runtime_cmd_normalize_error(
			"start", cfg->runtime_ops.start(arg1, arg2));

	case APP_RT_CMD_SUSPEND:
		if (cfg->runtime_ops.suspend == NULL) {
			return app_rt_raise("cmd", "suspend",
				APP_RT_EX_NOT_SUPPORTED, -ENOTSUP);
		}
		if (arg1 == NULL) {
			return app_rt_raise("cmd", "suspend",
				APP_RT_EX_INVALID_ARGUMENT, -EINVAL);
		}
		return app_runtime_cmd_normalize_error(
			"suspend", cfg->runtime_ops.suspend(arg1));

	case APP_RT_CMD_RESUME:
		if (cfg->runtime_ops.resume == NULL) {
			return app_rt_raise("cmd", "resume",
				APP_RT_EX_NOT_SUPPORTED, -ENOTSUP);
		}
		if (arg1 == NULL) {
			return app_rt_raise("cmd", "resume",
				APP_RT_EX_INVALID_ARGUMENT, -EINVAL);
		}
		return app_runtime_cmd_normalize_error(
			"resume", cfg->runtime_ops.resume(arg1));

	case APP_RT_CMD_STOP:
		if (cfg->runtime_ops.stop == NULL) {
			return app_rt_raise("cmd", "stop",
				APP_RT_EX_NOT_SUPPORTED, -ENOTSUP);
		}
		if (arg1 == NULL) {
			return app_rt_raise("cmd", "stop",
				APP_RT_EX_INVALID_ARGUMENT, -EINVAL);
		}
		return app_runtime_cmd_normalize_error(
			"stop", cfg->runtime_ops.stop(arg1));

	case APP_RT_CMD_UNLOAD:
		if (cfg->runtime_ops.unload == NULL) {
			return app_rt_raise("cmd", "unload",
				APP_RT_EX_NOT_SUPPORTED, -ENOTSUP);
		}
		if (arg1 == NULL) {
			return app_rt_raise("cmd", "unload",
				APP_RT_EX_INVALID_ARGUMENT, -EINVAL);
		}
		return app_runtime_cmd_normalize_error(
			"unload", cfg->runtime_ops.unload(arg1));

	default:
		return app_rt_raise(
			"cmd", "dispatch", APP_RT_EX_INVALID_ARGUMENT, -EINVAL);
	}
}
