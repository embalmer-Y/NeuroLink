#include <zephyr/fs/fs.h>
#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>

#include <errno.h>

#include "neuro_unit_port.h"
#include "shell/neuro_unit_shell_internal.h"

int neuro_unit_shell_cmd_mount_storage(
	const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	ARG_UNUSED(argv);
	int ret;

	ret = neuro_unit_shell_cmd_guard(sh, "mount_storage");
	if (ret) {
		return ret;
	}

	ret = app_runtime_cmd_exec(APP_RT_CMD_STORAGE_MOUNT, NULL, NULL);
	if (ret) {
		return neuro_unit_shell_report_cmd_error(
			sh, "mount storage", ret);
	}

	shell_print(sh, "storage mounted");
	return 0;
}

int neuro_unit_shell_cmd_unmount_storage(
	const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	ARG_UNUSED(argv);
	int ret;

	ret = neuro_unit_shell_cmd_guard(sh, "unmount_storage");
	if (ret) {
		return ret;
	}

	ret = app_runtime_cmd_exec(APP_RT_CMD_STORAGE_UNMOUNT, NULL, NULL);
	if (ret) {
		return neuro_unit_shell_report_cmd_error(
			sh, "unmount storage", ret);
	}

	shell_print(sh, "storage unmounted");
	return 0;
}

int neuro_unit_shell_cmd_ls(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	ARG_UNUSED(argv);
	int ret;
	struct fs_dir_t dir;
	struct fs_dirent ent;
	const struct app_runtime_cmd_config *cfg = app_runtime_cmd_get_config();
	const struct neuro_unit_port_fs_ops *fs_ops =
		neuro_unit_port_get_fs_ops();

	ret = neuro_unit_shell_cmd_guard(sh, "ls");
	if (ret) {
		return ret;
	}

	if (fs_ops == NULL || fs_ops->opendir == NULL ||
		fs_ops->readdir == NULL || fs_ops->closedir == NULL) {
		shell_error(sh, "list storage unsupported");
		return -ENOTSUP;
	}

	ret = app_runtime_cmd_exec(APP_RT_CMD_STORAGE_MOUNT, NULL, NULL);
	if (ret) {
		return neuro_unit_shell_report_cmd_error(
			sh, "mount storage", ret);
	}

	fs_dir_t_init(&dir);
	ret = fs_ops->opendir(&dir, cfg->apps_dir);
	if (ret) {
		shell_error(sh, "open dir failed: %s (%d)", cfg->apps_dir, ret);
		return ret;
	}

	shell_print(sh, "listing %s", cfg->apps_dir);
	while (true) {
		ret = fs_ops->readdir(&dir, &ent);
		if (ret) {
			shell_error(sh, "readdir failed: %d", ret);
			break;
		}

		if (ent.name[0] == '\0') {
			ret = 0;
			break;
		}

		shell_print(sh, "%c %s (%zu bytes)",
			ent.type == FS_DIR_ENTRY_DIR ? 'd' : 'f', ent.name,
			ent.size);
	}

	(void)fs_ops->closedir(&dir);
	return ret;
}
