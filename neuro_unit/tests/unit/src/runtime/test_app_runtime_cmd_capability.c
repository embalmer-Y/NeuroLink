#include <zephyr/ztest.h>

#include <errno.h>
#include <string.h>

#include "app_runtime.h"
#include "app_runtime_cmd.h"
#include "app_runtime_exception.h"
#include "neuro_unit_port.h"

static int g_network_connect_calls;
static int g_network_disconnect_calls;
static int g_storage_mount_calls;
static int g_storage_unmount_calls;

static int mock_storage_mount(void)
{
	g_storage_mount_calls++;
	return 0;
}

static int mock_storage_unmount(void)
{
	g_storage_unmount_calls++;
	return 0;
}

static int mock_wifi_connect(
	const struct neuro_unit_port_network_connect_params *params)
{
	zassert_not_null(params, "connect params must be provided");
	zassert_equal(params->type, NEURO_UNIT_PORT_NETWORK_WIFI,
		"network command should request Wi-Fi compatibility mode");
	zassert_not_null(params->endpoint, "endpoint must be forwarded");
	zassert_not_null(params->credential, "credential must be forwarded");
	g_network_connect_calls++;
	return 0;
}

static int mock_wifi_disconnect(void)
{
	g_network_disconnect_calls++;
	return 0;
}

/* Runtime stubs for app_runtime_cmd default runtime-op symbols. */
int app_runtime_init(void) { return 0; }

int app_runtime_set_policy(const struct app_runtime_policy *policy)
{
	ARG_UNUSED(policy);
	return 0;
}

void app_runtime_get_policy(struct app_runtime_policy *policy)
{
	ARG_UNUSED(policy);
}

int app_runtime_load(const char *name, const char *path)
{
	ARG_UNUSED(name);
	ARG_UNUSED(path);
	return 0;
}

int app_runtime_start(const char *name, const char *start_args)
{
	ARG_UNUSED(name);
	ARG_UNUSED(start_args);
	return 0;
}

int app_runtime_suspend(const char *name)
{
	ARG_UNUSED(name);
	return 0;
}

int app_runtime_resume(const char *name)
{
	ARG_UNUSED(name);
	return 0;
}

int app_runtime_stop(const char *name)
{
	ARG_UNUSED(name);
	return 0;
}

int app_runtime_unload(const char *name)
{
	ARG_UNUSED(name);
	return 0;
}

bool app_runtime_supports_command_callback(const char *name)
{
	ARG_UNUSED(name);
	return false;
}

void app_runtime_get_status(struct app_runtime_status *status)
{
	if (status != NULL) {
		memset(status, 0, sizeof(*status));
	}
}

static void test_reset(void *fixture)
{
	ARG_UNUSED(fixture);
	g_network_connect_calls = 0;
	g_network_disconnect_calls = 0;
	g_storage_mount_calls = 0;
	g_storage_unmount_calls = 0;
	app_rt_clear_last_exception();
	(void)app_runtime_cmd_set_config(NULL);
	(void)neuro_unit_port_set_fs_ops(NULL);
	(void)neuro_unit_port_set_network_ops(NULL);
}

ZTEST(app_runtime_cmd_capability, test_generic_provider_reports_unsupported_ops)
{
	const struct neuro_unit_port_provider *provider;
	struct app_rt_exception exc = { 0 };
	const struct app_runtime_cmd_config *cfg;
	int ret;

	provider = neuro_unit_port_provider_generic();
	zassert_not_null(provider, "generic provider must exist");
	zassert_not_null(provider->init, "generic provider init must exist");

	ret = provider->init();
	zassert_equal(ret, 0, "generic init should succeed");

	cfg = app_runtime_cmd_get_config();
	zassert_true(!cfg->support.network.connect,
		"generic network_connect should be unsupported");
	zassert_true(!cfg->support.network.disconnect,
		"generic network_disconnect should be unsupported");
	zassert_true(strcmp(cfg->apps_dir, "/apps") == 0,
		"generic apps_dir default mismatch");
	zassert_true(strcmp(cfg->seed_path, "/recovery.seed") == 0,
		"generic seed_path default mismatch");

	ret = app_runtime_cmd_exec(APP_RT_CMD_NETWORK_CONNECT, "ssid", "psk");
	zassert_true(app_rt_is_framework_error(ret),
		"unsupported network op should be framework error");
	app_rt_get_last_exception(&exc);
	zassert_equal(exc.code, APP_RT_EX_NOT_SUPPORTED,
		"network_connect should be not supported");

	ret = app_runtime_cmd_exec(APP_RT_CMD_NETWORK_DISCONNECT, NULL, NULL);
	zassert_true(app_rt_is_framework_error(ret),
		"unsupported network disconnect should be framework error");
	app_rt_get_last_exception(&exc);
	zassert_equal(exc.code, APP_RT_EX_NOT_SUPPORTED,
		"network_disconnect should be not supported");
}

ZTEST(app_runtime_cmd_capability, test_storage_mount_requires_port_hook)
{
	struct app_runtime_cmd_config cfg = { 0 };
	struct app_rt_exception exc = { 0 };
	int ret;

	cfg.support.storage.mount = true;

	ret = app_runtime_cmd_set_config(&cfg);
	zassert_equal(ret, 0, "set config should succeed");

	ret = app_runtime_cmd_exec(APP_RT_CMD_STORAGE_MOUNT, NULL, NULL);
	zassert_true(app_rt_is_framework_error(ret),
		"storage mount without port hook should be framework error");
	app_rt_get_last_exception(&exc);
	zassert_equal(exc.code, APP_RT_EX_NOT_SUPPORTED,
		"storage mount without port hook should be not supported");
	zassert_equal(g_storage_mount_calls, 0,
		"storage mount hook must not run when missing");
}

