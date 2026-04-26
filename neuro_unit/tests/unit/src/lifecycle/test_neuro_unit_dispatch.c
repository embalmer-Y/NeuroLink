#include <zephyr/ztest.h>
#include <zephyr/sys/printk.h>

#include <errno.h>
#include <stdbool.h>
#include <string.h>

#include "neuro_unit_dispatch.h"
#include "neuro_unit_reply_context.h"

struct dispatch_probe {
	bool transport_healthy;
	bool validate_ok;
	int ensure_recovery_ret;
	int last_status_code;
	char last_error_message[64];
	char app_id[32];
	char action[32];
	char lease_id[32];
	char start_args[96];
	char reason[64];
	int lease_acquire_calls;
	int lease_release_calls;
	int app_action_calls;
	int query_device_calls;
	int query_apps_calls;
	int query_leases_calls;
	int update_action_calls;
	int ensure_recovery_calls;
	int transport_snapshot_calls;
};

static struct dispatch_probe g_probe;

static bool cb_transport_healthy(void) { return g_probe.transport_healthy; }

static void cb_transport_snapshot(
	const char *stage, const char *key, const char *request_id)
{
	ARG_UNUSED(stage);
	ARG_UNUSED(key);
	ARG_UNUSED(request_id);

	g_probe.transport_snapshot_calls++;
}

static bool cb_validate(const z_loaned_query_t *query, const char *payload,
	struct neuro_request_metadata *metadata, uint32_t required_fields)
{
	ARG_UNUSED(query);
	ARG_UNUSED(payload);
	ARG_UNUSED(metadata);
	ARG_UNUSED(required_fields);

	return g_probe.validate_ok;
}

static int cb_ensure_recovery_seed_initialized(void)
{
	g_probe.ensure_recovery_calls++;
	return g_probe.ensure_recovery_ret;
}

static void cb_reply_error(const z_loaned_query_t *query,
	const char *request_id, const char *message, int status_code)
{
	ARG_UNUSED(query);
	ARG_UNUSED(request_id);

	g_probe.last_status_code = status_code;
	snprintk(g_probe.last_error_message, sizeof(g_probe.last_error_message),
		"%s", message);
}

static void cb_handle_lease_acquire(const z_loaned_query_t *query,
	const char *payload, const char *request_id)
{
	ARG_UNUSED(query);
	ARG_UNUSED(payload);
	ARG_UNUSED(request_id);

	g_probe.lease_acquire_calls++;
}

static void cb_handle_lease_release(const z_loaned_query_t *query,
	const char *payload, const char *request_id)
{
	ARG_UNUSED(query);
	ARG_UNUSED(payload);
	ARG_UNUSED(request_id);

	g_probe.lease_release_calls++;
}

static void cb_handle_app_action(const z_loaned_query_t *query,
	const char *app_id, const char *action, const char *payload,
	const char *request_id, const struct neuro_request_metadata *metadata,
	const struct neuro_unit_request_fields *request_fields)
{
	ARG_UNUSED(query);
	ARG_UNUSED(payload);
	ARG_UNUSED(request_id);

	g_probe.app_action_calls++;
	snprintk(g_probe.app_id, sizeof(g_probe.app_id), "%s", app_id);
	snprintk(g_probe.action, sizeof(g_probe.action), "%s", action);
	snprintk(g_probe.lease_id, sizeof(g_probe.lease_id), "%s",
		metadata != NULL ? metadata->lease_id : "");
	snprintk(g_probe.start_args, sizeof(g_probe.start_args), "%s",
		request_fields != NULL ? request_fields->start_args : "");
}

static void cb_handle_query_device(
	const z_loaned_query_t *query, const char *request_id)
{
	ARG_UNUSED(query);
	ARG_UNUSED(request_id);

	g_probe.query_device_calls++;
}

static void cb_handle_query_apps(
	const z_loaned_query_t *query, const char *request_id)
{
	ARG_UNUSED(query);
	ARG_UNUSED(request_id);

	g_probe.query_apps_calls++;
}

static void cb_handle_query_leases(
	const z_loaned_query_t *query, const char *request_id)
{
	ARG_UNUSED(query);
	ARG_UNUSED(request_id);

	g_probe.query_leases_calls++;
}

