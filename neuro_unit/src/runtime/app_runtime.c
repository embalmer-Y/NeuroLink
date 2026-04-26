#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/llext/llext.h>
#include <zephyr/llext/buf_loader.h>
#include <zephyr/sys/slist.h>

#if defined(CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER) &&                   \
	CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER
#include <zephyr/multi_heap/shared_multi_heap.h>
#endif

#include <errno.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "app_runtime.h"
#include "app_runtime_arch.h"
#include "neuro_unit_port.h"

LOG_MODULE_REGISTER(app_runtime, LOG_LEVEL_INF);

#define APP_NAME_MAX_LEN 31
#define APP_PATH_MAX_LEN 127
#define APP_START_ARGS_RAW_MAX_LEN 255
#define APP_RT_DEFAULT_PRIORITY 128U

typedef int (*app_init_fn_t)(void);
typedef int (*app_start_legacy_fn_t)(const char *args);
typedef int (*app_start_v2_fn_t)(const struct app_runtime_start_args *args);
typedef int (*app_suspend_fn_t)(void);
typedef int (*app_resume_fn_t)(void);
typedef int (*app_stop_fn_t)(void);
typedef int (*app_deinit_fn_t)(void);
typedef int (*app_on_command_fn_t)(const char *command_name,
	const char *request_json, char *reply_buf, size_t reply_buf_len);

enum app_runtime_elf_buffer_source {
	APP_RUNTIME_ELF_BUFFER_MALLOC = 0,
	APP_RUNTIME_ELF_BUFFER_STATIC,
	APP_RUNTIME_ELF_BUFFER_PSRAM,
};

struct app_runtime_app {
	sys_snode_t node;
	struct llext *ext;
	uint8_t *elf_buf;
	size_t elf_size;
	enum app_runtime_elf_buffer_source elf_buf_source;
	app_init_fn_t app_init;
	app_start_legacy_fn_t app_start_legacy;
	app_start_v2_fn_t app_start_v2;
	app_suspend_fn_t app_suspend;
	app_resume_fn_t app_resume;
	app_stop_fn_t app_stop;
	app_deinit_fn_t app_deinit;
	app_on_command_fn_t app_on_command;
	enum app_runtime_state state;
	char name[APP_NAME_MAX_LEN + 1];
	char path[APP_PATH_MAX_LEN + 1];
	unsigned int priority;
	bool auto_suspended;
	bool manifest_present;
	struct app_runtime_manifest manifest;
};

struct app_runtime_ctx {
	struct k_mutex lock;
	bool initialized;
	struct app_runtime_policy policy;
	sys_slist_t apps;
};

static struct app_runtime_ctx g_ctx;

#if defined(CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE) &&                    \
	CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE > 0
static bool g_static_elf_buf_in_use;
static union {
	uint32_t align;
	uint8_t bytes[CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE];
} g_static_elf_buf;
#endif

static int app_runtime_fail(
	const char *op, enum app_rt_exception_code code, int cause);

static void *app_runtime_exec_addr_fixup(const void *sym)
{
	return (void *)APP_RT_EXEC_ADDR_FIXUP(sym);
}

static bool app_runtime_callback_addr_is_valid(const void *fn)
{
	uintptr_t addr = (uintptr_t)fn;

	if (addr == 0U) {
		return false;
	}

	return addr >= 0x1000U;
}

static int app_runtime_require_callback(const void *fn, const char *op)
{
	if (app_runtime_callback_addr_is_valid(fn)) {
		return 0;
	}

	LOG_ERR("%s invalid callback address: %p", op, fn);
	return app_runtime_fail(op, APP_RT_EX_SYMBOL_MISSING, -ENOENT);
}

static int app_runtime_fail(
	const char *op, enum app_rt_exception_code code, int cause)
{
	int err;

	err = app_rt_raise("runtime", op, code, cause);
	LOG_ERR("%s failed: %s (cause=%d)", op, app_rt_exception_code_str(code),
		cause);
	return err;
}

static int app_runtime_fail_errno(const char *op, int errno_value)
{
	int err;

	err = app_rt_raise_errno("runtime", op, errno_value);
	LOG_ERR("%s failed: errno=%d", op, errno_value);
	return err;
}

static const char *app_runtime_elf_buffer_source_str(
	enum app_runtime_elf_buffer_source source)
{
	switch (source) {
	case APP_RUNTIME_ELF_BUFFER_PSRAM:
		return "psram";
	case APP_RUNTIME_ELF_BUFFER_STATIC:
		return "static";
	case APP_RUNTIME_ELF_BUFFER_MALLOC:
	default:
		return "malloc";
	}
}

