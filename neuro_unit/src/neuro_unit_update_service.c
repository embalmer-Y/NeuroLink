#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/printk.h>

#include <errno.h>
#include <string.h>

#include "app_runtime.h"
#include "app_runtime_cmd.h"
#include "app_runtime_exception.h"
#include "neuro_app_command_registry.h"
#include "neuro_protocol_codec_cbor.h"
#include "neuro_unit_port.h"
#include "neuro_unit_diag.h"
#include "neuro_unit_update_service.h"

LOG_MODULE_REGISTER(neuro_unit_update_service, LOG_LEVEL_INF);

#define NEURO_RECOVERY_STAGE "recovery"
#define NEURO_UNIT_UPDATE_JSON_LEN 256
#define NEURO_UNIT_UPDATE_FIELD_LEN 96
#define NEURO_UNIT_PREPARE_DEFAULT_CHUNK_SIZE 1024
#define NEURO_UNIT_PREPARE_MAX_CHUNK_SIZE 4096

static void query_reply_update_cbor_or_json(
	struct neuro_unit_update_service *service,
	const struct neuro_unit_reply_context *reply_ctx,
	const char *request_id, const char *app_id, const char *action,
	const struct neuro_protocol_update_reply_cbor *reply, const char *json)
{
	uint8_t cbor[256];
	size_t encoded_len = 0U;
	int ret = -ENOTSUP;

	if (service->ops->query_reply_cbor != NULL) {
		if (strcmp(action, "prepare") == 0) {
			ret = neuro_protocol_encode_update_prepare_reply_cbor(
				cbor, sizeof(cbor), reply, &encoded_len);
		} else if (strcmp(action, "verify") == 0) {
			ret = neuro_protocol_encode_update_verify_reply_cbor(
				cbor, sizeof(cbor), reply, &encoded_len);
		} else if (strcmp(action, "activate") == 0) {
			ret = neuro_protocol_encode_update_activate_reply_cbor(
				cbor, sizeof(cbor), reply, &encoded_len);
		} else if (strcmp(action, "rollback") == 0 ||
			   strcmp(action, "recover") == 0) {
			ret = neuro_protocol_encode_update_rollback_reply_cbor(
				cbor, sizeof(cbor), reply, &encoded_len);
		}
	}

	ARG_UNUSED(request_id);
	ARG_UNUSED(app_id);
	if (ret == 0) {
		service->ops->query_reply_cbor(reply_ctx, cbor, encoded_len);
		return;
	}

	service->ops->query_reply_json(reply_ctx, json);
}

static void service_log_transaction(struct neuro_unit_update_service *service,
	const char *app_id, const char *action, const char *request_id,
	const char *phase, int code, const char *detail)
{
	const char *id = app_id != NULL && app_id[0] != '\0' ? app_id : "-";
	const char *act = action != NULL && action[0] != '\0' ? action : "-";
	const char *req =
		request_id != NULL && request_id[0] != '\0' ? request_id : "-";
	const char *txn_phase = phase != NULL && phase[0] != '\0' ? phase : "-";
	const char *msg = detail != NULL && detail[0] != '\0' ? detail : "-";

	if (service != NULL && service->ops != NULL &&
		service->ops->log_transaction != NULL) {
		service->ops->log_transaction(
			id, act, req, txn_phase, code, msg);
		return;
	}

	neuro_unit_diag_update_transaction(id, act, req, txn_phase, code, msg);
}

static bool artifact_path_available(const char *path)
{
	struct fs_dirent ent;
	int ret;

	if (path == NULL || path[0] == '\0') {
		return false;
	}
	{
		const struct neuro_unit_port_fs_ops *fs_ops =
			neuro_unit_port_get_fs_ops();

		if (fs_ops == NULL || fs_ops->stat == NULL) {
			return false;
		}

		memset(&ent, 0, sizeof(ent));
		ret = fs_ops->stat(path, &ent);
	}
	if (ret < 0) {
		return false;
	}

	return ent.type == FS_DIR_ENTRY_FILE && ent.size > 0U;
}

static void build_app_path(const char *app_id, char *path, size_t path_len)
{
	const struct app_runtime_cmd_config *cfg = app_runtime_cmd_get_config();

	snprintk(path, path_len, "%s/%s.llext", cfg->apps_dir, app_id);
}

static int artifact_stat(const char *path, struct fs_dirent *ent)
{
	const struct neuro_unit_port_fs_ops *fs_ops =
		neuro_unit_port_get_fs_ops();

	if (fs_ops == NULL || fs_ops->stat == NULL) {
		return -ENOTSUP;
	}

	return fs_ops->stat(path, ent);
}

static bool runtime_app_is_active(const char *app_id)
{
	struct app_runtime_status status;
	size_t listed_count;
	size_t i;

	if (app_id == NULL || app_id[0] == '\0') {
		return false;
	}

	memset(&status, 0, sizeof(status));
	app_runtime_get_status(&status);
	listed_count = app_runtime_status_listed_count(&status);
	if (listed_count > ARRAY_SIZE(status.apps)) {
		listed_count = ARRAY_SIZE(status.apps);
	}

	for (i = 0; i < listed_count; i++) {
		if (strcmp(status.apps[i].name, app_id) == 0) {
			return status.apps[i].state == APP_RT_RUNNING;
		}
	}

	return false;
}

