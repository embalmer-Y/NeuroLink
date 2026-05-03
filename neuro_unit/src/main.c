#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include "app_runtime.h"
#include "neuro_unit_port.h"
#include "neuro_unit.h"

LOG_MODULE_REGISTER(neurolink_unit_main, LOG_LEVEL_INF);

static size_t app_policy_limit_from_config(int limit)
{
	return limit == 0 ? APP_RT_POLICY_NO_LIMIT : (size_t)limit;
}

int main(void)
{
	int ret;
	struct app_runtime_policy policy = {
		.max_loaded_apps = app_policy_limit_from_config(
			CONFIG_NEUROLINK_APP_MAX_LOADED),
		.max_running_apps = (size_t)CONFIG_NEUROLINK_APP_MAX_RUNNING,
		.allow_preemptive_suspend = true,
	};

	ret = neuro_unit_port_init();
	if (ret) {
		LOG_ERR("unit port init failed: %d", ret);
		return ret;
	}

	ret = app_runtime_init();
	if (ret) {
		LOG_ERR("app runtime init failed: %d", ret);
		return ret;
	}

	ret = app_runtime_set_policy(&policy);
	if (ret) {
		LOG_ERR("app runtime set policy failed: %d", ret);
		return ret;
	}

	ret = neuro_unit_start();
	if (ret) {
		LOG_ERR("neuro unit start failed: %d", ret);
		return ret;
	}

	LOG_INF("NeuroLink unit bootstrap initialized for node '%s'",
		CONFIG_NEUROLINK_NODE_ID);

	while (true) {
		k_sleep(K_SECONDS(60));
	}

	return 0;
}
