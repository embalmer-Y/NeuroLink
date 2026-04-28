#include <zephyr/ztest.h>
#include <zephyr/sys/printk.h>

#include <errno.h>
#include <stdint.h>
#include <string.h>

#include "app_runtime_cmd.h"
#include "neuro_unit_port.h"
#include "neuro_unit_update_service.h"

static struct neuro_update_manager g_update_manager;
static struct neuro_artifact_store g_artifact_store;
static struct neuro_recovery_seed_store g_seed_store;
static struct neuro_unit_update_service g_service;

static int g_reply_error_calls;
static int g_reply_error_status;
static int g_query_reply_calls;
static int g_publish_update_event_calls;
static int g_publish_state_event_calls;
static int g_register_callback_calls;
static int g_log_calls;
static int g_download_artifact_calls;
static int g_download_artifact_return;
static int g_remove_calls;
static bool g_mock_runtime_app_is_loaded;
static bool g_require_lease_result;
static char g_last_error_message[64];
static char g_last_reply_json[256];
static char g_last_event_app_id[32];
static char g_last_event_stage[24];
static char g_last_event_status[16];
static char g_last_event_message[96];
static char g_last_log_action[24];
static char g_last_log_phase[24];
static char g_last_lease_id[32];
static char g_last_download_artifact_key[128];
static char g_last_download_path[128];
static uint8_t g_dummy_query_storage;
static struct neuro_unit_reply_context g_reply_ctx;
static size_t g_mock_artifact_size;
static size_t g_mock_download_artifact_size;

void app_runtime_test_reset(void);
void app_runtime_test_set_load_return(int ret);
void app_runtime_test_set_start_return(int ret);
int app_runtime_test_load_calls(void);
int app_runtime_test_start_calls(void);
int app_runtime_test_unload_calls(void);
const char *app_runtime_test_last_load_path(void);
const char *app_runtime_test_last_start_args(void);
const char *app_runtime_test_sequence(void);

struct mock_seed_file {
	bool exists;
	bool is_dir;
	uint8_t data[1024];
	size_t len;
};

static struct mock_seed_file g_seed_parent_dir;
static struct mock_seed_file g_seed_primary_file;
static struct mock_seed_file g_seed_tmp_file;
static struct mock_seed_file g_seed_legacy_file;
static const char *g_seed_open_path;

static struct mock_seed_file *mock_seed_file_for_path(const char *path)
{
	if (path == NULL) {
		return NULL;
	}

	if (strcmp(path, "/tmp") == 0) {
		return &g_seed_parent_dir;
	}

	if (strcmp(path, g_seed_store.path) == 0) {
		return &g_seed_primary_file;
	}

	if (strcmp(path, g_seed_store.tmp_path) == 0) {
		return &g_seed_tmp_file;
	}

	if (strcmp(path, g_seed_store.legacy_path) == 0) {
		return &g_seed_legacy_file;
	}

	return NULL;
}

static int mock_seed_fs_stat(const char *path, struct fs_dirent *entry)
{
	struct mock_seed_file *file = mock_seed_file_for_path(path);

	if (file == NULL || !file->exists) {
		return -ENOENT;
	}

	if (entry != NULL) {
		memset(entry, 0, sizeof(*entry));
		entry->type =
			file->is_dir ? FS_DIR_ENTRY_DIR : FS_DIR_ENTRY_FILE;
		entry->size = file->len;
	}

	return 0;
}

static int mock_seed_fs_mkdir(const char *path)
{
	struct mock_seed_file *file = mock_seed_file_for_path(path);

	if (file == NULL) {
		return -ENOENT;
	}

	file->exists = true;
	file->is_dir = true;
	file->len = 0U;
	return 0;
}

static int mock_seed_fs_open(
	struct fs_file_t *file, const char *path, fs_mode_t flags)
{
	struct mock_seed_file *slot = mock_seed_file_for_path(path);

	ARG_UNUSED(file);

	if (slot == NULL) {
		return -ENOENT;
	}

	if ((flags & FS_O_CREATE) != 0) {
		slot->exists = true;
		slot->is_dir = false;
	}

	if (!slot->exists) {
		return -ENOENT;
	}

	if ((flags & FS_O_TRUNC) != 0) {
		slot->len = 0U;
	}

	g_seed_open_path = path;
	return 0;
}

