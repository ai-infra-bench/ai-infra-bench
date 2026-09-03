I ran into a strange failure while using open code with a local OpenAI-compatible endpoint backed by vLLM. The model was `MiniMaxAI/MiniMax-M2.5`.

My project has this property in `pom.xml`:

```xml
<central.search.url>https://search.maven.org/solrsearch/select?q=g%3Aorg.junit.jupiter&amp;rows=20&amp;wt=json</central.search.url>
```

This is roughly how the session went:

```console
$ opencode run --model vllm-local/MiniMaxAI/MiniMax-M2.5 --format json \
    "Change the Maven Central query limit from 20 to 100. I need a higher limit."

OpenCode edit event:
status: error
error: Could not find oldString in the file. It must match exactly, including whitespace, indentation, and line endings.

$ opencode run --continue --format json \
    "? You have to read the file before you edit it. Read it again and retry with the exact oldString that's actually there."

OpenCode edit event:
status: error
error: Could not find oldString in the file. It must match exactly, including whitespace, indentation, and line endings.

$ opencode run --continue --format json \
    "It failed again. Seriously, what are you even changing?? Show me the exact oldString you used."
```

OpenCode then returned this text event:

````json
{
  "type": "text",
  "part": {
    "text": "I used this exact oldString:\n```xml\n<central.search.url>https://search.maven.org/solrsearch/select?q=g%3Aorg.junit.jupiter&amp;rows=20&amp;wt=json</central.search.url>\n```"
  }
}
````

That should match the file exactly, so at first I thought OpenCode's `edit` tool was broken. I dug into the OpenCode events and found the tool call it had actually received:

```json
{
  "type": "tool_use",
  "timestamp": 1788425956275,
  "sessionID": "ses_f998195ecffeVs5Gl4eUboyHif",
  "part": {
    "type": "tool",
    "tool": "edit",
    "callID": "call_a0180ff8ba622a195b91ae4f",
    "state": {
      "status": "error",
      "input": {
        "filePath": "/workspace/maven-search-client/pom.xml",
        "oldString": "<central.search.url>https://search.maven.org/solrsearch/select?q=g%3Aorg.junit.jupiter&rows=20&wt=json</central.search.url>",
        "newString": "<central.search.url>https://search.maven.org/solrsearch/select?q=g%3Aorg.junit.jupiter&rows=100&wt=json</central.search.url>"
      },
      "error": "Could not find oldString in the file. It must match exactly, including whitespace, indentation, and line endings.",
      "time": {
        "start": 1788425956258,
        "end": 1788425956267
      }
    },
    "id": "prt_0667e6b9e001QWkvWek6Nr5OQ2",
    "sessionID": "ses_f998195ecffeVs5Gl4eUboyHif",
    "messageID": "msg_0667e6b6e001gVTl0dDj6Fw2BK"
  }
}
```

That is clearly not the same string. The file contains `&amp;`, but the arguments passed to `edit` contain plain `&`. This does not look like an OpenCode matching bug, and the model can produce the escaped text correctly in a normal response. So this looks like an escaping issue somewhere in vLLM. My vLLM checkout is at `/workspace/vllm`. Please track down the problem and fix it.

I doubt this is limited to one URL or even to MiniMax. Please investigate how broad the impact is; other models may be running into the same problem. Fix it properly and comprehensively, but do not break behavior that already works.
