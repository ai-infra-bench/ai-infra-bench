While checking that the PyAV video backend is compatible with the existing OpenCV backend, I decoded `/opt/video/sintel-trailer.mp4` with `num_frames=8` through both backends.

Both backends report the same target positions and return arrays with the same shape and dtype. OpenCV returns the requested moments, but several PyAV frames come from different moments even though they are reported at those target positions.

Make PyAV return the frames from the requested moments throughout the existing video-loading interface. Preserve its existing sampling behavior and metadata, keep it on its own PyAV decoding path, and avoid affecting other video loads.
