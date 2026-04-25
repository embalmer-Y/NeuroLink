#include <zephyr/sys/util.h>

#include <errno.h>

#include "app_runtime_cmd.h"
#include "neuro_unit_port.h"

#if defined(CONFIG_BOARD_DNESP32S3B)

#include <zephyr/fs/fs.h>
#include <zephyr/logging/log.h>
#include <zephyr/net/net_if.h>
#include <zephyr/net/net_ip.h>
#include <zephyr/net/net_mgmt.h>
#include <zephyr/net/wifi_mgmt.h>
#include <zephyr/storage/disk_access.h>

#include <ff.h>

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

LOG_MODULE_REGISTER(neuro_unit_port_generic_dnesp32s3b, LOG_LEVEL_INF);

#define APP_SD_MOUNT_POINT "/SD:"
#define APP_SD_DISK_NAME "SD"
#define APP_APPS_DIR APP_SD_MOUNT_POINT "/apps"
#define APP_SEED_PATH APP_SD_MOUNT_POINT "/recovery.seed"

struct board_runtime_ctx {
	bool wifi_connected;
	bool sd_mounted;
};

static struct board_runtime_ctx g_board_ctx;
static struct net_if *g_wifi_iface;
static struct net_mgmt_event_callback g_wifi_cb;
static bool g_wifi_cb_registered;
static FATFS g_fatfs;

static struct fs_mount_t g_sd_mount = {
	.type = FS_FATFS,
	.mnt_point = APP_SD_MOUNT_POINT,
	.fs_data = &g_fatfs,
	.storage_dev = (void *)APP_SD_DISK_NAME,
};

static void wifi_event_handler(struct net_mgmt_event_callback *cb,
	uint64_t mgmt_event, struct net_if *iface)
{
	ARG_UNUSED(cb);
	ARG_UNUSED(iface);

	if (mgmt_event == NET_EVENT_WIFI_CONNECT_RESULT) {
		g_board_ctx.wifi_connected = true;
		LOG_INF("Wi-Fi connected");
	} else if (mgmt_event == NET_EVENT_WIFI_DISCONNECT_RESULT) {
		g_board_ctx.wifi_connected = false;
		LOG_INF("Wi-Fi disconnected");
	}
}

static int ensure_apps_dir(void)
{
	struct fs_dirent ent;
	int ret;

	ret = fs_stat(APP_APPS_DIR, &ent);
	if (ret == 0) {
		return 0;
	}

	if (ret != -ENOENT) {
		LOG_ERR("stat %s failed: %d", APP_APPS_DIR, ret);
		return ret;
	}

	ret = fs_mkdir(APP_APPS_DIR);
	if (ret == 0) {
		return 0;
	}

	LOG_ERR("mkdir %s failed: %d", APP_APPS_DIR, ret);
	return ret;
}

static int board_mount_sd(void)
{
	int ret;

	if (g_board_ctx.sd_mounted) {
		return 0;
	}

	ret = disk_access_init(APP_SD_DISK_NAME);
	if (ret != 0) {
		LOG_ERR("disk_access_init failed: %d", ret);
		return ret;
	}

	ret = fs_mount(&g_sd_mount);
	if (ret != 0) {
		LOG_ERR("fs_mount %s failed: %d", APP_SD_MOUNT_POINT, ret);
		return ret;
	}

	ret = ensure_apps_dir();
	if (ret != 0) {
		(void)fs_unmount(&g_sd_mount);
		return ret;
	}

	g_board_ctx.sd_mounted = true;
	LOG_INF("SD mounted at %s", APP_SD_MOUNT_POINT);
	return 0;
}

static int board_unmount_sd(void)
{
	int ret;

	if (!g_board_ctx.sd_mounted) {
		return 0;
	}

	ret = fs_unmount(&g_sd_mount);
	if (ret != 0) {
		LOG_ERR("fs_unmount %s failed: %d", APP_SD_MOUNT_POINT, ret);
		return ret;
	}

	g_board_ctx.sd_mounted = false;
	LOG_INF("SD unmounted from %s", APP_SD_MOUNT_POINT);
	return 0;
}

static int board_wifi_connect(const char *endpoint, const char *credential)
{
	struct wifi_connect_req_params params = { 0 };

	if (g_wifi_iface == NULL) {
		return -ENODEV;
	}

	params.ssid = (const uint8_t *)endpoint;
	params.ssid_length = strlen(endpoint);
	params.psk = (const uint8_t *)credential;
	params.psk_length = strlen(credential);
	params.security = params.psk_length > 0 ? WIFI_SECURITY_TYPE_PSK
						: WIFI_SECURITY_TYPE_NONE;
	params.channel = WIFI_CHANNEL_ANY;
	params.band = WIFI_FREQ_BAND_2_4_GHZ;

	LOG_INF("Connecting Wi-Fi SSID: %s", endpoint);
	return net_mgmt(NET_REQUEST_WIFI_CONNECT, g_wifi_iface, &params,
		sizeof(params));
}

static int board_wifi_disconnect(void)
{
	if (g_wifi_iface == NULL) {
		return -ENODEV;
	}

	LOG_INF("Disconnecting Wi-Fi link");
	return net_mgmt(NET_REQUEST_WIFI_DISCONNECT, g_wifi_iface, NULL, 0);
}