static int persist_recovery_seed_snapshot(
	struct neuro_unit_update_service *service);

static void reconcile_recovery_seed_after_boot(
	struct neuro_unit_update_service *service)
{
	struct neuro_update_entry entries[NEURO_UPDATE_MANAGER_MAX_ENTRIES];
	size_t entry_count;
	size_t i;
	int ret;

	entry_count = neuro_update_manager_export_entries(
		service->ctx.update_manager, entries, ARRAY_SIZE(entries));
	for (i = 0; i < entry_count; i++) {
		const struct neuro_artifact_meta *meta;
		bool runtime_active;
		bool artifact_available;

		meta = neuro_artifact_store_get(
			service->ctx.artifact_store, entries[i].app_id);
		runtime_active = runtime_app_is_active(entries[i].app_id);
		artifact_available =
			meta != NULL && artifact_path_available(meta->path);

		ret = neuro_update_manager_reconcile_after_boot(
			service->ctx.update_manager, entries[i].app_id,
			runtime_active, artifact_available);
		if (ret != 0) {
			service_log_transaction(service, entries[i].app_id,
				"recover", "-", "reconcile_error", ret,
				"reconcile failed");
			continue;
		}

		if (neuro_update_manager_state_for(service->ctx.update_manager,
			    entries[i].app_id) == NEURO_UPDATE_STATE_FAILED) {
			service->ops->publish_update_event(entries[i].app_id,
				NEURO_RECOVERY_STAGE, "error",
				neuro_update_manager_last_error_for(
					service->ctx.update_manager,
					entries[i].app_id));
		}
	}

	ret = persist_recovery_seed_snapshot(service);
	if (ret) {
		LOG_WRN("recovery seed persist after boot reconcile failed: %d",
			ret);
	}
}

int neuro_unit_update_service_ensure_recovery_seed_initialized(
	struct neuro_unit_update_service *service)
{
	struct neuro_recovery_seed_snapshot snapshot;
	int ret;

	if (service == NULL || service->ops == NULL ||
		service->ctx.update_manager == NULL ||
		service->ctx.artifact_store == NULL ||
		service->ctx.recovery_seed_store == NULL) {
		return -EINVAL;
	}

	if (service->recovery_seed_initialized) {
		return 0;
	}

	service_log_transaction(service, "system", "recover", "-", "init", 0,
		"begin recovery seed init");
	ret = app_runtime_cmd_exec(APP_RT_CMD_STORAGE_MOUNT, NULL, NULL);
	if (ret) {
		LOG_WRN("recovery seed init deferred: storage_mount failed: %d",
			ret);
		service_log_transaction(service, "system", "recover", "-",
			"init_deferred", ret, "storage mount failed");
		return ret;
	}

	/*
	 * Mark initialized before reconcile to avoid recursive re-entry via
	 * persist path.
	 */
	service->recovery_seed_initialized = true;

	ret = neuro_recovery_seed_store_load(
		service->ctx.recovery_seed_store, &snapshot);
	if (ret == 0) {
		ret = neuro_recovery_seed_apply_snapshot(&snapshot,
			service->ctx.update_manager,
			service->ctx.artifact_store);
		if (ret == 0) {
			reconcile_recovery_seed_after_boot(service);
			service->ops->publish_update_event("system",
				NEURO_RECOVERY_STAGE, "ok",
				"boot reconciliation complete");
			service_log_transaction(service, "system", "recover",
				"-", "init_done", 0,
				"recovery seed initialized");
		} else {
			LOG_WRN("recovery seed apply failed: %d", ret);
			service->ops->publish_update_event("system",
				NEURO_RECOVERY_STAGE, "error",
				"seed apply failed");
			service_log_transaction(service, "system", "recover",
				"-", "apply_error", ret,
				"recovery seed apply failed");
		}
	} else if (ret != -ENOENT) {
		LOG_WRN("recovery seed load failed: %d", ret);
		service->ops->publish_update_event("system",
			NEURO_RECOVERY_STAGE, "error", "seed load failed");
		service_log_transaction(service, "system", "recover", "-",
			"load_error", ret, "recovery seed load failed");
	}

	return 0;
}

static int persist_recovery_seed_snapshot(
	struct neuro_unit_update_service *service)
{
	struct neuro_recovery_seed_snapshot snapshot;
	int ret;

	ret = neuro_unit_update_service_ensure_recovery_seed_initialized(
		service);
	if (ret) {
		return ret;
	}

	ret = neuro_recovery_seed_build_snapshot(service->ctx.update_manager,
		service->ctx.artifact_store, &snapshot);
	if (ret) {
		LOG_WRN("recovery seed snapshot build failed: %d", ret);
		return ret;
	}

