#include <zephyr/ztest.h>

#include <errno.h>
#include <string.h>

#include "neuro_protocol_codec.h"
#include "neuro_protocol_codec_cbor.h"

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

ZTEST(neuro_protocol_codec, test_cbor_facade_build_config_contract)
{
	zassert_true(IS_ENABLED(CONFIG_NEUROLINK_PROTOCOL_CBOR),
		"NeuroLink CBOR facade config should be enabled");
	zassert_true(IS_ENABLED(CONFIG_ZCBOR), "zcbor should be selected");
	zassert_true(IS_ENABLED(CONFIG_ZCBOR_CANONICAL),
		"CBOR vectors should be canonical");
}

ZTEST(neuro_protocol_codec, test_cbor_envelope_header_contract)
{
	const uint8_t expected[] = { 0xa2, 0x00, 0x02, 0x01, 0x01 };
	struct neuro_protocol_cbor_envelope envelope;
	uint8_t payload[16];
	size_t encoded_len;

	zassert_equal(
		neuro_protocol_cbor_encode_envelope_header(payload,
			sizeof(payload), NEURO_PROTOCOL_CBOR_MSG_QUERY_REQUEST,
			&encoded_len),
		0, "CBOR envelope header should encode");
	zassert_equal(encoded_len, sizeof(expected),
		"CBOR envelope header length changed");
	zassert_mem_equal(payload, expected, sizeof(expected),
		"CBOR envelope header bytes changed");

	zassert_equal(neuro_protocol_cbor_decode_envelope_header(
			      payload, encoded_len, &envelope),
		0, "CBOR envelope header should decode");
	zassert_equal(envelope.schema_version,
		NEURO_PROTOCOL_CBOR_SCHEMA_VERSION,
		"schema version should decode");
	zassert_equal(envelope.message_kind,
		NEURO_PROTOCOL_CBOR_MSG_QUERY_REQUEST,
		"message kind should decode");
}

ZTEST(neuro_protocol_codec, test_cbor_envelope_rejects_bad_inputs)
{
	const uint8_t bad_version[] = { 0xa2, 0x00, 0x01, 0x01, 0x01 };
	const uint8_t bad_kind[] = { 0xa2, 0x00, 0x02, 0x01, 0x18, 0x63 };
	const uint8_t truncated[] = { 0xa2, 0x00, 0x02, 0x01 };
	struct neuro_protocol_cbor_envelope envelope;
	uint8_t payload[4];
	size_t encoded_len;

	zassert_equal(
		neuro_protocol_cbor_encode_envelope_header(NULL,
			sizeof(payload), NEURO_PROTOCOL_CBOR_MSG_QUERY_REQUEST,
			&encoded_len),
		-EINVAL, "null payload should fail");
	zassert_equal(
		neuro_protocol_cbor_encode_envelope_header(payload,
			sizeof(payload), NEURO_PROTOCOL_CBOR_MSG_QUERY_REQUEST,
			&encoded_len),
		-ENAMETOOLONG, "small payload should fail");
	zassert_equal(neuro_protocol_cbor_encode_envelope_header(
			      payload, sizeof(payload), 99, &encoded_len),
		-ENOTSUP, "unknown message kind should fail");
	zassert_equal(neuro_protocol_cbor_decode_envelope_header(
			      NULL, sizeof(bad_version), &envelope),
		-EINVAL, "null decode payload should fail");
	zassert_equal(neuro_protocol_cbor_decode_envelope_header(
			      bad_version, sizeof(bad_version), &envelope),
		-ENOTSUP, "bad schema version should fail");
	zassert_equal(neuro_protocol_cbor_decode_envelope_header(
			      bad_kind, sizeof(bad_kind), &envelope),
		-ENOTSUP, "bad message kind should fail");
	zassert_equal(neuro_protocol_cbor_decode_envelope_header(
			      truncated, sizeof(truncated), &envelope),
		-EBADMSG, "truncated payload should fail");
}