static int board_fs_stat(const char *path, struct fs_dirent *entry)
{
	return fs_stat(path, entry);
}

static int board_fs_mkdir(const char *path) { return fs_mkdir(path); }

static int board_fs_remove(const char *path) { return fs_unlink(path); }

static int board_fs_rename(const char *from, const char *to)
{
	return fs_rename(from, to);
}

static int board_fs_open(
	struct fs_file_t *file, const char *path, fs_mode_t flags)
{
	return fs_open(file, path, flags);
}

static ssize_t board_fs_read(struct fs_file_t *file, void *ptr, size_t size)
{
	return fs_read(file, ptr, size);
}

static ssize_t board_fs_write(
	struct fs_file_t *file, const void *ptr, size_t size)
{
	return fs_write(file, ptr, size);
}

static int board_fs_close(struct fs_file_t *file) { return fs_close(file); }

static int board_fs_opendir(struct fs_dir_t *dir, const char *path)
{
	return fs_opendir(dir, path);
}

static int board_fs_readdir(struct fs_dir_t *dir, struct fs_dirent *entry)
{
	return fs_readdir(dir, entry);
}

static int board_fs_closedir(struct fs_dir_t *dir) { return fs_closedir(dir); }

static int board_network_connect(
	const struct neuro_unit_port_network_connect_params *params)
{
	if (params == NULL || params->endpoint == NULL ||
		params->credential == NULL) {
		return -EINVAL;
	}

	return board_wifi_connect(params->endpoint, params->credential);
}

static int board_network_get_status(
	struct neuro_unit_port_network_status *status)
{
	struct net_in_addr *addr;

	if (status == NULL) {
		return -EINVAL;
	}

	memset(status, 0, sizeof(*status));
	snprintk(status->ipv4_addr, sizeof(status->ipv4_addr), "no-ipv4");

	if (g_wifi_iface == NULL) {
		return 0;
	}

	status->ifindex = net_if_get_by_iface(g_wifi_iface);
	snprintk(status->iface_name, sizeof(status->iface_name), "wifi%d",
		status->ifindex);
	status->iface_up = net_if_is_up(g_wifi_iface);
	status->link_ready = g_board_ctx.wifi_connected;

	addr = net_if_ipv4_get_global_addr(g_wifi_iface, NET_ADDR_PREFERRED);
	if (addr != NULL) {
		if (net_addr_ntop(NET_AF_INET, addr, status->ipv4_addr,
			    sizeof(status->ipv4_addr)) == NULL) {
			snprintk(status->ipv4_addr, sizeof(status->ipv4_addr),
				"<format-failed>");
		}
	}

	return 0;
}

static const struct neuro_unit_port_fs_ops g_board_fs_ops = {
	.mount = board_mount_sd,
	.unmount = board_unmount_sd,
	.stat = board_fs_stat,
	.mkdir = board_fs_mkdir,
	.remove = board_fs_remove,
	.rename = board_fs_rename,
	.open = board_fs_open,
	.read = board_fs_read,
	.write = board_fs_write,
	.close = board_fs_close,
	.opendir = board_fs_opendir,
	.readdir = board_fs_readdir,
	.closedir = board_fs_closedir,
};

static const struct neuro_unit_port_network_ops g_board_network_ops = {
	.connect = board_network_connect,
	.disconnect = board_wifi_disconnect,
	.get_status = board_network_get_status,
};

const struct neuro_unit_port_fs_ops *neuro_unit_port_generic_board_fs_ops(void)
{
	return &g_board_fs_ops;
}

const struct neuro_unit_port_network_ops *
neuro_unit_port_generic_board_network_ops(void)
{
	return &g_board_network_ops;
}

int neuro_unit_port_generic_board_caps_apply(struct app_runtime_cmd_config *cfg)
{
	if (cfg == NULL) {
		return -EINVAL;
	}

	memset(&g_board_ctx, 0, sizeof(g_board_ctx));

	g_wifi_iface = net_if_get_default();
	if (g_wifi_iface == NULL) {
		LOG_WRN("No default network interface, Wi-Fi connect may fail");
	}

	if (!g_wifi_cb_registered) {
		net_mgmt_init_event_callback(&g_wifi_cb, wifi_event_handler,
			NET_EVENT_WIFI_CONNECT_RESULT |
				NET_EVENT_WIFI_DISCONNECT_RESULT);
		net_mgmt_add_event_callback(&g_wifi_cb);
		g_wifi_cb_registered = true;
	}

	cfg->support.storage.mount = true;
	cfg->support.storage.unmount = true;
	cfg->support.network.connect = true;
	cfg->support.network.disconnect = true;

	cfg->apps_dir = APP_APPS_DIR;
	cfg->seed_path = APP_SEED_PATH;

	LOG_INF("board capability injection applied for %s", CONFIG_BOARD);
	return 0;
}

#else

int neuro_unit_port_generic_board_caps_apply(struct app_runtime_cmd_config *cfg)
{
	ARG_UNUSED(cfg);
	return 0;
}

#endif