static uint8_t *app_runtime_alloc_elf_buffer(
	size_t size, enum app_runtime_elf_buffer_source *source)
{
	uint8_t *buf;

	if (source == NULL) {
		return NULL;
	}

	*source = APP_RUNTIME_ELF_BUFFER_MALLOC;
#if defined(CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER) &&                   \
	CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER
	buf = shared_multi_heap_aligned_alloc(SMH_REG_ATTR_EXTERNAL, 32, size);
	if (buf != NULL) {
		*source = APP_RUNTIME_ELF_BUFFER_PSRAM;
		return buf;
	}
	LOG_WRN("LLEXT ELF PSRAM staging alloc failed: bytes=%zu", size);
#endif
#if defined(CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE) &&                    \
	CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE > 0
	if (!g_static_elf_buf_in_use &&
		size <= sizeof(g_static_elf_buf.bytes)) {
		g_static_elf_buf_in_use = true;
		*source = APP_RUNTIME_ELF_BUFFER_STATIC;
		return g_static_elf_buf.bytes;
	}
#endif

	return malloc(size);
}

static void app_runtime_release_elf_buffer(
	uint8_t *buf, enum app_runtime_elf_buffer_source source)
{
	if (buf == NULL) {
		return;
	}

	if (source == APP_RUNTIME_ELF_BUFFER_PSRAM) {
#if defined(CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER) &&                   \
	CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER
		shared_multi_heap_free(buf);
#endif
		return;
	}

	if (source == APP_RUNTIME_ELF_BUFFER_STATIC) {
#if defined(CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE) &&                    \
	CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE > 0
		if (buf == g_static_elf_buf.bytes) {
			g_static_elf_buf_in_use = false;
		}
#endif
		return;
	}

	free(buf);
}

static int load_file_to_ram(const char *path, uint8_t **out_buf,
	size_t *out_size, enum app_runtime_elf_buffer_source *out_source)
{
	struct fs_dirent ent;
	struct fs_file_t file;
	const struct neuro_unit_port_fs_ops *fs_ops =
		neuro_unit_port_get_fs_ops();
	uint8_t *buf;
	ssize_t rd;
	int ret;

	*out_buf = NULL;
	*out_size = 0;
	*out_source = APP_RUNTIME_ELF_BUFFER_MALLOC;

	if (fs_ops == NULL || fs_ops->stat == NULL || fs_ops->open == NULL ||
		fs_ops->read == NULL || fs_ops->close == NULL) {
		return -ENOTSUP;
	}

	ret = fs_ops->stat(path, &ent);
	if (ret) {
		return ret;
	}

	LOG_INF("%s: path=%s size=%zu type=%d", __func__, path, ent.size,
		ent.type);

	if (ent.type != FS_DIR_ENTRY_FILE || ent.size == 0U) {
		return -EINVAL;
	}

	buf = app_runtime_alloc_elf_buffer(ent.size, out_source);
	if (buf == NULL) {
		return -ENOMEM;
	}

	fs_file_t_init(&file);
	ret = fs_ops->open(&file, path, FS_O_READ);
	if (ret) {
		app_runtime_release_elf_buffer(buf, *out_source);
		return ret;
	}

	LOG_INF("%s: fs_open ok path=%s", __func__, path);

	rd = fs_ops->read(&file, buf, ent.size);
	(void)fs_ops->close(&file);
	if (rd < 0) {
		app_runtime_release_elf_buffer(buf, *out_source);
		return (int)rd;
	}

	if ((size_t)rd != ent.size) {
		app_runtime_release_elf_buffer(buf, *out_source);
		return -EIO;
	}

	LOG_INF("%s: fs_read ok path=%s bytes=%zu source=%s", __func__, path,
		ent.size, app_runtime_elf_buffer_source_str(*out_source));

	*out_buf = buf;
	*out_size = ent.size;
	return 0;
}

static char *trim_token(char *s)
{
	char *end;

	while (*s == ' ' || *s == '\t') {
		s++;
	}

	end = s + strlen(s);
	while (end > s && (end[-1] == ' ' || end[-1] == '\t')) {
		end--;
	}
	*end = '\0';

	return s;
}