static ssize_t mock_seed_fs_read(struct fs_file_t *file, void *ptr, size_t size)
{
	struct mock_seed_file *slot = mock_seed_file_for_path(g_seed_open_path);

	ARG_UNUSED(file);

	if (slot == NULL || !slot->exists) {
		return -ENOENT;
	}

	if (size < slot->len) {
		return -EIO;
	}

	memcpy(ptr, slot->data, slot->len);
	return (ssize_t)slot->len;
}

static ssize_t mock_seed_fs_write(
	struct fs_file_t *file, const void *ptr, size_t size)
{
	struct mock_seed_file *slot = mock_seed_file_for_path(g_seed_open_path);

	ARG_UNUSED(file);

	if (slot == NULL) {
		return -ENOENT;
	}

	if (size > sizeof(slot->data)) {
		return -ENOSPC;
	}

	memcpy(slot->data, ptr, size);
	slot->len = size;
	slot->exists = true;
	slot->is_dir = false;
	return (ssize_t)size;
}

static int mock_seed_fs_sync(struct fs_file_t *file)
{
	ARG_UNUSED(file);
	return 0;
}

static int mock_seed_fs_close(struct fs_file_t *file)
{
	ARG_UNUSED(file);
	g_seed_open_path = NULL;
	return 0;
}

static int mock_seed_fs_unlink(const char *path)
{
	struct mock_seed_file *slot = mock_seed_file_for_path(path);

	if (slot == NULL || !slot->exists) {
		return -ENOENT;
	}

	memset(slot, 0, sizeof(*slot));
	return 0;
}

static int mock_seed_fs_rename(const char *from, const char *to)
{
	struct mock_seed_file *source = mock_seed_file_for_path(from);
	struct mock_seed_file *target = mock_seed_file_for_path(to);

	if (source == NULL || target == NULL || !source->exists) {
		return -ENOENT;
	}

	*target = *source;
	memset(source, 0, sizeof(*source));
	return 0;
}

static const struct neuro_recovery_seed_store_fs_ops g_success_seed_fs_ops = {
	.stat = mock_seed_fs_stat,
	.mkdir = mock_seed_fs_mkdir,
	.rename = mock_seed_fs_rename,
	.unlink = mock_seed_fs_unlink,
	.open = mock_seed_fs_open,
	.read = mock_seed_fs_read,
	.write = mock_seed_fs_write,
	.sync = mock_seed_fs_sync,
	.close = mock_seed_fs_close,
};

static void reset_mock_seed_fs(void)
{
	memset(&g_seed_parent_dir, 0, sizeof(g_seed_parent_dir));
	memset(&g_seed_primary_file, 0, sizeof(g_seed_primary_file));
	memset(&g_seed_tmp_file, 0, sizeof(g_seed_tmp_file));
	memset(&g_seed_legacy_file, 0, sizeof(g_seed_legacy_file));
	g_seed_open_path = NULL;
}

static int mock_fs_mount(void) { return 0; }

static int mock_fs_remove(const char *path)
{
	ARG_UNUSED(path);
	g_remove_calls++;
	g_mock_artifact_size = 0U;
	return 0;
}

static int mock_fs_stat(const char *path, struct fs_dirent *ent)
{
	zassert_not_null(path, "stat path must be provided");
	zassert_not_null(ent, "stat dirent must be provided");

	memset(ent, 0, sizeof(*ent));
	ent->type = FS_DIR_ENTRY_FILE;
	ent->size = g_mock_artifact_size;
	return 0;
}

static const struct neuro_unit_port_fs_ops g_success_fs_ops = {
	.mount = mock_fs_mount,
	.stat = mock_fs_stat,
	.remove = mock_fs_remove,
};

static void enable_successful_update_io(void)
{
	struct app_runtime_cmd_config cfg = { 0 };

	g_mock_artifact_size = 8192U;
	cfg.apps_dir = "/mock/apps";
	cfg.support.storage.mount = true;
	(void)app_runtime_cmd_set_config(&cfg);
	(void)neuro_unit_port_set_fs_ops(&g_success_fs_ops);
	neuro_recovery_seed_store_set_fs_ops(&g_success_seed_fs_ops);
}

static void mock_reply_error(const struct neuro_unit_reply_context *reply_ctx,
	const char *request_id, const char *message, int status_code)
{
	ARG_UNUSED(reply_ctx);
	ARG_UNUSED(request_id);

	g_reply_error_calls++;
	g_reply_error_status = status_code;
	snprintk(g_last_error_message, sizeof(g_last_error_message), "%s",
		message != NULL ? message : "");
}

