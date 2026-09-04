Implement an Anthropic-compatible inference server in vLLM's Rust frontend that is fully compatible with `anthropic==1.3.0`.

All functionality exposed by the SDK's Messages and token-counting interfaces must work correctly when the SDK is configured to use the local vLLM server.

The implementation must work when vLLM is started with `VLLM_USE_RUST_FRONTEND=1`, and it must preserve the Rust frontend's existing APIs.

Message Batches and other Anthropic SDK resources outside the Messages and token-counting interfaces are out of scope. The Rust frontend must serve the requests itself rather than forwarding them to the Python frontend.

For tools that are hosted by Anthropic's platform, compatibility means accepting their SDK request types and conversation content blocks; local vLLM is not expected to execute external Anthropic services.
