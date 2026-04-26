#include "neuro_unit_app_api.h"

int neuro_unit_app_start(const char *args)
{
	(void)args;
	return 0;
}

int neuro_unit_app_stop(void)
{
	return 0;
}

int neuro_unit_app_invoke(const char *args, char *reply, size_t reply_len)
{
	const struct neuro_unit_app_command_reply command_reply = {
		.command_name = "invoke",
		.invoke_count = 1U,
		.callback_enabled = false,
		.trigger_every = 0,
		.event_name = "callback",
		.config_changed = false,
		.publish_ret = 0,
		.echo = args != NULL ? args : "",
	};

	return neuro_unit_write_command_reply_json(
		reply, reply_len, &command_reply);
}