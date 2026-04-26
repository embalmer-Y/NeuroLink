#include <zephyr/ztest.h>

#include <string.h>

#include "neuro_request_envelope.h"

ZTEST(neuro_request_envelope, test_parse_extracts_all_supported_fields)
{
	struct neuro_request_metadata metadata;
	const char *json =
		"{\"request_id\":\"req-1\",\"source_core\":\"ai-core\",\"source_agent\":\"scheduler\",\"target_node\":\"unit-01\",\"lease_id\":\"lease-7\",\"idempotency_key\":\"idem-9\",\"timeout_ms\":12000,\"priority\":88,\"forwarded\":true}";

	zassert_true(neuro_request_metadata_parse(json, &metadata),
		"metadata parse must succeed");
	zassert_equal(strcmp(metadata.request_id, "req-1"), 0,
		"request_id must be parsed");
	zassert_equal(strcmp(metadata.source_core, "ai-core"), 0,
		"source_core must be parsed");
	zassert_equal(strcmp(metadata.source_agent, "scheduler"), 0,
		"source_agent must be parsed");
	zassert_equal(strcmp(metadata.target_node, "unit-01"), 0,
		"target_node must be parsed");
	zassert_equal(strcmp(metadata.lease_id, "lease-7"), 0,
		"lease_id must be parsed");
	zassert_equal(strcmp(metadata.idempotency_key, "idem-9"), 0,
		"idempotency_key must be parsed");
	zassert_equal(metadata.timeout_ms, 12000U, "timeout_ms must be parsed");
	zassert_equal(metadata.priority, 88, "priority must be parsed");
	zassert_true(metadata.forwarded, "forwarded flag must be parsed");
}

ZTEST(neuro_request_envelope, test_parse_with_null_json_or_metadata_fails)
{
	struct neuro_request_metadata metadata;

	zassert_false(neuro_request_metadata_parse(NULL, &metadata),
		"parse must fail when json is null");
	zassert_false(neuro_request_metadata_parse("{}", NULL),
		"parse must fail when metadata pointer is null");
}

ZTEST(neuro_request_envelope, test_parse_defaults_priority_and_forwarded)
{
	struct neuro_request_metadata metadata;

	zassert_true(neuro_request_metadata_parse(
			     "{\"request_id\":\"req-d\"}", &metadata),
		"parse must succeed with partial fields");
	zassert_equal(metadata.priority, -1,
		"priority must keep default when field is absent");
	zassert_false(metadata.forwarded,
		"forwarded must default to false when field is absent");
}

ZTEST(neuro_request_envelope, test_validate_accepts_common_fields)
{
	struct neuro_request_metadata metadata;
	char error[96];

	neuro_request_metadata_init(&metadata);
	snprintk(metadata.request_id, sizeof(metadata.request_id), "%s",
		"req-2");
	snprintk(metadata.source_core, sizeof(metadata.source_core), "%s",
		"core-a");
	snprintk(metadata.source_agent, sizeof(metadata.source_agent), "%s",
		"agent-a");
	snprintk(metadata.target_node, sizeof(metadata.target_node), "%s",
		"unit-01");
	metadata.timeout_ms = 8000U;

	zassert_true(neuro_request_metadata_validate(&metadata,
			     NEURO_REQ_META_REQUIRE_COMMON, "unit-01", error,
			     sizeof(error)),
		"common metadata must validate");
	zassert_true(error[0] == '\0', "error buffer must be empty on success");
}

ZTEST(neuro_request_envelope, test_validate_rejects_missing_common_field)
{
	struct neuro_request_metadata metadata;
	char error[96];

	neuro_request_metadata_init(&metadata);
	snprintk(metadata.source_core, sizeof(metadata.source_core), "%s",
		"core-a");
	snprintk(metadata.source_agent, sizeof(metadata.source_agent), "%s",
		"agent-a");
	snprintk(metadata.target_node, sizeof(metadata.target_node), "%s",
		"unit-01");
	metadata.timeout_ms = 8000U;

	zassert_false(neuro_request_metadata_validate(&metadata,
			      NEURO_REQ_META_REQUIRE_COMMON, "unit-01", error,
			      sizeof(error)),
		"missing request_id must fail validation");
	zassert_equal(strcmp(error, "request_id is required"), 0,
		"validation must identify missing field");
}

