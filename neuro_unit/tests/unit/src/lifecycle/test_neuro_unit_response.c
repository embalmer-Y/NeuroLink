#include <zephyr/ztest.h>
#include <zephyr/sys/printk.h>

#include <string.h>

#include "neuro_protocol_codec_cbor.h"
#include "neuro_unit_response.h"

ZTEST(neuro_unit_response, test_build_error_response_contract)
{
	char json[256];
	int ret;

	ret = neuro_unit_build_error_response(
		json, sizeof(json), "req-1", "unit-01", 404, "missing");
	zassert_equal(ret, 0, "error response build should succeed");
	zassert_true(
		strcmp(json,
			"{\"status\":\"error\",\"request_id\":\"req-1\",\"node_id\":\"unit-01\",\"status_code\":404,\"message\":\"missing\"}") ==
			0,
		"error response JSON contract changed");
	zassert_not_null(strstr(json, "\"status\":\"error\""),
		"error response should contain status=error");
	zassert_not_null(strstr(json, "\"request_id\":\"req-1\""),
		"error response should include request id");
	zassert_not_null(strstr(json, "\"status_code\":404"),
		"error response should include status code");
}

ZTEST(neuro_unit_response, test_build_error_response_cbor_contract)
{
	struct neuro_protocol_cbor_envelope envelope;
	uint8_t payload[128];
	size_t encoded_len;
	int ret;

	ret = neuro_unit_build_error_response_cbor(payload, sizeof(payload),
		"req-1", "unit-01", 404, "missing", &encoded_len);
	zassert_equal(ret, 0, "error response CBOR build should succeed");
	zassert_equal(neuro_protocol_cbor_decode_envelope_header(
			      payload, encoded_len, &envelope),
		0, "error response CBOR envelope should decode");
	zassert_equal(envelope.message_kind,
		NEURO_PROTOCOL_CBOR_MSG_ERROR_REPLY,
		"error response CBOR kind should match");
}

ZTEST(neuro_unit_response, test_build_lease_responses_contract)
{
	struct neuro_lease_entry lease = {
		.active = true,
		.priority = 7,
		.expires_at_ms = 12345,
	};
	char json[256];
	int ret;

	snprintk(lease.lease_id, sizeof(lease.lease_id), "lease-1");
	snprintk(lease.resource, sizeof(lease.resource), "app/x/control");

	ret = neuro_unit_build_lease_acquire_response(
		json, sizeof(json), "req-2", "unit-01", &lease);
	zassert_equal(ret, 0, "lease acquire response build should succeed");
	zassert_true(
		strcmp(json,
			"{\"status\":\"ok\",\"request_id\":\"req-2\",\"node_id\":\"unit-01\",\"lease_id\":\"lease-1\",\"resource\":\"app/x/control\",\"expires_at_ms\":12345}") ==
			0,
		"lease acquire JSON contract changed");
	zassert_not_null(strstr(json, "\"lease_id\":\"lease-1\""),
		"lease acquire response should include lease id");
	zassert_not_null(strstr(json, "\"expires_at_ms\":12345"),
		"lease acquire response should include expires_at_ms");

	ret = neuro_unit_build_lease_release_response(
		json, sizeof(json), "req-3", "unit-01", &lease);
	zassert_equal(ret, 0, "lease release response build should succeed");
	zassert_true(
		strcmp(json,
			"{\"status\":\"ok\",\"request_id\":\"req-3\",\"node_id\":\"unit-01\",\"lease_id\":\"lease-1\",\"resource\":\"app/x/control\"}") ==
			0,
		"lease release JSON contract changed");
	zassert_not_null(strstr(json, "\"resource\":\"app/x/control\""),
		"lease release response should include resource");
}