static int app_runtime_parse_start_args(
	const char *raw, struct app_runtime_start_args *out)
{
	char scratch[APP_START_ARGS_RAW_MAX_LEN + 1];
	char *saveptr = NULL;
	char *token;

	memset(out, 0, sizeof(*out));
	out->raw = raw;

	if (raw == NULL || raw[0] == '\0') {
		return 0;
	}

	if (strlen(raw) > APP_START_ARGS_RAW_MAX_LEN) {
		return -ENAMETOOLONG;
	}

	snprintk(scratch, sizeof(scratch), "%s", raw);
	token = strtok_r(scratch, ",", &saveptr);

	while (token != NULL) {
		char *eq;
		char *key;
		char *value;

		if (out->pair_count >= APP_RT_MAX_START_ARG_PAIRS) {
			return -ENOSPC;
		}

		token = trim_token(token);
		eq = strchr(token, '=');
		if (eq == NULL) {
			return -EINVAL;
		}

		*eq = '\0';
		key = trim_token(token);
		value = trim_token(eq + 1);
		if (key[0] == '\0') {
			return -EINVAL;
		}

		if (strlen(key) > APP_RT_START_ARG_KEY_MAX_LEN ||
			strlen(value) > APP_RT_START_ARG_VAL_MAX_LEN) {
			return -ENAMETOOLONG;
		}

		snprintk(out->pairs[out->pair_count].key,
			sizeof(out->pairs[out->pair_count].key), "%s", key);
		snprintk(out->pairs[out->pair_count].value,
			sizeof(out->pairs[out->pair_count].value), "%s", value);
		out->pair_count++;

		token = strtok_r(NULL, ",", &saveptr);
	}

	return 0;
}

static void app_runtime_manifest_fill_default(
	struct app_runtime_manifest *manifest)
{
	memset(manifest, 0, sizeof(*manifest));
	manifest->abi_major = APP_RT_MANIFEST_ABI_MAJOR;
	manifest->abi_minor = APP_RT_MANIFEST_ABI_MINOR;
}

static int app_runtime_manifest_validate(
	const struct app_runtime_manifest *manifest)
{
	if (manifest->abi_major != APP_RT_MANIFEST_ABI_MAJOR) {
		return -EPROTONOSUPPORT;
	}

	if (manifest->resource.cpu_budget_percent > 100U) {
		return -ERANGE;
	}

	return 0;
}

static size_t app_runtime_loaded_count_locked(void)
{
	size_t count = 0;
	struct app_runtime_app *app;

	SYS_SLIST_FOR_EACH_CONTAINER(&g_ctx.apps, app, node) { count++; }

	return count;
}

static size_t app_runtime_running_count_locked(void)
{
	size_t count = 0;
	struct app_runtime_app *app;

	/* clang-format off */
	SYS_SLIST_FOR_EACH_CONTAINER(&g_ctx.apps, app, node) {
		/* clang-format on */
		if (app->state == APP_RT_RUNNING) {
			count++;
		}
	}

	return count;
}

static struct app_runtime_app *find_app_by_name_locked(const char *name)
{
	struct app_runtime_app *app;

	if (name == NULL || name[0] == '\0') {
		return NULL;
	}

	/* clang-format off */
	SYS_SLIST_FOR_EACH_CONTAINER(&g_ctx.apps, app, node) {
		/* clang-format on */
		if (strcmp(app->name, name) == 0) {
			return app;
		}
	}

	return NULL;
}

static struct app_runtime_app *alloc_app_record(void)
{
	return calloc(1, sizeof(struct app_runtime_app));
}

static int app_runtime_read_priority(struct app_runtime_app *app)
{
	int *priority_sym;

	app->priority = APP_RT_DEFAULT_PRIORITY;
	priority_sym = (int *)app_runtime_exec_addr_fixup(
		llext_find_sym(&app->ext->exp_tab, "app_runtime_priority"));
	if (priority_sym == NULL) {
		return 0;
	}

	if (*priority_sym < 0) {
		app->priority = 0U;
	} else if (*priority_sym > 255) {
		app->priority = 255U;
	} else {
		app->priority = (unsigned int)*priority_sym;
	}

	return 0;
}

static int app_runtime_read_manifest(struct app_runtime_app *app)
{
	const struct app_runtime_manifest *manifest_sym;
	int ret;

	app_runtime_manifest_fill_default(&app->manifest);
	app->manifest_present = false;

	manifest_sym = (const struct app_runtime_manifest *)
		app_runtime_exec_addr_fixup(llext_find_sym(
			&app->ext->exp_tab, "app_runtime_manifest"));
	if (manifest_sym == NULL) {
		return 0;
	}

	app->manifest = *manifest_sym;
	app->manifest.app_name[APP_RT_MANIFEST_NAME_MAX_LEN] = '\0';
	app->manifest.dependency[APP_RT_MANIFEST_DEPENDENCY_MAX_LEN] = '\0';

	ret = app_runtime_manifest_validate(&app->manifest);
	if (ret) {
		return ret;
	}

	app->manifest_present = true;
	return 0;
}

