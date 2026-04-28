#include <zephyr/ztest.h>

#include <string.h>

#include "app_runtime_elf_staging.h"
#include "neuro_unit_port.h"

#define STAGING_TEST_STATIC_ELF_BUFFER_SIZE 64

static void release_if_allocated(
	uint8_t **buf, enum app_runtime_elf_buffer_source *source)
{
	if (*buf != NULL) {
		app_runtime_elf_staging_release(*buf, *source);
		*buf = NULL;
	}
}

static void test_reset(void *fixture)
{
	ARG_UNUSED(fixture);
	(void)neuro_unit_port_set_memory_ops(NULL);
}

ZTEST(app_runtime_elf_staging, test_null_source_rejects_allocation)
{
	zassert_is_null(app_runtime_elf_staging_alloc(16U, NULL),
		"allocation without source output should fail");
}

ZTEST(app_runtime_elf_staging, test_static_buffer_exact_fit_and_release)
{
	enum app_runtime_elf_buffer_source source;
	uint8_t *buf;

	buf = app_runtime_elf_staging_alloc(
		STAGING_TEST_STATIC_ELF_BUFFER_SIZE, &source);
	zassert_not_null(buf, "static-sized allocation should succeed");
	zassert_equal(source, APP_RUNTIME_ELF_BUFFER_STATIC,
		"exact-fit allocation should use static staging buffer");
	zassert_true(app_runtime_elf_staging_static_in_use(),
		"static staging buffer should be marked in use");
	zassert_true(strcmp(app_runtime_elf_buffer_source_str(source),
			     "static") == 0,
		"static source string changed");

	app_runtime_elf_staging_release(buf, source);
	zassert_false(app_runtime_elf_staging_static_in_use(),
		"static staging buffer should be released");
}

ZTEST(app_runtime_elf_staging,
	test_second_static_sized_allocation_falls_back_to_malloc_when_busy)
{
	enum app_runtime_elf_buffer_source first_source;
	enum app_runtime_elf_buffer_source second_source;
	uint8_t *first = NULL;
	uint8_t *second = NULL;

	first = app_runtime_elf_staging_alloc(32U, &first_source);
	zassert_not_null(first, "first allocation should succeed");
	zassert_equal(first_source, APP_RUNTIME_ELF_BUFFER_STATIC,
		"first allocation should use static staging buffer");

	second = app_runtime_elf_staging_alloc(32U, &second_source);
	zassert_not_null(second, "fallback allocation should succeed");
	zassert_equal(second_source, APP_RUNTIME_ELF_BUFFER_MALLOC,
		"busy static staging buffer should fall back to malloc");
	zassert_true(first != second,
		"fallback allocation must not alias the static staging buffer");

	release_if_allocated(&second, &second_source);
	release_if_allocated(&first, &first_source);
	zassert_false(app_runtime_elf_staging_static_in_use(),
		"static staging buffer should be free after releases");
}

ZTEST(app_runtime_elf_staging, test_oversized_allocation_uses_malloc_fallback)
{
	enum app_runtime_elf_buffer_source source;
	uint8_t *buf;

	buf = app_runtime_elf_staging_alloc(
		STAGING_TEST_STATIC_ELF_BUFFER_SIZE + 1U, &source);
	zassert_not_null(
		buf, "oversized allocation should fall back to malloc");
	zassert_equal(source, APP_RUNTIME_ELF_BUFFER_MALLOC,
		"oversized allocation should not reserve static staging buffer");
	zassert_false(app_runtime_elf_staging_static_in_use(),
		"oversized malloc fallback should not mark static buffer busy");
	zassert_true(strcmp(app_runtime_elf_buffer_source_str(source),
			     "malloc") == 0,
		"malloc source string changed");

	app_runtime_elf_staging_release(buf, source);
}

ZTEST(app_runtime_elf_staging, test_external_source_string_is_generic)
{
	zassert_true(strcmp(app_runtime_elf_buffer_source_str(
				    APP_RUNTIME_ELF_BUFFER_EXTERNAL),
			     "external") == 0,
		"external staging source string changed");
	zassert_true(strcmp(app_runtime_elf_buffer_source_str(
				    APP_RUNTIME_ELF_BUFFER_PSRAM),
			     "external") == 0,
		"legacy PSRAM source alias should use generic external text");
}

ZTEST(app_runtime_elf_staging,
	test_provider_string_reports_active_memory_provider)
{
	static const struct neuro_unit_port_memory_ops ops = {
		.provider = "unit-external",
	};

	zassert_true(
		strcmp(app_runtime_elf_staging_provider_str(), "none") == 0,
		"empty memory ops should report provider=none");
	zassert_equal(neuro_unit_port_set_memory_ops(&ops), 0,
		"memory ops install should succeed");
	zassert_true(strcmp(app_runtime_elf_staging_provider_str(),
			     "unit-external") == 0,
		"active memory provider label should be visible to staging diagnostics");
}

ZTEST_SUITE(app_runtime_elf_staging, NULL, NULL, test_reset, NULL, NULL);