	ret = neuro_recovery_seed_store_save(
		service->ctx.recovery_seed_store, &snapshot);
	if (ret) {
		LOG_WRN("recovery seed save failed: %d", ret);
		return ret;
	}

	return 0;
}

static void format_runtime_failure_detail(
	char *buf, size_t buf_len, const char *fallback, int ret)
{
	struct app_rt_exception exc = { 0 };

	if (buf == NULL || buf_len == 0U) {
		return;
	}

	app_rt_get_last_exception(&exc);
	if (exc.code != APP_RT_EX_NONE) {
		snprintk(buf, buf_len, "%s: %s/%s %s cause=%d ret=%d", fallback,
			exc.component, exc.operation,
			app_rt_exception_code_str(exc.code), exc.cause, ret);
		return;
	}

	snprintk(buf, buf_len, "%s: ret=%d", fallback, ret);
}

static void handle_update_prepare(struct neuro_unit_update_service *service,
	const struct neuro_unit_reply_context *reply_ctx, const char *app_id,
	const char *payload, const char *request_id)
{
	const struct neuro_unit_request_fields *request_fields;
	char transport[32] = "zenoh";
	char keyexpr[128];
	char artifact_key[128] = "";
	char path[NEURO_UNIT_UPDATE_FIELD_LEN];
	char json[NEURO_UNIT_UPDATE_JSON_LEN];
	struct neuro_protocol_update_reply_cbor reply;
	struct fs_dirent ent;
	size_t requested_size = 0U;
	int chunk_size;
	int ret;

	service_log_transaction(
		service, app_id, "prepare", request_id, "begin", 0, "enter");
	request_fields = neuro_unit_reply_context_request_fields(reply_ctx);
	ret = neuro_update_manager_prepare_begin(
		service->ctx.update_manager, app_id);
	if (ret) {
		service_log_transaction(service, app_id, "prepare", request_id,
			"reject", ret, "prepare state conflict");
		service->ops->reply_error(
			reply_ctx, request_id, "prepare state conflict", 409);
		return;
	}

	if (request_fields != NULL && request_fields->transport[0] != '\0') {
		snprintk(transport, sizeof(transport), "%s",
			request_fields->transport);
	} else {
		(void)neuro_json_extract_string(
			payload, "transport", transport, sizeof(transport));
	}
	if (request_fields != NULL && request_fields->chunk_size > 0U) {
		chunk_size = (int)request_fields->chunk_size;
	} else {
		chunk_size = neuro_json_extract_int(payload, "chunk_size",
			NEURO_UNIT_PREPARE_DEFAULT_CHUNK_SIZE);
	}
	if (request_fields != NULL && request_fields->artifact_key[0] != '\0') {
		snprintk(artifact_key, sizeof(artifact_key), "%s",
			request_fields->artifact_key);
	} else {
		(void)neuro_json_extract_string(payload, "artifact_key",
			artifact_key, sizeof(artifact_key));
	}
	if (request_fields != NULL && request_fields->size > 0U) {
		requested_size = request_fields->size;
	} else {
		requested_size =
			(size_t)neuro_json_extract_int(payload, "size", 0);
	}
	if (chunk_size <= 0) {
		chunk_size = NEURO_UNIT_PREPARE_DEFAULT_CHUNK_SIZE;
	}

	if (chunk_size > NEURO_UNIT_PREPARE_MAX_CHUNK_SIZE) {
		chunk_size = NEURO_UNIT_PREPARE_MAX_CHUNK_SIZE;
	}

	build_app_path(app_id, path, sizeof(path));
	snprintk(keyexpr, sizeof(keyexpr), "%s",
		artifact_key[0] != '\0' ? artifact_key : "");
	if (strcmp(transport, "zenoh") == 0) {
		if (keyexpr[0] == '\0' || requested_size == 0U ||
			service->ops->download_artifact == NULL) {
			ret = -EINVAL;
			(void)neuro_update_manager_prepare_fail(
				service->ctx.update_manager, app_id,
				"artifact download contract invalid");
			(void)persist_recovery_seed_snapshot(service);
			service->ops->publish_update_event(app_id, "prepare",
				"error", "artifact download contract invalid");
			service_log_transaction(service, app_id, "prepare",
				request_id, "fail", ret,
				"artifact download contract invalid");
			service->ops->reply_error(reply_ctx, request_id,
				"prepare artifact download contract invalid",
				400);
			return;
		}

		ret = service->ops->download_artifact(app_id, keyexpr,
			requested_size, (size_t)chunk_size, path);
		if (ret) {
			const struct neuro_unit_port_fs_ops *fs_ops =
				neuro_unit_port_get_fs_ops();

			if (fs_ops != NULL && fs_ops->remove != NULL) {
				(void)fs_ops->remove(path);
			}
			(void)neuro_update_manager_prepare_fail(
				service->ctx.update_manager, app_id,
				"artifact download failed");
			(void)persist_recovery_seed_snapshot(service);
			service->ops->publish_update_event(app_id, "prepare",
				"error", "artifact download failed");
			service_log_transaction(service, app_id, "prepare",
				request_id, "fail", ret,
				"artifact download failed");
			service->ops->reply_error(reply_ctx, request_id,
				"prepare artifact download failed", 500);
			return;
		}

		ret = artifact_stat(path, &ent);
		if (ret || ent.type != FS_DIR_ENTRY_FILE ||
			(size_t)ent.size != requested_size) {
			const struct neuro_unit_port_fs_ops *fs_ops =
				neuro_unit_port_get_fs_ops();

			if (fs_ops != NULL && fs_ops->remove != NULL) {
				(void)fs_ops->remove(path);
			}
			ret = ret != 0 ? ret : -EIO;
			(void)neuro_update_manager_prepare_fail(
				service->ctx.update_manager, app_id,
				"artifact size mismatch");
			(void)persist_recovery_seed_snapshot(service);
			service->ops->publish_update_event(app_id, "prepare",
				"error", "artifact size mismatch");
			service_log_transaction(service, app_id, "prepare",
				request_id, "fail", ret,
				"artifact size mismatch");
			service->ops->reply_error(reply_ctx, request_id,
				"prepare artifact size mismatch", 500);
			return;
		}
	} else {
		snprintk(keyexpr, sizeof(keyexpr),
			"neuro/%s/update/app/%s/artifact",
			service->ops->node_id, app_id);
	}
	ret = neuro_artifact_store_stage(service->ctx.artifact_store, app_id,
		transport, keyexpr, path, requested_size, (size_t)chunk_size,
		0U);
	if (ret) {
		(void)neuro_update_manager_prepare_fail(
			service->ctx.update_manager, app_id,
			"artifact stage failed");
		(void)persist_recovery_seed_snapshot(service);
		service->ops->publish_update_event(
			app_id, "prepare", "error", "artifact stage failed");
		service_log_transaction(service, app_id, "prepare", request_id,
			"fail", ret, "artifact stage failed");
		service->ops->reply_error(reply_ctx, request_id,
			"prepare artifact stage failed", 500);
		return;
	}

	ret = neuro_update_manager_prepare_complete(
		service->ctx.update_manager, app_id);
	if (ret) {
		service->ops->publish_update_event(
			app_id, "prepare", "error", "prepare complete failed");
		service_log_transaction(service, app_id, "prepare", request_id,
			"fail", ret, "prepare complete failed");
		service->ops->reply_error(
			reply_ctx, request_id, "prepare complete failed", 500);
		return;
	}

	(void)persist_recovery_seed_snapshot(service);
	service->ops->publish_update_event(app_id, "prepare", "ok", path);
	snprintk(json, sizeof(json),
		"{\"status\":\"ok\",\"request_id\":\"%s\",\"node_id\":\"%s\",\"app_id\":\"%s\",\"path\":\"%s\",\"transport\":\"%s\"}",
		request_id, service->ops->node_id, app_id, path, transport);
	reply.request_id = request_id;
	reply.node_id = service->ops->node_id;
	reply.app_id = app_id;
	reply.path = path;
	reply.transport = transport;
	reply.size = 0U;
	reply.reason = "";
	service_log_transaction(service, app_id, "prepare", request_id,
		"commit", 0, "prepare success");
	query_reply_update_cbor_or_json(service, reply_ctx, request_id, app_id,
		"prepare", &reply, json);
}