ZTEST(neuro_request_envelope, test_validate_rejects_target_node_mismatch)
{
	struct neuro_request_metadata metadata;
	char error[96];

	neuro_request_metadata_init(&metadata);
	snprintk(metadata.request_id, sizeof(metadata.request_id), "%s",
		"req-3");
	snprintk(metadata.source_core, sizeof(metadata.source_core), "%s",
		"core-a");
	snprintk(metadata.source_agent, sizeof(metadata.source_agent), "%s",
		"agent-a");
	snprintk(metadata.target_node, sizeof(metadata.target_node), "%s",
		"unit-99");
	metadata.timeout_ms = 5000U;

	zassert_false(neuro_request_metadata_validate(&metadata,
			      NEURO_REQ_META_REQUIRE_COMMON, "unit-01", error,
			      sizeof(error)),
		"target mismatch must fail validation");
	zassert_equal(strcmp(error, "target_node mismatch"), 0,
		"validation must report target mismatch");
}

ZTEST(neuro_request_envelope, test_validate_accepts_when_expected_target_empty)
{
	struct neuro_request_metadata metadata;
	char error[96];

	neuro_request_metadata_init(&metadata);
	snprintk(metadata.request_id, sizeof(metadata.request_id), "%s",
		"req-3b");
	snprintk(metadata.source_core, sizeof(metadata.source_core), "%s",
		"core-a");
	snprintk(metadata.source_agent, sizeof(metadata.source_agent), "%s",
		"agent-a");
	snprintk(metadata.target_node, sizeof(metadata.target_node), "%s",
		"unit-99");
	metadata.timeout_ms = 5000U;

	zassert_true(neuro_request_metadata_validate(&metadata,
			     NEURO_REQ_META_REQUIRE_COMMON, "", error,
			     sizeof(error)),
		"empty expected target must skip mismatch check");
}

ZTEST(neuro_request_envelope,
	test_validate_write_requires_priority_and_idempotency)
{
	struct neuro_request_metadata metadata;
	char error[96];
	uint32_t write_fields = NEURO_REQ_META_REQUIRE_COMMON |
				NEURO_REQ_META_REQUIRE_PRIORITY |
				NEURO_REQ_META_REQUIRE_IDEMPOTENCY_KEY;

	neuro_request_metadata_init(&metadata);
	snprintk(metadata.request_id, sizeof(metadata.request_id), "%s",
		"req-4");
	snprintk(metadata.source_core, sizeof(metadata.source_core), "%s",
		"core-a");
	snprintk(metadata.source_agent, sizeof(metadata.source_agent), "%s",
		"agent-a");
	snprintk(metadata.target_node, sizeof(metadata.target_node), "%s",
		"unit-01");
	metadata.timeout_ms = 3000U;

	zassert_false(neuro_request_metadata_validate(&metadata, write_fields,
			      "unit-01", error, sizeof(error)),
		"write request without priority must fail");
	zassert_equal(strcmp(error, "priority is required"), 0,
		"missing priority must be reported first");

	metadata.priority = 42;
	zassert_false(neuro_request_metadata_validate(&metadata, write_fields,
			      "unit-01", error, sizeof(error)),
		"write request without idempotency key must fail");
	zassert_equal(strcmp(error, "idempotency_key is required"), 0,
		"missing idempotency_key must be reported");

	snprintk(metadata.idempotency_key, sizeof(metadata.idempotency_key),
		"%s", "idem-42");
	zassert_true(neuro_request_metadata_validate(&metadata, write_fields,
			     "unit-01", error, sizeof(error)),
		"write request with complete metadata must pass");
}