static void cb_handle_update_action(const z_loaned_query_t *query,
	const char *app_id, const char *action, const char *payload,
	const char *request_id, const struct neuro_request_metadata *metadata,
	const struct neuro_unit_request_fields *request_fields)
{
	ARG_UNUSED(query);
	ARG_UNUSED(payload);
	ARG_UNUSED(request_id);

	g_probe.update_action_calls++;
	snprintk(g_probe.app_id, sizeof(g_probe.app_id), "%s", app_id);
	snprintk(g_probe.action, sizeof(g_probe.action), "%s", action);
	snprintk(g_probe.lease_id, sizeof(g_probe.lease_id), "%s",
		metadata != NULL ? metadata->lease_id : "");
	snprintk(g_probe.reason, sizeof(g_probe.reason), "%s",
		request_fields != NULL ? request_fields->reason : "");
}

static struct neuro_unit_dispatch_ops g_ops = {
	.node_id = "unit-01",
	.transport_healthy = cb_transport_healthy,
	.log_transport_health_snapshot = cb_transport_snapshot,
	.validate_request_metadata_or_reply = cb_validate,
	.ensure_recovery_seed_initialized = cb_ensure_recovery_seed_initialized,
	.reply_error = cb_reply_error,
	.handle_lease_acquire = cb_handle_lease_acquire,
	.handle_lease_release = cb_handle_lease_release,
	.handle_app_action = cb_handle_app_action,
	.handle_query_device = cb_handle_query_device,
	.handle_query_apps = cb_handle_query_apps,
	.handle_query_leases = cb_handle_query_leases,
	.handle_update_action = cb_handle_update_action,
};

static void test_reset(void *fixture)
{
	ARG_UNUSED(fixture);
	memset(&g_probe, 0, sizeof(g_probe));
	g_probe.transport_healthy = true;
	g_probe.validate_ok = true;
}

ZTEST(neuro_unit_dispatch, test_command_lease_acquire_route_dispatches)
{
	struct neuro_request_metadata metadata = { 0 };
	struct neuro_unit_request_fields request_fields = { 0 };

	snprintk(metadata.request_id, sizeof(metadata.request_id), "req-1");
	snprintk(request_fields.start_args, sizeof(request_fields.start_args),
		"--dispatch");
	neuro_unit_dispatch_command_query(NULL,
		"neuro/unit-01/cmd/lease/acquire", "{}", &metadata,
		&request_fields, &g_ops);

	zassert_equal(g_probe.lease_acquire_calls, 1,
		"lease acquire route should dispatch exactly once");
	zassert_equal(g_probe.last_status_code, 0,
		"no error should be reported on a handled route");
}

ZTEST(neuro_unit_dispatch, test_command_lease_release_route_dispatches)
{
	struct neuro_request_metadata metadata = { 0 };

	snprintk(metadata.request_id, sizeof(metadata.request_id), "req-1b");
	neuro_unit_dispatch_command_query(NULL,
		"neuro/unit-01/cmd/lease/release", "{}", &metadata, NULL,
		&g_ops);

	zassert_equal(g_probe.lease_release_calls, 1,
		"lease release route should dispatch exactly once");
	zassert_equal(g_probe.last_status_code, 0,
		"no error should be reported on a handled route");
}

ZTEST(neuro_unit_dispatch, test_command_app_route_extracts_app_and_action)
{
	struct neuro_request_metadata metadata = { 0 };
	struct neuro_unit_request_fields request_fields = { 0 };

	snprintk(metadata.request_id, sizeof(metadata.request_id), "req-2");
	snprintk(
		metadata.lease_id, sizeof(metadata.lease_id), "lease-dispatch");
	snprintk(request_fields.start_args, sizeof(request_fields.start_args),
		"--from-fields");
	neuro_unit_dispatch_command_query(NULL,
		"neuro/unit-01/cmd/app/neuro_unit_app/invoke", "{}", &metadata,
		&request_fields, &g_ops);

	zassert_equal(g_probe.app_action_calls, 1,
		"app command route should dispatch once");
	zassert_true(strcmp(g_probe.app_id, "neuro_unit_app") == 0,
		"app id should be extracted from route");
	zassert_true(strcmp(g_probe.action, "invoke") == 0,
		"action should be extracted from route");
	zassert_true(strcmp(g_probe.lease_id, "lease-dispatch") == 0,
		"decoded metadata should be forwarded to app handler");
	zassert_true(strcmp(g_probe.start_args, "--from-fields") == 0,
		"decoded request fields should be forwarded to app handler");
}

