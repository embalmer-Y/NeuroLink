#ifndef NEURO_UNIT_H
#define NEURO_UNIT_H

#ifdef __cplusplus
extern "C" {
#endif

struct k_heap;

int neuro_unit_start(void);
const char *neuro_unit_get_zenoh_connect(void);
int neuro_unit_set_zenoh_connect_override(const char *endpoint);
int neuro_unit_clear_zenoh_connect_override(void);

extern struct k_heap _system_heap;

#ifdef __cplusplus
}
#endif

#endif