ZTEST(neuro_unit_response, test_build_lease_responses_cbor_contract)
{
	struct neuro_lease_entry lease = {
		.active = true,
		.priority = 7,
		.expires_at_ms = 12345,
	};
	struct neuro_protocol_cbor_envelope envelope;
	uint8_t payload[160];
	size_t encoded_len;
	int ret;

	snprintk(lease.lease_id, sizeof(lease.lease_id), "lease-1");
	snprintk(lease.resource, sizeof(lease.resource), "app/x/control");

	ret = neuro_unit_build_lease_acquire_response_cbor(payload,
		sizeof(payload), "req-2", "unit-01", &lease, &encoded_len);
	zassert_equal(ret, 0, "lease acquire CBOR build should succeed");
	zassert_equal(neuro_protocol_cbor_decode_envelope_header(
			      payload, encoded_len, &envelope),
		0, "lease acquire CBOR envelope should decode");
	zassert_equal(envelope.message_kind,
		NEURO_PROTOCOL_CBOR_MSG_LEASE_REPLY,
		"lease acquire CBOR kind should match");

	ret = neuro_unit_build_lease_release_response_cbor(payload,
		sizeof(payload), "req-3", "unit-01", &lease, &encoded_len);
	zassert_equal(ret, 0, "lease release CBOR build should succeed");
	zassert_equal(neuro_protocol_cbor_decode_envelope_header(
			      payload, encoded_len, &envelope),
		0, "lease release CBOR envelope should decode");
	zassert_equal(envelope.message_kind,
		NEURO_PROTOCOL_CBOR_MSG_LEASE_REPLY,
		"lease release CBOR kind should match");
}

ZTEST(neuro_unit_response, test_build_query_device_response_contract)
{
	struct neuro_network_status network_status = {
		.state = NEURO_NETWORK_READY,
	};
	char json[256];
	int ret;

	snprintk(network_status.ipv4_addr, sizeof(network_status.ipv4_addr),
		"192.168.2.69");
	ret = neuro_unit_build_query_device_response(json, sizeof(json),
		"req-4", "unit-01", "dnesp32s3b", "client", true,
		&network_status);
	zassert_equal(ret, 0, "query device response build should succeed");
	zassert_true(
		strcmp(json,
			"{\"status\":\"ok\",\"request_id\":\"req-4\",\"node_id\":\"unit-01\",\"board\":\"dnesp32s3b\",\"zenoh_mode\":\"client\",\"session_ready\":true,\"network_state\":\"NETWORK_READY\",\"ipv4\":\"192.168.2.69\"}") ==
			0,
		"query device JSON contract changed");
	zassert_not_null(strstr(json, "\"board\":\"dnesp32s3b\""),
		"query device response should include board");
	zassert_not_null(strstr(json, "\"network_state\":\"NETWORK_READY\""),
		"query device response should include network state");
}

ZTEST(neuro_unit_response, test_build_query_device_response_cbor_contract)
{
	struct neuro_network_status network_status = {
		.state = NEURO_NETWORK_READY,
	};
	struct neuro_protocol_cbor_envelope envelope;
	uint8_t payload[192];
	size_t encoded_len;
	int ret;

	snprintk(network_status.ipv4_addr, sizeof(network_status.ipv4_addr),
		"192.168.2.69");
	ret = neuro_unit_build_query_device_response_cbor(payload,
		sizeof(payload), "req-4", "unit-01", "dnesp32s3b", "client",
		true, &network_status, &encoded_len);
	zassert_equal(ret, 0, "query device CBOR build should succeed");
	zassert_equal(neuro_protocol_cbor_decode_envelope_header(
			      payload, encoded_len, &envelope),
		0, "query device CBOR envelope should decode");
	zassert_equal(envelope.message_kind,
		NEURO_PROTOCOL_CBOR_MSG_QUERY_DEVICE_REPLY,
		"query device CBOR kind should match");
}

ZTEST(neuro_unit_response, test_build_query_apps_response_contract)
{
	struct app_runtime_status status;
	struct neuro_artifact_store artifact_store;
	struct neuro_update_manager update_manager;
	char json[1024];
	int ret;

	memset(&status, 0, sizeof(status));
	neuro_artifact_store_init(&artifact_store);
	neuro_update_manager_init(&update_manager);

	status.app_count = 1U;
	status.listed_app_count = 1U;
	status.running_count = 1U;
	status.apps[0].state = APP_RT_RUNNING;
	status.apps[0].priority = 3U;
	status.apps[0].manifest_present = true;
	snprintk(status.apps[0].name, sizeof(status.apps[0].name),
		"neuro_unit_app");
	snprintk(status.apps[0].path, sizeof(status.apps[0].path),
		"/SD:/apps/neuro_unit_app.llext");

	ret = neuro_artifact_store_stage(&artifact_store, "neuro_unit_app",
		"zenoh", "k1", "/SD:/apps/neuro_unit_app.llext", 4096U, 512U,
		8U);
	zassert_equal(ret, 0, "artifact stage should succeed for test setup");

	ret = neuro_unit_build_query_apps_response(json, sizeof(json), "req-5",
		"unit-01", &status, &artifact_store, &update_manager);
	zassert_equal(ret, 0, "query apps response build should succeed");
	zassert_true(
		strcmp(json,
			"{\"status\":\"ok\",\"request_id\":\"req-5\",\"node_id\":\"unit-01\",\"app_count\":1,\"running_count\":1,\"suspended_count\":0,\"apps\":[{\"app_id\":\"neuro_unit_app\",\"state\":\"RUNNING\",\"path\":\"/SD:/apps/neuro_unit_app.llext\",\"priority\":3,\"manifest_present\":true,\"update_state\":\"NONE\",\"artifact_state\":\"STAGED\",\"stable_ref\":\"\",\"last_error\":\"\",\"rollback_reason\":\"\"}]}") ==
			0,
		"query apps JSON contract changed");
	zassert_not_null(strstr(json, "\"app_id\":\"neuro_unit_app\""),
		"query apps response should include app id");
	zassert_not_null(strstr(json, "\"state\":\"RUNNING\""),
		"query apps response should include runtime state");
	zassert_not_null(strstr(json, "\"artifact_state\":\"STAGED\""),
		"query apps response should include artifact state");
}

