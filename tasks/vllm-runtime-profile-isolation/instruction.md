A user runs a vLLM server for several customers. Each customer has their own model setup. Most requests work normally, but the user noticed something odd while the server was being updated without a restart.

They first sent the same two long, greedy requests twice and got the same output both times. Then they sent those requests again and, while they were still running, added setups for two other customers through the server's runtime update API. The update calls succeeded and there were no errors in the server log, but after a while one of the original responses no longer matched its earlier output. If they repeated the test without adding anything in the background, the responses stayed identical.

This is roughly how they reproduced it:

1. Start one server and allow it to keep only two customer setups active at once.
2. Send two long requests that use two different existing setups. Run them twice without changing the server and save the output from each request.
3. Send the same two requests again. While they are running, repeatedly add two other customer setups through the runtime update API.
4. Compare each new response with the saved response for that same request. On an affected build, a response changes only in the run with background updates, even though that request still asks for the same setup.

The original report used a public model on a GPU server. The model weights and their serving script are not included here. Work in `/workspace/vllm` and make the smallest local reproduction you can that still follows the sequence above.

Find and fix the bug so a running request cannot be changed by another customer's setup. The server must still support adding setups at runtime and keeping only a limited number active. Normal requests without background updates must still work. Switching a request to another setup, adding a setup without using it, replacing setups several times, sending a request with no customer setup, and using an older setup again later must also keep working. Do not solve the problem by turning off runtime updates or by keeping every setup active forever.
