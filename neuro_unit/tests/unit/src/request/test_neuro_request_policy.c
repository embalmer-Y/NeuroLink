#include <zephyr/ztest.h>

#include "neuro_request_envelope.h"
#include "neuro_request_policy.h"

ZTEST(neuro_request_policy, test_command_lease_acquire_requires_write_fields)
{
	zassert_equal(neuro_request_policy_required_fields_for_command(
			      "neuro/unit-01/cmd/lease/acquire"),
		(uint32_t)(NEURO_REQ_META_REQUIRE_COMMON |
			   NEURO_REQ_META_REQUIRE_PRIORITY |
			   NEURO_REQ_META_REQUIRE_IDEMPOTENCY_KEY),
		"lease acquire should require write fields");
}

ZTEST(neuro_request_policy, test_command_protected_paths_require_lease)
{
	uint32_t expected = (uint32_t)(NEURO_REQ_META_REQUIRE_COMMON |
				       NEURO_REQ_META_REQUIRE_PRIORITY |
				       NEURO_REQ_META_REQUIRE_IDEMPOTENCY_KEY |
				       NEURO_REQ_META_REQUIRE_LEASE_ID);

	zassert_equal(neuro_request_policy_required_fields_for_command(
			      "neuro/unit-01/cmd/lease/release"),
		expected,
		"lease release should require protected write fields");
	zassert_equal(neuro_request_policy_required_fields_for_command(
			      "neuro/unit-01/cmd/app/demo/start"),
		expected, "app command should require protected write fields");
}

ZTEST(neuro_request_policy, test_command_unknown_path_has_no_policy)
{
	zassert_equal(neuro_request_policy_required_fields_for_command(
			      "neuro/unit-01/cmd/unknown"),
		0U, "unknown command should have no mapped policy");
}

ZTEST(neuro_request_policy, test_query_standard_paths_require_common_fields)
{
	zassert_equal(neuro_request_policy_required_fields_for_query(
			      "neuro/unit-01/query/device"),
		(uint32_t)NEURO_REQ_META_REQUIRE_COMMON,
		"query/device should require common metadata");
	zassert_equal(neuro_request_policy_required_fields_for_query(
			      "neuro/unit-01/query/apps"),
		(uint32_t)NEURO_REQ_META_REQUIRE_COMMON,
		"query/apps should require common metadata");
	zassert_equal(neuro_request_policy_required_fields_for_query(
			      "neuro/unit-01/query/leases"),
		(uint32_t)NEURO_REQ_META_REQUIRE_COMMON,
		"query/leases should require common metadata");
}

ZTEST(neuro_request_policy, test_query_unknown_path_has_no_policy)
{
	zassert_equal(neuro_request_policy_required_fields_for_query(
			      "neuro/unit-01/query/unknown"),
		0U, "unknown query should have no mapped policy");
}

ZTEST(neuro_request_policy, test_update_prepare_requires_write_fields)
{
	zassert_equal(neuro_request_policy_required_fields_for_update_action(
			      "prepare"),
		(uint32_t)(NEURO_REQ_META_REQUIRE_COMMON |
			   NEURO_REQ_META_REQUIRE_PRIORITY |
			   NEURO_REQ_META_REQUIRE_IDEMPOTENCY_KEY),
		"prepare should require write fields");
}

ZTEST(neuro_request_policy, test_update_verify_requires_common_fields)
{
	zassert_equal(neuro_request_policy_required_fields_for_update_action(
			      "verify"),
		(uint32_t)NEURO_REQ_META_REQUIRE_COMMON,
		"verify should require common fields");
}

ZTEST(neuro_request_policy,
	test_update_activate_requires_protected_write_fields)
{
	zassert_equal(neuro_request_policy_required_fields_for_update_action(
			      "activate"),
		(uint32_t)(NEURO_REQ_META_REQUIRE_COMMON |
			   NEURO_REQ_META_REQUIRE_PRIORITY |
			   NEURO_REQ_META_REQUIRE_IDEMPOTENCY_KEY |
			   NEURO_REQ_META_REQUIRE_LEASE_ID),
		"activate should require protected write fields");
}

ZTEST(neuro_request_policy, test_update_unknown_action_has_no_policy)
{
	zassert_equal(neuro_request_policy_required_fields_for_update_action(
			      "rollback"),
		(uint32_t)(NEURO_REQ_META_REQUIRE_COMMON |
			   NEURO_REQ_META_REQUIRE_PRIORITY |
			   NEURO_REQ_META_REQUIRE_IDEMPOTENCY_KEY |
			   NEURO_REQ_META_REQUIRE_LEASE_ID),
		"rollback should require protected write fields");
	zassert_equal(neuro_request_policy_required_fields_for_update_action(
			      "recover"),
		(uint32_t)(NEURO_REQ_META_REQUIRE_COMMON |
			   NEURO_REQ_META_REQUIRE_PRIORITY |
			   NEURO_REQ_META_REQUIRE_IDEMPOTENCY_KEY |
			   NEURO_REQ_META_REQUIRE_LEASE_ID),
		"recover should require protected write fields");
	zassert_equal(neuro_request_policy_required_fields_for_update_action(
			      "unknown"),
		0U, "unknown action should have no mapped policy");
}

ZTEST(neuro_request_policy, test_null_input_has_no_policy)
{
	zassert_equal(neuro_request_policy_required_fields_for_command(NULL),
		0U, "null command key should be treated as unknown");
	zassert_equal(neuro_request_policy_required_fields_for_query(NULL), 0U,
		"null query key should be treated as unknown");
	zassert_equal(
		neuro_request_policy_required_fields_for_update_action(NULL),
		0U, "null update action should be treated as unknown");
}

ZTEST_SUITE(neuro_request_policy, NULL, NULL, NULL, NULL, NULL);
