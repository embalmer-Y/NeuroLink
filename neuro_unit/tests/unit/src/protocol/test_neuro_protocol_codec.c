#include <zephyr/ztest.h>

#include <errno.h>
#include <string.h>

#include "neuro_protocol_codec.h"

ZTEST(neuro_protocol_codec, test_encode_error_reply_json_contract)
{
	const struct neuro_protocol_error_reply reply = {
		.request_id = "req-1",
		.node_id = "unit-01",
		.status_code = 404,
		.message = "missing",
	};
	char json[256];

	zassert_equal(neuro_protocol_encode_error_reply_json(
			      json, sizeof(json), &reply),
		0, "error reply should encode");
	zassert_true(
		strcmp(json,
			"{\"status\":\"error\",\"request_id\":\"req-1\",\"node_id\":\"unit-01\",\"status_code\":404,\"message\":\"missing\"}") ==
			0,
		"error reply JSON-v2 contract changed");
}

ZTEST(neuro_protocol_codec, test_encode_lease_replies_json_contract)
{
	const struct neuro_protocol_lease_reply acquire = {
		.request_id = "req-2",
		.node_id = "unit-01",
		.lease_id = "lease-1",
		.resource = "app/neuro_unit_app/control",
		.expires_at_ms = 12345,
		.include_expires_at_ms = true,
	};
	const struct neuro_protocol_lease_reply release = {
		.request_id = "req-3",
		.node_id = "unit-01",
		.lease_id = "lease-1",
		.resource = "app/neuro_unit_app/control",
		.include_expires_at_ms = false,
	};
	char json[256];

	zassert_equal(neuro_protocol_encode_lease_reply_json(
			      json, sizeof(json), &acquire),
		0, "lease acquire reply should encode");
	zassert_true(
		strcmp(json,
			"{\"status\":\"ok\",\"request_id\":\"req-2\",\"node_id\":\"unit-01\",\"lease_id\":\"lease-1\",\"resource\":\"app/neuro_unit_app/control\",\"expires_at_ms\":12345}") ==
			0,
		"lease acquire JSON-v2 contract changed");

	zassert_equal(neuro_protocol_encode_lease_reply_json(
			      json, sizeof(json), &release),
		0, "lease release reply should encode");
	zassert_true(
		strcmp(json,
			"{\"status\":\"ok\",\"request_id\":\"req-3\",\"node_id\":\"unit-01\",\"lease_id\":\"lease-1\",\"resource\":\"app/neuro_unit_app/control\"}") ==
			0,
		"lease release JSON-v2 contract changed");
}

ZTEST(neuro_protocol_codec, test_encode_query_device_reply_json_contract)
{
	const struct neuro_protocol_query_device_reply reply = {
		.request_id = "req-4",
		.node_id = "unit-01",
		.board = "dnesp32s3b",
		.zenoh_mode = "client",
		.session_ready = true,
		.network_state = "NETWORK_READY",
		.ipv4 = "192.168.2.69",
	};
	char json[256];

	zassert_equal(neuro_protocol_encode_query_device_reply_json(
			      json, sizeof(json), &reply),
		0, "query device reply should encode");
	zassert_true(
		strcmp(json,
			"{\"status\":\"ok\",\"request_id\":\"req-4\",\"node_id\":\"unit-01\",\"board\":\"dnesp32s3b\",\"zenoh_mode\":\"client\",\"session_ready\":true,\"network_state\":\"NETWORK_READY\",\"ipv4\":\"192.168.2.69\"}") ==
			0,
		"query device JSON-v2 contract changed");
}

