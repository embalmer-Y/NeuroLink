#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>

#include "shell/neuro_unit_shell_internal.h"

int neuro_unit_shell_cmd_network_connect(
	const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	int ret;

	ret = neuro_unit_shell_cmd_guard(sh, "network_connect");
	if (ret) {
		return ret;
	}

	ret = app_runtime_cmd_exec(
		APP_RT_CMD_NETWORK_CONNECT, argv[1], argv[2]);
	if (ret) {
		return neuro_unit_shell_report_cmd_error(
			sh, "network connect", ret);
	}

	shell_print(sh, "network connect request sent");
	return 0;
}

int neuro_unit_shell_cmd_network_disconnect(
	const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	ARG_UNUSED(argv);
	int ret;

	ret = neuro_unit_shell_cmd_guard(sh, "network_disconnect");
	if (ret) {
		return ret;
	}

	ret = app_runtime_cmd_exec(APP_RT_CMD_NETWORK_DISCONNECT, NULL, NULL);
	if (ret) {
		return neuro_unit_shell_report_cmd_error(
			sh, "network disconnect", ret);
	}

	shell_print(sh, "network disconnect request sent");
	return 0;
}