static bool mock_require_resource_lease_or_reply(
	const struct neuro_unit_reply_context *reply_ctx,
	const char *request_id, const char *resource,
	const struct neuro_request_metadata *metadata)
{
	ARG_UNUSED(reply_ctx);
	ARG_UNUSED(request_id);
	ARG_UNUSED(resource);
	snprintk(g_last_lease_id, sizeof(g_last_lease_id), "%s",
		metadata != NULL ? metadata->lease_id : "");
	return g_require_lease_result;
}

static void mock_query_reply_json(
	const struct neuro_unit_reply_context *reply_ctx, const char *json)
{
	ARG_UNUSED(reply_ctx);

	g_query_reply_calls++;
	snprintk(g_last_reply_json, sizeof(g_last_reply_json), "%s",
		json != NULL ? json : "");
}

static void mock_publish_update_event(const char *app_id, const char *stage,
	const char *status, const char *message)
{
	g_publish_update_event_calls++;
	snprintk(g_last_event_app_id, sizeof(g_last_event_app_id), "%s",
		app_id != NULL ? app_id : "");
	snprintk(g_last_event_stage, sizeof(g_last_event_stage), "%s",
		stage != NULL ? stage : "");
	snprintk(g_last_event_status, sizeof(g_last_event_status), "%s",
		status != NULL ? status : "");
	snprintk(g_last_event_message, sizeof(g_last_event_message), "%s",
		message != NULL ? message : "");
}

static void mock_publish_state_event(void) { g_publish_state_event_calls++; }

static bool mock_runtime_app_is_loaded(const char *app_id)
{
	ARG_UNUSED(app_id);
	return g_mock_runtime_app_is_loaded;
}

static int mock_download_artifact(const char *app_id, const char *artifact_key,
	size_t total_size, size_t chunk_size, const char *dst_path)
{
	ARG_UNUSED(app_id);
	ARG_UNUSED(chunk_size);

	g_download_artifact_calls++;
	snprintk(g_last_download_artifact_key,
		sizeof(g_last_download_artifact_key), "%s",
		artifact_key != NULL ? artifact_key : "");
	snprintk(g_last_download_path, sizeof(g_last_download_path), "%s",
		dst_path != NULL ? dst_path : "");
	if (g_download_artifact_return != 0) {
		return g_download_artifact_return;
	}
	g_mock_artifact_size = g_mock_download_artifact_size != SIZE_MAX
				       ? g_mock_download_artifact_size
				       : total_size;
	return 0;
}

static void mock_register_app_callback_command(const char *app_id)
{
	ARG_UNUSED(app_id);
	g_register_callback_calls++;
}

static void mock_log_transaction(const char *app_id, const char *action,
	const char *request_id, const char *phase, int code, const char *detail)
{
	ARG_UNUSED(app_id);
	ARG_UNUSED(request_id);
	ARG_UNUSED(code);
	ARG_UNUSED(detail);

	g_log_calls++;
	snprintk(g_last_log_action, sizeof(g_last_log_action), "%s",
		action != NULL ? action : "");
	snprintk(g_last_log_phase, sizeof(g_last_log_phase), "%s",
		phase != NULL ? phase : "");
}

static const struct neuro_unit_update_service_ops g_ops = {
	.node_id = "unit-01",
	.reply_error = mock_reply_error,
	.require_resource_lease_or_reply = mock_require_resource_lease_or_reply,
	.query_reply_json = mock_query_reply_json,
	.publish_update_event = mock_publish_update_event,
	.publish_state_event = mock_publish_state_event,
	.runtime_app_is_loaded = mock_runtime_app_is_loaded,
	.download_artifact = mock_download_artifact,
	.register_app_callback_command = mock_register_app_callback_command,
	.log_transaction = mock_log_transaction,
};

