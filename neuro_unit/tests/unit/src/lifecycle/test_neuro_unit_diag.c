#include <zephyr/ztest.h>

#include <string.h>

#include "neuro_unit_diag.h"

ZTEST(neuro_unit_diag, test_format_context_uses_safe_defaults)
{
	char context[NEURO_UNIT_DIAG_CONTEXT_MAX_LEN];
	int ret;

	ret = neuro_unit_diag_format_context(context, sizeof(context), NULL);
	zassert_equal(ret, 0, "null context should format safely");
	zassert_true(
		strcmp(context,
			"request_id=- app_id=- route=- stage=- ret=0") == 0,
		"null context should use stable default tokens");
}

ZTEST(neuro_unit_diag, test_update_transaction_accepts_null_fields)
{
	neuro_unit_diag_update_transaction(NULL, NULL, NULL, NULL, 0, NULL);
	neuro_unit_diag_update_transaction(
		"demo_app", "activate", "req-1", "fail", -5, NULL);
}

ZTEST_SUITE(neuro_unit_diag, NULL, NULL, NULL, NULL, NULL);
