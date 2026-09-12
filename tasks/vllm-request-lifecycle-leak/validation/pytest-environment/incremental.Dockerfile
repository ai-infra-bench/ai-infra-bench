FROM ai-infra-bench/vllm-request-lifecycle-leak:base-e94ec597334d-avx2
USER root
# Install the local test runner in the agent interpreter before going offline.
RUN python -m pip install --no-cache-dir pytest==8.4.1 pytest-asyncio==1.1.0 tblib==3.1.0

USER agent
