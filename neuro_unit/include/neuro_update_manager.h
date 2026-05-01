#ifndef NEURO_UPDATE_MANAGER_H
#define NEURO_UPDATE_MANAGER_H

#include <stddef.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NEURO_UPDATE_MANAGER_MAX_ENTRIES 4

enum neuro_update_state {
	NEURO_UPDATE_STATE_NONE = 0,
	NEURO_UPDATE_STATE_PREPARE_REQUESTED,
	NEURO_UPDATE_STATE_PREPARING,
	NEURO_UPDATE_STATE_PREPARED,
	NEURO_UPDATE_STATE_VERIFYING,
	NEURO_UPDATE_STATE_VERIFIED,
	NEURO_UPDATE_STATE_ACTIVATING,
	NEURO_UPDATE_STATE_ACTIVE,
	NEURO_UPDATE_STATE_ROLLBACK_PENDING,
	NEURO_UPDATE_STATE_ROLLING_BACK,
	NEURO_UPDATE_STATE_ROLLED_BACK,
	NEURO_UPDATE_STATE_FAILED,
};

struct neuro_update_entry {
	char app_id[32];
	enum neuro_update_state state;
	char last_error[64];
	char rollback_reason[64];
	char stable_ref[96];
	bool used;
};

struct neuro_update_manager {
	struct neuro_update_entry entries[NEURO_UPDATE_MANAGER_MAX_ENTRIES];
};

void neuro_update_manager_init(struct neuro_update_manager *manager);

int neuro_update_manager_prepare_begin(
	struct neuro_update_manager *manager, const char *app_id);
int neuro_update_manager_prepare_complete(
	struct neuro_update_manager *manager, const char *app_id);
int neuro_update_manager_prepare_fail(struct neuro_update_manager *manager,
	const char *app_id, const char *reason);

int neuro_update_manager_verify_begin(
	struct neuro_update_manager *manager, const char *app_id);
int neuro_update_manager_verify_complete(
	struct neuro_update_manager *manager, const char *app_id);
int neuro_update_manager_verify_fail(struct neuro_update_manager *manager,
	const char *app_id, const char *reason);

int neuro_update_manager_activate_begin(
	struct neuro_update_manager *manager, const char *app_id);
int neuro_update_manager_activate_complete(
	struct neuro_update_manager *manager, const char *app_id);
int neuro_update_manager_activate_fail(struct neuro_update_manager *manager,
	const char *app_id, const char *reason);

int neuro_update_manager_record_stable_ref(struct neuro_update_manager *manager,
	const char *app_id, const char *stable_ref);
int neuro_update_manager_remove(
	struct neuro_update_manager *manager, const char *app_id);
int neuro_update_manager_rollback_begin(struct neuro_update_manager *manager,
	const char *app_id, const char *reason);
int neuro_update_manager_rollback_mark_in_progress(
	struct neuro_update_manager *manager, const char *app_id);
int neuro_update_manager_rollback_complete(
	struct neuro_update_manager *manager, const char *app_id);
int neuro_update_manager_rollback_fail(struct neuro_update_manager *manager,
	const char *app_id, const char *reason);

int neuro_update_manager_reconcile_after_boot(
	struct neuro_update_manager *manager, const char *app_id,
	bool runtime_active, bool artifact_available);

enum neuro_update_state neuro_update_manager_state_for(
	const struct neuro_update_manager *manager, const char *app_id);
const char *neuro_update_manager_stable_ref_for(
	const struct neuro_update_manager *manager, const char *app_id);
const char *neuro_update_manager_rollback_reason_for(
	const struct neuro_update_manager *manager, const char *app_id);
const char *neuro_update_manager_last_error_for(
	const struct neuro_update_manager *manager, const char *app_id);

size_t neuro_update_manager_export_entries(
	const struct neuro_update_manager *manager,
	struct neuro_update_entry *entries, size_t max_entries);
int neuro_update_manager_import_entries(struct neuro_update_manager *manager,
	const struct neuro_update_entry *entries, size_t entry_count);
const char *neuro_update_manager_state_to_str(enum neuro_update_state state);

#ifdef __cplusplus
}
#endif

#endif