static void test_reset(void *fixture)
{
	struct app_runtime_cmd_config cfg = { 0 };
	struct neuro_unit_update_service_ctx ctx = {
		.update_manager = &g_update_manager,
		.artifact_store = &g_artifact_store,
		.recovery_seed_store = &g_seed_store,
	};
	int ret;

	ARG_UNUSED(fixture);
	neuro_update_manager_init(&g_update_manager);
	neuro_artifact_store_init(&g_artifact_store);
	neuro_recovery_seed_store_init(
		&g_seed_store, "/tmp/neuro_unit_seed.bin");
	reset_mock_seed_fs();
	neuro_recovery_seed_store_reset_fs_ops();

	g_reply_error_calls = 0;
	g_reply_error_status = 0;
	g_query_reply_calls = 0;
	g_publish_update_event_calls = 0;
	g_publish_state_event_calls = 0;
	g_register_callback_calls = 0;
	g_log_calls = 0;
	g_download_artifact_calls = 0;
	g_download_artifact_return = 0;
	g_remove_calls = 0;
	g_mock_runtime_app_is_loaded = false;
	g_require_lease_result = true;
	g_reply_ctx.transport_query = &g_dummy_query_storage;
	g_reply_ctx.request_id = NULL;
	g_reply_ctx.metadata = NULL;
	g_reply_ctx.request_fields = NULL;
	g_mock_artifact_size = 8192U;
	g_mock_download_artifact_size = SIZE_MAX;
	memset(g_last_error_message, 0, sizeof(g_last_error_message));
	memset(g_last_reply_json, 0, sizeof(g_last_reply_json));
	memset(g_last_event_app_id, 0, sizeof(g_last_event_app_id));
	memset(g_last_event_stage, 0, sizeof(g_last_event_stage));
	memset(g_last_event_status, 0, sizeof(g_last_event_status));
	memset(g_last_event_message, 0, sizeof(g_last_event_message));
	memset(g_last_log_action, 0, sizeof(g_last_log_action));
	memset(g_last_log_phase, 0, sizeof(g_last_log_phase));
	memset(g_last_lease_id, 0, sizeof(g_last_lease_id));
	memset(g_last_download_artifact_key, 0,
		sizeof(g_last_download_artifact_key));
	memset(g_last_download_path, 0, sizeof(g_last_download_path));
	app_runtime_test_reset();

	cfg.apps_dir = "/mock/apps";
	(void)app_runtime_cmd_set_config(&cfg);
	(void)neuro_unit_port_set_fs_ops(NULL);

	ret = neuro_unit_update_service_init(&g_service, &ctx, &g_ops);
	zassert_equal(ret, 0, "service init should succeed");
}

static void drive_prepared_state(
	const struct neuro_unit_reply_context *reply_ctx)
{
	neuro_unit_update_service_handle_action(&g_service, reply_ctx,
		"demo_app", "prepare", "{\"transport\":\"file\"}",
		"req-prepare");
}

static void drive_verified_state(
	const struct neuro_unit_reply_context *reply_ctx)
{
	drive_prepared_state(reply_ctx);
	neuro_unit_update_service_handle_action(&g_service, reply_ctx,
		"demo_app", "verify", "{}", "req-verify");
}

static void drive_active_state(const struct neuro_unit_reply_context *reply_ctx)
{
	drive_verified_state(reply_ctx);
	neuro_unit_update_service_handle_action(&g_service, reply_ctx,
		"demo_app", "activate", "{}", "req-activate");
}

ZTEST(neuro_unit_update_service,
	test_prepare_action_stages_artifact_and_replies)
{
	const struct neuro_artifact_meta *artifact;

	neuro_unit_update_service_handle_action(&g_service, &g_reply_ctx,
		"demo_app", "prepare",
		"{\"transport\":\"file\",\"chunk_size\":99999}", "req-svc-1");

	artifact = neuro_artifact_store_get(&g_artifact_store, "demo_app");
	zassert_not_null(
		artifact, "prepare via service should stage artifact metadata");
	zassert_true(strcmp(artifact->transport, "file") == 0,
		"service prepare should preserve requested transport");
	zassert_true(strcmp(artifact->artifact_key,
			     "neuro/unit-01/update/app/demo_app/artifact") == 0,
		"service prepare artifact key mismatch");
	zassert_true(strcmp(artifact->path, "/mock/apps/demo_app.llext") == 0,
		"service prepare should use runtime app artifact path");
	zassert_equal(artifact->chunk_size, 4096,
		"service prepare should clamp oversized chunk size");
	zassert_equal(
		neuro_update_manager_state_for(&g_update_manager, "demo_app"),
		NEURO_UPDATE_STATE_PREPARED,
		"prepare via service should advance update state");
	zassert_equal(g_reply_error_calls, 0,
		"prepare via service should not emit reply_error");
	zassert_equal(g_query_reply_calls, 1,
		"prepare via service should reply once");
	zassert_true(
		strcmp(g_last_reply_json,
			"{\"status\":\"ok\",\"request_id\":\"req-svc-1\",\"node_id\":\"unit-01\",\"app_id\":\"demo_app\",\"path\":\"/mock/apps/demo_app.llext\",\"transport\":\"file\"}") ==
			0,
		"prepare reply JSON contract changed");
	zassert_true(strstr(g_last_reply_json, "\"status\":\"ok\"") != NULL,
		"prepare should emit success payload");
	zassert_true(
		strstr(g_last_reply_json, "\"transport\":\"file\"") != NULL,
		"prepare reply should include requested transport");
	zassert_equal(g_publish_update_event_calls, 1,
		"prepare via service should publish one update event");
	zassert_true(strcmp(g_last_event_app_id, "demo_app") == 0,
		"service prepare event app mismatch");
	zassert_true(strcmp(g_last_event_stage, "prepare") == 0,
		"service prepare event stage mismatch");
	zassert_true(strcmp(g_last_event_status, "ok") == 0,
		"service prepare event status mismatch");
	zassert_true(g_log_calls >= 3,
		"service prepare flow should emit transaction logs");
	zassert_true(strcmp(g_last_log_action, "prepare") == 0,
		"service prepare should keep prepare transaction action");
	zassert_true(strcmp(g_last_log_phase, "egress") == 0,
		"service prepare should end at service egress");
}