ZTEST(app_runtime_cmd_capability, test_storage_commands_use_port_fs_ops)
{
	struct app_runtime_cmd_config cfg = { 0 };
	const struct neuro_unit_port_fs_ops fs_ops = {
		.mount = mock_storage_mount,
		.unmount = mock_storage_unmount,
	};
	int ret;

	cfg.support.storage.mount = true;
	cfg.support.storage.unmount = true;

	ret = app_runtime_cmd_set_config(&cfg);
	zassert_equal(ret, 0, "set config should succeed");
	ret = neuro_unit_port_set_fs_ops(&fs_ops);
	zassert_equal(ret, 0, "set port fs ops should succeed");

	ret = app_runtime_cmd_exec(APP_RT_CMD_STORAGE_MOUNT, NULL, NULL);
	zassert_equal(ret, 0, "storage mount should execute via port fs ops");
	zassert_equal(g_storage_mount_calls, 1,
		"storage mount hook should be called once");

	ret = app_runtime_cmd_exec(APP_RT_CMD_STORAGE_UNMOUNT, NULL, NULL);
	zassert_equal(ret, 0, "storage unmount should execute via port fs ops");
	zassert_equal(g_storage_unmount_calls, 1,
		"storage unmount hook should be called once");
}

ZTEST(app_runtime_cmd_capability, test_supported_op_requires_arguments)
{
	struct app_runtime_cmd_config cfg = { 0 };
	const struct neuro_unit_port_network_ops network_ops = {
		.connect = mock_wifi_connect,
	};
	struct app_rt_exception exc = { 0 };
	int ret;

	cfg.support.network.connect = true;

	ret = app_runtime_cmd_set_config(&cfg);
	zassert_equal(ret, 0, "set config should succeed");
	ret = neuro_unit_port_set_network_ops(&network_ops);
	zassert_equal(ret, 0, "set port network ops should succeed");

	ret = app_runtime_cmd_exec(APP_RT_CMD_NETWORK_CONNECT, NULL, "psk");
	zassert_true(app_rt_is_framework_error(ret),
		"missing args should be framework error");
	app_rt_get_last_exception(&exc);
	zassert_equal(exc.code, APP_RT_EX_INVALID_ARGUMENT,
		"network_connect missing args should be invalid argument");
	zassert_equal(g_network_connect_calls, 0,
		"op callback must not run when args invalid");
}

ZTEST(app_runtime_cmd_capability, test_supported_disconnect_requires_hook)
{
	struct app_runtime_cmd_config cfg = { 0 };
	const struct neuro_unit_port_network_ops network_ops = {
		.connect = mock_wifi_connect,
	};
	struct app_rt_exception exc = { 0 };
	int ret;

	cfg.support.network.disconnect = true;

	ret = app_runtime_cmd_set_config(&cfg);
	zassert_equal(ret, 0, "set config should succeed");
	ret = neuro_unit_port_set_network_ops(&network_ops);
	zassert_equal(ret, 0, "set port network ops should succeed");

	ret = app_runtime_cmd_exec(APP_RT_CMD_NETWORK_DISCONNECT, NULL, NULL);
	zassert_true(app_rt_is_framework_error(ret),
		"disconnect without hook should be framework error");
	app_rt_get_last_exception(&exc);
	zassert_equal(exc.code, APP_RT_EX_NOT_SUPPORTED,
		"disconnect without hook should be not supported");
	zassert_equal(g_network_disconnect_calls, 0,
		"disconnect hook must not run when missing");
}

ZTEST(app_runtime_cmd_capability, test_generic_hooks_execute_generic_enum_ids)
{
	struct app_runtime_cmd_config cfg = { 0 };
	const struct neuro_unit_port_network_ops network_ops = {
		.connect = mock_wifi_connect,
		.disconnect = mock_wifi_disconnect,
	};
	int ret;

	cfg.support.network.connect = true;
	cfg.support.network.disconnect = true;

	ret = app_runtime_cmd_set_config(&cfg);
	zassert_equal(ret, 0, "set config should succeed");
	ret = neuro_unit_port_set_network_ops(&network_ops);
	zassert_equal(ret, 0, "set port network ops should succeed");

	ret = app_runtime_cmd_exec(APP_RT_CMD_NETWORK_CONNECT, "ssid", "psk");
	zassert_equal(ret, 0,
		"network enum id should execute via generic network hook");
	zassert_equal(g_network_connect_calls, 1,
		"network hook should be called once");

	ret = app_runtime_cmd_exec(APP_RT_CMD_NETWORK_DISCONNECT, NULL, NULL);
	zassert_equal(ret, 0,
		"network disconnect enum id should execute via generic hook");
	zassert_equal(g_network_disconnect_calls, 1,
		"network disconnect hook should be called once");
}

ZTEST(app_runtime_cmd_capability,
	test_generic_hooks_require_explicit_generic_registration)
{
	struct app_runtime_cmd_config cfg = { 0 };
	struct app_rt_exception exc = { 0 };
	int ret;

	cfg.support.network.connect = true;

	ret = app_runtime_cmd_set_config(&cfg);
	zassert_equal(ret, 0, "set config should succeed");

	ret = app_runtime_cmd_exec(APP_RT_CMD_NETWORK_CONNECT, "ssid", "psk");
	zassert_true(app_rt_is_framework_error(ret),
		"network command without generic hook should return framework error");
	app_rt_get_last_exception(&exc);
	zassert_equal(exc.code, APP_RT_EX_NOT_SUPPORTED,
		"network command without generic hook should be not supported");
}

ZTEST_SUITE(app_runtime_cmd_capability, NULL, NULL, test_reset, NULL, NULL);
