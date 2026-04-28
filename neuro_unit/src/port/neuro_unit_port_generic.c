#include <zephyr/logging/log.h>
#include <zephyr/sys/util.h>

#include <errno.h>
#include <string.h>

#include "app_runtime_cmd.h"
#include "neuro_unit_port.h"

static int fs_stat_adapter(const char *path, struct fs_dirent *entry)
{
#if defined(CONFIG_FILE_SYSTEM)
	return fs_stat(path, entry);
#else
	ARG_UNUSED(path);
	ARG_UNUSED(entry);
	return -ENOTSUP;
#endif
}

static int fs_mkdir_adapter(const char *path)
{
#if defined(CONFIG_FILE_SYSTEM)
	return fs_mkdir(path);
#else
	ARG_UNUSED(path);
	return -ENOTSUP;
#endif
}

static int fs_remove_adapter(const char *path)
{
#if defined(CONFIG_FILE_SYSTEM)
	return fs_unlink(path);
#else
	ARG_UNUSED(path);
	return -ENOTSUP;
#endif
}

static int fs_rename_adapter(const char *from, const char *to)
{
#if defined(CONFIG_FILE_SYSTEM)
	return fs_rename(from, to);
#else
	ARG_UNUSED(from);
	ARG_UNUSED(to);
	return -ENOTSUP;
#endif
}

static int fs_open_adapter(
	struct fs_file_t *file, const char *path, fs_mode_t flags)
{
#if defined(CONFIG_FILE_SYSTEM)
	return fs_open(file, path, flags);
#else
	ARG_UNUSED(file);
	ARG_UNUSED(path);
	ARG_UNUSED(flags);
	return -ENOTSUP;
#endif
}

static ssize_t fs_read_adapter(struct fs_file_t *file, void *ptr, size_t size)
{
#if defined(CONFIG_FILE_SYSTEM)
	return fs_read(file, ptr, size);
#else
	ARG_UNUSED(file);
	ARG_UNUSED(ptr);
	ARG_UNUSED(size);
	return -ENOTSUP;
#endif
}

static ssize_t fs_write_adapter(
	struct fs_file_t *file, const void *ptr, size_t size)
{
#if defined(CONFIG_FILE_SYSTEM)
	return fs_write(file, ptr, size);
#else
	ARG_UNUSED(file);
	ARG_UNUSED(ptr);
	ARG_UNUSED(size);
	return -ENOTSUP;
#endif
}

static int fs_close_adapter(struct fs_file_t *file)
{
#if defined(CONFIG_FILE_SYSTEM)
	return fs_close(file);
#else
	ARG_UNUSED(file);
	return -ENOTSUP;
#endif
}

static int fs_opendir_adapter(struct fs_dir_t *dir, const char *path)
{
#if defined(CONFIG_FILE_SYSTEM)
	return fs_opendir(dir, path);
#else
	ARG_UNUSED(dir);
	ARG_UNUSED(path);
	return -ENOTSUP;
#endif
}

static int fs_readdir_adapter(struct fs_dir_t *dir, struct fs_dirent *entry)
{
#if defined(CONFIG_FILE_SYSTEM)
	return fs_readdir(dir, entry);
#else
	ARG_UNUSED(dir);
	ARG_UNUSED(entry);
	return -ENOTSUP;
#endif
}

static int fs_closedir_adapter(struct fs_dir_t *dir)
{
#if defined(CONFIG_FILE_SYSTEM)
	return fs_closedir(dir);
#else
	ARG_UNUSED(dir);
	return -ENOTSUP;
#endif
}

static const struct neuro_unit_port_fs_ops g_port_fs_ops = {
	.mount = NULL,
	.unmount = NULL,
	.stat = fs_stat_adapter,
	.mkdir = fs_mkdir_adapter,
	.remove = fs_remove_adapter,
	.rename = fs_rename_adapter,
	.open = fs_open_adapter,
	.read = fs_read_adapter,
	.write = fs_write_adapter,
	.close = fs_close_adapter,
	.opendir = fs_opendir_adapter,
	.readdir = fs_readdir_adapter,
	.closedir = fs_closedir_adapter,
};