ZTEST(neuro_protocol_codec, test_encode_error_reply_cbor_golden_contract)
{
	const struct neuro_protocol_error_reply reply = {
		.request_id = "req-1",
		.node_id = "unit-01",
		.status_code = 404,
		.message = "missing",
	};
	const uint8_t expected[] = { 0xa7, 0x00, 0x02, 0x01, 0x14, 0x02, 0x65,
		0x65, 0x72, 0x72, 0x6f, 0x72, 0x03, 0x65, 0x72, 0x65, 0x71,
		0x2d, 0x31, 0x04, 0x67, 0x75, 0x6e, 0x69, 0x74, 0x2d, 0x30,
		0x31, 0x14, 0x19, 0x01, 0x94, 0x15, 0x67, 0x6d, 0x69, 0x73,
		0x73, 0x69, 0x6e, 0x67 };
	uint8_t payload[96];
	size_t encoded_len;

	zassert_equal(neuro_protocol_encode_error_reply_cbor(
			      payload, sizeof(payload), &reply, &encoded_len),
		0, "error reply should encode as CBOR");
	zassert_equal(encoded_len, sizeof(expected),
		"error reply CBOR length changed");
	zassert_mem_equal(payload, expected, sizeof(expected),
		"error reply CBOR golden vector changed");
}

ZTEST(neuro_protocol_codec, test_encode_basic_replies_cbor_contract)
{
	const struct neuro_protocol_lease_reply lease_reply = {
		.request_id = "req-2",
		.node_id = "unit-01",
		.lease_id = "lease-1",
		.resource = "app/neuro_unit_app/control",
		.expires_at_ms = 12345,
		.include_expires_at_ms = true,
	};
	const struct neuro_protocol_query_device_reply device_reply = {
		.request_id = "req-4",
		.node_id = "unit-01",
		.board = "dnesp32s3b",
		.zenoh_mode = "client",
		.session_ready = true,
		.network_state = "NETWORK_READY",
		.ipv4 = "192.168.2.69",
	};
	struct neuro_protocol_cbor_envelope envelope;
	uint8_t payload[256];
	size_t encoded_len;

	zassert_equal(neuro_protocol_encode_lease_reply_cbor(payload,
			      sizeof(payload), &lease_reply, &encoded_len),
		0, "lease reply should encode as CBOR");
	zassert_equal(neuro_protocol_cbor_decode_envelope_header(
			      payload, encoded_len, &envelope),
		0, "lease reply envelope should decode");
	zassert_equal(envelope.message_kind,
		NEURO_PROTOCOL_CBOR_MSG_LEASE_REPLY,
		"lease reply kind should decode");

	zassert_equal(neuro_protocol_encode_query_device_reply_cbor(payload,
			      sizeof(payload), &device_reply, &encoded_len),
		0, "query device reply should encode as CBOR");
	zassert_equal(neuro_protocol_cbor_decode_envelope_header(
			      payload, encoded_len, &envelope),
		0, "query device reply envelope should decode");
	zassert_equal(envelope.message_kind,
		NEURO_PROTOCOL_CBOR_MSG_QUERY_DEVICE_REPLY,
		"query device reply kind should decode");
}

ZTEST(neuro_protocol_codec, test_encode_callback_payloads_cbor_contract)
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
	struct neuro_protocol_cbor_envelope envelope;
	uint8_t payload[256];
	size_t encoded_len;

	zassert_equal(neuro_protocol_encode_callback_event_cbor(
			      payload, sizeof(payload), &event, &encoded_len),
		0, "callback event should encode as CBOR");
	zassert_equal(neuro_protocol_cbor_decode_envelope_header(
			      payload, encoded_len, &envelope),
		0, "callback event envelope should decode");
	zassert_equal(envelope.message_kind,
		NEURO_PROTOCOL_CBOR_MSG_CALLBACK_EVENT,
		"callback event kind should decode");

	zassert_equal(neuro_protocol_encode_app_command_reply_cbor(
			      payload, sizeof(payload), &reply, &encoded_len),
		0, "app command reply should encode as CBOR");
	zassert_equal(neuro_protocol_cbor_decode_envelope_header(
			      payload, encoded_len, &envelope),
		0, "app command reply envelope should decode");
	zassert_equal(envelope.message_kind,
		NEURO_PROTOCOL_CBOR_MSG_APP_COMMAND_REPLY,
		"app command reply kind should decode");
}

