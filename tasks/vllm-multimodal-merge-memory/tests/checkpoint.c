#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <sys/socket.h>
#include <unistd.h>
#include <string.h>

/* Keys never become Python globals, callback closures, stdin or environment.
 * This is a scoped checkpoint authenticator, not a native-code sandbox. */
static unsigned char key[32], previous[32];
static int ready = 0, channel = -1;
static Py_ssize_t sequence = 0;
static PyObject *suite_code = NULL, *json_dumps = NULL, *hmac_digest = NULL;

static PyObject *configure(PyObject *self, PyObject *args) {
    const char *input;
    Py_ssize_t size;
    PyObject *code, *dumps;
    int fd;
    if (ready || geteuid() != 0) {
        PyErr_SetString(PyExc_RuntimeError, "checkpoint configuration is sealed");
        return NULL;
    }
    if (!PyArg_ParseTuple(args, "y#iOO", &input, &size, &fd, &code, &dumps)) return NULL;
    if (size != sizeof(key) || !PyCode_Check(code) || !PyCallable_Check(dumps)) {
        PyErr_SetString(PyExc_ValueError, "invalid checkpoint configuration");
        return NULL;
    }
    PyObject *hashlib = PyImport_ImportModule("_hashlib");
    if (!hashlib) return NULL;
    hmac_digest = PyObject_GetAttrString(hashlib, "hmac_digest");
    Py_DECREF(hashlib);
    if (!hmac_digest || !PyCFunction_Check(hmac_digest)) {
        PyErr_SetString(PyExc_RuntimeError, "trusted native HMAC is unavailable");
        return NULL;
    }
    memcpy(key, input, sizeof(key));
    channel = fd;
    suite_code = Py_NewRef(code);
    json_dumps = Py_NewRef(dumps);
    ready = 1;
    Py_RETURN_NONE;
}

static PyObject *emit(PyObject *self, PyObject *args) {
    PyObject *name, *value;
    if (!ready || !PyArg_ParseTuple(args, "OO", &name, &value)) return NULL;
    PyFrameObject *frame = PyEval_GetFrame();
    PyCodeObject *code = frame ? PyFrame_GetCode(frame) : NULL;
    int allowed = code && (PyObject *)code == suite_code;
    Py_XDECREF(code);
    if (!allowed) {
        PyErr_SetString(PyExc_RuntimeError, "checkpoint did not originate in the trusted suite");
        return NULL;
    }
    PyObject *record = Py_BuildValue("{s:n,s:O,s:O}", "index", sequence, "name", name, "value", value);
    if (!record) return NULL;
    PyObject *text = PyObject_CallOneArg(json_dumps, record);
    Py_DECREF(record);
    if (!text) return NULL;
    Py_ssize_t size;
    const char *body = PyUnicode_AsUTF8AndSize(text, &size);
    if (!body) { Py_DECREF(text); return NULL; }
    if (size > 60000) {
        Py_DECREF(text);
        PyErr_SetString(PyExc_ValueError, "checkpoint is too large");
        return NULL;
    }
    size_t prefix = sequence ? 32 : 0;
    unsigned char *input = PyMem_Malloc(prefix + size);
    unsigned char *packet = PyMem_Malloc(32 + size);
    if (!input || !packet) {
        PyMem_Free(input); PyMem_Free(packet); Py_DECREF(text);
        return PyErr_NoMemory();
    }
    memcpy(input, previous, prefix);
    memcpy(input + prefix, body, size);
    /* Capture CPython's native OpenSSL binding before candidate imports.
     * Keys remain C state; neither a Python signing closure nor libssl-dev
     * headers are required in the agent image. */
    PyObject *secret = PyBytes_FromStringAndSize((char *)key, sizeof(key));
    PyObject *message = PyBytes_FromStringAndSize((char *)input, prefix + size);
    PyObject *algorithm = PyUnicode_FromString("sha256");
    PyObject *digest = NULL;
    if (secret && message && algorithm)
        digest = PyObject_CallFunctionObjArgs(hmac_digest, secret, message, algorithm, NULL);
    Py_XDECREF(secret); Py_XDECREF(message); Py_XDECREF(algorithm);
    if (!digest || !PyBytes_Check(digest) || PyBytes_GET_SIZE(digest) != 32) {
        Py_XDECREF(digest);
        PyMem_Free(input); PyMem_Free(packet); Py_DECREF(text);
        if (!PyErr_Occurred())
            PyErr_SetString(PyExc_RuntimeError, "checkpoint authentication failed");
        return NULL;
    }
    memcpy(packet, PyBytes_AS_STRING(digest), 32);
    Py_DECREF(digest);
    memcpy(packet + 32, body, size);
    ssize_t sent = send(channel, packet, 32 + size, MSG_NOSIGNAL);
    if (sent == 32 + size) {
        memcpy(previous, packet, 32);
        sequence++;
    }
    PyMem_Free(input); PyMem_Free(packet); Py_DECREF(text);
    if (sent != 32 + size) return PyErr_SetFromErrno(PyExc_OSError);
    Py_RETURN_NONE;
}

static PyMethodDef methods[] = {
    {"configure", configure, METH_VARARGS, "Initialize once before candidate imports."},
    {"emit", emit, METH_VARARGS, "Authenticate a checkpoint from the trusted suite."},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "_checkpoint", NULL, -1, methods};
PyMODINIT_FUNC PyInit__checkpoint(void) { return PyModule_Create(&module); }
