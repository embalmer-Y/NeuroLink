#include "neuro_update_manager.h"

#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

static void copy_bounded(char *dst, size_t dst_len, const char *src)
{
	if (dst == NULL || dst_len == 0U) {
		return;
	}

	if (src == NULL) {
		dst[0] = '\0';
		return;
	}

	snprintf(dst, dst_len, "%s", src);
}

static struct neuro_update_entry *find_entry(
	struct neuro_update_manager *manager, const char *app_id)
{
	size_t i;

	for (i = 0; i < NEURO_UPDATE_MANAGER_MAX_ENTRIES; i++) {
		if (manager->entries[i].used &&
			strcmp(manager->entries[i].app_id, app_id) == 0) {
			return &manager->entries[i];
		}
	}

	return NULL;
}

static struct neuro_update_entry *find_or_create_entry(
	struct neuro_update_manager *manager, const char *app_id)
{
	struct neuro_update_entry *entry;
	size_t i;

	entry = find_entry(manager, app_id);
	if (entry != NULL) {
		return entry;
	}

	for (i = 0; i < NEURO_UPDATE_MANAGER_MAX_ENTRIES; i++) {
		if (!manager->entries[i].used) {
			manager->entries[i].used = true;
			copy_bounded(manager->entries[i].app_id,
				sizeof(manager->entries[i].app_id), app_id);
			manager->entries[i].state = NEURO_UPDATE_STATE_NONE;
			manager->entries[i].last_error[0] = '\0';
			manager->entries[i].rollback_reason[0] = '\0';
			manager->entries[i].stable_ref[0] = '\0';
			return &manager->entries[i];
		}
	}

	return NULL;
}

void neuro_update_manager_init(struct neuro_update_manager *manager)
{
	if (manager == NULL) {
		return;
	}

	memset(manager, 0, sizeof(*manager));
}

int neuro_update_manager_prepare_begin(
	struct neuro_update_manager *manager, const char *app_id)
{
	struct neuro_update_entry *entry;

	if (manager == NULL || app_id == NULL || app_id[0] == '\0') {
		return -EINVAL;
	}

	entry = find_or_create_entry(manager, app_id);
	if (entry == NULL) {
		return -ENOSPC;
	}

	if (entry->state == NEURO_UPDATE_STATE_PREPARE_REQUESTED ||
		entry->state == NEURO_UPDATE_STATE_PREPARING ||
		entry->state == NEURO_UPDATE_STATE_VERIFYING ||
		entry->state == NEURO_UPDATE_STATE_ACTIVATING) {
		return -EBUSY;
	}

	/*
	 * Prepare admission clears the previous error and marks the entry as an
	 * in-flight update candidate before later verify/activate stages
	 * advance it.
	 */
	entry->state = NEURO_UPDATE_STATE_PREPARE_REQUESTED;
	entry->state = NEURO_UPDATE_STATE_PREPARING;
	entry->last_error[0] = '\0';
	return 0;
}

int neuro_update_manager_prepare_complete(
	struct neuro_update_manager *manager, const char *app_id)
{
	struct neuro_update_entry *entry;

	if (manager == NULL || app_id == NULL || app_id[0] == '\0') {
		return -EINVAL;
	}

	entry = find_entry(manager, app_id);
	if (entry == NULL || entry->state != NEURO_UPDATE_STATE_PREPARING) {
		return -EPERM;
	}

	entry->state = NEURO_UPDATE_STATE_PREPARED;
	return 0;
}

int neuro_update_manager_prepare_fail(struct neuro_update_manager *manager,
	const char *app_id, const char *reason)
{
	struct neuro_update_entry *entry;

	if (manager == NULL || app_id == NULL || app_id[0] == '\0') {
		return -EINVAL;
	}

	entry = find_entry(manager, app_id);
	if (entry == NULL ||
		(entry->state != NEURO_UPDATE_STATE_PREPARE_REQUESTED &&
			entry->state != NEURO_UPDATE_STATE_PREPARING)) {
		return -EPERM;
	}

	entry->state = NEURO_UPDATE_STATE_FAILED;
	copy_bounded(entry->last_error, sizeof(entry->last_error), reason);
	return 0;
}

int neuro_update_manager_verify_begin(
	struct neuro_update_manager *manager, const char *app_id)
{
	struct neuro_update_entry *entry;

	if (manager == NULL || app_id == NULL || app_id[0] == '\0') {
		return -EINVAL;
	}

	entry = find_entry(manager, app_id);
	if (entry == NULL || entry->state != NEURO_UPDATE_STATE_PREPARED) {
		return -EPERM;
	}