ZTEST(neuro_protocol_codec, test_encode_lease_event_cbor_contract)
{
	const struct neuro_protocol_lease_event_cbor event = {
		.node_id = "unit-01",
		.action = "acquired",
		.lease_id = "lease-1",
		.resource = "app/neuro_unit_app/control",
		.source_core = "core-cli",
		.source_agent = "rational",
		.priority = 50,
	};
	struct neuro_protocol_cbor_envelope envelope;
	uint8_t payload[256];
	size_t encoded_len;

	zassert_equal(neuro_protocol_encode_lease_event_cbor(
			      payload, sizeof(payload), &event, &encoded_len),
		0, "lease event should encode as CBOR");
	zassert_equal(neuro_protocol_cbor_decode_envelope_header(
			      payload, encoded_len, &envelope),
		0, "lease event envelope should decode");
	zassert_equal(envelope.message_kind,
		NEURO_PROTOCOL_CBOR_MSG_LEASE_EVENT,
		"lease event kind should decode");
}

ZTEST(neuro_protocol_codec, test_decode_request_metadata_cbor_contract)
{
	const uint8_t payload[] = { 0xab, 0x00, 0x02, 0x01, 0x01, 0x03, 0x65,
		0x72, 0x65, 0x71, 0x2d, 0x31, 0x05, 0x64, 0x63, 0x6f, 0x72,
		0x65, 0x06, 0x65, 0x61, 0x67, 0x65, 0x6e, 0x74, 0x07, 0x67,
		0x75, 0x6e, 0x69, 0x74, 0x2d, 0x30, 0x31, 0x08, 0x19, 0x03,
		0xe8, 0x09, 0x07, 0x0a, 0x66, 0x69, 0x64, 0x65, 0x6d, 0x2d,
		0x31, 0x0b, 0x67, 0x6c, 0x65, 0x61, 0x73, 0x65, 0x2d, 0x31,
		0x0c, 0xf5 };
	struct neuro_protocol_request_metadata metadata;
	enum neuro_protocol_cbor_message_kind message_kind;

	zassert_equal(neuro_protocol_decode_request_metadata_cbor(payload,
			      sizeof(payload), &metadata, &message_kind),
		0, "request metadata should decode as CBOR");
	zassert_equal(message_kind, NEURO_PROTOCOL_CBOR_MSG_QUERY_REQUEST,
		"message kind should decode");
	zassert_equal(strcmp(metadata.request_id, "req-1"), 0,
		"request_id should decode");
	zassert_equal(strcmp(metadata.source_core, "core"), 0,
		"source_core should decode");
	zassert_equal(strcmp(metadata.source_agent, "agent"), 0,
		"source_agent should decode");
	zassert_equal(strcmp(metadata.target_node, "unit-01"), 0,
		"target_node should decode");
	zassert_equal(metadata.timeout_ms, 1000U, "timeout_ms should decode");
	zassert_equal(metadata.priority, 7, "priority should decode");
	zassert_equal(strcmp(metadata.idempotency_key, "idem-1"), 0,
		"idempotency_key should decode");
	zassert_equal(strcmp(metadata.lease_id, "lease-1"), 0,
		"lease_id should decode");
	zassert_true(metadata.forwarded, "forwarded should decode");
}

