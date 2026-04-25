#include <zephyr/shell/shell.h>

#include <errno.h>
#include <string.h>

#include "shell/neuro_unit_shell_internal.h"

void neuro_unit_shell_print_exception(
	const struct shell *sh, const struct app_rt_exception *exc)
{
	if (exc->code == APP_RT_EX_NONE) {
		return;
	}

	shell_print(sh,
		"last_exception code=%s cause=%d component=%s operation=%s",
		app_rt_exception_code_str(exc->code), exc->cause,
		exc->component[0] ? exc->component : "-",
		exc->operation[0] ? exc->operation : "-");
}

int neuro_unit_shell_report_cmd_error(
	const struct shell *sh, const char *action, int ret)
{
	char err_buf[32];
	struct app_runtime_status status;

	shell_error(sh, "%s failed: %s (%d)", action,
		app_rt_strerror(ret, err_buf, sizeof(err_buf)), ret);

	if (app_runtime_cmd_get_status(&status) == 0) {
		neuro_unit_shell_print_exception(sh, &status.last_exception);
	}

	return ret;
}

const char *neuro_unit_shell_state_to_str(enum app_runtime_state state)
{
	switch (state) {
	case APP_RT_UNLOADED:
		return "UNLOADED";
	case APP_RT_LOADED:
		return "LOADED";
	case APP_RT_INITIALIZED:
		return "INITIALIZED";
	case APP_RT_RUNNING:
		return "RUNNING";
	case APP_RT_SUSPENDED:
		return "SUSPENDED";
	default:
		return "UNKNOWN";
	}
}

static bool app_runtime_cmd_is_supported(
	const struct app_runtime_cmd_config *cfg, const char *name)
{
	if (strcmp(name, "status") == 0) {
		return cfg->runtime_ops.get_status != NULL;
	}

	if (strcmp(name, "mount_storage") == 0) {
		return cfg->support.storage.mount;
	}

	if (strcmp(name, "unmount_storage") == 0) {
		return cfg->support.storage.unmount;
	}

	if (strcmp(name, "ls") == 0) {
		return cfg->support.storage.mount;
	}

	if (strcmp(name, "network_connect") == 0) {
		return cfg->support.network.connect;
	}

	if (strcmp(name, "network_disconnect") == 0) {
		return cfg->support.network.disconnect;
	}

	if (strcmp(name, "load") == 0) {
		return cfg->runtime_ops.load != NULL;
	}

	if (strcmp(name, "start") == 0) {
		return cfg->runtime_ops.start != NULL;
	}

	if (strcmp(name, "suspend") == 0) {
		return cfg->runtime_ops.suspend != NULL;
	}

	if (strcmp(name, "resume") == 0) {
		return cfg->runtime_ops.resume != NULL;
	}

	if (strcmp(name, "stop") == 0) {
		return cfg->runtime_ops.stop != NULL;
	}

	if (strcmp(name, "unload") == 0) {
		return cfg->runtime_ops.unload != NULL;
	}

	return false;
}

int neuro_unit_shell_cmd_guard(const struct shell *sh, const char *cmd_name)
{
	const struct app_runtime_cmd_config *cfg = app_runtime_cmd_get_config();

	if (!app_runtime_cmd_is_supported(cfg, cmd_name)) {
		shell_error(sh, "command '%s' is not supported on this board",
			cmd_name);
		return -ENOTSUP;
	}

	return 0;
}

NEURO_UNIT_SHELL_APP_CMD_SET_CREATE(sub_app);

NEURO_UNIT_SHELL_APP_CMD_ADD(
	status, NULL, "Show runtime status", neuro_unit_shell_cmd_status, 0, 0);
NEURO_UNIT_SHELL_APP_CMD_ADD(mount_storage, NULL, "Mount default app storage",
	neuro_unit_shell_cmd_mount_storage, 0, 0);
NEURO_UNIT_SHELL_APP_CMD_ADD(unmount_storage, NULL,
	"Unmount default app storage", neuro_unit_shell_cmd_unmount_storage, 0,
	0);
NEURO_UNIT_SHELL_APP_CMD_ADD(
	ls, NULL, "List files in app dir", neuro_unit_shell_cmd_ls, 0, 0);
NEURO_UNIT_SHELL_APP_CMD_ADD(network_connect, NULL,
	"network_connect <endpoint> <credential>",
	neuro_unit_shell_cmd_network_connect, 3, 0);
NEURO_UNIT_SHELL_APP_CMD_ADD(network_disconnect, NULL,
	"Disconnect active network link",
	neuro_unit_shell_cmd_network_disconnect, 0, 0);
NEURO_UNIT_SHELL_APP_CMD_ADD(zenoh_connect_show, NULL,
	"Show current zenoh connect endpoint",
	neuro_unit_shell_cmd_zenoh_connect_show, 0, 0);
NEURO_UNIT_SHELL_APP_CMD_ADD(zenoh_connect_set, NULL,
	"zenoh_connect_set <locator>", neuro_unit_shell_cmd_zenoh_connect_set,
	2, 0);
NEURO_UNIT_SHELL_APP_CMD_ADD(zenoh_connect_clear, NULL,
	"Clear zenoh runtime override and use default",
	neuro_unit_shell_cmd_zenoh_connect_clear, 0, 0);
NEURO_UNIT_SHELL_APP_CMD_ADD(load, NULL, "load <app_name> <llext_path>",
	neuro_unit_shell_cmd_load, 3, 0);
NEURO_UNIT_SHELL_APP_CMD_ADD(start, NULL, "start <app_name> [start_args]",
	neuro_unit_shell_cmd_start, 2, 1);
NEURO_UNIT_SHELL_APP_CMD_ADD(suspend, NULL, "suspend <app_name>",
	neuro_unit_shell_cmd_suspend, 2, 0);
NEURO_UNIT_SHELL_APP_CMD_ADD(
	resume, NULL, "resume <app_name>", neuro_unit_shell_cmd_resume, 2, 0);
NEURO_UNIT_SHELL_APP_CMD_ADD(
	stop, NULL, "stop <app_name>", neuro_unit_shell_cmd_stop, 2, 0);
NEURO_UNIT_SHELL_APP_CMD_ADD(
	unload, NULL, "unload <app_name>", neuro_unit_shell_cmd_unload, 2, 0);

SHELL_CMD_REGISTER(app, &sub_app, "App runtime framework commands", NULL);