	entry->state = NEURO_UPDATE_STATE_VERIFYING;
	entry->last_error[0] = '\0';
	return 0;
}

int neuro_update_manager_verify_complete(
	struct neuro_update_manager *manager, const char *app_id)
{
	struct neuro_update_entry *entry;

	if (manager == NULL || app_id == NULL || app_id[0] == '\0') {
		return -EINVAL;
	}

	entry = find_entry(manager, app_id);
	if (entry == NULL || entry->state != NEURO_UPDATE_STATE_VERIFYING) {
		return -EPERM;
	}

	entry->state = NEURO_UPDATE_STATE_VERIFIED;
	return 0;
}

int neuro_update_manager_verify_fail(struct neuro_update_manager *manager,
	const char *app_id, const char *reason)
{
	struct neuro_update_entry *entry;

	if (manager == NULL || app_id == NULL || app_id[0] == '\0') {
		return -EINVAL;
	}

	entry = find_entry(manager, app_id);
	if (entry == NULL || entry->state != NEURO_UPDATE_STATE_VERIFYING) {
		return -EPERM;
	}

	entry->state = NEURO_UPDATE_STATE_FAILED;
	copy_bounded(entry->last_error, sizeof(entry->last_error), reason);
	return 0;
}

int neuro_update_manager_activate_begin(
	struct neuro_update_manager *manager, const char *app_id)
{
	struct neuro_update_entry *entry;

	if (manager == NULL || app_id == NULL || app_id[0] == '\0') {
		return -EINVAL;
	}

	entry = find_entry(manager, app_id);
	if (entry == NULL || entry->state != NEURO_UPDATE_STATE_VERIFIED) {
		return -EPERM;
	}

	entry->state = NEURO_UPDATE_STATE_ACTIVATING;
	entry->last_error[0] = '\0';
	return 0;
}

int neuro_update_manager_activate_complete(
	struct neuro_update_manager *manager, const char *app_id)
{
	struct neuro_update_entry *entry;

	if (manager == NULL || app_id == NULL || app_id[0] == '\0') {
		return -EINVAL;
	}

	entry = find_entry(manager, app_id);
	if (entry == NULL || entry->state != NEURO_UPDATE_STATE_ACTIVATING) {
		return -EPERM;
	}

	entry->state = NEURO_UPDATE_STATE_ACTIVE;
	return 0;
}

int neuro_update_manager_activate_fail(struct neuro_update_manager *manager,
	const char *app_id, const char *reason)
{
	struct neuro_update_entry *entry;

	if (manager == NULL || app_id == NULL || app_id[0] == '\0') {
		return -EINVAL;
	}

	entry = find_entry(manager, app_id);
	if (entry == NULL || entry->state != NEURO_UPDATE_STATE_ACTIVATING) {
		return -EPERM;
	}

	entry->state = NEURO_UPDATE_STATE_FAILED;
	copy_bounded(entry->last_error, sizeof(entry->last_error), reason);
	return 0;
}

int neuro_update_manager_record_stable_ref(struct neuro_update_manager *manager,
	const char *app_id, const char *stable_ref)
{
	struct neuro_update_entry *entry;

	if (manager == NULL || app_id == NULL || app_id[0] == '\0' ||
		stable_ref == NULL || stable_ref[0] == '\0') {
		return -EINVAL;
	}

	entry = find_entry(manager, app_id);
	if (entry == NULL) {
		return -EPERM;
	}

	copy_bounded(entry->stable_ref, sizeof(entry->stable_ref), stable_ref);
	return 0;
}

int neuro_update_manager_remove(
	struct neuro_update_manager *manager, const char *app_id)
{
	struct neuro_update_entry *entry;

	if (manager == NULL || app_id == NULL || app_id[0] == '\0') {
		return -EINVAL;
	}

	entry = find_entry(manager, app_id);
	if (entry == NULL) {
		return -ENOENT;
	}

	memset(entry, 0, sizeof(*entry));
	return 0;
}