ZTEST(neuro_protocol_codec,
	test_decode_request_metadata_cbor_rejects_bad_inputs)
{
	const uint8_t bad_version[] = { 0xa2, 0x00, 0x01, 0x01, 0x01 };
	const uint8_t reply_kind[] = { 0xa2, 0x00, 0x02, 0x01, 0x14 };
	const uint8_t truncated[] = { 0xa2, 0x00, 0x02, 0x01 };
	struct neuro_protocol_request_metadata metadata;
	enum neuro_protocol_cbor_message_kind message_kind;

	zassert_equal(neuro_protocol_decode_request_metadata_cbor(NULL,
			      sizeof(bad_version), &metadata, &message_kind),
		-EINVAL, "null metadata payload should fail");
	zassert_equal(neuro_protocol_decode_request_metadata_cbor(bad_version,
			      sizeof(bad_version), &metadata, &message_kind),
		-ENOTSUP, "bad schema version should fail");
	zassert_equal(neuro_protocol_decode_request_metadata_cbor(reply_kind,
			      sizeof(reply_kind), &metadata, &message_kind),
		-ENOTSUP,
		"reply message kind should fail for request metadata");
	zassert_equal(neuro_protocol_decode_request_metadata_cbor(truncated,
			      sizeof(truncated), &metadata, &message_kind),
		-EBADMSG, "truncated metadata should fail");
}

ZTEST(neuro_protocol_codec, test_encode_query_aggregates_cbor_contract)
{
	const struct neuro_protocol_query_app_cbor app = {
		.app_id = "neuro_unit_app",
		.runtime_state = "RUNNING",
		.path = "/SD:/apps/neuro_unit_app.llext",
		.priority = 3U,
		.manifest_present = true,
		.update_state = "NONE",
		.artifact_state = "STAGED",
		.stable_ref = "",
		.last_error = "",
		.rollback_reason = "",
	};
	const struct neuro_protocol_query_apps_reply_cbor apps_reply = {
		.request_id = "req-5",
		.node_id = "unit-01",
		.app_count = 1U,
		.running_count = 1U,
		.suspended_count = 0U,
		.apps = &app,
		.app_count_listed = 1U,
	};
	const struct neuro_protocol_query_lease_cbor lease = {
		.lease_id = "l-1",
		.resource = "update/app/a/activate",
		.source_core = "core",
		.source_agent = "agent",
		.priority = 4,
		.expires_at_ms = 111,
	};
	const struct neuro_protocol_query_leases_reply_cbor leases_reply = {
		.request_id = "req-6",
		.node_id = "unit-01",
		.leases = &lease,
		.lease_count = 1U,
	};
	struct neuro_protocol_cbor_envelope envelope;
	uint8_t payload[512];
	size_t encoded_len;

	zassert_equal(neuro_protocol_encode_query_apps_reply_cbor(payload,
			      sizeof(payload), &apps_reply, &encoded_len),
		0, "query apps reply should encode as CBOR");
	zassert_equal(neuro_protocol_cbor_decode_envelope_header(
			      payload, encoded_len, &envelope),
		0, "query apps envelope should decode");
	zassert_equal(envelope.message_kind,
		NEURO_PROTOCOL_CBOR_MSG_QUERY_APPS_REPLY,
		"query apps message kind should decode");

	zassert_equal(neuro_protocol_encode_query_leases_reply_cbor(payload,
			      sizeof(payload), &leases_reply, &encoded_len),
		0, "query leases reply should encode as CBOR");
	zassert_equal(neuro_protocol_cbor_decode_envelope_header(
			      payload, encoded_len, &envelope),
		0, "query leases envelope should decode");
	zassert_equal(envelope.message_kind,
		NEURO_PROTOCOL_CBOR_MSG_QUERY_LEASES_REPLY,
		"query leases message kind should decode");
}