ZTEST(neuro_unit_dispatch, test_classify_routes_are_node_scoped)
{
	struct neuro_unit_dispatch_route route;

	zassert_true(
		neuro_unit_dispatch_classify_command_route(
			"neuro/unit-01/cmd/lease/acquire", "unit-01", &route),
		"lease acquire should classify for matching node");
	zassert_equal(route.kind, NEURO_UNIT_DISPATCH_ROUTE_LEASE_ACQUIRE,
		"lease acquire kind should classify");

	zassert_false(
		neuro_unit_dispatch_classify_command_route(
			"neuro/unit-02/cmd/lease/acquire", "unit-01", &route),
		"wrong-node lease route must not classify");
	zassert_equal(route.kind, NEURO_UNIT_DISPATCH_ROUTE_INVALID,
		"failed classification should reset route state");
}

ZTEST(neuro_unit_dispatch, test_classify_app_and_update_routes)
{
	struct neuro_unit_dispatch_route route;

	zassert_true(neuro_unit_dispatch_classify_command_route(
			     "neuro/unit-01/cmd/app/neuro_unit_app/invoke",
			     "unit-01", &route),
		"app command should classify");
	zassert_equal(route.kind, NEURO_UNIT_DISPATCH_ROUTE_APP_ACTION,
		"app command kind should classify");
	zassert_true(strcmp(route.app_id, "neuro_unit_app") == 0,
		"app id should classify");
	zassert_true(strcmp(route.action, "invoke") == 0,
		"app command action should classify");

	zassert_true(neuro_unit_dispatch_classify_update_route(
			     "neuro/unit-01/update/app/neuro_unit_app/activate",
			     "unit-01", &route),
		"update command should classify");
	zassert_equal(route.kind, NEURO_UNIT_DISPATCH_ROUTE_UPDATE_ACTION,
		"update kind should classify");
	zassert_true(strcmp(route.app_id, "neuro_unit_app") == 0,
		"update app id should classify");
	zassert_true(strcmp(route.action, "activate") == 0,
		"update action should classify");
}

ZTEST(neuro_unit_dispatch, test_classify_rejects_nested_actions)
{
	struct neuro_unit_dispatch_route route;

	zassert_false(
		neuro_unit_dispatch_classify_command_route(
			"neuro/unit-01/cmd/app/neuro_unit_app/invoke/extra",
			"unit-01", &route),
		"nested app command action must not classify");
	zassert_false(
		neuro_unit_dispatch_classify_update_route(
			"neuro/unit-01/update/app/neuro_unit_app/activate/extra",
			"unit-01", &route),
		"nested update action must not classify");
}

ZTEST(neuro_unit_dispatch, test_update_prepare_requires_recovery_ready)
{
	struct neuro_request_metadata metadata = { 0 };
	struct neuro_unit_request_fields request_fields = { 0 };

	snprintk(metadata.request_id, sizeof(metadata.request_id), "req-3");
	snprintk(metadata.lease_id, sizeof(metadata.lease_id), "lease-update");
	snprintk(request_fields.reason, sizeof(request_fields.reason),
		"from-fields");
	neuro_unit_dispatch_update_query(NULL,
		"neuro/unit-01/update/app/neuro_unit_app/prepare", "{}",
		&metadata, &request_fields, &g_ops);

	zassert_equal(g_probe.ensure_recovery_calls, 1,
		"lifecycle update route should pass recovery gate");
	zassert_equal(g_probe.update_action_calls, 1,
		"prepared action should dispatch when recovery gate passes");
	zassert_true(strcmp(g_probe.lease_id, "lease-update") == 0,
		"decoded metadata should be forwarded to update handler");
	zassert_true(strcmp(g_probe.reason, "from-fields") == 0,
		"decoded request fields should be forwarded to update handler");
}

ZTEST(neuro_unit_dispatch, test_query_routes_dispatch_to_handlers)
{
	struct neuro_request_metadata metadata = { 0 };

	snprintk(metadata.request_id, sizeof(metadata.request_id), "req-q1");
	neuro_unit_dispatch_query_query(
		NULL, "neuro/unit-01/query/device", "{}", &metadata, &g_ops);
	neuro_unit_dispatch_query_query(
		NULL, "neuro/unit-01/query/apps", "{}", &metadata, &g_ops);
	neuro_unit_dispatch_query_query(
		NULL, "neuro/unit-01/query/leases", "{}", &metadata, &g_ops);

	zassert_equal(g_probe.query_device_calls, 1,
		"device query route should dispatch once");
	zassert_equal(g_probe.query_apps_calls, 1,
		"apps query route should dispatch once");
	zassert_equal(g_probe.query_leases_calls, 1,
		"leases query route should dispatch once");
	zassert_equal(g_probe.last_status_code, 0,
		"handled query routes should not report an error");
}