ZTEST(neuro_unit_update_service,
	test_repeated_prepare_preserves_existing_state_machine_semantics)
{
	neuro_unit_update_service_handle_action(&g_service, &g_reply_ctx,
		"demo_app", "prepare", "{\"transport\":\"file\"}", "req-svc-3");
	neuro_unit_update_service_handle_action(&g_service, &g_reply_ctx,
		"demo_app", "prepare", "{\"transport\":\"file\"}", "req-svc-4");

	zassert_equal(g_reply_error_calls, 0,
		"repeated prepare should preserve current no-error semantics");
	zassert_equal(g_query_reply_calls, 2,
		"repeated prepare should preserve current success reply behavior");
	zassert_equal(
		neuro_update_manager_state_for(&g_update_manager, "demo_app"),
		NEURO_UPDATE_STATE_PREPARED,
		"repeated prepare should leave update state prepared");
	zassert_true(strcmp(g_last_log_action, "prepare") == 0,
		"repeated prepare should still be logged as prepare action");
	zassert_true(strcmp(g_last_log_phase, "egress") == 0,
		"repeated prepare should still return through service egress");
}

ZTEST(neuro_unit_update_service, test_prepare_prefers_context_request_fields)
{
	const struct neuro_artifact_meta *artifact;
	struct neuro_unit_request_fields request_fields = { 0 };

	snprintk(request_fields.transport, sizeof(request_fields.transport),
		"contextfs");
	request_fields.chunk_size = 2048U;
	g_reply_ctx.request_fields = &request_fields;

	neuro_unit_update_service_handle_action(&g_service, &g_reply_ctx,
		"demo_app", "prepare",
		"{\"transport\":\"payloadfs\",\"chunk_size\":1024}",
		"req-prepare-fields");

	artifact = neuro_artifact_store_get(&g_artifact_store, "demo_app");
	zassert_not_null(artifact,
		"prepare with context fields should stage artifact metadata");
	zassert_true(strcmp(artifact->transport, "contextfs") == 0,
		"prepare should prefer context transport over payload JSON");
	zassert_equal(artifact->chunk_size, 2048,
		"prepare should prefer context chunk size over payload JSON");
}

ZTEST(neuro_unit_update_service,
	test_zenoh_prepare_downloads_requested_artifact)
{
	const struct neuro_artifact_meta *artifact;

	enable_successful_update_io();
	neuro_unit_update_service_handle_action(&g_service, &g_reply_ctx,
		"demo_app", "prepare",
		"{\"transport\":\"zenoh\",\"artifact_key\":\"neuro/artifact/unit-01/demo_app\",\"size\":20164,\"chunk_size\":1024}",
		"req-prepare-zenoh");

	artifact = neuro_artifact_store_get(&g_artifact_store, "demo_app");
	zassert_not_null(artifact,
		"zenoh prepare should stage downloaded artifact metadata");
	zassert_equal(g_download_artifact_calls, 1,
		"zenoh prepare should download the requested artifact");
	zassert_true(strcmp(g_last_download_artifact_key,
			     "neuro/artifact/unit-01/demo_app") == 0,
		"zenoh prepare should use the request artifact key");
	zassert_true(
		strcmp(g_last_download_path, "/mock/apps/demo_app.llext") == 0,
		"zenoh prepare should download into the runtime app path");
	zassert_equal(artifact->size_bytes, 20164,
		"zenoh prepare should persist the expected artifact size");
	zassert_equal(artifact->chunk_size, 1024,
		"zenoh prepare should persist the requested chunk size");
	zassert_equal(g_reply_error_calls, 0,
		"matching downloaded artifact size should not fail prepare");
	zassert_equal(
		neuro_update_manager_state_for(&g_update_manager, "demo_app"),
		NEURO_UPDATE_STATE_PREPARED,
		"matching downloaded artifact should leave app prepared");
}

