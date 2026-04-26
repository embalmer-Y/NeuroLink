#ifndef NEURO_UNIT_SHELL_H
#define NEURO_UNIT_SHELL_H

#include <zephyr/shell/shell.h>

#define NEURO_UNIT_SHELL_APP_PARENT (app)

#define NEURO_UNIT_SHELL_APP_CMD_SET_CREATE(name)                              \
	SHELL_SUBCMD_SET_CREATE(name, NEURO_UNIT_SHELL_APP_PARENT)

#define NEURO_UNIT_SHELL_APP_CMD_ADD(                                          \
	syntax, subcmd, help, handler, mandatory, optional)                    \
	SHELL_SUBCMD_ADD(NEURO_UNIT_SHELL_APP_PARENT, syntax, subcmd, help,    \
		handler, mandatory, optional)

#define NEURO_UNIT_SHELL_APP_CMD_COND_ADD(                                     \
	flag, syntax, subcmd, help, handler, mandatory, optional)              \
	SHELL_SUBCMD_COND_ADD(flag, NEURO_UNIT_SHELL_APP_PARENT, syntax,       \
		subcmd, help, handler, mandatory, optional)

#endif
