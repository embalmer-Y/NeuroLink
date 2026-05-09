/* SPDX-License-Identifier: Apache-2.0 */

#include <zephyr/llext/symbol.h>
#include <zephyr/sys/printk.h>

#include <stdbool.h>
#include <stddef.h>

#include "app_runtime_manifest.h"
#include "neuro_unit_app_api.h"

/* Forward declaration for use in maybe_publish_callback_event. */
extern const struct app_runtime_manifest app_runtime_manifest;

static bool app_initialized;
static bool app_running;
static int start_count;
static bool callback_enabled;
static int callback_trigger_every;
static unsigned int invoke_count;
static char callback_event_name[NEURO_UNIT_APP_EVENT_NAME_LEN] = "callback";

/* Sample app command exposed through the Unit app-command registry contract. */
static const char app_command_name[] = "invoke";
static const char app_id[] = "neuro_unit_app";
static const char app_version[] = "1.2.4";
static const char app_build_id[] = "neuro_unit_app-1.2.4-cbor-v2";

static void print_app_version(const char *stage)
{
  printk("neuro_unit_app version stage=%s version=%s build_id=%s "
    "manifest=%u.%u.%u\n",
    stage, app_version, app_build_id, app_runtime_manifest.version.major,
    app_runtime_manifest.version.minor, app_runtime_manifest.version.patch);
}

static bool str_eq(const char *lhs, const char *rhs)
{
  while (lhs != NULL && rhs != NULL) {
    if (*lhs != *rhs) {
      return false;
    }

    if (*lhs == '\0') {
      return true;
    }

    lhs++;
    rhs++;
  }

  return lhs == rhs;
}

static bool command_updates_callback_config(const char *request_json)
{
  struct neuro_unit_app_callback_config config;
  bool changed = false;

  if (request_json == NULL) {
    return false;
  }

  if (neuro_unit_read_callback_config_json(request_json, &config) != 0) {
    return false;
  }

  if (config.has_callback_enabled &&
    config.callback_enabled != callback_enabled) {
    callback_enabled = config.callback_enabled;
    changed = true;
  }

  if (config.has_trigger_every) {
    if (config.trigger_every < 0) {
      config.trigger_every = 0;
    }
    if (config.trigger_every != callback_trigger_every) {
      callback_trigger_every = config.trigger_every;
      changed = true;
    }
  }

  if (config.has_event_name) {
    snprintk(callback_event_name, sizeof(callback_event_name), "%s",
      config.event_name);
    changed = true;
  }

  return changed;
}

static int maybe_publish_callback_event(void)
{
  const struct neuro_unit_app_callback_event event = {
    .app_id = app_id,
    .event_name = callback_event_name,
    .invoke_count = invoke_count,
    .start_count = start_count,
  };

  if (!callback_enabled || callback_trigger_every <= 0) {
    return 0;
  }

  if ((invoke_count % (unsigned int)callback_trigger_every) != 0U) {
    return 0;
  }

  return neuro_unit_publish_callback_event(&event);
}

static void write_command_reply(char *reply_buf, size_t reply_buf_len,
  bool config_changed, int publish_ret)
{
  const struct neuro_unit_app_command_reply reply = {
    .command_name = app_command_name,
    .invoke_count = invoke_count,
    .callback_enabled = callback_enabled,
    .trigger_every = callback_trigger_every,
    .event_name = callback_event_name,
    .config_changed = config_changed,
    .publish_ret = publish_ret,
    .echo = app_build_id,
  };

  (void)neuro_unit_write_command_reply_json(
    reply_buf, reply_buf_len, &reply);
}

int app_runtime_priority = 88;

/*
 * This manifest is intentionally minimal and stable so Unit-side lifecycle and
 * callback tests have a predictable LLEXT payload to load.
 */
const struct app_runtime_manifest app_runtime_manifest = {
  .abi_major = APP_RT_MANIFEST_ABI_MAJOR,
  .abi_minor = APP_RT_MANIFEST_ABI_MINOR,
  .version = {
    .major = 1,
    .minor = 2,
    .patch = 4,
  },
  .capability_flags = APP_RT_CAP_STORAGE,
  .resource = {
    .ram_bytes = 20U * 1024U,
    .stack_bytes = 4U * 1024U,
    .cpu_budget_percent = 25U,
  },
  .app_name = "neuro_unit_app",
  .dependency = "none",
};

int app_init(void)
{
  app_initialized = true;
  callback_enabled = false;
  callback_trigger_every = 0;
  invoke_count = 0U;
  snprintk(callback_event_name, sizeof(callback_event_name), "%s",
    "callback");
  print_app_version("init");
  return 0;
}

int app_start(const char *args)
{
  if (!app_initialized) {
    return -1;
  }

  app_running = true;
  start_count++;
  print_app_version("start");
  (void)args;
  return 0;
}

int app_suspend(void)
{
  if (!app_running) {
    return -1;
  }

  app_running = false;
  return 0;
}

int app_resume(void)
{
  if (!app_initialized || app_running) {
    return -1;
  }

  app_running = true;
  return 0;
}

int app_stop(void)
{
  if (!app_initialized) {
    return -1;
  }

  app_running = false;
  return 0;
}

int app_deinit(void)
{
  app_initialized = false;
  app_running = false;
  callback_enabled = false;
  callback_trigger_every = 0;
  invoke_count = 0U;
  return 0;
}

int app_on_command(const char *command_name, const char *request_json,
  char *reply_buf, size_t reply_buf_len)
{
  bool config_changed;
  int publish_ret;

  if (!app_initialized || !app_running) {
    return -1;
  }

  if (!str_eq(command_name, app_command_name)) {
    return -2;
  }

  /*
   * The sample app accepts callback configuration embedded in the invoke
   * payload, then emits an app event whenever invoke_count reaches the
   * configured trigger interval.
   */
  config_changed = command_updates_callback_config(request_json);
  invoke_count++;
  publish_ret = maybe_publish_callback_event();
  write_command_reply(
    reply_buf, reply_buf_len, config_changed, publish_ret);

  return 0;
}

/* Export the exact lifecycle and callback symbols expected by the LLEXT ABI. */
LL_EXTENSION_SYMBOL(app_init);
LL_EXTENSION_SYMBOL(app_start);
LL_EXTENSION_SYMBOL(app_suspend);
LL_EXTENSION_SYMBOL(app_resume);
LL_EXTENSION_SYMBOL(app_stop);
LL_EXTENSION_SYMBOL(app_deinit);
LL_EXTENSION_SYMBOL(app_on_command);
LL_EXTENSION_SYMBOL(app_command_name);
LL_EXTENSION_SYMBOL(app_runtime_priority);
LL_EXTENSION_SYMBOL(app_runtime_manifest);