ZTEST(neuro_unit_update_service, test_zenoh_prepare_rejects_truncated_artifact)
{
	const struct neuro_artifact_meta *artifact;

	enable_successful_update_io();
	g_mock_download_artifact_size = 5232U;
	neuro_unit_update_service_handle_action(&g_service, &g_reply_ctx,
		"demo_app", "prepare",
		"{\"transport\":\"zenoh\",\"artifact_key\":\"neuro/artifact/unit-01/demo_app\",\"size\":20164,\"chunk_size\":1024}",
		"req-prepare-truncated");

	artifact = neuro_artifact_store_get(&g_artifact_store, "demo_app");
	zassert_is_null(artifact,
		"truncated zenoh prepare must not stage artifact metadata");
	zassert_equal(g_download_artifact_calls, 1,
		"truncated prepare should still attempt the requested download");
	zassert_equal(g_remove_calls, 1,
		"truncated prepare should remove the partial artifact");
	zassert_equal(g_reply_error_calls, 1,
		"truncated prepare should emit a semantic error");
	zassert_true(strcmp(g_last_error_message,
			     "prepare artifact size mismatch") == 0,
		"truncated prepare error message changed");
	zassert_equal(
		neuro_update_manager_state_for(&g_update_manager, "demo_app"),
		NEURO_UPDATE_STATE_FAILED,
		"truncated prepare should fail the update state");
}

ZTEST(neuro_unit_update_service, test_activate_prefers_context_metadata)
{
	struct neuro_request_metadata metadata;

	enable_successful_update_io();
	drive_verified_state(&g_reply_ctx);
	neuro_request_metadata_init(&metadata);
	snprintk(metadata.lease_id, sizeof(metadata.lease_id),
		"lease-from-context");
	g_reply_ctx.metadata = &metadata;

	neuro_unit_update_service_handle_action(&g_service, &g_reply_ctx,
		"demo_app", "activate", "{\"lease_id\":\"payload-lease\"}",
		"req-activate-context");

	zassert_true(strcmp(g_last_lease_id, "lease-from-context") == 0,
		"activate lease check should use decoded context metadata first");
}

ZTEST(neuro_unit_update_service,
	test_activate_unloads_existing_app_before_replacement_load)
{
	g_mock_runtime_app_is_loaded = true;

	enable_successful_update_io();
	drive_active_state(&g_reply_ctx);

	zassert_equal(app_runtime_test_unload_calls(), 1,
		"activate should unload an existing runtime app first");
	zassert_equal(app_runtime_test_load_calls(), 1,
		"activate should load the replacement once");
	zassert_equal(app_runtime_test_start_calls(), 1,
		"activate should start the replacement once");
	zassert_true(
		strcmp(app_runtime_test_sequence(), "unload,load,start") == 0,
		"activate runtime operation order changed");
	zassert_true(strcmp(app_runtime_test_last_load_path(),
			     "/mock/apps/demo_app.llext") == 0,
		"activate should load the staged app artifact path");
}

ZTEST(neuro_unit_update_service,
	test_activate_load_failure_skips_start_and_callback_registration)
{
	enable_successful_update_io();
	drive_verified_state(&g_reply_ctx);
	app_runtime_test_set_load_return(-ENOMEM);

	neuro_unit_update_service_handle_action(&g_service, &g_reply_ctx,
		"demo_app", "activate", "{}", "req-activate-load-fail");

	zassert_equal(app_runtime_test_load_calls(), 1,
		"activate should attempt runtime load once");
	zassert_equal(app_runtime_test_start_calls(), 0,
		"activate must not start after load failure");
	zassert_equal(g_register_callback_calls, 0,
		"activate must not register callbacks after load failure");
	zassert_equal(g_reply_error_calls, 1,
		"activate load failure should emit one reply error");
	zassert_true(
		strstr(g_last_error_message, "activate load failed") != NULL,
		"activate load failure message changed");
	zassert_equal(
		neuro_update_manager_state_for(&g_update_manager, "demo_app"),
		NEURO_UPDATE_STATE_FAILED,
		"activate load failure should mark update failed");
	zassert_true(strcmp(g_last_event_stage, "activate") == 0,
		"activate load failure should publish activate stage");
	zassert_true(strcmp(g_last_event_status, "error") == 0,
		"activate load failure should publish error status");
}

