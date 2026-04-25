#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>

#include "shell/neuro_unit_shell_internal.h"

int neuro_unit_shell_cmd_status(
	const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	ARG_UNUSED(argv);
	int ret;
	struct app_runtime_status status;

	ret = neuro_unit_shell_cmd_guard(sh, "status");
	if (ret) {
		return ret;
	}

	ret = app_runtime_cmd_get_status(&status);
	if (ret) {
		shell_error(sh, "get status failed: %d", ret);
		return ret;
	}

	shell_print(sh, "apps=%u running=%u suspended=%u",
		(unsigned int)status.app_count,
		(unsigned int)status.running_count,
		(unsigned int)status.suspended_count);
	if (app_runtime_policy_limit_is_unbounded(
		    status.capacity.max_loaded_apps) ||
		app_runtime_policy_limit_is_unbounded(
			status.capacity.max_running_apps)) {
		shell_print(sh, "capacity loaded=%s running=%s preempt=%s",
			app_runtime_policy_limit_is_unbounded(
				status.capacity.max_loaded_apps)
				? "unbounded"
				: "bounded",
			app_runtime_policy_limit_is_unbounded(
				status.capacity.max_running_apps)
				? "unbounded"
				: "bounded",
			status.capacity.allow_preemptive_suspend ? "on"
								 : "off");
		if (!app_runtime_policy_limit_is_unbounded(
			    status.capacity.max_loaded_apps)) {
			shell_print(sh, "loaded limit=%u",
				(unsigned int)status.capacity.max_loaded_apps);
		}
		if (!app_runtime_policy_limit_is_unbounded(
			    status.capacity.max_running_apps)) {
			shell_print(sh, "running limit=%u",
				(unsigned int)status.capacity.max_running_apps);
		}
	} else {
		shell_print(sh, "capacity loaded=%u running=%u preempt=%s",
			(unsigned int)status.capacity.max_loaded_apps,
			(unsigned int)status.capacity.max_running_apps,
			status.capacity.allow_preemptive_suspend ? "on"
								 : "off");
	}

	for (size_t i = 0; i < app_runtime_status_listed_count(&status); i++) {
		shell_print(sh,
			"[%u] state=%s prio=%u auto_suspended=%s name=%s path=%s",
			(unsigned int)i,
			neuro_unit_shell_state_to_str(status.apps[i].state),
			status.apps[i].priority,
			status.apps[i].auto_suspended ? "yes" : "no",
			status.apps[i].name, status.apps[i].path);

		if (status.apps[i].manifest_present) {
			shell_print(sh,
				"    manifest abi=%u.%u ver=%u.%u.%u cap=0x%08x budget(cpu=%u%% ram=%u stack=%u) dep=%s",
				status.apps[i].manifest.abi_major,
				status.apps[i].manifest.abi_minor,
				status.apps[i].manifest.version.major,
				status.apps[i].manifest.version.minor,
				status.apps[i].manifest.version.patch,
				(unsigned int)status.apps[i]
					.manifest.capability_flags,
				status.apps[i]
					.manifest.resource.cpu_budget_percent,
				(unsigned int)status.apps[i]
					.manifest.resource.ram_bytes,
				(unsigned int)status.apps[i]
					.manifest.resource.stack_bytes,
				status.apps[i].manifest.dependency[0]
					? status.apps[i].manifest.dependency
					: "-");
		}
	}

	if (status.listed_app_count_truncated) {
		shell_print(sh,
			"status snapshot truncated: showing %u of %u apps",
			(unsigned int)status.listed_app_count,
			(unsigned int)status.app_count);
	}

	neuro_unit_shell_print_exception(sh, &status.last_exception);
	return 0;
}

int neuro_unit_shell_cmd_load(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	int ret;

	ret = neuro_unit_shell_cmd_guard(sh, "load");
	if (ret) {
		return ret;
	}

	ret = app_runtime_cmd_exec(APP_RT_CMD_LOAD, argv[1], argv[2]);
	if (ret) {
		return neuro_unit_shell_report_cmd_error(sh, "load", ret);
	}

	shell_print(sh, "app loaded");
	return 0;
}

int neuro_unit_shell_cmd_start(const struct shell *sh, size_t argc, char **argv)
{
	int ret;
	const char *start_args = NULL;

	ret = neuro_unit_shell_cmd_guard(sh, "start");
	if (ret) {
		return ret;
	}

	if (argc > 2) {
		start_args = argv[2];
	}

	ret = app_runtime_cmd_exec(APP_RT_CMD_START, argv[1], start_args);
	if (ret) {
		return neuro_unit_shell_report_cmd_error(sh, "start", ret);
	}

	shell_print(sh, "app started");
	return 0;
}

int neuro_unit_shell_cmd_suspend(
	const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	int ret;

	ret = neuro_unit_shell_cmd_guard(sh, "suspend");
	if (ret) {
		return ret;
	}

	ret = app_runtime_cmd_exec(APP_RT_CMD_SUSPEND, argv[1], NULL);
	if (ret) {
		return neuro_unit_shell_report_cmd_error(sh, "suspend", ret);
	}

	shell_print(sh, "app suspended");
	return 0;
}

int neuro_unit_shell_cmd_resume(
	const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	int ret;

	ret = neuro_unit_shell_cmd_guard(sh, "resume");
	if (ret) {
		return ret;
	}

	ret = app_runtime_cmd_exec(APP_RT_CMD_RESUME, argv[1], NULL);
	if (ret) {
		return neuro_unit_shell_report_cmd_error(sh, "resume", ret);
	}

	shell_print(sh, "app resumed");
	return 0;
}

int neuro_unit_shell_cmd_stop(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	int ret;

	ret = neuro_unit_shell_cmd_guard(sh, "stop");
	if (ret) {
		return ret;
	}

	ret = app_runtime_cmd_exec(APP_RT_CMD_STOP, argv[1], NULL);
	if (ret) {
		return neuro_unit_shell_report_cmd_error(sh, "stop", ret);
	}

	shell_print(sh, "app stopped");
	return 0;
}

int neuro_unit_shell_cmd_unload(
	const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	int ret;

	ret = neuro_unit_shell_cmd_guard(sh, "unload");
	if (ret) {
		return ret;
	}

	ret = app_runtime_cmd_exec(APP_RT_CMD_UNLOAD, argv[1], NULL);
	if (ret) {
		return neuro_unit_shell_report_cmd_error(sh, "unload", ret);
	}

	shell_print(sh, "app unloaded");
	return 0;
}