static int app_runtime_bind_symbols(struct app_runtime_app *app)
{
	int ret;

	app->app_init = (app_init_fn_t)app_runtime_exec_addr_fixup(
		llext_find_sym(&app->ext->exp_tab, "app_init"));
	app->app_start_v2 = (app_start_v2_fn_t)app_runtime_exec_addr_fixup(
		llext_find_sym(&app->ext->exp_tab, "app_start_v2"));
	app->app_start_legacy =
		(app_start_legacy_fn_t)app_runtime_exec_addr_fixup(
			llext_find_sym(&app->ext->exp_tab, "app_start"));
	app->app_suspend = (app_suspend_fn_t)app_runtime_exec_addr_fixup(
		llext_find_sym(&app->ext->exp_tab, "app_suspend"));
	app->app_resume = (app_resume_fn_t)app_runtime_exec_addr_fixup(
		llext_find_sym(&app->ext->exp_tab, "app_resume"));
	app->app_stop = (app_stop_fn_t)app_runtime_exec_addr_fixup(
		llext_find_sym(&app->ext->exp_tab, "app_stop"));
	app->app_deinit = (app_deinit_fn_t)app_runtime_exec_addr_fixup(
		llext_find_sym(&app->ext->exp_tab, "app_deinit"));
	app->app_on_command = (app_on_command_fn_t)app_runtime_exec_addr_fixup(
		llext_find_sym(&app->ext->exp_tab, "app_on_command"));

	LOG_INF("app '%s' symbols: init=%p start_v2=%p start=%p suspend=%p resume=%p stop=%p deinit=%p on_command=%p",
		app->name, (void *)app->app_init, (void *)app->app_start_v2,
		(void *)app->app_start_legacy, (void *)app->app_suspend,
		(void *)app->app_resume, (void *)app->app_stop,
		(void *)app->app_deinit, (void *)app->app_on_command);

	if (app->app_init == NULL ||
		(app->app_start_v2 == NULL && app->app_start_legacy == NULL) ||
		app->app_suspend == NULL || app->app_resume == NULL ||
		app->app_stop == NULL || app->app_deinit == NULL) {
		return -ENOENT;
	}

	ret = app_runtime_read_priority(app);
	if (ret) {
		return ret;
	}

	return app_runtime_read_manifest(app);
}

static int app_runtime_stop_internal_locked(struct app_runtime_app *app)
{
	int ret;

	if (app->state != APP_RT_RUNNING && app->state != APP_RT_SUSPENDED) {
		return 0;
	}

	ret = app_runtime_require_callback(
		(const void *)app->app_stop, "app_stop_ptr");
	if (ret) {
		return ret;
	}

	ret = app->app_stop();
	if (ret) {
		return app_runtime_fail(
			"app_stop", APP_RT_EX_APP_CALLBACK_FAILURE, ret);
	}

	app->state = APP_RT_INITIALIZED;
	app->auto_suspended = false;
	return 0;
}

static int app_runtime_deinit_internal_locked(struct app_runtime_app *app)
{
	int ret;

	if (app->state != APP_RT_INITIALIZED) {
		return 0;
	}

	ret = app_runtime_require_callback(
		(const void *)app->app_deinit, "app_deinit_ptr");
	if (ret) {
		return ret;
	}

	ret = app->app_deinit();
	if (ret) {
		return app_runtime_fail(
			"app_deinit", APP_RT_EX_APP_CALLBACK_FAILURE, ret);
	}

	app->state = APP_RT_LOADED;
	return 0;
}

static int app_runtime_suspend_internal_locked(
	struct app_runtime_app *app, bool auto_suspend)
{
	int ret;

	if (app->state != APP_RT_RUNNING) {
		return app_runtime_fail(
			"app_suspend", APP_RT_EX_STATE_CONFLICT, app->state);
	}

	ret = app_runtime_require_callback(
		(const void *)app->app_suspend, "app_suspend_ptr");
	if (ret) {
		return ret;
	}

	ret = app->app_suspend();
	if (ret) {
		return app_runtime_fail(
			"app_suspend", APP_RT_EX_APP_CALLBACK_FAILURE, ret);
	}

	app->state = APP_RT_SUSPENDED;
	app->auto_suspended = auto_suspend;
	return 0;
}

static int app_runtime_ensure_running_slot_locked(
	struct app_runtime_app *request_app)
{
	size_t running_count;
	struct app_runtime_app *candidate = NULL;
	struct app_runtime_app *iter;
	int ret;

	running_count = app_runtime_running_count_locked();
	if (running_count < g_ctx.policy.max_running_apps) {
		return 0;
	}

	if (!g_ctx.policy.allow_preemptive_suspend) {
		return app_runtime_fail("ensure_running_slot",
			APP_RT_EX_RESOURCE_LIMIT, (int)running_count);
	}

