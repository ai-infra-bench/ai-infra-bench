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

static int failure_consumed = 0;
static int matching_open_count = 0;

static bool target_process(void) {
    char command[4096];
    long fd = syscall(SYS_openat, AT_FDCWD, "/proc/self/cmdline", O_RDONLY, 0);
    if (fd < 0) {
        return false;
    }
    long count = syscall(SYS_read, fd, command, sizeof(command) - 1);
    syscall(SYS_close, fd);
    if (count <= 0) {
        return false;
    }
    command[count] = '\0';
    return strstr(command, "APIServer_0") != NULL;
}

static bool target_path(const char *path) {
    const char *expected = getenv("AIB_FAIL_CONFIG_PATH");
    return path != NULL && expected != NULL && strcmp(path, expected) == 0;
}

static bool should_fail(const char *path) {
    if (!target_path(path) || !target_process()) {
        return false;
    }
    int current = __sync_add_and_fetch(&matching_open_count, 1);
    if (current != 2) {
        return false;
    }
    return __sync_bool_compare_and_swap(&failure_consumed, 0, 1);
}

static mode_t optional_mode(int flags, va_list args) {
    if ((flags & O_CREAT) || (flags & O_TMPFILE) == O_TMPFILE) {
        return va_arg(args, mode_t);
    }
    return 0;
}

int open(const char *path, int flags, ...) {
    static int (*real_open)(const char *, int, ...) = NULL;
    if (real_open == NULL) {
        real_open = dlsym(RTLD_NEXT, "open");
    }
    va_list args;
    va_start(args, flags);
    mode_t mode = optional_mode(flags, args);
    va_end(args);
    if (should_fail(path)) {
        errno = ENOENT;
        return -1;
    }
    return real_open(path, flags, mode);
}

int open64(const char *path, int flags, ...) {
    static int (*real_open64)(const char *, int, ...) = NULL;
    if (real_open64 == NULL) {
        real_open64 = dlsym(RTLD_NEXT, "open64");
    }
    va_list args;
    va_start(args, flags);
    mode_t mode = optional_mode(flags, args);
    va_end(args);
    if (should_fail(path)) {
        errno = ENOENT;
        return -1;
    }
    return real_open64(path, flags, mode);
}

int openat(int dirfd, const char *path, int flags, ...) {
    static int (*real_openat)(int, const char *, int, ...) = NULL;
    if (real_openat == NULL) {
        real_openat = dlsym(RTLD_NEXT, "openat");
    }
    va_list args;
    va_start(args, flags);
    mode_t mode = optional_mode(flags, args);
    va_end(args);
    if (should_fail(path)) {
        errno = ENOENT;
        return -1;
    }
    return real_openat(dirfd, path, flags, mode);
}

int openat64(int dirfd, const char *path, int flags, ...) {
    static int (*real_openat64)(int, const char *, int, ...) = NULL;
    if (real_openat64 == NULL) {
        real_openat64 = dlsym(RTLD_NEXT, "openat64");
    }
    va_list args;
    va_start(args, flags);
    mode_t mode = optional_mode(flags, args);
    va_end(args);
    if (should_fail(path)) {
        errno = ENOENT;
        return -1;
    }
    return real_openat64(dirfd, path, flags, mode);
}
