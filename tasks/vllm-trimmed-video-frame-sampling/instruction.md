We shorten uploaded recordings with ffmpeg's lossless cut before sending them to vLLM as video input:

```bash
ffmpeg -ss 7 -i recording.mp4 -t 2 -c copy clip.mp4
```

For one 12-second, 30 fps recording, `clip.mp4` plays as a 62-frame (about 2.07 s) clip. When vLLM loads it through the normal video path with `num_frames=8`, the default OpenCV backend returns only 2 frames and reports `total_num_frames=272` and a duration of about 9.07 s. With `"backend": "pyav"` it also returns only 2 frames and reports `total_num_frames=272`, and with `num_frames=-1` it returns 64 frames, repeating the final frame three times. Other clips cut this way are milder and only lose or repeat their last sample.

Make video loading handle clips trimmed this way, for both the `opencv` and `pyav` backends:

- Every returned frame is one that plays in the clip, with no repeats, and the samples cover the clip from its start to its end.
- When the clip has at least `num_frames` frames, exactly that many are returned. `num_frames=-1`, or a request for more frames than the clip has, returns each frame of the clip once.
- The reported `total_num_frames`, `duration` and `frames_indices` describe the clip as it plays and match the frames returned.

This applies to every loader that decodes through these backends, including the fps-based `opencv_dynamic`, `qwen2_vl` and `qwen3_vl` loaders, and with `frame_recovery` enabled.

Videos that already load correctly, whether trimmed or not, must load exactly as they do today, with the same frames, indices and metadata. The backend that was selected must still be the one that decodes, and the OpenCV backend must keep working when the optional PyAV package is not installed.