int neuro_update_manager_rollback_begin(struct neuro_update_manager *manager,
	const char *app_id, const char *reason)
{
	struct neuro_update_entry *entry;

	if (manager == NULL || app_id == NULL || app_id[0] == '\0') {
		return -EINVAL;
	}

	entry = find_entry(manager, app_id);
	if (entry == NULL) {
		return -EPERM;
	}

	if (entry->state == NEURO_UPDATE_STATE_ROLLBACK_PENDING ||
		entry->state == NEURO_UPDATE_STATE_ROLLING_BACK) {
		return -EBUSY;
	}

	if (entry->state != NEURO_UPDATE_STATE_ACTIVE &&
		entry->state != NEURO_UPDATE_STATE_FAILED) {
		return -EPERM;
	}

	/*
	 * Rollback is intentionally split into pending and in-progress states
	 * so the caller can persist rollback intent before destructive
	 * unload/restore work.
	 */
	entry->state = NEURO_UPDATE_STATE_ROLLBACK_PENDING;
	copy_bounded(
		entry->rollback_reason, sizeof(entry->rollback_reason), reason);
	return 0;
}

int neuro_update_manager_rollback_mark_in_progress(
	struct neuro_update_manager *manager, const char *app_id)
{
	struct neuro_update_entry *entry;

	if (manager == NULL || app_id == NULL || app_id[0] == '\0') {
		return -EINVAL;
	}

	entry = find_entry(manager, app_id);
	if (entry == NULL ||
		entry->state != NEURO_UPDATE_STATE_ROLLBACK_PENDING) {
		return -EPERM;
	}

	entry->state = NEURO_UPDATE_STATE_ROLLING_BACK;
	return 0;
}

int neuro_update_manager_rollback_complete(
	struct neuro_update_manager *manager, const char *app_id)
{
	struct neuro_update_entry *entry;

	if (manager == NULL || app_id == NULL || app_id[0] == '\0') {
		return -EINVAL;
	}

	entry = find_entry(manager, app_id);
	if (entry == NULL || entry->state != NEURO_UPDATE_STATE_ROLLING_BACK) {
		return -EPERM;
	}

	entry->state = NEURO_UPDATE_STATE_ROLLED_BACK;
	return 0;
}

int neuro_update_manager_rollback_fail(struct neuro_update_manager *manager,
	const char *app_id, const char *reason)
{
	struct neuro_update_entry *entry;

	if (manager == NULL || app_id == NULL || app_id[0] == '\0') {
		return -EINVAL;
	}

	entry = find_entry(manager, app_id);
	if (entry == NULL ||
		(entry->state != NEURO_UPDATE_STATE_ROLLBACK_PENDING &&
			entry->state != NEURO_UPDATE_STATE_ROLLING_BACK)) {
		return -EPERM;
	}

	entry->state = NEURO_UPDATE_STATE_FAILED;
	copy_bounded(entry->last_error, sizeof(entry->last_error), reason);
	return 0;
}

int neuro_update_manager_reconcile_after_boot(
	struct neuro_update_manager *manager, const char *app_id,
	bool runtime_active, bool artifact_available)
{
	struct neuro_update_entry *entry;

	if (manager == NULL || app_id == NULL || app_id[0] == '\0') {
		return -EINVAL;
	}

	entry = find_entry(manager, app_id);
	if (entry == NULL) {
		return -ENOENT;
	}

	/*
	 * Boot reconciliation stays conservative: if power was lost in a
	 * transient stage or persisted state no longer matches runtime/artifact
	 * reality, the entry is marked failed and higher layers decide the next
	 * operator action.
	 */
	switch (entry->state) {
	case NEURO_UPDATE_STATE_PREPARE_REQUESTED:
	case NEURO_UPDATE_STATE_PREPARING:
	case NEURO_UPDATE_STATE_VERIFYING:
	case NEURO_UPDATE_STATE_ACTIVATING:
	case NEURO_UPDATE_STATE_ROLLBACK_PENDING:
	case NEURO_UPDATE_STATE_ROLLING_BACK:
		entry->state = NEURO_UPDATE_STATE_FAILED;
		copy_bounded(entry->last_error, sizeof(entry->last_error),
			"recovery interrupted transition");
		break;
	case NEURO_UPDATE_STATE_PREPARED:
	case NEURO_UPDATE_STATE_VERIFIED:
		if (!artifact_available) {
			entry->state = NEURO_UPDATE_STATE_FAILED;
			copy_bounded(entry->last_error,
				sizeof(entry->last_error),
				"recovery artifact missing");
		}
		break;
	case NEURO_UPDATE_STATE_ACTIVE:
		if (!runtime_active) {
			entry->state = NEURO_UPDATE_STATE_FAILED;
			copy_bounded(entry->last_error,
				sizeof(entry->last_error),
				"recovery runtime state mismatch");
		}
		break;
	default:
		break;
	}

	return 0;
}

