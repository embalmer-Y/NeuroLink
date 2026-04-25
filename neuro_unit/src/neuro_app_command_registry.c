#include <zephyr/kernel.h>

#include <ctype.h>
#include <errno.h>
#include <string.h>

#include "neuro_app_command_registry.h"

#define NEURO_APPCMD_MAX_ENTRIES 16

struct neuro_app_command_entry {
	bool in_use;
	struct neuro_app_command_desc desc;
};

static struct k_mutex g_registry_lock;
static struct neuro_app_command_entry g_registry[NEURO_APPCMD_MAX_ENTRIES];

static bool neuro_app_command_name_valid(const char *name)
{
	size_t i;

	if (name == NULL || name[0] == '\0' ||
		strlen(name) > NEURO_APP_COMMAND_NAME_MAX_LEN) {
		return false;
	}

	for (i = 0; name[i] != '\0'; i++) {
		unsigned char ch = (unsigned char)name[i];

		if (isalnum(ch) || ch == '_' || ch == '-') {
			continue;
		}

		return false;
	}

	if (strcmp(name, "start") == 0 || strcmp(name, "stop") == 0 ||
		strcmp(name, "suspend") == 0 || strcmp(name, "resume") == 0 ||
		strcmp(name, "load") == 0 || strcmp(name, "unload") == 0 ||
		strcmp(name, "lease") == 0) {
		return false;
	}

	return true;
}

static bool neuro_app_id_valid(const char *app_id)
{
	return app_id != NULL && app_id[0] != '\0' &&
	       strlen(app_id) <= NEURO_APP_ID_MAX_LEN;
}

static int neuro_app_command_entry_find_locked(
	const char *app_id, const char *command_name)
{
	int i;

	for (i = 0; i < NEURO_APPCMD_MAX_ENTRIES; i++) {
		if (!g_registry[i].in_use) {
			continue;
		}

		if (strcmp(g_registry[i].desc.app_id, app_id) == 0 &&
			strcmp(g_registry[i].desc.command_name, command_name) ==
				0) {
			return i;
		}
	}

	return -ENOENT;
}

static int neuro_app_command_find_free_locked(void)
{
	int i;

	for (i = 0; i < NEURO_APPCMD_MAX_ENTRIES; i++) {
		if (!g_registry[i].in_use) {
			return i;
		}
	}

	return -ENOSPC;
}

int neuro_app_command_registry_init(void)
{
	k_mutex_init(&g_registry_lock);
	memset(g_registry, 0, sizeof(g_registry));
	return 0;
}

int neuro_app_command_registry_register(
	const struct neuro_app_command_desc *desc)
{
	int i;
	int free_idx = -1;
	int existing_idx;

	if (desc == NULL || !neuro_app_id_valid(desc->app_id) ||
		!neuro_app_command_name_valid(desc->command_name)) {
		return -EINVAL;
	}

	k_mutex_lock(&g_registry_lock, K_FOREVER);
	existing_idx = neuro_app_command_entry_find_locked(
		desc->app_id, desc->command_name);
	if (existing_idx >= 0) {
		g_registry[existing_idx].desc = *desc;
		g_registry[existing_idx].desc.state =
			NEURO_APPCMD_STATE_REGISTERED;
		k_mutex_unlock(&g_registry_lock);
		return 0;
	}

	for (i = 0; i < NEURO_APPCMD_MAX_ENTRIES; i++) {
		if (!g_registry[i].in_use) {
			free_idx = i;
			break;
		}
	}

	if (free_idx < 0) {
		k_mutex_unlock(&g_registry_lock);
		return -ENOSPC;
	}

	g_registry[free_idx].in_use = true;
	g_registry[free_idx].desc = *desc;
	g_registry[free_idx].desc.state = NEURO_APPCMD_STATE_REGISTERED;
	k_mutex_unlock(&g_registry_lock);
	return 0;
}

