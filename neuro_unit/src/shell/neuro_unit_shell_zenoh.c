#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>

#include "neuro_unit.h"
#include "shell/neuro_unit_shell_internal.h"

int neuro_unit_shell_cmd_zenoh_connect_show(
	const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	ARG_UNUSED(argv);

	shell_print(sh, "zenoh connect endpoint: %s",
		neuro_unit_get_zenoh_connect());
	return 0;
}

int neuro_unit_shell_cmd_zenoh_connect_set(
	const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	int ret;

	ret = neuro_unit_set_zenoh_connect_override(argv[1]);
	if (ret) {
		shell_error(sh, "zenoh connect override failed: %d", ret);
		return ret;
	}

	shell_print(sh, "zenoh connect override applied: %s",
		neuro_unit_get_zenoh_connect());
	return 0;
}

int neuro_unit_shell_cmd_zenoh_connect_clear(
	const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	ARG_UNUSED(argv);
	int ret;

	ret = neuro_unit_clear_zenoh_connect_override();
	if (ret) {
		shell_error(sh, "zenoh connect override clear failed: %d", ret);
		return ret;
	}

	shell_print(sh, "zenoh connect override cleared: %s",
		neuro_unit_get_zenoh_connect());
	return 0;
}