ZTEST(neuro_request_envelope, test_validate_protected_write_requires_lease_id)
{
	struct neuro_request_metadata metadata;
	char error[96];
	uint32_t protected_write_fields =
		NEURO_REQ_META_REQUIRE_COMMON |
		NEURO_REQ_META_REQUIRE_PRIORITY |
		NEURO_REQ_META_REQUIRE_IDEMPOTENCY_KEY |
		NEURO_REQ_META_REQUIRE_LEASE_ID;

	neuro_request_metadata_init(&metadata);
	snprintk(metadata.request_id, sizeof(metadata.request_id), "%s",
		"req-5");
	snprintk(metadata.source_core, sizeof(metadata.source_core), "%s",
		"core-a");
	snprintk(metadata.source_agent, sizeof(metadata.source_agent), "%s",
		"agent-a");
	snprintk(metadata.target_node, sizeof(metadata.target_node), "%s",
		"unit-01");
	snprintk(metadata.idempotency_key, sizeof(metadata.idempotency_key),
		"%s", "idem-55");
	metadata.timeout_ms = 4500U;
	metadata.priority = 77;

	zassert_false(neuro_request_metadata_validate(&metadata,
			      protected_write_fields, "unit-01", error,
			      sizeof(error)),
		"protected write without lease_id must fail");
	zassert_equal(strcmp(error, "lease_id is required"), 0,
		"missing lease_id must be reported");

	snprintk(
		metadata.lease_id, sizeof(metadata.lease_id), "%s", "lease-99");
	zassert_true(neuro_request_metadata_validate(&metadata,
			     protected_write_fields, "unit-01", error,
			     sizeof(error)),
		"protected write with lease_id must pass");
}

ZTEST(neuro_request_envelope, test_validate_null_metadata_reports_error)
{
	char error[96];

	zassert_false(neuro_request_metadata_validate(NULL,
			      NEURO_REQ_META_REQUIRE_COMMON, "unit-01", error,
			      sizeof(error)),
		"null metadata must fail validation");
	zassert_equal(strcmp(error, "request metadata missing"), 0,
		"null metadata failure must report clear reason");
}

ZTEST(neuro_request_envelope,
	test_json_extract_helpers_return_defaults_on_missing_key)
{
	char out[8] = "x";

	zassert_false(neuro_json_extract_string(
			      "{\"k\":\"v\"}", "missing", out, sizeof(out)),
		"string extractor must report missing key");
	zassert_equal(neuro_json_extract_int("{\"k\":\"v\"}", "missing", 17),
		17, "int extractor must return default when key is absent");
	zassert_true(neuro_json_extract_bool("{\"k\":\"v\"}", "missing", true),
		"bool extractor must return default when key is absent");
}

ZTEST(neuro_request_envelope, test_callback_config_decode_reports_presence)
{
	struct neuro_unit_app_callback_config config;

	zassert_equal(
		neuro_unit_read_callback_config_json(
			"{\"callback_enabled\":true,\"trigger_every\":3,\"event_name\":\"notify\"}",
			&config),
		0, "callback config decode should succeed");
	zassert_true(config.has_callback_enabled,
		"callback_enabled presence should be reported");
	zassert_true(config.callback_enabled,
		"callback_enabled value should be decoded");
	zassert_true(config.has_trigger_every,
		"trigger_every presence should be reported");
	zassert_equal(config.trigger_every, 3,
		"trigger_every value should be decoded");
	zassert_true(config.has_event_name,
		"event_name presence should be reported");
	zassert_equal(strcmp(config.event_name, "notify"), 0,
		"event_name value should be decoded");

	zassert_equal(neuro_unit_read_callback_config_json("{}", &config), 0,
		"empty callback config should decode");
	zassert_false(config.has_callback_enabled,
		"missing callback_enabled should be explicit");
	zassert_false(config.has_trigger_every,
		"missing trigger_every should be explicit");
	zassert_false(
		config.has_event_name, "missing event_name should be explicit");
}

ZTEST_SUITE(neuro_request_envelope, NULL, NULL, NULL, NULL, NULL);
