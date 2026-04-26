#include <zephyr/ztest.h>

#include <errno.h>
#include <string.h>

#include "neuro_protocol.h"

ZTEST(neuro_protocol, test_version_and_wire_encoding_contract)
{
	zassert_equal(NEURO_PROTOCOL_VERSION_MAJOR, 2U,
		"protocol-v2 major version changed");
	zassert_equal(NEURO_PROTOCOL_VERSION_MINOR, 0U,
		"protocol-v2 minor version changed");
	zassert_true(strcmp(neuro_protocol_wire_encoding_to_str(
				    NEURO_PROTOCOL_WIRE_JSON_V2),
			     "json-v2") == 0,
		"JSON-v2 encoding name changed");
	zassert_true(strcmp(neuro_protocol_wire_encoding_to_str(
				    NEURO_PROTOCOL_WIRE_CBOR_V2),
			     "cbor-v2") == 0,
		"CBOR-v2 encoding name changed");
}

ZTEST(neuro_protocol, test_status_and_error_contract)
{
	zassert_true(
		strcmp(neuro_protocol_status_to_str(NEURO_PROTOCOL_STATUS_OK),
			"ok") == 0,
		"ok status string changed");
	zassert_true(strcmp(neuro_protocol_status_to_str(
				    NEURO_PROTOCOL_STATUS_ERROR),
			     "error") == 0,
		"error status string changed");
	zassert_equal(NEURO_PROTOCOL_ERROR_BAD_REQUEST, 400,
		"bad request status code changed");
	zassert_equal(NEURO_PROTOCOL_ERROR_CONFLICT, 409,
		"conflict status code changed");
	zassert_equal(NEURO_PROTOCOL_ERROR_UNAVAILABLE, 503,
		"unavailable status code changed");
}

ZTEST(neuro_protocol, test_route_builders_contract)
{
	char route[NEURO_PROTOCOL_ROUTE_LEN];

	zassert_equal(neuro_protocol_build_query_route(route, sizeof(route),
			      "unit-01", NEURO_PROTOCOL_QUERY_DEVICE),
		0, "query route build should succeed");
	zassert_true(strcmp(route, "neuro/unit-01/query/device") == 0,
		"query route contract changed");

	zassert_equal(neuro_protocol_build_lease_route(route, sizeof(route),
			      "unit-01", NEURO_PROTOCOL_LEASE_ACQUIRE),
		0, "lease route build should succeed");
	zassert_true(strcmp(route, "neuro/unit-01/cmd/lease/acquire") == 0,
		"lease route contract changed");

	zassert_equal(
		neuro_protocol_build_app_command_route(route, sizeof(route),
			"unit-01", "neuro_unit_app", "invoke"),
		0, "app command route build should succeed");
	zassert_true(
		strcmp(route, "neuro/unit-01/cmd/app/neuro_unit_app/invoke") ==
			0,
		"app command route contract changed");

	zassert_equal(neuro_protocol_build_update_route(route, sizeof(route),
			      "unit-01", "neuro_unit_app",
			      NEURO_PROTOCOL_UPDATE_ACTIVATE),
		0, "update route build should succeed");
	zassert_true(
		strcmp(route,
			"neuro/unit-01/update/app/neuro_unit_app/activate") ==
			0,
		"update route contract changed");
}

ZTEST(neuro_protocol, test_event_route_builders_contract)
{
	char route[NEURO_PROTOCOL_ROUTE_LEN];

	zassert_equal(neuro_protocol_build_event_route(route, sizeof(route),
			      "unit-01", "lease/acquired"),
		0, "framework event route should build");
	zassert_true(strcmp(route, "neuro/unit-01/event/lease/acquired") == 0,
		"framework event route contract changed");

	zassert_equal(neuro_protocol_build_app_event_route(route, sizeof(route),
			      "unit-01", "neuro_unit_app", "callback"),
		0, "app event route should build");
	zassert_true(
		strcmp(route,
			"neuro/unit-01/event/app/neuro_unit_app/callback") == 0,
		"app event route contract changed");
}

ZTEST(neuro_protocol, test_route_builders_reject_bad_tokens)
{
	char route[NEURO_PROTOCOL_ROUTE_LEN];

	zassert_equal(neuro_protocol_build_query_route(route, sizeof(route),
			      "bad/node", NEURO_PROTOCOL_QUERY_DEVICE),
		-EINVAL, "node tokens must reject slashes");
	zassert_equal(neuro_protocol_build_app_command_route(route,
			      sizeof(route), "unit-01", "bad/app", "invoke"),
		-EINVAL, "app id tokens must reject slashes");
	zassert_equal(neuro_protocol_build_app_event_route(route, 8U, "unit-01",
			      "neuro_unit_app", "callback"),
		-ENAMETOOLONG, "small route buffers must fail explicitly");
}

ZTEST_SUITE(neuro_protocol, NULL, NULL, NULL, NULL, NULL);