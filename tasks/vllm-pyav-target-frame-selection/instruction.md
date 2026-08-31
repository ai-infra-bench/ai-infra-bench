While checking that the PyAV video backend is compatible with the existing OpenCV backend, I decoded `/opt/video/sintel-trailer.mp4` with `num_frames=8` through both backends.

Both backends report the same eight target indices and return arrays with the same shape and dtype. OpenCV returns the requested moments, but several PyAV frames come from different moments even though they carry the same position labels.

Make PyAV return the frames from the requested moments, as OpenCV does here. It needs to remain on its own PyAV decoding path, with the rest of the video-loading interface working as before.
