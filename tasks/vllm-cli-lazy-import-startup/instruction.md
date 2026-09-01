An import-time profile on the current tree shows that lightweight vLLM CLI paths, including help and argument handling, initialize benchmark modules, plotting/dataframe libraries, and much of torch._inductor before they know which command will run.

On the same machine with torch 2.11, vllm --help took 7.91 seconds, importing vllm.entrypoints.cli.main took 7.4 seconds, and importing vllm alone took about 2.3 seconds. The corresponding target measurements were 6.24 seconds, 1.79 seconds, and 1.79 seconds; a real serve startup also dropped from about 31 seconds to 28–29 seconds.

Reduce unnecessary cold-start work on unrelated CLI paths. vllm --help, vllm serve, the current global flags, every existing vllm bench subcommand, and sweep plot/plot_pareto must still work. Plotting dependencies may remain optional but must still be loaded when a figure is actually generated. TORCHINDUCTOR_COMPILE_THREADS must remain set to 1, and torch._inductor must still observe compile_threads=1 when its config is used.

Use `/opt/repro/cli_import_report.py` to compare fresh `import vllm` and `import vllm.entrypoints.cli.main` processes on the same machine. The CLI layer should add only a small fraction of the plain import time; an absolute wall-clock threshold alone is not sufficient because host speed and warm filesystem state vary.