ZTEST(neuro_unit_update_service,
	test_activate_start_args_prefer_context_request_fields)
{
	struct neuro_unit_request_fields request_fields = { 0 };

	enable_successful_update_io();
	drive_verified_state(&g_reply_ctx);
	snprintk(request_fields.start_args, sizeof(request_fields.start_args),
		"mode=context,level=7");
	g_reply_ctx.request_fields = &request_fields;

	neuro_unit_update_service_handle_action(&g_service, &g_reply_ctx,
		"demo_app", "activate", "{\"start_args\":\"mode=payload\"}",
		"req-activate-start-args");

	zassert_true(strcmp(app_runtime_test_last_start_args(),
			     "mode=context,level=7") == 0,
		"activate should prefer decoded context start args");
	zassert_equal(g_reply_error_calls, 0,
		"context start args should not fail activate");
}

ZTEST(neuro_unit_update_service, test_rollback_prefers_context_request_fields)
{
	struct neuro_unit_request_fields request_fields = { 0 };

	enable_successful_update_io();
	drive_active_state(&g_reply_ctx);
	snprintk(request_fields.reason, sizeof(request_fields.reason),
		"context reason");
	g_reply_ctx.request_fields = &request_fields;

	neuro_unit_update_service_handle_action(&g_service, &g_reply_ctx,
		"demo_app", "rollback", "{\"reason\":\"payload reason\"}",
		"req-rollback-fields");

	zassert_true(strstr(g_last_reply_json,
			     "\"reason\":\"context reason\"") != NULL,
		"rollback should prefer context reason over payload JSON");
}

ZTEST(neuro_unit_update_service, test_verify_action_marks_artifact_verified)
{
	const struct neuro_artifact_meta *artifact;

	enable_successful_update_io();
	drive_verified_state(&g_reply_ctx);

	artifact = neuro_artifact_store_get(&g_artifact_store, "demo_app");
	zassert_not_null(
		artifact, "verify via service should retain artifact metadata");
	zassert_equal(artifact->state, NEURO_ARTIFACT_VERIFIED,
		"verify via service should mark artifact verified");
	zassert_equal(
		neuro_update_manager_state_for(&g_update_manager, "demo_app"),
		NEURO_UPDATE_STATE_VERIFIED,
		"verify via service should advance update state");
	zassert_equal(g_reply_error_calls, 0,
		"verify via service should not emit reply_error");
	zassert_equal(g_query_reply_calls, 2,
		"prepare+verify should emit two success replies");
	zassert_true(
		strcmp(g_last_reply_json,
			"{\"status\":\"ok\",\"request_id\":\"req-verify\",\"node_id\":\"unit-01\",\"app_id\":\"demo_app\",\"size\":8192}") ==
			0,
		"verify reply JSON contract changed");
	zassert_true(strstr(g_last_reply_json, "\"size\":8192") != NULL,
		"verify reply should include artifact size");
	zassert_true(strcmp(g_last_event_stage, "verify") == 0,
		"service verify event stage mismatch");
	zassert_true(strcmp(g_last_event_status, "ok") == 0,
		"service verify event status mismatch");
	zassert_true(strcmp(g_last_log_action, "verify") == 0,
		"service verify should keep verify transaction action");
	zassert_true(strcmp(g_last_log_phase, "egress") == 0,
		"service verify should end at service egress");
}

ZTEST(neuro_unit_update_service, test_activate_action_marks_app_active)
{
	const struct neuro_artifact_meta *artifact;

	enable_successful_update_io();
	drive_active_state(&g_reply_ctx);

	artifact = neuro_artifact_store_get(&g_artifact_store, "demo_app");
	zassert_not_null(artifact,
		"activate via service should retain artifact metadata");
	zassert_equal(artifact->state, NEURO_ARTIFACT_ACTIVE,
		"activate via service should mark artifact active");
	zassert_equal(
		neuro_update_manager_state_for(&g_update_manager, "demo_app"),
		NEURO_UPDATE_STATE_ACTIVE,
		"activate via service should advance update state");
	zassert_equal(g_reply_error_calls, 0,
		"activate via service should not emit reply_error");
	zassert_equal(g_query_reply_calls, 3,
		"prepare+verify+activate should emit three success replies");
	zassert_true(
		strcmp(g_last_reply_json,
			"{\"status\":\"ok\",\"request_id\":\"req-activate\",\"node_id\":\"unit-01\",\"app_id\":\"demo_app\",\"path\":\"/mock/apps/demo_app.llext\"}") ==
			0,
		"activate reply JSON contract changed");
	zassert_equal(g_register_callback_calls, 1,
		"activate via service should register callback command once");
	zassert_equal(g_publish_state_event_calls, 1,
		"activate via service should publish one state event");
	zassert_true(strcmp(g_last_event_stage, "activate") == 0,
		"service activate event stage mismatch");
	zassert_true(strcmp(g_last_event_status, "ok") == 0,
		"service activate event status mismatch");
	zassert_true(strcmp(g_last_log_action, "activate") == 0,
		"service activate should keep activate transaction action");
	zassert_true(strcmp(g_last_log_phase, "egress") == 0,
		"service activate should end at service egress");
}

