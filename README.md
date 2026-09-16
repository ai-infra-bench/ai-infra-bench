# AI Infra Bench

**How much real AI-inference engineering work can frontier coding agents solve?**

AI Infra Bench is a public benchmark built from real vLLM maintainer workloads. Its first release will contain 100 expert-reviewed tasks: 76 representative bugs, features, performance changes, refactors, and tests, plus 24 memorable problems nominated by maintainers. Every task will run offline in a reproducible environment and be graded by execution-based tests, with performance measured where relevant.

We will evaluate Claude Opus 5, GPT-5.6, Hunyuan 3, Qwen 3.8 Max, Kimi K3, GLM 5.2, and MiniMax M3 using Claude Code, Codex, and mini-swe-agent under frozen tasks, environments, and budgets.

## Timeline

- August 16: workload analysis and 200 PR candidates
- August 21: five validated Harbor tasks
- Week of August 22: build the 100-task benchmark
- Week of August 29: begin evaluation

## Links

- [Weekly sync notes](https://docs.google.com/document/d/16E7Xm08JTIwKT6pbC5YezCEu-UbbNDzA1PTjk0ZH724/edit?tab=t.0#heading=h.45siya4cjzvw)
- [Benchmark design](docs/BENCHMARK_DESIGN.md)
- [RQ1 conclusions](analysis/rq1/RQ1_CONCLUSIONS_CN.md)
- [RQ1 methods](docs/RQ1_METHODS.md)
- [RQ1 derived Issue data and PR labels](data/rq1/README.md)
- [Dataset card](docs/DATASET_CARD.md)
- [Contributing](CONTRIBUTING.md)

## License

Software and documentation are licensed under [Apache-2.0](LICENSE). The survey dataset under `data/` is licensed under [CC BY 4.0](data/LICENSE).
