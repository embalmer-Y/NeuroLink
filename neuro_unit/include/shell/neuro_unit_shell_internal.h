#ifndef NEURO_UNIT_SHELL_INTERNAL_H
#define NEURO_UNIT_SHELL_INTERNAL_H

#include "app_runtime_cmd.h"
#include "shell/neuro_unit_shell.h"

#ifdef __cplusplus
extern "C" {
#endif

void neuro_unit_shell_print_exception(
	const struct shell *sh, const struct app_rt_exception *exc);
int neuro_unit_shell_report_cmd_error(
	const struct shell *sh, const char *action, int ret);
const char *neuro_unit_shell_state_to_str(enum app_runtime_state state);
int neuro_unit_shell_cmd_guard(const struct shell *sh, const char *cmd_name);

int neuro_unit_shell_cmd_status(
	const struct shell *sh, size_t argc, char **argv);
int neuro_unit_shell_cmd_mount_storage(
	const struct shell *sh, size_t argc, char **argv);
int neuro_unit_shell_cmd_unmount_storage(
	const struct shell *sh, size_t argc, char **argv);
int neuro_unit_shell_cmd_ls(const struct shell *sh, size_t argc, char **argv);
int neuro_unit_shell_cmd_network_connect(
	const struct shell *sh, size_t argc, char **argv);
int neuro_unit_shell_cmd_network_disconnect(
	const struct shell *sh, size_t argc, char **argv);
int neuro_unit_shell_cmd_zenoh_connect_show(
	const struct shell *sh, size_t argc, char **argv);
int neuro_unit_shell_cmd_zenoh_connect_set(
	const struct shell *sh, size_t argc, char **argv);
int neuro_unit_shell_cmd_zenoh_connect_clear(
	const struct shell *sh, size_t argc, char **argv);
int neuro_unit_shell_cmd_load(const struct shell *sh, size_t argc, char **argv);
int neuro_unit_shell_cmd_start(
	const struct shell *sh, size_t argc, char **argv);
int neuro_unit_shell_cmd_suspend(
	const struct shell *sh, size_t argc, char **argv);
int neuro_unit_shell_cmd_resume(
	const struct shell *sh, size_t argc, char **argv);
int neuro_unit_shell_cmd_stop(const struct shell *sh, size_t argc, char **argv);
int neuro_unit_shell_cmd_unload(
	const struct shell *sh, size_t argc, char **argv);

#ifdef __cplusplus
}
#endif

#endif