	/* clang-format off */
	SYS_SLIST_FOR_EACH_CONTAINER(&g_ctx.apps, iter, node) {
		/* clang-format on */
		if (iter == request_app || iter->state != APP_RT_RUNNING) {
			continue;
		}

		if (iter->priority <= request_app->priority) {
			continue;
		}

		if (candidate == NULL || iter->priority > candidate->priority) {
			candidate = iter;
		}
	}

	if (candidate == NULL) {
		return app_runtime_fail("ensure_running_slot",
			APP_RT_EX_RESOURCE_LIMIT, (int)running_count);
	}

	ret = app_runtime_suspend_internal_locked(candidate, true);
	if (ret) {
		return ret;
	}

	LOG_INF("Preempted app '%s' for '%s'", candidate->name,
		request_app->name);
	return 0;
}

static void app_runtime_cleanup_app(struct app_runtime_app *app)
{
	if (app == NULL) {
		return;
	}

	if (app->ext != NULL) {
		(void)llext_unload(&app->ext);
	}

	if (app->elf_buf != NULL) {
		app_runtime_release_elf_buffer(
			app->elf_buf, app->elf_buf_source);
	}

	app->ext = NULL;
	app->elf_buf = NULL;
	app->elf_size = 0U;
	app->elf_buf_source = APP_RUNTIME_ELF_BUFFER_MALLOC;
}

static void app_runtime_release_app_locked(struct app_runtime_app *app)
{
	if (app == NULL) {
		return;
	}

	(void)sys_slist_find_and_remove(&g_ctx.apps, &app->node);
	app_runtime_cleanup_app(app);
	free(app);
}

int app_runtime_init(void)
{
	memset(&g_ctx, 0, sizeof(g_ctx));
	k_mutex_init(&g_ctx.lock);
	sys_slist_init(&g_ctx.apps);
	g_ctx.initialized = true;
	g_ctx.policy.max_loaded_apps = APP_RT_POLICY_NO_LIMIT;
	g_ctx.policy.max_running_apps = APP_RT_POLICY_NO_LIMIT;
	g_ctx.policy.allow_preemptive_suspend = true;
	app_rt_clear_last_exception();
	return 0;
}

int app_runtime_set_policy(const struct app_runtime_policy *policy)
{
	size_t running_count;

	if (policy == NULL) {
		return app_runtime_fail(
			"set_policy", APP_RT_EX_INVALID_ARGUMENT, 0);
	}

	if (policy->max_loaded_apps == 0 || policy->max_running_apps == 0 ||
		policy->max_running_apps > policy->max_loaded_apps) {
		return app_runtime_fail(
			"set_policy", APP_RT_EX_INVALID_ARGUMENT, 0);
	}

	k_mutex_lock(&g_ctx.lock, K_FOREVER);
	running_count = app_runtime_running_count_locked();
	if (running_count > policy->max_running_apps) {
		k_mutex_unlock(&g_ctx.lock);
		return app_runtime_fail("set_policy", APP_RT_EX_STATE_CONFLICT,
			(int)running_count);
	}

	g_ctx.policy = *policy;
	k_mutex_unlock(&g_ctx.lock);
	app_rt_clear_last_exception();
	return 0;
}

void app_runtime_get_policy(struct app_runtime_policy *policy)
{
	if (policy == NULL) {
		return;
	}

	k_mutex_lock(&g_ctx.lock, K_FOREVER);
	*policy = g_ctx.policy;
	k_mutex_unlock(&g_ctx.lock);
}

