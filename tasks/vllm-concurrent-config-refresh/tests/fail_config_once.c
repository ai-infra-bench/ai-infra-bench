#define _GNU_SOURCE

#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

static int matching_open_count = 0;
static int failure_consumed = 0;
static int corrupt_fd = -1;

static int worker_index(void) {
    char command[4096];
    long fd = syscall(SYS_openat, AT_FDCWD, "/proc/self/cmdline", O_RDONLY, 0);
    if (fd < 0) return -1;
    long count = syscall(SYS_read, fd, command, sizeof(command) - 1);
    syscall(SYS_close, fd);
    if (count <= 0) return -1;
    command[count] = '\0';
    if (strstr(command, "APIServer_0") != NULL) return 0;
    if (strstr(command, "APIServer_1") != NULL) return 1;
    return -1;
}

static bool target_path(const char *path) {
    const char *expected = getenv("AIB_FAIL_CONFIG_PATH");
    return path != NULL && expected != NULL && strcmp(path, expected) == 0;
}

static void marker(const char *message) {
    const char *path = getenv("AIB_FAULT_MARKER_PATH");
    if (path == NULL) return;
    long fd = syscall(SYS_openat, AT_FDCWD, path,
                      O_WRONLY | O_CREAT | O_APPEND, 0644);
    if (fd >= 0) {
        syscall(SYS_write, fd, message, strlen(message));
        syscall(SYS_close, fd);
    }
}

static int prepare_open(const char *path) {
    int worker = worker_index();
    if (worker < 0 || !target_path(path)) return -1;
    int current = __sync_add_and_fetch(&matching_open_count, 1);
    if (current != 2 || !__sync_bool_compare_and_swap(&failure_consumed, 0, 1)) {
        return -1;
    }
    if (worker == 0) {
        marker("ApiServer_0 ENOENT\n");
        return 0;
    }
    return 1;
}

static mode_t optional_mode(int flags, va_list args) {
    if ((flags & O_CREAT) || (flags & O_TMPFILE) == O_TMPFILE) {
        return va_arg(args, mode_t);
    }
    return 0;
}

#define DEFINE_OPEN(name, real_type, call_args, params)                        \
int name params {                                                               \
    static real_type real_fn = NULL;                                             \
    if (real_fn == NULL) real_fn = dlsym(RTLD_NEXT, #name);                     \
    va_list args; va_start(args, flags);                                         \
    mode_t mode = optional_mode(flags, args); va_end(args);                     \
    int action = prepare_open(path);                                             \
    if (action == 0) { errno = ENOENT; return -1; }                             \
    int fd = real_fn call_args;                                                  \
    if (action == 1 && fd >= 0) corrupt_fd = fd;                                \
    return fd;                                                                   \
}

typedef int (*open_fn)(const char *, int, ...);
typedef int (*openat_fn)(int, const char *, int, ...);
DEFINE_OPEN(open, open_fn, (path, flags, mode),
            (const char *path, int flags, ...))
DEFINE_OPEN(open64, open_fn, (path, flags, mode),
            (const char *path, int flags, ...))
DEFINE_OPEN(openat, openat_fn, (dirfd, path, flags, mode),
            (int dirfd, const char *path, int flags, ...))
DEFINE_OPEN(openat64, openat_fn, (dirfd, path, flags, mode),
            (int dirfd, const char *path, int flags, ...))

ssize_t read(int fd, void *buffer, size_t count) {
    static ssize_t (*real_read)(int, void *, size_t) = NULL;
    if (real_read == NULL) real_read = dlsym(RTLD_NEXT, "read");
    if (fd == corrupt_fd) {
        corrupt_fd = -1;
        marker("ApiServer_1 EMPTY_READ\n");
        return 0;
    }
    return real_read(fd, buffer, count);
}