LOG_MODULE_REGISTER(neuro_unit_port_generic, LOG_LEVEL_INF);

static const struct neuro_unit_port_provider *g_provider;

__attribute__((weak)) int neuro_unit_port_generic_board_caps_apply(
	struct app_runtime_cmd_config *cfg)
{
	ARG_UNUSED(cfg);
	return 0;
}

__attribute__((weak)) const struct neuro_unit_port_fs_ops *
neuro_unit_port_generic_board_fs_ops(void)
{
	return NULL;
}

__attribute__((weak)) const struct neuro_unit_port_network_ops *
neuro_unit_port_generic_board_network_ops(void)
{
	return NULL;
}

__attribute__((weak)) const struct neuro_unit_port_memory_ops *
neuro_unit_port_generic_board_memory_ops(void)
{
	return NULL;
}

static int generic_port_init(void)
{
	struct app_runtime_cmd_config cfg = {
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
			.load = NULL,
			.start = NULL,
			.suspend = NULL,
			.resume = NULL,
			.stop = NULL,
			.unload = NULL,
			.get_status = NULL,
		},
		.apps_dir = "/apps",
		.seed_path = "/recovery.seed",
	};
	int ret;

	ret = neuro_unit_port_generic_board_caps_apply(&cfg);
	if (ret != 0) {
		LOG_ERR("board capability injection failed: %d", ret);
		return ret;
	}

	ret = app_runtime_cmd_set_config(&cfg);
	if (ret != 0) {
		LOG_ERR("runtime cmd config init failed: %d", ret);
		return ret;
	}

	ret = neuro_unit_port_set_paths(cfg.apps_dir, cfg.seed_path);
	if (ret != 0) {
		LOG_ERR("port path contract init failed: %d", ret);
		return ret;
	}

	if (cfg.support.storage.mount || cfg.support.storage.unmount) {
		const struct neuro_unit_port_fs_ops *board_fs_ops =
			neuro_unit_port_generic_board_fs_ops();

		(void)neuro_unit_port_set_fs_ops(
			board_fs_ops != NULL ? board_fs_ops : &g_port_fs_ops);
	} else {
		(void)neuro_unit_port_set_fs_ops(NULL);
	}

	if (cfg.support.network.connect || cfg.support.network.disconnect) {
		(void)neuro_unit_port_set_network_ops(
			neuro_unit_port_generic_board_network_ops());
	} else {
		(void)neuro_unit_port_set_network_ops(NULL);
	}

	(void)neuro_unit_port_set_memory_ops(
		neuro_unit_port_generic_board_memory_ops());

	LOG_INF("generic provider enabled for board: %s", CONFIG_BOARD);
	return 0;
}

static const struct neuro_unit_port_provider g_generic_provider = {
	.name = "generic",
	.init = generic_port_init,
};

const struct neuro_unit_port_provider *neuro_unit_port_provider_generic(void)
{
	return &g_generic_provider;
}

int neuro_unit_port_init(void)
{
	if (g_provider == NULL) {
		g_provider = neuro_unit_port_provider_generic();
	}

	if (g_provider == NULL || g_provider->init == NULL) {
		LOG_ERR("no valid unit port provider");
		return -ENODEV;
	}

	LOG_INF("unit port provider: %s",
		g_provider->name ? g_provider->name : "unknown");
	return g_provider->init();
}

const char *neuro_unit_port_name(void)
{
	if (g_provider == NULL) {
		g_provider = neuro_unit_port_provider_generic();
	}

	if (g_provider == NULL || g_provider->name == NULL) {
		return "unknown";
	}

	return g_provider->name;
}