int app_runtime_load(const char *name, const char *path)
{
	int ret;
	struct app_runtime_app *app;
	struct llext_buf_loader buf_loader;
	struct llext_loader *ldr;
	struct llext_load_param param = LLEXT_LOAD_PARAM_DEFAULT;

	if (name == NULL || path == NULL || name[0] == '\0' ||
		path[0] == '\0') {
		return app_runtime_fail("load", APP_RT_EX_INVALID_ARGUMENT, 0);
	}

	if (strlen(name) > APP_NAME_MAX_LEN ||
		strlen(path) > APP_PATH_MAX_LEN) {
		return app_runtime_fail(
			"load", APP_RT_EX_INVALID_ARGUMENT, -ENAMETOOLONG);
	}

	LOG_INF("%s: begin name=%s path=%s", __func__, name, path);

	k_mutex_lock(&g_ctx.lock, K_FOREVER);
	if (app_runtime_loaded_count_locked() >= g_ctx.policy.max_loaded_apps) {
		k_mutex_unlock(&g_ctx.lock);
		return app_runtime_fail("load", APP_RT_EX_RESOURCE_LIMIT,
			(int)g_ctx.policy.max_loaded_apps);
	}

	if (find_app_by_name_locked(name) != NULL) {
		k_mutex_unlock(&g_ctx.lock);
		return app_runtime_fail(
			"load", APP_RT_EX_ALREADY_EXISTS, -EALREADY);
	}

	app = alloc_app_record();
	if (app == NULL) {
		k_mutex_unlock(&g_ctx.lock);
		return app_runtime_fail(
			"load", APP_RT_EX_RESOURCE_LIMIT, -ENOMEM);
	}

	ret = load_file_to_ram(
		path, &app->elf_buf, &app->elf_size, &app->elf_buf_source);
	if (ret) {
		k_mutex_unlock(&g_ctx.lock);
		return app_runtime_fail_errno("load_file", ret);
	}

	LOG_INF("%s: artifact staged name=%s size=%zu", __func__, name,
		app->elf_size);

	buf_loader = (struct llext_buf_loader)LLEXT_WRITABLE_BUF_LOADER(
		app->elf_buf, app->elf_size);
	ldr = &buf_loader.loader;
	LOG_INF("%s: calling llext_load name=%s", __func__, name);

	ret = llext_load(ldr, name, &app->ext, &param);
	if (ret < 0) {
		app_runtime_cleanup_app(app);
		free(app);
		k_mutex_unlock(&g_ctx.lock);
		return app_runtime_fail(
			"llext_load", APP_RT_EX_LOAD_FAILURE, ret);
	}

	LOG_INF("%s: llext_load ok name=%s ext=%p", __func__, name, app->ext);

	snprintk(app->name, sizeof(app->name), "%s", name);
	snprintk(app->path, sizeof(app->path), "%s", path);
	LOG_INF("%s: binding symbols name=%s", __func__, name);

	ret = app_runtime_bind_symbols(app);
	if (ret) {
		app_runtime_cleanup_app(app);
		free(app);
		k_mutex_unlock(&g_ctx.lock);
		if (ret == -ENOENT) {
			return app_runtime_fail(
				"bind_symbols", APP_RT_EX_SYMBOL_MISSING, ret);
		}
		return app_runtime_fail(
			"bind_manifest", APP_RT_EX_INVALID_ARGUMENT, ret);
	}

	LOG_INF("%s: symbols bound name=%s priority=%u manifest=%d", __func__,
		name, app->priority, app->manifest_present);

	if (app->manifest.app_name[0] == '\0') {
		snprintk(app->manifest.app_name, sizeof(app->manifest.app_name),
			"%s", name);
	}
	app->state = APP_RT_LOADED;
	app->auto_suspended = false;

	ret = app_runtime_require_callback(
		(const void *)app->app_init, "app_init_ptr");
	if (ret) {
		app_runtime_cleanup_app(app);
		free(app);
		k_mutex_unlock(&g_ctx.lock);
		return ret;
	}

	LOG_INF("%s: invoking app_init name=%s", __func__, name);

	ret = app->app_init();
	if (ret) {
		app_runtime_cleanup_app(app);
		free(app);
		k_mutex_unlock(&g_ctx.lock);
		return app_runtime_fail(
			"app_init", APP_RT_EX_APP_CALLBACK_FAILURE, ret);
	}

	LOG_INF("%s: app_init ok name=%s", __func__, name);

	app->state = APP_RT_INITIALIZED;
	sys_slist_append(&g_ctx.apps, &app->node);

	k_mutex_unlock(&g_ctx.lock);
	app_rt_clear_last_exception();
	LOG_INF("App loaded and initialized: %s (priority=%u)", app->name,
		app->priority);
	return 0;
}

