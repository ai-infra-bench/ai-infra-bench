# AI Infra Bench

**How much real AI-inference engineering work can frontier models solve?**

AI Infra Bench is a public benchmark built from real vLLM maintainer workloads. Its first release will contain 100 expert-reviewed tasks: 76 representative bugs, features, performance changes, refactors, and tests, plus 24 memorable problems nominated by maintainers. Every task will run offline in a reproducible environment and be graded by execution-based tests, with performance measured where relevant.

We will evaluate Claude Opus 5, GPT-5.6, Hunyuan 4 Preview, Qwen 3.8 Max, Kimi K3, GLM 5.3, and MiniMax M3 using Claude Code, Codex, and mini-swe-agent under frozen tasks, environments, and budgets.

## Timeline

- August 16: workload analysis and 200 PR candidates
- August 21: five validated Harbor tasks
- Week of August 29: continue building and reviewing the 100-task benchmark
- Week of September 7: begin evaluation

## License

Software and documentation are licensed under [Apache-2.0](LICENSE). The survey dataset under `data/` is licensed under [CC BY 4.0](data/LICENSE).