ZTEST(neuro_protocol_codec, test_encode_update_replies_cbor_contract)
{
	const struct neuro_protocol_update_reply_cbor reply = {
		.request_id = "req-7",
		.node_id = "unit-01",
		.app_id = "neuro_unit_app",
		.path = "/SD:/apps/neuro_unit_app.llext",
		.transport = "zenoh",
		.size = 4096U,
		.reason = "manual",
	};
	struct neuro_protocol_cbor_envelope envelope;
	uint8_t payload[256];
	size_t encoded_len;

	zassert_equal(neuro_protocol_encode_update_prepare_reply_cbor(
			      payload, sizeof(payload), &reply, &encoded_len),
		0, "update prepare reply should encode as CBOR");
	zassert_equal(neuro_protocol_cbor_decode_envelope_header(
			      payload, encoded_len, &envelope),
		0, "update prepare envelope should decode");
	zassert_equal(envelope.message_kind,
		NEURO_PROTOCOL_CBOR_MSG_UPDATE_PREPARE_REPLY,
		"update prepare kind should decode");

	zassert_equal(neuro_protocol_encode_update_verify_reply_cbor(
			      payload, sizeof(payload), &reply, &encoded_len),
		0, "update verify reply should encode as CBOR");
	zassert_equal(neuro_protocol_cbor_decode_envelope_header(
			      payload, encoded_len, &envelope),
		0, "update verify envelope should decode");
	zassert_equal(envelope.message_kind,
		NEURO_PROTOCOL_CBOR_MSG_UPDATE_VERIFY_REPLY,
		"update verify kind should decode");

	zassert_equal(neuro_protocol_encode_update_activate_reply_cbor(
			      payload, sizeof(payload), &reply, &encoded_len),
		0, "update activate reply should encode as CBOR");
	zassert_equal(neuro_protocol_cbor_decode_envelope_header(
			      payload, encoded_len, &envelope),
		0, "update activate envelope should decode");
	zassert_equal(envelope.message_kind,
		NEURO_PROTOCOL_CBOR_MSG_UPDATE_ACTIVATE_REPLY,
		"update activate kind should decode");

	zassert_equal(neuro_protocol_encode_update_rollback_reply_cbor(
			      payload, sizeof(payload), &reply, &encoded_len),
		0, "update rollback reply should encode as CBOR");
	zassert_equal(neuro_protocol_cbor_decode_envelope_header(
			      payload, encoded_len, &envelope),
		0, "update rollback envelope should decode");
	zassert_equal(envelope.message_kind,
		NEURO_PROTOCOL_CBOR_MSG_UPDATE_ROLLBACK_REPLY,
		"update rollback kind should decode");
}

ZTEST(neuro_protocol_codec, test_encode_framework_events_cbor_contract)
{
	const struct neuro_protocol_update_event_cbor update_event = {
		.node_id = "unit-01",
		.app_id = "neuro_unit_app",
		.stage = "activate",
		.status = "ok",
		.detail = "app running",
	};
	const struct neuro_protocol_state_event_cbor state_event = {
		.node_id = "unit-01",
		.app_count = 2U,
		.running_count = 1U,
		.network_state = "NETWORK_READY",
	};
	struct neuro_protocol_cbor_envelope envelope;
	uint8_t payload[256];
	size_t encoded_len;

	zassert_equal(neuro_protocol_encode_update_event_cbor(payload,
			      sizeof(payload), &update_event, &encoded_len),
		0, "update event should encode as CBOR");
	zassert_equal(neuro_protocol_cbor_decode_envelope_header(
			      payload, encoded_len, &envelope),
		0, "update event envelope should decode");
	zassert_equal(envelope.message_kind,
		NEURO_PROTOCOL_CBOR_MSG_UPDATE_EVENT,
		"update event kind should decode");

	zassert_equal(neuro_protocol_encode_state_event_cbor(payload,
			      sizeof(payload), &state_event, &encoded_len),
		0, "state event should encode as CBOR");
	zassert_equal(neuro_protocol_cbor_decode_envelope_header(
			      payload, encoded_len, &envelope),
		0, "state event envelope should decode");
	zassert_equal(envelope.message_kind,
		NEURO_PROTOCOL_CBOR_MSG_STATE_EVENT,
		"state event kind should decode");
}

