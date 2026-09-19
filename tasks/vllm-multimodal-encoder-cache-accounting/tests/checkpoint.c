#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <sys/socket.h>
#include <errno.h>
#include <string.h>

/* Scoped completion authentication, not a sandbox for arbitrary native code.
 * The secret arrives after fork, directly into native storage. It is never a
 * Python object in the candidate process, a command argument or environment.
 * Only the preloaded suite's original code object may emit, exactly once. */
static unsigned char secret[32];
static int configured = 0, emitted = 0, channel = -1;
static PyObject *suite_code = NULL, *dumps = NULL;

static PyObject *configure(PyObject *self, PyObject *args) {
    int fd;
    PyObject *code, *serializer;
    if (configured) {
        PyErr_SetString(PyExc_RuntimeError, "completion channel is sealed");
        return NULL;
    }
    if (!PyArg_ParseTuple(args, "iOO", &fd, &code, &serializer)) return NULL;
    if (!PyCode_Check(code) || !PyCallable_Check(serializer)) {
        PyErr_SetString(PyExc_ValueError, "invalid trusted suite");
        return NULL;
    }
    size_t done = 0;
    while (done < sizeof(secret)) {
        ssize_t n = recv(fd, secret + done, sizeof(secret) - done, 0);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) {
            PyErr_SetString(PyExc_RuntimeError, "missing completion secret");
            return NULL;
        }
        done += n;
    }
    channel = fd;
    suite_code = Py_NewRef(code);
    dumps = Py_NewRef(serializer);
    configured = 1;
    Py_RETURN_NONE;
}

static PyObject *emit(PyObject *self, PyObject *value) {
    if (!configured || emitted) {
        PyErr_SetString(PyExc_RuntimeError, "completion is unavailable");
        return NULL;
    }
    PyFrameObject *frame = PyEval_GetFrame();
    PyCodeObject *code = frame ? PyFrame_GetCode(frame) : NULL;
    int allowed = code && (PyObject *)code == suite_code;
    Py_XDECREF(code);
    if (!allowed) {
        PyErr_SetString(PyExc_RuntimeError, "completion caller is not the trusted suite");
        return NULL;
    }
    PyObject *text = PyObject_CallOneArg(dumps, value);
    if (!text) return NULL;
    Py_ssize_t size;
    const char *body = PyUnicode_AsUTF8AndSize(text, &size);
    if (!body) { Py_DECREF(text); return NULL; }
    if (size > 1000000) {
        Py_DECREF(text);
        PyErr_SetString(PyExc_ValueError, "completion report is too large");
        return NULL;
    }
    char *packet = PyMem_Malloc(32 + size);
    if (!packet) { Py_DECREF(text); return PyErr_NoMemory(); }
    memcpy(packet, secret, 32);
    memcpy(packet + 32, body, size);
    size_t sent = 0, total = 32 + size;
    while (sent < total) {
        ssize_t n = send(channel, packet + sent, total - sent, 0);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) {
            PyMem_Free(packet); Py_DECREF(text);
            return PyErr_SetFromErrno(PyExc_OSError);
        }
        sent += n;
    }
    emitted = 1;
    memset(secret, 0, sizeof(secret));
    PyMem_Free(packet); Py_DECREF(text);
    Py_RETURN_NONE;
}
static PyMethodDef methods[] = {
    {"configure", configure, METH_VARARGS, "Seal the channel before candidate imports."},
    {"emit", emit, METH_O, "Authenticate completion from the original suite."},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "_encoder_checkpoint", NULL, -1, methods};
PyMODINIT_FUNC PyInit__encoder_checkpoint(void) { return PyModule_Create(&module); }