ZTEST(neuro_protocol_codec, test_encode_app_event_payloads_json_contract)
{
	const struct neuro_protocol_callback_event event = {
		.app_id = "neuro_unit_app",
		.event_name = "callback-test",
		.invoke_count = 3U,
		.start_count = 1,
	};
	const struct neuro_protocol_app_command_reply reply = {
		.command_name = "invoke",
		.invoke_count = 4U,
		.callback_enabled = true,
		.trigger_every = 2,
		.event_name = "callback-test",
		.config_changed = true,
		.publish_ret = 0,
		.echo = "hello",
	};
	char json[256];

	zassert_equal(neuro_protocol_encode_callback_event_json(
			      json, sizeof(json), &event),
		0, "callback event should encode");
	zassert_true(
		strcmp(json,
			"{\"app_id\":\"neuro_unit_app\",\"event_name\":\"callback-test\",\"invoke_count\":3,\"start_count\":1}") ==
			0,
		"callback event JSON-v2 contract changed");

	zassert_equal(neuro_protocol_encode_app_command_reply_json(
			      json, sizeof(json), &reply),
		0, "app command reply should encode");
	zassert_true(
		strcmp(json,
			"{\"echo\":\"hello\",\"command\":\"invoke\",\"invoke_count\":4,\"callback_enabled\":true,\"trigger_every\":2,\"event_name\":\"callback-test\",\"config_changed\":true,\"publish_ret\":0}") ==
			0,
		"app command reply JSON-v2 contract changed");
}

ZTEST(neuro_protocol_codec, test_encode_reports_contract_errors)
{
	const struct neuro_protocol_error_reply reply = {
		.request_id = "req-1",
		.node_id = "unit-01",
		.status_code = 500,
		.message = "too long",
	};
	char json[8];

	zassert_equal(neuro_protocol_encode_error_reply_json(
			      NULL, sizeof(json), &reply),
		-EINVAL, "null buffer should fail");
	zassert_equal(neuro_protocol_encode_error_reply_json(
			      json, sizeof(json), NULL),
		-EINVAL, "null reply should fail");
	zassert_equal(neuro_protocol_encode_error_reply_json(
			      json, sizeof(json), &reply),
		-ENAMETOOLONG, "small buffer should fail explicitly");
}

ZTEST(neuro_protocol_codec, test_decode_request_metadata_json_contract)
{
	struct neuro_protocol_request_metadata metadata;

	zassert_equal(
		neuro_protocol_decode_request_metadata_json(
			"{\"request_id\":\"req-1\",\"source_core\":\"core\",\"source_agent\":\"agent\",\"target_node\":\"unit-01\",\"lease_id\":\"lease-1\",\"idempotency_key\":\"idem-1\",\"timeout_ms\":1000,\"priority\":7,\"forwarded\":true}",
			&metadata),
		0, "request metadata decode should succeed");
	zassert_equal(strcmp(metadata.request_id, "req-1"), 0,
		"request_id should decode");
	zassert_equal(strcmp(metadata.source_core, "core"), 0,
		"source_core should decode");
	zassert_equal(strcmp(metadata.source_agent, "agent"), 0,
		"source_agent should decode");
	zassert_equal(strcmp(metadata.target_node, "unit-01"), 0,
		"target_node should decode");
	zassert_equal(strcmp(metadata.lease_id, "lease-1"), 0,
		"lease_id should decode");
	zassert_equal(strcmp(metadata.idempotency_key, "idem-1"), 0,
		"idempotency_key should decode");
	zassert_equal(metadata.timeout_ms, 1000U, "timeout_ms should decode");
	zassert_equal(metadata.priority, 7, "priority should decode");
	zassert_true(metadata.forwarded, "forwarded should decode");

	zassert_equal(neuro_protocol_decode_request_metadata_json(
			      "{\"request_id\":\"req-partial\"}", &metadata),
		0, "partial metadata should decode");
	zassert_equal(metadata.priority, -1,
		"missing priority should keep metadata default");
}

ZTEST(neuro_protocol_codec, test_decode_callback_config_json_contract)
{
	struct neuro_protocol_callback_config config;

	zassert_equal(
		neuro_protocol_decode_callback_config_json(
			"{\"callback_enabled\":false,\"trigger_every\":5,\"event_name\":\"tick\"}",
			&config),
		0, "callback config decode should succeed");
	zassert_true(config.has_callback_enabled,
		"callback_enabled presence should be reported");
	zassert_false(config.callback_enabled,
		"callback_enabled false should decode");
	zassert_true(config.has_trigger_every,
		"trigger_every presence should be reported");
	zassert_equal(config.trigger_every, 5, "trigger_every should decode");
	zassert_true(config.has_event_name,
		"event_name presence should be reported");
	zassert_equal(strcmp(config.event_name, "tick"), 0,
		"event_name should decode");
}

ZTEST_SUITE(neuro_protocol_codec, NULL, NULL, NULL, NULL, NULL);