static void handle_update_verify(struct neuro_unit_update_service *service,
	const struct neuro_unit_reply_context *reply_ctx, const char *app_id,
	const char *request_id)
{
	char path[NEURO_UNIT_UPDATE_FIELD_LEN];
	char json[NEURO_UNIT_UPDATE_JSON_LEN];
	struct neuro_protocol_update_reply_cbor reply;
	const struct neuro_artifact_meta *artifact;
	struct fs_dirent ent;
	int ret;
	int save_ret;

	service_log_transaction(
		service, app_id, "verify", request_id, "begin", 0, "enter");
	ret = neuro_update_manager_verify_begin(
		service->ctx.update_manager, app_id);
	if (ret) {
		service_log_transaction(service, app_id, "verify", request_id,
			"reject", ret, "verify state conflict");
		service->ops->reply_error(
			reply_ctx, request_id, "verify state conflict", 409);
		return;
	}

	build_app_path(app_id, path, sizeof(path));
	ret = artifact_stat(path, &ent);
	if (ret || ent.type != FS_DIR_ENTRY_FILE || ent.size == 0U) {
		(void)neuro_artifact_store_set_state(
			service->ctx.artifact_store, app_id,
			NEURO_ARTIFACT_INVALID);
		(void)neuro_update_manager_verify_fail(
			service->ctx.update_manager, app_id,
			"artifact missing");
		(void)persist_recovery_seed_snapshot(service);
		service->ops->publish_update_event(
			app_id, "verify", "error", "artifact missing");
		service_log_transaction(service, app_id, "verify", request_id,
			"fail", ret != 0 ? ret : -ENOENT, "artifact missing");
		service->ops->reply_error(
			reply_ctx, request_id, "artifact missing", 404);
		return;
	}

	artifact =
		neuro_artifact_store_get(service->ctx.artifact_store, app_id);
	if (artifact != NULL && artifact->size_bytes > 0U &&
		(size_t)ent.size != artifact->size_bytes) {
		(void)neuro_artifact_store_set_state(
			service->ctx.artifact_store, app_id,
			NEURO_ARTIFACT_INVALID);
		(void)neuro_update_manager_verify_fail(
			service->ctx.update_manager, app_id,
			"artifact size mismatch");
		(void)persist_recovery_seed_snapshot(service);
		service->ops->publish_update_event(
			app_id, "verify", "error", "artifact size mismatch");
		service_log_transaction(service, app_id, "verify", request_id,
			"fail", -EIO, "artifact size mismatch");
		service->ops->reply_error(
			reply_ctx, request_id, "artifact size mismatch", 500);
		return;
	}

	ret = neuro_artifact_store_set_state(
		service->ctx.artifact_store, app_id, NEURO_ARTIFACT_VERIFIED);
	if (ret) {
		(void)neuro_update_manager_verify_fail(
			service->ctx.update_manager, app_id,
			"verify artifact state update failed");
		(void)persist_recovery_seed_snapshot(service);
		service->ops->publish_update_event(app_id, "verify", "error",
			"artifact state update failed");
		service_log_transaction(service, app_id, "verify", request_id,
			"fail", ret, "artifact state update failed");
		service->ops->reply_error(reply_ctx, request_id,
			"verify artifact state update failed", 500);
		return;
	}

	ret = neuro_update_manager_verify_complete(
		service->ctx.update_manager, app_id);
	if (ret) {
		(void)neuro_update_manager_verify_fail(
			service->ctx.update_manager, app_id,
			"verify complete failed");
		(void)persist_recovery_seed_snapshot(service);
		service->ops->publish_update_event(
			app_id, "verify", "error", "verify complete failed");
		service_log_transaction(service, app_id, "verify", request_id,
			"fail", ret, "verify complete failed");
		service->ops->reply_error(
			reply_ctx, request_id, "verify complete failed", 500);
		return;
	}

	save_ret = persist_recovery_seed_snapshot(service);
	if (save_ret) {
		LOG_WRN("verify recovery seed save failed: %d", save_ret);
	}

	service->ops->publish_update_event(
		app_id, "verify", "ok", "artifact present");
	snprintk(json, sizeof(json),
		"{\"status\":\"ok\",\"request_id\":\"%s\",\"node_id\":\"%s\",\"app_id\":\"%s\",\"size\":%zu}",
		request_id, service->ops->node_id, app_id, ent.size);
	reply.request_id = request_id;
	reply.node_id = service->ops->node_id;
	reply.app_id = app_id;
	reply.path = "";
	reply.transport = "";
	reply.size = (uint32_t)ent.size;
	reply.reason = "";
	service_log_transaction(service, app_id, "verify", request_id, "commit",
		0, "verify success");
	query_reply_update_cbor_or_json(
		service, reply_ctx, request_id, app_id, "verify", &reply, json);
}

