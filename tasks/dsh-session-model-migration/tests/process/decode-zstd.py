"""Independent decoder using immutable system libzstd, including every frame."""
import ctypes,sys
from pathlib import Path
z=ctypes.CDLL('libzstd.so.1')
z.ZSTD_findFrameCompressedSize.argtypes=[ctypes.c_void_p,ctypes.c_size_t];z.ZSTD_findFrameCompressedSize.restype=ctypes.c_size_t
z.ZSTD_getFrameContentSize.argtypes=[ctypes.c_void_p,ctypes.c_size_t];z.ZSTD_getFrameContentSize.restype=ctypes.c_ulonglong
z.ZSTD_decompress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t];z.ZSTD_decompress.restype=ctypes.c_size_t
z.ZSTD_isError.argtypes=[ctypes.c_size_t];z.ZSTD_isError.restype=ctypes.c_uint
raw=Path(sys.argv[1]).read_bytes();offset=0
while offset<len(raw):
 src=ctypes.create_string_buffer(raw[offset:]);size=z.ZSTD_findFrameCompressedSize(src,len(raw)-offset)
 assert not z.ZSTD_isError(size) and size>0
 cap=z.ZSTD_getFrameContentSize(src,size)
 if cap==2**64-1:cap=64*1024*1024
 assert 0<=cap<=64*1024*1024,cap
 dst=ctypes.create_string_buffer(cap);n=z.ZSTD_decompress(dst,cap,src,size)
 assert not z.ZSTD_isError(n) and n<=cap
 sys.stdout.buffer.write(dst.raw[:n]);offset+=size
assert offset==len(raw)