ZTEST(neuro_protocol_codec, test_decode_callback_config_cbor_contract)
{
	const uint8_t payload[] = { 0xa5, 0x00, 0x02, 0x01, 0x05, 0x18, 0x50,
		0xf4, 0x18, 0x51, 0x05, 0x18, 0x52, 0x64, 0x74, 0x69, 0x63,
		0x6b };
	struct neuro_protocol_callback_config config;

	zassert_equal(neuro_protocol_decode_callback_config_cbor(
			      payload, sizeof(payload), &config),
		0, "callback config should decode as CBOR");
	zassert_true(config.has_callback_enabled,
		"callback_enabled presence should decode");
	zassert_false(config.callback_enabled,
		"callback_enabled value should decode");
	zassert_true(config.has_trigger_every,
		"trigger_every presence should decode");
	zassert_equal(config.trigger_every, 5, "trigger_every should decode");
	zassert_true(
		config.has_event_name, "event_name presence should decode");
	zassert_equal(strcmp(config.event_name, "tick"), 0,
		"event_name should decode");
}

ZTEST(neuro_protocol_codec, test_decode_request_fields_cbor_contract)
{
	const uint8_t payload[] = { 0xa7, 0x00, 0x02, 0x01, 0x02, 0x18, 0x1e,
		0x6d, 0x61, 0x70, 0x70, 0x2f, 0x61, 0x2f, 0x63, 0x6f, 0x6e,
		0x74, 0x72, 0x6f, 0x6c, 0x18, 0x20, 0x19, 0xea, 0x60, 0x18,
		0x50, 0xf5, 0x18, 0x51, 0x03, 0x18, 0x52, 0x64, 0x74, 0x69,
		0x63, 0x6b };
	struct neuro_protocol_request_fields_cbor fields;

	zassert_equal(neuro_protocol_decode_request_fields_cbor(
			      payload, sizeof(payload), &fields),
		0, "request fields should decode as CBOR");
	zassert_equal(strcmp(fields.resource, "app/a/control"), 0,
		"resource should decode");
	zassert_equal(fields.ttl_ms, 60000U, "ttl_ms should decode");
	zassert_true(fields.has_callback_enabled,
		"callback_enabled presence should decode");
	zassert_true(fields.callback_enabled,
		"callback_enabled value should decode");
	zassert_true(fields.has_trigger_every,
		"trigger_every presence should decode");
	zassert_equal(fields.trigger_every, 3, "trigger_every should decode");
	zassert_true(
		fields.has_event_name, "event_name presence should decode");
	zassert_equal(strcmp(fields.event_name, "tick"), 0,
		"event_name should decode");
}

ZTEST(neuro_protocol_codec, test_decode_update_prepare_request_cbor_contract)
{
	const uint8_t payload[] = { 0xa6, 0x00, 0x02, 0x01, 0x06, 0x18, 0x38,
		0x65, 0x7a, 0x65, 0x6e, 0x6f, 0x68, 0x18, 0x39, 0x62, 0x6b,
		0x31, 0x18, 0x3a, 0x19, 0x10, 0x00, 0x18, 0x3b, 0x19, 0x02,
		0x00 };
	struct neuro_protocol_update_prepare_request_cbor request;

	zassert_equal(neuro_protocol_decode_update_prepare_request_cbor(
			      payload, sizeof(payload), &request),
		0, "update prepare request should decode as CBOR");
	zassert_equal(strcmp(request.transport, "zenoh"), 0,
		"transport should decode");
	zassert_equal(strcmp(request.artifact_key, "k1"), 0,
		"artifact key should decode");
	zassert_equal(request.size, 4096U, "size should decode");
	zassert_equal(request.chunk_size, 512U, "chunk size should decode");
}

ZTEST_SUITE(neuro_protocol_codec, NULL, NULL, NULL, NULL, NULL);