int app_runtime_start(const char *name, const char *start_args)
{
	struct app_runtime_app *app;
	struct app_runtime_start_args parsed_args;
	int ret;

	if (name == NULL || name[0] == '\0') {
		return app_runtime_fail("start", APP_RT_EX_INVALID_ARGUMENT, 0);
	}

	LOG_INF("%s: begin name=%s args=%s", __func__, name,
		start_args != NULL ? start_args : "<null>");

	k_mutex_lock(&g_ctx.lock, K_FOREVER);
	app = find_app_by_name_locked(name);
	if (app == NULL) {
		k_mutex_unlock(&g_ctx.lock);
		return app_runtime_fail("start", APP_RT_EX_NOT_FOUND, 0);
	}

	if (app->state != APP_RT_INITIALIZED) {
		k_mutex_unlock(&g_ctx.lock);
		return app_runtime_fail(
			"start", APP_RT_EX_STATE_CONFLICT, app->state);
	}

	ret = app_runtime_ensure_running_slot_locked(app);
	if (ret) {
		k_mutex_unlock(&g_ctx.lock);
		return ret;
	}

	if (app->app_start_v2 != NULL) {
		ret = app_runtime_require_callback(
			(const void *)app->app_start_v2, "app_start_v2_ptr");
	} else {
		ret = app_runtime_require_callback(
			(const void *)app->app_start_legacy, "app_start_ptr");
	}
	if (ret) {
		k_mutex_unlock(&g_ctx.lock);
		return ret;
	}

	if (app->app_start_v2 != NULL) {
		ret = app_runtime_parse_start_args(start_args, &parsed_args);
		if (ret) {
			k_mutex_unlock(&g_ctx.lock);
			return app_runtime_fail_errno("start_parse_args", ret);
		}

		LOG_INF("%s: invoking app_start_v2 name=%s pair_count=%zu",
			__func__, name, parsed_args.pair_count);
		ret = app->app_start_v2(&parsed_args);
	} else {
		LOG_INF("%s: invoking app_start name=%s", __func__, name);
		ret = app->app_start_legacy(start_args);
	}

	if (ret) {
		k_mutex_unlock(&g_ctx.lock);
		return app_runtime_fail(
			"app_start", APP_RT_EX_APP_CALLBACK_FAILURE, ret);
	}

	app->state = APP_RT_RUNNING;
	app->auto_suspended = false;
	k_mutex_unlock(&g_ctx.lock);
	app_rt_clear_last_exception();
	LOG_INF("%s: app running name=%s", __func__, name);
	return 0;
}

int app_runtime_suspend(const char *name)
{
	struct app_runtime_app *app;
	int ret;

	if (name == NULL || name[0] == '\0') {
		return app_runtime_fail(
			"suspend", APP_RT_EX_INVALID_ARGUMENT, 0);
	}

	k_mutex_lock(&g_ctx.lock, K_FOREVER);
	app = find_app_by_name_locked(name);
	if (app == NULL) {
		k_mutex_unlock(&g_ctx.lock);
		return app_runtime_fail("suspend", APP_RT_EX_NOT_FOUND, 0);
	}

	ret = app_runtime_suspend_internal_locked(app, false);
	k_mutex_unlock(&g_ctx.lock);
	if (ret) {
		return ret;
	}

	app_rt_clear_last_exception();
	return 0;
}

int app_runtime_resume(const char *name)
{
	struct app_runtime_app *app;
	int ret;

	if (name == NULL || name[0] == '\0') {
		return app_runtime_fail(
			"resume", APP_RT_EX_INVALID_ARGUMENT, 0);
	}

	k_mutex_lock(&g_ctx.lock, K_FOREVER);
	app = find_app_by_name_locked(name);
	if (app == NULL) {
		k_mutex_unlock(&g_ctx.lock);
		return app_runtime_fail("resume", APP_RT_EX_NOT_FOUND, 0);
	}

	if (app->state != APP_RT_SUSPENDED) {
		k_mutex_unlock(&g_ctx.lock);
		return app_runtime_fail(
			"resume", APP_RT_EX_STATE_CONFLICT, app->state);
	}

	ret = app_runtime_ensure_running_slot_locked(app);
	if (ret) {
		k_mutex_unlock(&g_ctx.lock);
		return ret;
	}

	ret = app_runtime_require_callback(
		(const void *)app->app_resume, "app_resume_ptr");
	if (ret) {
		k_mutex_unlock(&g_ctx.lock);
		return ret;
	}

	ret = app->app_resume();
	if (ret) {
		k_mutex_unlock(&g_ctx.lock);
		return app_runtime_fail(
			"app_resume", APP_RT_EX_APP_CALLBACK_FAILURE, ret);
	}

	app->state = APP_RT_RUNNING;
	app->auto_suspended = false;
	k_mutex_unlock(&g_ctx.lock);
	app_rt_clear_last_exception();
	return 0;
}

int app_runtime_stop(const char *name)
{
	struct app_runtime_app *app;
	int ret;

	if (name == NULL || name[0] == '\0') {
		return app_runtime_fail("stop", APP_RT_EX_INVALID_ARGUMENT, 0);
	}

	k_mutex_lock(&g_ctx.lock, K_FOREVER);
	app = find_app_by_name_locked(name);
	if (app == NULL) {
		k_mutex_unlock(&g_ctx.lock);
		return app_runtime_fail("stop", APP_RT_EX_NOT_FOUND, 0);
	}

	ret = app_runtime_stop_internal_locked(app);
	k_mutex_unlock(&g_ctx.lock);
	if (ret) {
		return ret;
	}

	app_rt_clear_last_exception();
	return 0;
}