enum neuro_update_state neuro_update_manager_state_for(
	const struct neuro_update_manager *manager, const char *app_id)
{
	size_t i;

	if (manager == NULL || app_id == NULL || app_id[0] == '\0') {
		return NEURO_UPDATE_STATE_NONE;
	}

	for (i = 0; i < NEURO_UPDATE_MANAGER_MAX_ENTRIES; i++) {
		if (manager->entries[i].used &&
			strcmp(manager->entries[i].app_id, app_id) == 0) {
			return manager->entries[i].state;
		}
	}

	return NEURO_UPDATE_STATE_NONE;
}

const char *neuro_update_manager_stable_ref_for(
	const struct neuro_update_manager *manager, const char *app_id)
{
	size_t i;

	if (manager == NULL || app_id == NULL || app_id[0] == '\0') {
		return "";
	}

	for (i = 0; i < NEURO_UPDATE_MANAGER_MAX_ENTRIES; i++) {
		if (manager->entries[i].used &&
			strcmp(manager->entries[i].app_id, app_id) == 0) {
			return manager->entries[i].stable_ref;
		}
	}

	return "";
}

const char *neuro_update_manager_rollback_reason_for(
	const struct neuro_update_manager *manager, const char *app_id)
{
	size_t i;

	if (manager == NULL || app_id == NULL || app_id[0] == '\0') {
		return "";
	}

	for (i = 0; i < NEURO_UPDATE_MANAGER_MAX_ENTRIES; i++) {
		if (manager->entries[i].used &&
			strcmp(manager->entries[i].app_id, app_id) == 0) {
			return manager->entries[i].rollback_reason;
		}
	}

	return "";
}

const char *neuro_update_manager_last_error_for(
	const struct neuro_update_manager *manager, const char *app_id)
{
	size_t i;

	if (manager == NULL || app_id == NULL || app_id[0] == '\0') {
		return "";
	}

	for (i = 0; i < NEURO_UPDATE_MANAGER_MAX_ENTRIES; i++) {
		if (manager->entries[i].used &&
			strcmp(manager->entries[i].app_id, app_id) == 0) {
			return manager->entries[i].last_error;
		}
	}

	return "";
}

size_t neuro_update_manager_export_entries(
	const struct neuro_update_manager *manager,
	struct neuro_update_entry *entries, size_t max_entries)
{
	size_t i;
	size_t exported = 0U;

	if (manager == NULL || entries == NULL || max_entries == 0U) {
		return 0U;
	}

	for (i = 0; i < NEURO_UPDATE_MANAGER_MAX_ENTRIES; i++) {
		if (!manager->entries[i].used) {
			continue;
		}

		if (exported >= max_entries) {
			break;
		}

		entries[exported++] = manager->entries[i];
	}

	return exported;
}

int neuro_update_manager_import_entries(struct neuro_update_manager *manager,
	const struct neuro_update_entry *entries, size_t entry_count)
{
	size_t i;

	if (manager == NULL) {
		return -EINVAL;
	}

	if (entries == NULL && entry_count != 0U) {
		return -EINVAL;
	}

	if (entry_count > NEURO_UPDATE_MANAGER_MAX_ENTRIES) {
		return -ENOSPC;
	}

	memset(manager, 0, sizeof(*manager));
	for (i = 0; i < entry_count; i++) {
		manager->entries[i] = entries[i];
		manager->entries[i].used = entries[i].used;
	}

	return 0;
}

const char *neuro_update_manager_state_to_str(enum neuro_update_state state)
{
	switch (state) {
	case NEURO_UPDATE_STATE_NONE:
		return "NONE";
	case NEURO_UPDATE_STATE_PREPARE_REQUESTED:
		return "PREPARE_REQUESTED";
	case NEURO_UPDATE_STATE_PREPARING:
		return "PREPARING";
	case NEURO_UPDATE_STATE_PREPARED:
		return "PREPARED";
	case NEURO_UPDATE_STATE_VERIFYING:
		return "VERIFYING";
	case NEURO_UPDATE_STATE_VERIFIED:
		return "VERIFIED";
	case NEURO_UPDATE_STATE_ACTIVATING:
		return "ACTIVATING";
	case NEURO_UPDATE_STATE_ACTIVE:
		return "ACTIVE";
	case NEURO_UPDATE_STATE_ROLLBACK_PENDING:
		return "ROLLBACK_PENDING";
	case NEURO_UPDATE_STATE_ROLLING_BACK:
		return "ROLLING_BACK";
	case NEURO_UPDATE_STATE_ROLLED_BACK:
		return "ROLLED_BACK";
	case NEURO_UPDATE_STATE_FAILED:
		return "FAILED";
	default:
		return "UNKNOWN";
	}
}
