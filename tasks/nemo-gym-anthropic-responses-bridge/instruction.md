# Use Responses and Messages harnesses with the same NeMo Gym backends

We use NeMo Gym to collect coding-agent rollouts. Gym's model backends speak
OpenAI Responses, but some of the harnesses we want to use speak Anthropic
Messages. We also need the other direction: a Gym client should be able to
prepare a request for an Anthropic backend and turn its reply back into Gym's
Responses types. I'd like this conversion to live in Gym so each integration
doesn't have to implement it again.

Please add a default `POST /v1/messages` handler to `SimpleResponsesAPIModel`
and a reusable converter for both directions. The handler should use the
model's existing `responses()` implementation. The reverse direction needs
reusable request/response conversion; it does not require a new configured
Anthropic model server.

What matters is that a coding-agent session can keep going across this
boundary. The harness should receive usable tool calls, execute them, and
return the results for the next turn, including when several calls finish in
a different order. Text, instructions, images and reasoning should survive the
trip along with the tool history. The caller must still be able to distinguish
a finished answer, a tool call, a truncated reply and an error, and account for
the backend's token usage.

Messages clients should work with both ordinary and streaming replies. It's
fine to buffer the backend's complete reply before producing Messages SSE;
this change doesn't need to make Gym's backend generation incremental. Keep
existing model routes, sessions and subclass overrides working, so backends
can inherit the new handler without each needing its own adapter.

The new public interfaces and supported protocol subset are defined in
[bridge-contract.md](/opt/nemo-gym/docs/bridge-contract.md), which is part of this task. Use Gym's
existing types and the installed OpenAI and Anthropic SDKs. No external API
credentials or model weights are needed. This is a protocol integration task;
RL token capture and provider-specific encrypted state are outside its scope.