static void handle_update_activate(struct neuro_unit_update_service *service,
	const struct neuro_unit_reply_context *reply_ctx, const char *app_id,
	const char *payload, const char *request_id)
{
	struct neuro_request_metadata metadata;
	const struct neuro_request_metadata *request_metadata;
	const struct neuro_unit_request_fields *request_fields;
	char start_args[NEURO_UNIT_UPDATE_FIELD_LEN] = "";
	char path[NEURO_UNIT_UPDATE_FIELD_LEN];
	char resource[64];
	char error_detail[128];
	char json[NEURO_UNIT_UPDATE_JSON_LEN];
	struct neuro_protocol_update_reply_cbor reply;
	int64_t t_start_ms;
	int64_t t_stage_ms;
	int ret;
	int save_ret;

	service_log_transaction(
		service, app_id, "activate", request_id, "begin", 0, "enter");
	request_metadata = neuro_unit_reply_context_metadata(reply_ctx);
	request_fields = neuro_unit_reply_context_request_fields(reply_ctx);
	if (request_metadata == NULL) {
		neuro_request_metadata_init(&metadata);
		(void)neuro_request_metadata_parse(payload, &metadata);
		request_metadata = &metadata;
	}
	t_start_ms = k_uptime_get();
	LOG_INF("activate request: app=%s request_id=%s lease_id=%s", app_id,
		request_id != NULL ? request_id : "-",
		request_metadata->lease_id);

	snprintk(resource, sizeof(resource), "update/app/%s/activate", app_id);
	t_stage_ms = k_uptime_get();
	if (!service->ops->require_resource_lease_or_reply(
		    reply_ctx, request_id, resource, request_metadata)) {
		LOG_WRN("activate lease check failed: app=%s elapsed=%lldms",
			app_id, (long long)(k_uptime_get() - t_start_ms));
		service_log_transaction(service, app_id, "activate", request_id,
			"reject", -EPERM, "lease check failed");
		return;
	}
	LOG_INF("activate lease check ok: app=%s elapsed=%lldms", app_id,
		(long long)(k_uptime_get() - t_stage_ms));

	t_stage_ms = k_uptime_get();
	ret = neuro_update_manager_activate_begin(
		service->ctx.update_manager, app_id);
	if (ret) {
		service_log_transaction(service, app_id, "activate", request_id,
			"reject", ret, "activate state conflict");
		service->ops->reply_error(
			reply_ctx, request_id, "activate state conflict", 409);
		return;
	}
	LOG_INF("activate manager begin ok: app=%s elapsed=%lldms", app_id,
		(long long)(k_uptime_get() - t_stage_ms));

	if (service->ops->runtime_app_is_loaded(app_id)) {
		LOG_INF("activate: unloading existing runtime app=%s", app_id);
		t_stage_ms = k_uptime_get();
		ret = app_runtime_unload(app_id);
		if (ret) {
			(void)neuro_update_manager_activate_fail(
				service->ctx.update_manager, app_id,
				"existing app unload failed");
			(void)persist_recovery_seed_snapshot(service);
			service->ops->publish_update_event(app_id, "activate",
				"error", "existing app unload failed");
			service_log_transaction(service, app_id, "activate",
				request_id, "fail", ret,
				"existing app unload failed");
			service->ops->reply_error(reply_ctx, request_id,
				"activate unload existing app failed", 500);
			return;
		}
		LOG_INF("activate: existing runtime app unloaded app=%s elapsed=%lldms",
			app_id, (long long)(k_uptime_get() - t_stage_ms));
	}

	build_app_path(app_id, path, sizeof(path));
	LOG_INF("activate begin: app=%s path=%s", app_id, path);
	LOG_INF("activate: calling app_runtime_load app=%s", app_id);
	t_stage_ms = k_uptime_get();
	ret = app_runtime_load(app_id, path);
	if (ret) {
		format_runtime_failure_detail(error_detail,
			sizeof(error_detail), "activate load failed", ret);
		(void)neuro_update_manager_activate_fail(
			service->ctx.update_manager, app_id, error_detail);
		(void)persist_recovery_seed_snapshot(service);
		service->ops->publish_update_event(
			app_id, "activate", "error", error_detail);
		service_log_transaction(service, app_id, "activate", request_id,
			"fail", ret, error_detail);
		service->ops->reply_error(
			reply_ctx, request_id, error_detail, 500);
		return;
	}
	LOG_INF("activate: app_runtime_load ok app=%s elapsed=%lldms", app_id,
		(long long)(k_uptime_get() - t_stage_ms));

	if (request_fields != NULL && request_fields->start_args[0] != '\0') {
		snprintk(start_args, sizeof(start_args), "%s",
			request_fields->start_args);
	} else {
		(void)neuro_json_extract_string(
			payload, "start_args", start_args, sizeof(start_args));
	}
	LOG_INF("activate: calling app_runtime_start app=%s start_args=%s",
		app_id, start_args[0] ? start_args : "<null>");
	t_stage_ms = k_uptime_get();
	ret = app_runtime_start(app_id, start_args[0] ? start_args : NULL);
	if (ret) {
		format_runtime_failure_detail(error_detail,
			sizeof(error_detail), "activate start failed", ret);
		(void)neuro_update_manager_activate_fail(
			service->ctx.update_manager, app_id, error_detail);
		(void)persist_recovery_seed_snapshot(service);
		service->ops->publish_update_event(
			app_id, "activate", "error", error_detail);
		service_log_transaction(service, app_id, "activate", request_id,
			"fail", ret, error_detail);
		service->ops->reply_error(
			reply_ctx, request_id, error_detail, 500);
		return;
	}
	LOG_INF("activate: app_runtime_start ok app=%s elapsed=%lldms", app_id,
		(long long)(k_uptime_get() - t_stage_ms));
	(void)neuro_artifact_store_set_state(
		service->ctx.artifact_store, app_id, NEURO_ARTIFACT_ACTIVE);
	t_stage_ms = k_uptime_get();
	ret = neuro_update_manager_activate_complete(
		service->ctx.update_manager, app_id);
	if (ret) {
		service_log_transaction(service, app_id, "activate", request_id,
			"fail", ret, "activate complete failed");
		service->ops->reply_error(
			reply_ctx, request_id, "activate complete failed", 500);
		return;
	}
	LOG_INF("activate manager complete ok: app=%s elapsed=%lldms", app_id,
		(long long)(k_uptime_get() - t_stage_ms));

	ret = neuro_update_manager_record_stable_ref(
		service->ctx.update_manager, app_id, path);
	if (ret) {
		LOG_WRN("record stable ref failed: app=%s ret=%d", app_id, ret);
	}

	save_ret = persist_recovery_seed_snapshot(service);
	if (save_ret) {
		LOG_WRN("activate recovery seed save failed: %d", save_ret);
	}
	service->ops->register_app_callback_command(app_id);

	service->ops->publish_update_event(
		app_id, "activate", "ok", "app running");
	service->ops->publish_state_event();
	snprintk(json, sizeof(json),
		"{\"status\":\"ok\",\"request_id\":\"%s\",\"node_id\":\"%s\",\"app_id\":\"%s\",\"path\":\"%s\"}",
		request_id, service->ops->node_id, app_id, path);
	reply.request_id = request_id;
	reply.node_id = service->ops->node_id;
	reply.app_id = app_id;
	reply.path = path;
	reply.transport = "";
	reply.size = 0U;
	reply.reason = "";
	service_log_transaction(service, app_id, "activate", request_id,
		"commit", 0, "activate success");
	LOG_INF("activate response ready: app=%s total_elapsed=%lldms", app_id,
		(long long)(k_uptime_get() - t_start_ms));
	query_reply_update_cbor_or_json(service, reply_ctx, request_id, app_id,
		"activate", &reply, json);
}