ZTEST(neuro_unit_update_service, test_rollback_action_completes_recovery_flow)
{
	enable_successful_update_io();
	drive_active_state(&g_reply_ctx);
	neuro_unit_update_service_handle_action(&g_service, &g_reply_ctx,
		"demo_app", "rollback", "{\"reason\":\"operator\"}",
		"req-rollback");

	zassert_equal(
		neuro_update_manager_state_for(&g_update_manager, "demo_app"),
		NEURO_UPDATE_STATE_ROLLED_BACK,
		"rollback via service should complete update rollback");
	zassert_equal(g_reply_error_calls, 0,
		"rollback via service should not emit reply_error");
	zassert_equal(g_query_reply_calls, 4,
		"prepare+verify+activate+rollback should emit four replies");
	zassert_true(
		strcmp(g_last_reply_json,
			"{\"status\":\"ok\",\"request_id\":\"req-rollback\",\"node_id\":\"unit-01\",\"app_id\":\"demo_app\",\"reason\":\"operator\"}") ==
			0,
		"rollback reply JSON contract changed");
	zassert_equal(g_publish_state_event_calls, 2,
		"activate+rollback should publish two state events");
	zassert_equal(g_register_callback_calls, 2,
		"activate and stable restore should register callback commands");
	zassert_true(strcmp(g_last_event_stage, "rollback") == 0,
		"service rollback event stage mismatch");
	zassert_true(strcmp(g_last_event_status, "ok") == 0,
		"service rollback event status mismatch");
	zassert_true(strcmp(g_last_log_action, "recover") == 0,
		"service rollback should use recover transaction action");
	zassert_true(strcmp(g_last_log_phase, "egress") == 0,
		"service rollback should end at service egress");
}

ZTEST(neuro_unit_update_service, test_recover_alias_is_preserved)
{
	neuro_unit_update_service_handle_action(&g_service, &g_reply_ctx,
		"demo_app", "recover", "{}", "req-svc-2");

	zassert_equal(g_reply_error_calls, 1,
		"recover on fresh state should fail with rollback conflict");
	zassert_equal(g_reply_error_status, 409,
		"recover alias should preserve rollback conflict status");
	zassert_true(strcmp(g_last_log_action, "recover") == 0,
		"recover alias should use recover transaction context");
}

ZTEST(neuro_unit_update_service, test_unsupported_action_replies_404)
{
	neuro_unit_update_service_handle_action(&g_service, &g_reply_ctx,
		"demo_app", "unsupported", "{}", "req-unsupported");

	zassert_equal(g_reply_error_calls, 1,
		"unsupported update action must emit reply_error");
	zassert_equal(g_reply_error_status, 404,
		"unsupported update action should map to 404");
	zassert_true(
		strcmp(g_last_error_message, "unsupported update path") == 0,
		"unsupported update action message mismatch");
	zassert_equal(g_query_reply_calls, 0,
		"unsupported update action must not emit success reply");
	zassert_true(strcmp(g_last_log_action, "unsupported") == 0,
		"unsupported action should keep its transaction action");
	zassert_true(strcmp(g_last_log_phase, "egress") == 0,
		"unsupported action should return through service egress");
}

ZTEST(neuro_unit_update_service,
	test_recovery_seed_gate_bubbles_storage_not_ready)
{
	int ret;

	ret = neuro_unit_update_service_ensure_recovery_seed_initialized(
		&g_service);
	zassert_not_equal(ret, 0,
		"recovery gate should fail when storage mount is unsupported");
}

ZTEST_SUITE(neuro_unit_update_service, NULL, NULL, test_reset, NULL, NULL);