ZTEST(neuro_unit_response, test_build_query_apps_snapshot_response_contract)
{
	const struct neuro_unit_query_app_snapshot app = {
		.app_id = "neuro_unit_app",
		.runtime_state = APP_RT_RUNNING,
		.path = "/SD:/apps/neuro_unit_app.llext",
		.priority = 3U,
		.manifest_present = true,
		.update_state = "NONE",
		.artifact_state = NEURO_ARTIFACT_STAGED,
		.stable_ref = "",
		.last_error = "",
		.rollback_reason = "",
	};
	const struct neuro_unit_query_apps_snapshot snapshot = {
		.app_count = 1U,
		.running_count = 1U,
		.suspended_count = 0U,
		.apps = &app,
		.app_snapshot_count = 1U,
	};
	char json[1024];
	int ret;

	ret = neuro_unit_build_query_apps_snapshot_response(
		json, sizeof(json), "req-5", "unit-01", &snapshot);
	zassert_equal(
		ret, 0, "query apps snapshot response build should succeed");
	zassert_true(
		strcmp(json,
			"{\"status\":\"ok\",\"request_id\":\"req-5\",\"node_id\":\"unit-01\",\"app_count\":1,\"running_count\":1,\"suspended_count\":0,\"apps\":[{\"app_id\":\"neuro_unit_app\",\"state\":\"RUNNING\",\"path\":\"/SD:/apps/neuro_unit_app.llext\",\"priority\":3,\"manifest_present\":true,\"update_state\":\"NONE\",\"artifact_state\":\"STAGED\",\"stable_ref\":\"\",\"last_error\":\"\",\"rollback_reason\":\"\"}]}") ==
			0,
		"query apps snapshot JSON contract changed");
}

ZTEST(neuro_unit_response,
	test_build_query_apps_snapshot_response_cbor_contract)
{
	const struct neuro_unit_query_app_snapshot app = {
		.app_id = "neuro_unit_app",
		.runtime_state = APP_RT_RUNNING,
		.path = "/SD:/apps/neuro_unit_app.llext",
		.priority = 3U,
		.manifest_present = true,
		.update_state = "NONE",
		.artifact_state = NEURO_ARTIFACT_STAGED,
		.stable_ref = "",
		.last_error = "",
		.rollback_reason = "",
	};
	const struct neuro_unit_query_apps_snapshot snapshot = {
		.app_count = 1U,
		.running_count = 1U,
		.suspended_count = 0U,
		.apps = &app,
		.app_snapshot_count = 1U,
	};
	struct neuro_protocol_cbor_envelope envelope;
	uint8_t payload[512];
	size_t encoded_len;
	int ret;

	ret = neuro_unit_build_query_apps_snapshot_response_cbor(payload,
		sizeof(payload), "req-5", "unit-01", &snapshot, &encoded_len);
	zassert_equal(ret, 0, "query apps snapshot CBOR build should succeed");
	zassert_equal(neuro_protocol_cbor_decode_envelope_header(
			      payload, encoded_len, &envelope),
		0, "query apps CBOR envelope should decode");
	zassert_equal(envelope.message_kind,
		NEURO_PROTOCOL_CBOR_MSG_QUERY_APPS_REPLY,
		"query apps CBOR kind should match");
}

