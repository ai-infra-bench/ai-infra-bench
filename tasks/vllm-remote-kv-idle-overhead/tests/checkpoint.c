#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

/* Observe live Python allocator requests, including list/dict backing buffers.
 * No Python callable supplies the byte count and there is no reset/stop API.
 * Nested domain allocations are counted once. Observer bookkeeping uses libc
 * malloc and is excluded. This is not a sandbox against arbitrary native code.
 */
#define BUCKETS (1u << 20)
typedef struct Entry { void *ptr; size_t size; struct Entry *next; } Entry;
static Entry **entries;
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static _Thread_local int depth;
static uint64_t live_bytes;
static int sealed, channel = -1;
static unsigned char key[32];
static PyObject *digest_fn;
static PyMemAllocatorEx original[3];

static size_t bucket(void *p) {
    uintptr_t x = (uintptr_t)p >> 3;
    x ^= x >> 21;
    x *= (uintptr_t)0x9e3779b97f4a7c15ULL;
    return (x >> 20) & (BUCKETS - 1);
}
static void forget(void *ptr) {
    if (!ptr) return;
    size_t b = bucket(ptr);
    pthread_mutex_lock(&lock);
    Entry **next = &entries[b];
    while (*next) {
        Entry *e = *next;
        if (e->ptr == ptr) {
            *next = e->next;
            live_bytes -= e->size;
            free(e);
            break;
        }
        next = &e->next;
    }
    pthread_mutex_unlock(&lock);
}
static void remember(void *ptr, size_t size) {
    if (!ptr) return;
    Entry *e = malloc(sizeof(*e));
    if (!e) abort();
    size_t b = bucket(ptr);
    e->ptr = ptr; e->size = size;
    pthread_mutex_lock(&lock);
    e->next = entries[b]; entries[b] = e; live_bytes += size;
    pthread_mutex_unlock(&lock);
}
static void *allocate(void *ctx, size_t n) {
    PyMemAllocatorEx *a = ctx;
    int outer = depth++ == 0;
    void *p = a->malloc(a->ctx, n);
    --depth;
    if (outer) remember(p, n);
    return p;
}
static void *zero_allocate(void *ctx, size_t count, size_t n) {
    PyMemAllocatorEx *a = ctx;
    int outer = depth++ == 0;
    void *p = a->calloc(a->ctx, count, n);
    --depth;
    if (outer) remember(p, count * n);
    return p;
}
static void *resize(void *ctx, void *ptr, size_t n) {
    PyMemAllocatorEx *a = ctx;
    int outer = depth++ == 0;
    void *p = a->realloc(a->ctx, ptr, n);
    --depth;
    if (outer && p) { forget(ptr); remember(p, n); }
    return p;
}
static void release(void *ctx, void *ptr) {
    PyMemAllocatorEx *a = ctx;
    int outer = depth++ == 0;
    if (outer) forget(ptr);
    a->free(a->ctx, ptr);
    --depth;
}
static PyObject *configure(PyObject *self, PyObject *args) {
    const char *input; Py_ssize_t size; int fd; PyObject *digest;
    if (sealed || geteuid() != 0) {
        PyErr_SetString(PyExc_RuntimeError, "allocation observer is sealed");
        return NULL;
    }
    if (!PyArg_ParseTuple(args, "y#iO", &input, &size, &fd, &digest)) return NULL;
    if (size != 32 || !PyCallable_Check(digest)) {
        PyErr_SetString(PyExc_ValueError, "invalid observer configuration"); return NULL;
    }
    entries = calloc(BUCKETS, sizeof(*entries));
    if (!entries) return PyErr_NoMemory();
    memcpy(key, input, 32); channel = fd; digest_fn = Py_NewRef(digest);
    for (int i = 0; i < 3; ++i) {
        PyMem_GetAllocator(i, &original[i]);
        PyMemAllocatorEx a = {&original[i], allocate, zero_allocate, resize, release};
        PyMem_SetAllocator(i, &a);
    }
    sealed = 1;
    Py_RETURN_NONE;
}
static PyObject *snapshot(PyObject *self, PyObject *args) {
    const char *nonce; Py_ssize_t size;
    if (!sealed || !PyArg_ParseTuple(args, "y#", &nonce, &size)) return NULL;
    if (size != 16) { PyErr_SetString(PyExc_ValueError, "bad challenge"); return NULL; }
    PyGC_Collect();
    unsigned char packet[56];
    memcpy(packet + 32, nonce, 16);
    pthread_mutex_lock(&lock);
    uint64_t count = live_bytes;
    pthread_mutex_unlock(&lock);
    for (int i = 0; i < 8; ++i) packet[48 + i] = (count >> (56 - 8 * i)) & 255;
    PyObject *k = PyBytes_FromStringAndSize((char *)key, 32);
    PyObject *body = PyBytes_FromStringAndSize((char *)packet + 32, 24);
    PyObject *alg = PyUnicode_FromString("sha256");
    PyObject *digest = k && body && alg ? PyObject_CallFunctionObjArgs(digest_fn, k, body, alg, NULL) : NULL;
    Py_XDECREF(k); Py_XDECREF(body); Py_XDECREF(alg);
    if (!digest) return NULL;
    if (!PyBytes_Check(digest) || PyBytes_GET_SIZE(digest) != 32) {
        Py_DECREF(digest); PyErr_SetString(PyExc_RuntimeError, "invalid authentication"); return NULL;
    }
    memcpy(packet, PyBytes_AS_STRING(digest), 32); Py_DECREF(digest);
    if (send(channel, packet, sizeof(packet), MSG_NOSIGNAL) != sizeof(packet))
        return PyErr_SetFromErrno(PyExc_OSError);
    Py_RETURN_NONE;
}
static PyMethodDef methods[] = {
    {"configure", configure, METH_VARARGS, "Install once before candidate imports."},
    {"snapshot", snapshot, METH_VARARGS, "Send authenticated live allocator bytes."},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "_checkpoint", NULL, -1, methods};
PyMODINIT_FUNC PyInit__checkpoint(void) { return PyModule_Create(&module); }