int app_runtime_unload(const char *name)
{
	struct app_runtime_app *app;
	int ret;

	if (name == NULL || name[0] == '\0') {
		return app_runtime_fail(
			"unload", APP_RT_EX_INVALID_ARGUMENT, 0);
	}

	k_mutex_lock(&g_ctx.lock, K_FOREVER);
	app = find_app_by_name_locked(name);
	if (app == NULL) {
		k_mutex_unlock(&g_ctx.lock);
		return app_runtime_fail("unload", APP_RT_EX_NOT_FOUND, 0);
	}

	ret = app_runtime_stop_internal_locked(app);
	if (!ret) {
		ret = app_runtime_deinit_internal_locked(app);
	}
	if (!ret) {
		app_runtime_release_app_locked(app);
	}
	k_mutex_unlock(&g_ctx.lock);

	if (ret) {
		return ret;
	}

	app_rt_clear_last_exception();
	return 0;
}

void app_runtime_get_status(struct app_runtime_status *status)
{
	struct app_runtime_app *app;

	if (status == NULL) {
		return;
	}

	memset(status, 0, sizeof(*status));

	k_mutex_lock(&g_ctx.lock, K_FOREVER);
	status->capacity.max_loaded_apps = g_ctx.policy.max_loaded_apps;
	status->capacity.max_running_apps = g_ctx.policy.max_running_apps;
	status->capacity.allow_preemptive_suspend =
		g_ctx.policy.allow_preemptive_suspend;

	/* clang-format off */
	SYS_SLIST_FOR_EACH_CONTAINER(&g_ctx.apps, app, node) {
		/* clang-format on */
		status->app_count++;
		if (app->state == APP_RT_RUNNING) {
			status->running_count++;
		}
		if (app->state == APP_RT_SUSPENDED) {
			status->suspended_count++;
		}

		if (status->listed_app_count <
			APP_RT_STATUS_SNAPSHOT_CAPACITY) {
			size_t out_idx = status->listed_app_count;

			snprintk(status->apps[out_idx].name,
				sizeof(status->apps[out_idx].name), "%s",
				app->name);
			snprintk(status->apps[out_idx].path,
				sizeof(status->apps[out_idx].path), "%s",
				app->path);
			status->apps[out_idx].state = app->state;
			status->apps[out_idx].priority = app->priority;
			status->apps[out_idx].auto_suspended =
				app->auto_suspended;
			status->apps[out_idx].manifest_present =
				app->manifest_present;
			status->apps[out_idx].manifest = app->manifest;
			status->listed_app_count++;
		} else {
			status->listed_app_count_truncated = true;
		}
	}
	k_mutex_unlock(&g_ctx.lock);

	app_rt_get_last_exception(&status->last_exception);
}

bool app_runtime_supports_command_callback(const char *name)
{
	struct app_runtime_app *app;
	bool supported = false;

	if (name == NULL || name[0] == '\0') {
		return false;
	}

	k_mutex_lock(&g_ctx.lock, K_FOREVER);
	app = find_app_by_name_locked(name);
	if (app != NULL && app->app_on_command != NULL) {
		supported = true;
	}
	k_mutex_unlock(&g_ctx.lock);

	return supported;
}

int app_runtime_dispatch_command(const char *name, const char *command_name,
	const char *request_json, char *reply_buf, size_t reply_buf_len)
{
	struct app_runtime_app *app;
	int ret;

	if (name == NULL || name[0] == '\0' || command_name == NULL ||
		command_name[0] == '\0' || request_json == NULL) {
		return app_runtime_fail(
			"app_command", APP_RT_EX_INVALID_ARGUMENT, -EINVAL);
	}

	k_mutex_lock(&g_ctx.lock, K_FOREVER);
	app = find_app_by_name_locked(name);
	if (app == NULL) {
		k_mutex_unlock(&g_ctx.lock);
		return app_runtime_fail(
			"app_command", APP_RT_EX_NOT_FOUND, -ENOENT);
	}

	if (app->state != APP_RT_RUNNING) {
		k_mutex_unlock(&g_ctx.lock);
		return app_runtime_fail(
			"app_command", APP_RT_EX_STATE_CONFLICT, app->state);
	}

	if (app->app_on_command == NULL) {
		k_mutex_unlock(&g_ctx.lock);
		return app_runtime_fail(
			"app_command", APP_RT_EX_NOT_SUPPORTED, -ENOTSUP);
	}

	ret = app_runtime_require_callback(
		(const void *)app->app_on_command, "app_on_command_ptr");
	if (ret) {
		k_mutex_unlock(&g_ctx.lock);
		return ret;
	}

	ret = app->app_on_command(
		command_name, request_json, reply_buf, reply_buf_len);
	k_mutex_unlock(&g_ctx.lock);
	if (ret) {
		return app_runtime_fail(
			"app_on_command", APP_RT_EX_APP_CALLBACK_FAILURE, ret);
	}

	app_rt_clear_last_exception();
	return 0;
}