ZTEST(neuro_unit_dispatch, test_unsupported_routes_report_status_codes)
{
	struct neuro_request_metadata metadata = { 0 };

	snprintk(metadata.request_id, sizeof(metadata.request_id), "req-u1");
	neuro_unit_dispatch_command_query(NULL, "neuro/unit-01/cmd/unknown",
		"{}", &metadata, NULL, &g_ops);
	zassert_equal(g_probe.last_status_code, 404,
		"unsupported command route should map to 404");
	zassert_true(strcmp(g_probe.last_error_message,
			     "unsupported command path") == 0,
		"unsupported command message changed");

	g_probe.last_status_code = 0;
	g_probe.last_error_message[0] = '\0';
	neuro_unit_dispatch_query_query(
		NULL, "neuro/unit-01/query/unknown", "{}", &metadata, &g_ops);
	zassert_equal(g_probe.last_status_code, 404,
		"unsupported query route should map to 404");
	zassert_true(strcmp(g_probe.last_error_message,
			     "unsupported query path") == 0,
		"unsupported query message changed");

	g_probe.last_status_code = 0;
	g_probe.last_error_message[0] = '\0';
	neuro_unit_dispatch_update_query(NULL, "neuro/unit-01/update/bad", "{}",
		&metadata, NULL, &g_ops);
	zassert_equal(g_probe.last_status_code, 400,
		"invalid update route should map to 400");
	zassert_true(
		strcmp(g_probe.last_error_message, "invalid update path") == 0,
		"invalid update message changed");
}

ZTEST(neuro_unit_dispatch, test_update_recover_requires_recovery_ready)
{
	struct neuro_request_metadata metadata = { 0 };

	snprintk(metadata.request_id, sizeof(metadata.request_id), "req-3b");
	neuro_unit_dispatch_update_query(NULL,
		"neuro/unit-01/update/app/neuro_unit_app/recover", "{}",
		&metadata, NULL, &g_ops);

	zassert_equal(g_probe.ensure_recovery_calls, 1,
		"recover route should pass recovery gate");
	zassert_equal(g_probe.update_action_calls, 1,
		"recover route should dispatch when recovery gate passes");
	zassert_true(strcmp(g_probe.action, "recover") == 0,
		"recover action should be preserved for handler");
}

ZTEST(neuro_unit_dispatch, test_update_recovery_gate_failure_replies_503)
{
	struct neuro_request_metadata metadata = { 0 };

	g_probe.ensure_recovery_ret = -EIO;
	snprintk(metadata.request_id, sizeof(metadata.request_id), "req-4");
	neuro_unit_dispatch_update_query(NULL,
		"neuro/unit-01/update/app/neuro_unit_app/prepare", "{}",
		&metadata, NULL, &g_ops);

	zassert_equal(g_probe.ensure_recovery_calls, 1,
		"recovery gate should be invoked once");
	zassert_equal(g_probe.update_action_calls, 0,
		"update action must not dispatch when recovery gate fails");
	zassert_equal(g_probe.last_status_code, 503,
		"recovery gate failure should map to 503");
}

ZTEST(neuro_unit_dispatch, test_query_transport_unhealthy_replies_503)
{
	struct neuro_request_metadata metadata = { 0 };

	g_probe.transport_healthy = false;
	snprintk(metadata.request_id, sizeof(metadata.request_id), "req-5");
	neuro_unit_dispatch_query_query(
		NULL, "neuro/unit-01/query/device", "{}", &metadata, &g_ops);

	zassert_equal(g_probe.transport_snapshot_calls, 1,
		"transport snapshot should be logged on unhealthy gate");
	zassert_equal(g_probe.query_device_calls, 0,
		"query handler must not run on unhealthy transport");
	zassert_equal(g_probe.last_status_code, 503,
		"unhealthy transport should map to 503");
}

ZTEST_SUITE(neuro_unit_dispatch, NULL, NULL, test_reset, NULL, NULL);