int neuro_app_command_registry_register_descriptors(const char *app_id,
	const struct neuro_app_command_desc *descs, size_t desc_count)
{
	size_t i;
	int needed_new_entries = 0;
	int free_slots = 0;

	if (!neuro_app_id_valid(app_id) || descs == NULL || desc_count == 0U) {
		return -EINVAL;
	}

	for (i = 0; i < desc_count; i++) {
		size_t j;

		if (!neuro_app_command_name_valid(descs[i].command_name)) {
			return -EINVAL;
		}

		for (j = i + 1U; j < desc_count; j++) {
			if (strcmp(descs[i].command_name,
				    descs[j].command_name) == 0) {
				return -EEXIST;
			}
		}
	}

	k_mutex_lock(&g_registry_lock, K_FOREVER);
	for (i = 0; i < desc_count; i++) {
		int idx = neuro_app_command_entry_find_locked(
			app_id, descs[i].command_name);

		if (idx < 0) {
			needed_new_entries++;
		}
	}

	for (i = 0; i < NEURO_APPCMD_MAX_ENTRIES; i++) {
		if (!g_registry[i].in_use) {
			free_slots++;
		}
	}

	if (needed_new_entries > free_slots) {
		k_mutex_unlock(&g_registry_lock);
		return -ENOSPC;
	}

	for (i = 0; i < desc_count; i++) {
		int idx = neuro_app_command_entry_find_locked(
			app_id, descs[i].command_name);

		if (idx < 0) {
			idx = neuro_app_command_find_free_locked();
			if (idx < 0) {
				k_mutex_unlock(&g_registry_lock);
				return -ENOSPC;
			}
			g_registry[idx].in_use = true;
		}

		g_registry[idx].desc = descs[i];
		snprintk(g_registry[idx].desc.app_id,
			sizeof(g_registry[idx].desc.app_id), "%s", app_id);
		g_registry[idx].desc.state = NEURO_APPCMD_STATE_REGISTERED;
	}

	k_mutex_unlock(&g_registry_lock);
	return 0;
}

int neuro_app_command_registry_set_enabled(
	const char *app_id, const char *command_name, bool enabled)
{
	int idx;

	if (!neuro_app_id_valid(app_id) ||
		!neuro_app_command_name_valid(command_name)) {
		return -EINVAL;
	}

	k_mutex_lock(&g_registry_lock, K_FOREVER);
	idx = neuro_app_command_entry_find_locked(app_id, command_name);
	if (idx < 0) {
		k_mutex_unlock(&g_registry_lock);
		return -ENOENT;
	}

	g_registry[idx].desc.state = enabled ? NEURO_APPCMD_STATE_ENABLED
					     : NEURO_APPCMD_STATE_DISABLED;
	k_mutex_unlock(&g_registry_lock);
	return 0;
}

int neuro_app_command_registry_set_app_enabled(const char *app_id, bool enabled)
{
	int i;
	bool found = false;

	if (!neuro_app_id_valid(app_id)) {
		return -EINVAL;
	}

	k_mutex_lock(&g_registry_lock, K_FOREVER);
	for (i = 0; i < NEURO_APPCMD_MAX_ENTRIES; i++) {
		if (!g_registry[i].in_use) {
			continue;
		}

		if (strcmp(g_registry[i].desc.app_id, app_id) != 0) {
			continue;
		}

		g_registry[i].desc.state =
			enabled ? NEURO_APPCMD_STATE_ENABLED
				: NEURO_APPCMD_STATE_DISABLED;
		found = true;
	}
	k_mutex_unlock(&g_registry_lock);

	return found ? 0 : -ENOENT;
}

int neuro_app_command_registry_remove_app(const char *app_id)
{
	int i;
	bool found = false;

	if (!neuro_app_id_valid(app_id)) {
		return -EINVAL;
	}

	k_mutex_lock(&g_registry_lock, K_FOREVER);
	for (i = 0; i < NEURO_APPCMD_MAX_ENTRIES; i++) {
		if (!g_registry[i].in_use) {
			continue;
		}

		if (strcmp(g_registry[i].desc.app_id, app_id) != 0) {
			continue;
		}

		g_registry[i].desc.state = NEURO_APPCMD_STATE_REMOVED;
		g_registry[i].in_use = false;
		memset(&g_registry[i].desc, 0, sizeof(g_registry[i].desc));
		found = true;
	}
	k_mutex_unlock(&g_registry_lock);

	return found ? 0 : -ENOENT;
}

int neuro_app_command_registry_find(const char *app_id,
	const char *command_name, struct neuro_app_command_desc *out)
{
	int idx;

	if (!neuro_app_id_valid(app_id) ||
		!neuro_app_command_name_valid(command_name) || out == NULL) {
		return -EINVAL;
	}

	k_mutex_lock(&g_registry_lock, K_FOREVER);
	idx = neuro_app_command_entry_find_locked(app_id, command_name);
	if (idx < 0) {
		k_mutex_unlock(&g_registry_lock);
		return -ENOENT;
	}

	*out = g_registry[idx].desc;
	k_mutex_unlock(&g_registry_lock);
	return 0;
}