static void handle_update_rollback(struct neuro_unit_update_service *service,
	const struct neuro_unit_reply_context *reply_ctx, const char *app_id,
	const char *payload, const char *request_id)
{
	struct neuro_request_metadata metadata;
	const struct neuro_request_metadata *request_metadata;
	const struct neuro_unit_request_fields *request_fields;
	char reason[64] = "rollback requested";
	char resource[64];
	char json[NEURO_UNIT_UPDATE_JSON_LEN];
	struct neuro_protocol_update_reply_cbor reply;
	const char *stable_ref;
	int ret;
	int save_ret;

	service_log_transaction(
		service, app_id, "recover", request_id, "begin", 0, "enter");
	request_metadata = neuro_unit_reply_context_metadata(reply_ctx);
	request_fields = neuro_unit_reply_context_request_fields(reply_ctx);
	if (request_metadata == NULL) {
		neuro_request_metadata_init(&metadata);
		(void)neuro_request_metadata_parse(payload, &metadata);
		request_metadata = &metadata;
	}
	if (request_fields != NULL && request_fields->reason[0] != '\0') {
		snprintk(reason, sizeof(reason), "%s", request_fields->reason);
	} else {
		(void)neuro_json_extract_string(
			payload, "reason", reason, sizeof(reason));
	}

	snprintk(resource, sizeof(resource), "update/app/%s/rollback", app_id);
	if (!service->ops->require_resource_lease_or_reply(
		    reply_ctx, request_id, resource, request_metadata)) {
		service_log_transaction(service, app_id, "recover", request_id,
			"reject", -EPERM, "lease check failed");
		return;
	}

	ret = neuro_update_manager_rollback_begin(
		service->ctx.update_manager, app_id, reason);
	if (ret) {
		service_log_transaction(service, app_id, "recover", request_id,
			"reject", ret, "rollback state conflict");
		service->ops->reply_error(
			reply_ctx, request_id, "rollback state conflict", 409);
		return;
	}

	save_ret = persist_recovery_seed_snapshot(service);
	if (save_ret) {
		(void)neuro_update_manager_rollback_fail(
			service->ctx.update_manager, app_id,
			"rollback checkpoint save failed");
		LOG_WRN("rollback checkpoint seed save failed: %d", save_ret);
		service->ops->publish_update_event(
			app_id, "rollback", "error", "checkpoint save failed");
		service_log_transaction(service, app_id, "recover", request_id,
			"fail", save_ret, "checkpoint save failed");
		service->ops->reply_error(reply_ctx, request_id,
			"rollback checkpoint save failed", 500);
		return;
	}

	ret = neuro_update_manager_rollback_mark_in_progress(
		service->ctx.update_manager, app_id);
	if (ret) {
		(void)neuro_update_manager_rollback_fail(
			service->ctx.update_manager, app_id,
			"rollback state transition failed");
		service_log_transaction(service, app_id, "recover", request_id,
			"fail", ret, "rollback state transition failed");
		service->ops->reply_error(reply_ctx, request_id,
			"rollback state transition failed", 500);
		return;
	}

	(void)app_runtime_stop(app_id);
	ret = app_runtime_unload(app_id);
	if (ret && ret != -ENOENT) {
		(void)neuro_update_manager_rollback_fail(
			service->ctx.update_manager, app_id,
			"rollback unload failed");
		save_ret = persist_recovery_seed_snapshot(service);
		if (save_ret) {
			LOG_WRN("rollback failure seed save failed: %d",
				save_ret);
		}
		service->ops->publish_update_event(
			app_id, "rollback", "error", "unload failed");
		service_log_transaction(service, app_id, "recover", request_id,
			"fail", ret, "rollback unload failed");
		service->ops->reply_error(
			reply_ctx, request_id, "rollback unload failed", 500);
		return;
	}

	(void)neuro_app_command_registry_remove_app(app_id);

	stable_ref = neuro_update_manager_stable_ref_for(
		service->ctx.update_manager, app_id);
	if (stable_ref[0] != '\0') {
		ret = app_runtime_load(app_id, stable_ref);
		if (ret == 0) {
			ret = app_runtime_start(app_id, NULL);
		}

		if (ret) {
			(void)neuro_update_manager_rollback_fail(
				service->ctx.update_manager, app_id,
				"stable restore failed");
			save_ret = persist_recovery_seed_snapshot(service);
			if (save_ret) {
				LOG_WRN("rollback restore seed save failed: %d",
					save_ret);
			}
			service->ops->publish_update_event(app_id, "rollback",
				"error", "stable restore failed");
			service_log_transaction(service, app_id, "recover",
				request_id, "fail", ret,
				"stable restore failed");
			service->ops->reply_error(reply_ctx, request_id,
				"rollback stable restore failed", 500);
			return;
		}

		service->ops->register_app_callback_command(app_id);
		(void)neuro_artifact_store_set_state(
			service->ctx.artifact_store, app_id,
			NEURO_ARTIFACT_ACTIVE);
	} else {
		(void)neuro_artifact_store_remove(
			service->ctx.artifact_store, app_id);
	}

	ret = neuro_update_manager_rollback_complete(
		service->ctx.update_manager, app_id);
	if (ret) {
		service_log_transaction(service, app_id, "recover", request_id,
			"fail", ret, "rollback complete failed");
		service->ops->reply_error(
			reply_ctx, request_id, "rollback complete failed", 500);
		return;
	}

	save_ret = persist_recovery_seed_snapshot(service);
	if (save_ret) {
		LOG_WRN("rollback recovery seed save failed: %d", save_ret);
	}

	service->ops->publish_update_event(app_id, "rollback", "ok",
		stable_ref[0] != '\0' ? "stable restored" : "artifact removed");
	service->ops->publish_state_event();
	snprintk(json, sizeof(json),
		"{\"status\":\"ok\",\"request_id\":\"%s\",\"node_id\":\"%s\",\"app_id\":\"%s\",\"reason\":\"%s\"}",
		request_id, service->ops->node_id, app_id, reason);
	reply.request_id = request_id;
	reply.node_id = service->ops->node_id;
	reply.app_id = app_id;
	reply.path = "";
	reply.transport = "";
	reply.size = 0U;
	reply.reason = reason;
	service_log_transaction(service, app_id, "recover", request_id,
		"commit", 0, "recover success");
	query_reply_update_cbor_or_json(service, reply_ctx, request_id, app_id,
		"rollback", &reply, json);
}

