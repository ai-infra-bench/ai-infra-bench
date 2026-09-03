I am testing Kimi K2.5 on SWE-bench Verified with mini-swe-agent, using vLLM's streaming `/v1/responses` endpoint. The benchmark score came out lower than expected, so I checked the trajectories for some of the failed tasks. I found that several did not end with a wrong patch or a failed test. They stopped before mini-swe-agent ran the next shell command, even though the request returned HTTP 200 and the function call was marked completed.

This is the completed function-call item from one interrupted trajectory:

```json
{
  "arguments": "280p' astropy/modeling/separable.py && rg -n '_cstack|separability_matrix|compound_models' astropy/modeling/separable.py astropy/modeling/tests/test_separable.py && python -m pytest astropy/modeling/tests/test_separable.py -q\"}",
  "call_id": "call_88873b31e51a5a4d",
  "name": "bash",
  "type": "function_call",
  "id": "beb1affb24605641",
  "namespace": null,
  "status": "completed"
}
```

mini-swe-agent stopped the turn with:

```text
Tool call error:

<error>
Error parsing tool call arguments: Extra data: line 1 column 4 (char 3).Missing 'command' argument in bash tool call.
</error>

Here is general guidance on how to submit correct toolcalls:

Every response needs to use the 'bash' tool at least once to execute commands.

Call the bash tool with your command as the argument:
- Tool: bash
- Arguments: {"command": "your_command_here"}

If you have completed your assignment, please consult the first message about how to
submit your solution (you will not be able to continue working on this task after that).
```

I found another interrupted trajectory where the model attempted two bash calls in the same response. The client received this completed item before the stream ended:

```json
{
  "arguments": "tropy/modeling/separable.py && git log -5 --oneline -- astropy/modeling/separable.py\"}",
  "call_id": "call_abcc176cf553614d",
  "name": "bash",
  "type": "function_call",
  "id": "b818202ad9405f0f",
  "namespace": null,
  "status": "completed"
}
```

The second call never reached the client, and the HTTP stream ended with:

```text
httpx.RemoteProtocolError: peer closed connection without sending complete message body (incomplete chunked read)
```

These were not isolated cases. Several other failed trajectories ended with incomplete or missing bash arguments, while some trajectories from the same run executed their commands normally. The mix of successful and interrupted trajectories makes this look different from a model simply choosing the wrong command.

I think this may be a vLLM inference bug. Please find the cause and fix it in `/workspace/vllm` so mini-swe-agent receives usable tool calls without changing responses that already work. I currently don't have the Kimi model weights in this environment.
