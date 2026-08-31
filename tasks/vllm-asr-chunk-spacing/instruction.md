I’m testing long-form audio with Cohere Transcribe, and the transcript looks fine except at the points where vLLM moves to the next audio chunk. For example, one chunk ends with `"Hello, this"` and the next starts with `"is vLLM"`, but the final response contains `"Hello, thisis vLLM"`.

I’m seeing the same thing with Qwen3 ASR in both streaming and non-streaming requests, including translation. I can reproduce it both when I leave the language unset and when I explicitly select English. I also tried Whisper, which looks fine. Longer transcripts contain several joined boundaries such as `"superstar.A founding"`, `"server.But I guess"`, and `"mode.Putting this on"`.

Could you take a look? My guess is that a space is being lost when chunks from languages like English are joined. I wouldn’t expect the same behavior for languages such as Chinese or Japanese, since their text is not normally separated by spaces. Find out what’s causing this and fix it.