ZTEST(neuro_unit_response, test_build_query_leases_response_contract)
{
	struct neuro_lease_entry entries[2] = { 0 };
	char json[512];
	int ret;

	snprintk(entries[0].lease_id, sizeof(entries[0].lease_id), "l-1");
	snprintk(entries[0].resource, sizeof(entries[0].resource),
		"update/app/a/activate");
	snprintk(
		entries[0].source_core, sizeof(entries[0].source_core), "core");
	snprintk(entries[0].source_agent, sizeof(entries[0].source_agent),
		"agent");
	entries[0].priority = 4;
	entries[0].expires_at_ms = 111;

	snprintk(entries[1].lease_id, sizeof(entries[1].lease_id), "l-2");
	snprintk(entries[1].resource, sizeof(entries[1].resource),
		"update/app/b/activate");
	snprintk(
		entries[1].source_core, sizeof(entries[1].source_core), "core");
	snprintk(entries[1].source_agent, sizeof(entries[1].source_agent),
		"agent");
	entries[1].priority = 5;
	entries[1].expires_at_ms = 222;

	ret = neuro_unit_build_query_leases_response(
		json, sizeof(json), "req-6", "unit-01", entries, 2U);
	zassert_equal(ret, 0, "query leases response build should succeed");
	zassert_true(
		strcmp(json,
			"{\"status\":\"ok\",\"request_id\":\"req-6\",\"node_id\":\"unit-01\",\"leases\":[{\"lease_id\":\"l-1\",\"resource\":\"update/app/a/activate\",\"source_core\":\"core\",\"source_agent\":\"agent\",\"priority\":4,\"expires_at_ms\":111},{\"lease_id\":\"l-2\",\"resource\":\"update/app/b/activate\",\"source_core\":\"core\",\"source_agent\":\"agent\",\"priority\":5,\"expires_at_ms\":222}]}") ==
			0,
		"query leases JSON contract changed");
	zassert_not_null(strstr(json, "\"lease_id\":\"l-1\""),
		"query leases response should include first lease");
	zassert_not_null(strstr(json, "\"lease_id\":\"l-2\""),
		"query leases response should include second lease");
}

ZTEST(neuro_unit_response, test_build_query_leases_response_cbor_contract)
{
	struct neuro_lease_entry entries[1] = { 0 };
	struct neuro_protocol_cbor_envelope envelope;
	uint8_t payload[256];
	size_t encoded_len;
	int ret;

	snprintk(entries[0].lease_id, sizeof(entries[0].lease_id), "l-1");
	snprintk(entries[0].resource, sizeof(entries[0].resource),
		"update/app/a/activate");
	snprintk(
		entries[0].source_core, sizeof(entries[0].source_core), "core");
	snprintk(entries[0].source_agent, sizeof(entries[0].source_agent),
		"agent");
	entries[0].priority = 4;
	entries[0].expires_at_ms = 111;

	ret = neuro_unit_build_query_leases_response_cbor(payload,
		sizeof(payload), "req-6", "unit-01", entries, 1U, &encoded_len);
	zassert_equal(ret, 0, "query leases CBOR build should succeed");
	zassert_equal(neuro_protocol_cbor_decode_envelope_header(
			      payload, encoded_len, &envelope),
		0, "query leases CBOR envelope should decode");
	zassert_equal(envelope.message_kind,
		NEURO_PROTOCOL_CBOR_MSG_QUERY_LEASES_REPLY,
		"query leases CBOR kind should match");
}

ZTEST(neuro_unit_response, test_validate_request_metadata_payload)
{
	struct neuro_request_metadata metadata;
	char error[96];
	bool ok;
	const char *json =
		"{\"request_id\":\"r1\",\"source_core\":\"c1\",\"source_agent\":\"a1\",\"target_node\":\"unit-01\",\"timeout_ms\":1000}";

	memset(&metadata, 0, sizeof(metadata));
	memset(error, 0, sizeof(error));
	ok = neuro_unit_validate_request_metadata_payload(json, &metadata,
		NEURO_REQ_META_REQUIRE_COMMON, "unit-01", error, sizeof(error));
	zassert_true(ok, "metadata validation should pass on valid payload");

	memset(&metadata, 0, sizeof(metadata));
	memset(error, 0, sizeof(error));
	ok = neuro_unit_validate_request_metadata_payload(json, &metadata,
		NEURO_REQ_META_REQUIRE_COMMON, "unit-02", error, sizeof(error));
	zassert_false(ok,
		"metadata validation should fail on mismatched target node");
	zassert_not_null(strstr(error, "target_node"),
		"validation error should mention target_node");
}

ZTEST_SUITE(neuro_unit_response, NULL, NULL, NULL, NULL, NULL);