int neuro_unit_update_service_init(struct neuro_unit_update_service *service,
	const struct neuro_unit_update_service_ctx *ctx,
	const struct neuro_unit_update_service_ops *ops)
{
	if (service == NULL || ctx == NULL || ops == NULL ||
		ctx->update_manager == NULL || ctx->artifact_store == NULL ||
		ctx->recovery_seed_store == NULL || ops->node_id == NULL ||
		ops->reply_error == NULL ||
		ops->require_resource_lease_or_reply == NULL ||
		ops->query_reply_json == NULL ||
		ops->publish_update_event == NULL ||
		ops->publish_state_event == NULL ||
		ops->runtime_app_is_loaded == NULL ||
		ops->register_app_callback_command == NULL) {
		return -EINVAL;
	}

	service->ctx = *ctx;
	service->ops = ops;
	service->recovery_seed_initialized = false;
	return 0;
}

void neuro_unit_update_service_handle_action(
	struct neuro_unit_update_service *service,
	const struct neuro_unit_reply_context *reply_ctx, const char *app_id,
	const char *action, const char *payload, const char *request_id)
{
	const char *txn_action = action;

	if (service == NULL || service->ops == NULL || reply_ctx == NULL ||
		app_id == NULL || action == NULL || payload == NULL ||
		request_id == NULL) {
		return;
	}

	if (strcmp(action, "rollback") == 0) {
		txn_action = "recover";
	}

	service_log_transaction(service, app_id, txn_action, request_id,
		"ingress", 0, "service dispatch");

	if (strcmp(action, "prepare") == 0) {
		handle_update_prepare(
			service, reply_ctx, app_id, payload, request_id);
		service_log_transaction(service, app_id, txn_action, request_id,
			"egress", 0, "service done");
		return;
	}

	if (strcmp(action, "verify") == 0) {
		handle_update_verify(service, reply_ctx, app_id, request_id);
		service_log_transaction(service, app_id, txn_action, request_id,
			"egress", 0, "service done");
		return;
	}

	if (strcmp(action, "activate") == 0) {
		handle_update_activate(
			service, reply_ctx, app_id, payload, request_id);
		service_log_transaction(service, app_id, txn_action, request_id,
			"egress", 0, "service done");
		return;
	}

	if (strcmp(action, "rollback") == 0 || strcmp(action, "recover") == 0) {
		handle_update_rollback(
			service, reply_ctx, app_id, payload, request_id);
		service_log_transaction(service, app_id, txn_action, request_id,
			"egress", 0, "service done");
		return;
	}

	service->ops->reply_error(
		reply_ctx, request_id, "unsupported update path", 404);

	service_log_transaction(service, app_id, txn_action, request_id,
		"egress", 0, "service done");
}
