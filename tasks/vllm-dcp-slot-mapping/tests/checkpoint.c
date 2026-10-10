#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <sys/socket.h>
#include <unistd.h>
#include <string.h>

/* The key stays in native state. Authentication uses CPython's immutable
 * _hashlib.hmac_digest callable captured before candidate imports, so OpenSSL
 * headers are not required in the task image. This is not a native-memory
 * sandbox. */
static unsigned char key[32], previous[32];
static int ready = 0, channel = -1;
static Py_ssize_t sequence = 0;
static PyObject *suite_code = NULL, *json_dumps = NULL, *hmac_digest = NULL;

static PyObject *configure(PyObject *self, PyObject *args) {
    const char *input;
    Py_ssize_t size;
    PyObject *code, *dumps, *digest;
    int fd;
    if (ready || geteuid() != 0) {
        PyErr_SetString(PyExc_RuntimeError, "checkpoint configuration is sealed");
        return NULL;
    }
    if (!PyArg_ParseTuple(args, "y#iOOO", &input, &size, &fd, &code, &dumps, &digest)) return NULL;
    if (size != sizeof(key) || !PyCode_Check(code) || !PyCallable_Check(dumps) || !PyCallable_Check(digest)) {
        PyErr_SetString(PyExc_ValueError, "invalid checkpoint configuration");
        return NULL;
    }
    memcpy(key, input, sizeof(key));
    channel = fd;
    suite_code = Py_NewRef(code);
    json_dumps = Py_NewRef(dumps);
    hmac_digest = Py_NewRef(digest);
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
    Py_ssize_t body_size;
    const char *body = PyUnicode_AsUTF8AndSize(text, &body_size);
    if (!body) { Py_DECREF(text); return NULL; }
    if (body_size > 60000) {
        Py_DECREF(text);
        PyErr_SetString(PyExc_ValueError, "checkpoint is too large");
        return NULL;
    }
    Py_ssize_t prefix = sequence ? 32 : 0;
    PyObject *key_obj = PyBytes_FromStringAndSize((const char *)key, sizeof(key));
    PyObject *input_obj = PyBytes_FromStringAndSize(NULL, prefix + body_size);
    PyObject *algorithm = PyUnicode_FromString("sha256");
    if (!key_obj || !input_obj || !algorithm) {
        Py_XDECREF(key_obj); Py_XDECREF(input_obj); Py_XDECREF(algorithm); Py_DECREF(text);
        return NULL;
    }
    char *mac_input = PyBytes_AS_STRING(input_obj);
    if (prefix) memcpy(mac_input, previous, 32);
    memcpy(mac_input + prefix, body, body_size);
    PyObject *digest = PyObject_CallFunctionObjArgs(hmac_digest, key_obj, input_obj, algorithm, NULL);
    Py_DECREF(key_obj); Py_DECREF(input_obj); Py_DECREF(algorithm);
    if (!digest) { Py_DECREF(text); return NULL; }
    if (!PyBytes_Check(digest) || PyBytes_GET_SIZE(digest) != 32) {
        Py_DECREF(digest); Py_DECREF(text);
        PyErr_SetString(PyExc_RuntimeError, "checkpoint authentication failed");
        return NULL;
    }
    unsigned char *packet = PyMem_Malloc(32 + body_size);
    if (!packet) { Py_DECREF(digest); Py_DECREF(text); return PyErr_NoMemory(); }
    memcpy(packet, PyBytes_AS_STRING(digest), 32);
    memcpy(packet + 32, body, body_size);
    ssize_t sent = send(channel, packet, 32 + body_size, MSG_NOSIGNAL);
    if (sent == 32 + body_size) {
        memcpy(previous, packet, 32);
        sequence++;
    }
    PyMem_Free(packet); Py_DECREF(digest); Py_DECREF(text);
    if (sent != 32 + body_size) return PyErr_SetFromErrno(PyExc_OSError);
    Py_RETURN_NONE;
}

static PyMethodDef methods[] = {
    {"configure", configure, METH_VARARGS, "Initialize once before candidate imports."},
    {"emit", emit, METH_VARARGS, "Authenticate a checkpoint from the trusted suite."},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "_checkpoint", NULL, -1, methods};
PyMODINIT_FUNC PyInit__checkpoint(void) { return PyModule_Create(&module); }
