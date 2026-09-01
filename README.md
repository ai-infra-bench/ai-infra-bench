# AI Infra Bench

**How much real AI infrastructure engineering work can frontier models solve?**

AI Infra Bench is a benchmark built from real AI infrastructure engineering workloads. Its first release focuses exclusively on vLLM and will contain 50 expert-reviewed tasks: approximately 25 CPU tasks covering representative bugs, features, performance changes, refactors, and tests, plus approximately 25 GPU tasks drawn from memorable problems nominated by vLLM maintainers. Future releases will expand to SGLang, TensorRT-LLM, PyTorch, and end-to-end use cases contributed by downstream users.

In addition to the existing public task set, the benchmark will include a private set. Each model will be evaluated separately on the public and private sets.

We will evaluate Claude Opus 5, GPT-5.6, Hunyuan 4 Preview, Qwen 3.8 Max, Kimi K3, GLM 5.3, and MiniMax M3 using Claude Code, Codex, and mini-swe-agent under frozen tasks, environments, and budgets.

## Timeline

- August 16: workload analysis and 200 PR candidates
- August 21: five validated Harbor tasks
- Week of August 29: continue building and reviewing the 100-task benchmark
- Week of September 7: begin evaluation

## License

Software and documentation are licensed under [Apache-2.0](LICENSE). The survey dataset under `data/` is licensed under [CC BY 4.0](data/LICENSE).
