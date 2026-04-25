#ifndef NEURO_UNIT_PORT_FS_H
#define NEURO_UNIT_PORT_FS_H

#include <zephyr/fs/fs.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Port-owned filesystem contract used by higher layers to avoid directly
 * depending on board-specific storage plumbing.
 */
struct neuro_unit_port_fs_ops {
	int (*mount)(void);
	int (*unmount)(void);
	int (*stat)(const char *path, struct fs_dirent *entry);
	int (*mkdir)(const char *path);
	int (*remove)(const char *path);
	int (*rename)(const char *from, const char *to);
	int (*open)(struct fs_file_t *file, const char *path, fs_mode_t flags);
	ssize_t (*read)(struct fs_file_t *file, void *ptr, size_t size);
	ssize_t (*write)(struct fs_file_t *file, const void *ptr, size_t size);
	int (*close)(struct fs_file_t *file);
	int (*opendir)(struct fs_dir_t *dir, const char *path);
	int (*readdir)(struct fs_dir_t *dir, struct fs_dirent *entry);
	int (*closedir)(struct fs_dir_t *dir);
};

#ifdef __cplusplus
}
#endif

#endif
