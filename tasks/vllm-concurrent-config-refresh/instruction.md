I am starting vLLM with four API server processes against the same model: vllm serve /models/valid-model --api-server-count 4

The model directory contains a valid `config.json`, and the same command can succeed when retried. However, startup sometimes fails with output like this:

INFO 08-30 12:53:04 [importing.py:53] Triton is installed but 0 active driver(s) found (expected 1). Disabling Triton to prevent runtime errors.
WARNING 08-30 12:53:04 [importing.py:65] Triton is installed, but doesn't include CPU backend. Disabling Triton.
INFO 08-30 12:53:04 [importing.py:88] Triton not installed or not compatible; certain GPU-related functions will not be available.
INFO 08-30 12:53:05 [api_utils.py:345]
INFO 08-30 12:53:05 [api_utils.py:345]        █     █     █▄   ▄█
INFO 08-30 12:53:05 [api_utils.py:345]  ▄▄ ▄█ █     █     █ ▀▄▀ █  version 0.0.0+g910cc8543a6907c9cc87c417f8f2420969278bf5
INFO 08-30 12:53:05 [api_utils.py:345]   █▄█▀ █     █     █     █  model   /models/valid-model
INFO 08-30 12:53:05 [api_utils.py:345]    ▀▀  ▀▀▀▀▀ ▀▀▀▀▀ ▀     ▀
INFO 08-30 12:53:05 [api_utils.py:345]
INFO 08-30 12:53:05 [api_utils.py:273] non-default args: {'model_tag': '/models/valid-model', 'api_server_count': 4, 'host': '127.0.0.1', 'port': 18000, 'model': '/models/valid-model', 'dtype': 'float32', 'max_model_len': 64, 'enforce_eager': True, 'skip_tokenizer_init': True, 'gpu_memory_utilization': 0.5, 'max_num_batched_tokens': 64, 'max_num_seqs': 1}
INFO 08-30 12:53:09 [model.py:623] Resolved architecture: OPTForCausalLM
INFO 08-30 12:53:09 [model.py:1788] Using max model len 64
INFO 08-30 12:53:09 [scheduler.py:242] Chunked prefill is enabled with max_num_batched_tokens=64.
INFO 08-30 12:53:09 [vllm.py:1109] Asynchronous scheduling is enabled.
WARNING 08-30 12:53:09 [vllm.py:1163] Enforce eager set, disabling torch.compile and CUDAGraphs. This is equivalent to setting -cc.mode=none -cc.cudagraph_mode=none
WARNING 08-30 12:53:09 [vllm.py:1213] Inductor compilation was disabled by user settings, optimizations settings that are only active during inductor compilation will be ignored.
INFO 08-30 12:53:09 [kernel.py:303] Final IR op priority after setting platform defaults: IrOpPriorityConfig(rms_norm=['native'], fused_add_rms_norm=['native'])
WARNING 08-30 12:53:09 [vllm.py:577] Model Runner V2 requires Triton; using the V1 model runner instead.
INFO 08-30 12:53:09 [compilation.py:329] Enabled custom fusions: norm_quant, act_quant
INFO 08-30 12:53:09 [utils.py:241] Started 4 API server processes
INFO 08-30 12:53:12 [importing.py:53] Triton is installed but 0 active driver(s) found (expected 1). Disabling Triton to prevent runtime errors.
INFO 08-30 12:53:12 [importing.py:53] Triton is installed but 0 active driver(s) found (expected 1). Disabling Triton to prevent runtime errors.
WARNING 08-30 12:53:12 [importing.py:65] Triton is installed, but doesn't include CPU backend. Disabling Triton.
INFO 08-30 12:53:12 [importing.py:88] Triton not installed or not compatible; certain GPU-related functions will not be available.
WARNING 08-30 12:53:12 [importing.py:65] Triton is installed, but doesn't include CPU backend. Disabling Triton.
INFO 08-30 12:53:12 [importing.py:88] Triton not installed or not compatible; certain GPU-related functions will not be available.
INFO 08-30 12:53:12 [importing.py:53] Triton is installed but 0 active driver(s) found (expected 1). Disabling Triton to prevent runtime errors.
WARNING 08-30 12:53:12 [importing.py:65] Triton is installed, but doesn't include CPU backend. Disabling Triton.
INFO 08-30 12:53:12 [importing.py:88] Triton not installed or not compatible; certain GPU-related functions will not be available.
INFO 08-30 12:53:12 [importing.py:53] Triton is installed but 0 active driver(s) found (expected 1). Disabling Triton to prevent runtime errors.
WARNING 08-30 12:53:12 [importing.py:65] Triton is installed, but doesn't include CPU backend. Disabling Triton.
INFO 08-30 12:53:12 [importing.py:88] Triton not installed or not compatible; certain GPU-related functions will not be available.
INFO 08-30 12:53:12 [importing.py:53] Triton is installed but 0 active driver(s) found (expected 1). Disabling Triton to prevent runtime errors.
WARNING 08-30 12:53:12 [importing.py:65] Triton is installed, but doesn't include CPU backend. Disabling Triton.
INFO 08-30 12:53:12 [importing.py:88] Triton not installed or not compatible; certain GPU-related functions will not be available.
(ApiServer_0 pid=87) Process ApiServer_0:
(ApiServer_0 pid=87) Traceback (most recent call last):
(ApiServer_0 pid=87)   File "/usr/local/lib/python3.12/multiprocessing/process.py", line 314, in _bootstrap
(ApiServer_0 pid=87)     self.run()
(ApiServer_0 pid=87)   File "/usr/local/lib/python3.12/multiprocessing/process.py", line 108, in run
(ApiServer_0 pid=87)     self._target(*self._args, **self._kwargs)
(ApiServer_0 pid=87)   File "/workspace/vllm/vllm/v1/utils.py", line 512, in run_api_server_worker_proc
(ApiServer_0 pid=87)     uvloop.run(
(ApiServer_0 pid=87)   File "/usr/local/lib/python3.12/site-packages/uvloop/__init__.py", line 96, in run
(ApiServer_0 pid=87)     return __asyncio.run(
(ApiServer_0 pid=87)            ^^^^^^^^^^^^^^
(ApiServer_0 pid=87)   File "/usr/local/lib/python3.12/asyncio/runners.py", line 195, in run
(ApiServer_0 pid=87)     return runner.run(main)
(ApiServer_0 pid=87)            ^^^^^^^^^^^^^^^^
(ApiServer_0 pid=87)   File "/usr/local/lib/python3.12/asyncio/runners.py", line 118, in run
(ApiServer_0 pid=87)     return self._loop.run_until_complete(task)
(ApiServer_0 pid=87)            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
(ApiServer_0 pid=87)   File "uvloop/loop.pyx", line 1518, in uvloop.loop.Loop.run_until_complete
(ApiServer_0 pid=87)   File "/usr/local/lib/python3.12/site-packages/uvloop/__init__.py", line 48, in wrapper
(ApiServer_0 pid=87)     return await main
(ApiServer_0 pid=87)            ^^^^^^^^^^
(ApiServer_0 pid=87)   File "/workspace/vllm/vllm/entrypoints/openai/api_server.py", line 773, in run_server_worker
(ApiServer_0 pid=87)     async with build_async_engine_client(
(ApiServer_0 pid=87)                ^^^^^^^^^^^^^^^^^^^^^^^^^^
(ApiServer_0 pid=87)   File "/usr/local/lib/python3.12/contextlib.py", line 210, in __aenter__
(ApiServer_0 pid=87)     return await anext(self.gen)
(ApiServer_0 pid=87)            ^^^^^^^^^^^^^^^^^^^^^
(ApiServer_0 pid=87)   File "/workspace/vllm/vllm/entrypoints/openai/api_server.py", line 139, in build_async_engine_client
(ApiServer_0 pid=87)     async with build_async_engine_client_from_engine_args(
(ApiServer_0 pid=87)                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
(ApiServer_0 pid=87)   File "/usr/local/lib/python3.12/contextlib.py", line 210, in __aenter__
(ApiServer_0 pid=87)     return await anext(self.gen)
(ApiServer_0 pid=87)            ^^^^^^^^^^^^^^^^^^^^^
(ApiServer_0 pid=87)   File "/workspace/vllm/vllm/entrypoints/openai/api_server.py", line 163, in build_async_engine_client_from_engine_args
(ApiServer_0 pid=87)     vllm_config = engine_args.create_engine_config(usage_context=usage_context)
(ApiServer_0 pid=87)                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
(ApiServer_0 pid=87)   File "/workspace/vllm/vllm/engine/arg_utils.py", line 1871, in create_engine_config
(ApiServer_0 pid=87)     model_config = self.create_model_config()
(ApiServer_0 pid=87)                    ^^^^^^^^^^^^^^^^^^^^^^^^^^
(ApiServer_0 pid=87)   File "/workspace/vllm/vllm/engine/arg_utils.py", line 1630, in create_model_config
(ApiServer_0 pid=87)     return ModelConfig(
(ApiServer_0 pid=87)            ^^^^^^^^^^^^
(ApiServer_0 pid=87)   File "/usr/local/lib/python3.12/site-packages/pydantic/_internal/_dataclasses.py", line 121, in __init__
(ApiServer_0 pid=87)     s.__pydantic_validator__.validate_python(ArgsKwargs(args, kwargs), self_instance=s)
(ApiServer_0 pid=87)   File "/workspace/vllm/vllm/config/model.py", line 559, in __post_init__
(ApiServer_0 pid=87)     hf_config = get_config(
(ApiServer_0 pid=87)                 ^^^^^^^^^^^
(ApiServer_0 pid=87)   File "/workspace/vllm/vllm/transformers_utils/config.py", line 734, in get_config
(ApiServer_0 pid=87)     config_dict, config = config_parser.parse(
(ApiServer_0 pid=87)                           ^^^^^^^^^^^^^^^^^^^^
(ApiServer_0 pid=87)   File "/workspace/vllm/vllm/transformers_utils/config.py", line 249, in parse
(ApiServer_0 pid=87)     config_dict, _ = PretrainedConfig.get_config_dict(
(ApiServer_0 pid=87)                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
(ApiServer_0 pid=87)   File "/usr/local/lib/python3.12/site-packages/transformers/configuration_utils.py", line 721, in get_config_dict
(ApiServer_0 pid=87)     config_dict, kwargs = cls._get_config_dict(pretrained_model_name_or_path, **kwargs)
(ApiServer_0 pid=87)                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
(ApiServer_0 pid=87)   File "/usr/local/lib/python3.12/site-packages/transformers/configuration_utils.py", line 810, in _get_config_dict
(ApiServer_0 pid=87)     config_dict = cls._dict_from_json_file(resolved_config_file)
(ApiServer_0 pid=87)                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
(ApiServer_0 pid=87)   File "/usr/local/lib/python3.12/site-packages/transformers/configuration_utils.py", line 921, in _dict_from_json_file
(ApiServer_0 pid=87)     with open(json_file, encoding="utf-8") as reader:
(ApiServer_0 pid=87)          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
(ApiServer_0 pid=87) FileNotFoundError: [Errno 2] No such file or directory: '/models/valid-model/config.json'
(ApiServer_2 pid=89) INFO 08-30 12:53:13 [model.py:623] Resolved architecture: OPTForCausalLM
(ApiServer_2 pid=89) INFO 08-30 12:53:13 [model.py:1788] Using max model len 64
(ApiServer_2 pid=89) INFO 08-30 12:53:13 [scheduler.py:242] Chunked prefill is enabled with max_num_batched_tokens=64.
(ApiServer_2 pid=89) INFO 08-30 12:53:13 [vllm.py:1109] Asynchronous scheduling is enabled.
(ApiServer_2 pid=89) WARNING 08-30 12:53:13 [vllm.py:1163] Enforce eager set, disabling torch.compile and CUDAGraphs. This is equivalent to setting -cc.mode=none -cc.cudagraph_mode=none
(ApiServer_2 pid=89) WARNING 08-30 12:53:13 [vllm.py:1213] Inductor compilation was disabled by user settings, optimizations settings that are only active during inductor compilation will be ignored.
(ApiServer_2 pid=89) INFO 08-30 12:53:13 [kernel.py:303] Final IR op priority after setting platform defaults: IrOpPriorityConfig(rms_norm=['native'], fused_add_rms_norm=['native'])
(ApiServer_3 pid=90) INFO 08-30 12:53:13 [model.py:623] Resolved architecture: OPTForCausalLM
(ApiServer_1 pid=88) INFO 08-30 12:53:13 [model.py:623] Resolved architecture: OPTForCausalLM
(ApiServer_3 pid=90) INFO 08-30 12:53:13 [model.py:1788] Using max model len 64
(ApiServer_1 pid=88) INFO 08-30 12:53:13 [model.py:1788] Using max model len 64
(ApiServer_3 pid=90) INFO 08-30 12:53:13 [scheduler.py:242] Chunked prefill is enabled with max_num_batched_tokens=64.
(ApiServer_1 pid=88) INFO 08-30 12:53:13 [scheduler.py:242] Chunked prefill is enabled with max_num_batched_tokens=64.
(ApiServer_1 pid=88) INFO 08-30 12:53:13 [vllm.py:1109] Asynchronous scheduling is enabled.
(ApiServer_3 pid=90) INFO 08-30 12:53:13 [vllm.py:1109] Asynchronous scheduling is enabled.
(ApiServer_1 pid=88) WARNING 08-30 12:53:13 [vllm.py:1163] Enforce eager set, disabling torch.compile and CUDAGraphs. This is equivalent to setting -cc.mode=none -cc.cudagraph_mode=none
(ApiServer_3 pid=90) WARNING 08-30 12:53:13 [vllm.py:1163] Enforce eager set, disabling torch.compile and CUDAGraphs. This is equivalent to setting -cc.mode=none -cc.cudagraph_mode=none
(ApiServer_1 pid=88) WARNING 08-30 12:53:13 [vllm.py:1213] Inductor compilation was disabled by user settings, optimizations settings that are only active during inductor compilation will be ignored.
(ApiServer_3 pid=90) WARNING 08-30 12:53:13 [vllm.py:1213] Inductor compilation was disabled by user settings, optimizations settings that are only active during inductor compilation will be ignored.
(ApiServer_1 pid=88) INFO 08-30 12:53:13 [kernel.py:303] Final IR op priority after setting platform defaults: IrOpPriorityConfig(rms_norm=['native'], fused_add_rms_norm=['native'])
(ApiServer_3 pid=90) INFO 08-30 12:53:13 [kernel.py:303] Final IR op priority after setting platform defaults: IrOpPriorityConfig(rms_norm=['native'], fused_add_rms_norm=['native'])
(ApiServer_2 pid=89) WARNING 08-30 12:53:13 [vllm.py:577] Model Runner V2 requires Triton; using the V1 model runner instead.
(ApiServer_2 pid=89) INFO 08-30 12:53:13 [compilation.py:329] Enabled custom fusions: norm_quant, act_quant
(ApiServer_3 pid=90) WARNING 08-30 12:53:13 [vllm.py:577] Model Runner V2 requires Triton; using the V1 model runner instead.
(ApiServer_3 pid=90) INFO 08-30 12:53:13 [compilation.py:329] Enabled custom fusions: norm_quant, act_quant
(ApiServer_1 pid=88) WARNING 08-30 12:53:13 [vllm.py:577] Model Runner V2 requires Triton; using the V1 model runner instead.
(ApiServer_1 pid=88) INFO 08-30 12:53:13 [compilation.py:329] Enabled custom fusions: norm_quant, act_quant
Traceback (most recent call last):
  File "/workspace/vllm/vllm/v1/utils.py", line 286, in gather_actual_addresses
    msg: dict[str, str] = item.recv()
                          ^^^^^^^^^^^
  File "/usr/local/lib/python3.12/multiprocessing/connection.py", line 250, in recv
    buf = self._recv_bytes()
          ^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/multiprocessing/connection.py", line 430, in _recv_bytes
    buf = self._recv(4)
          ^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/multiprocessing/connection.py", line 399, in _recv
    raise EOFError
EOFError

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/usr/local/bin/vllm", line 10, in <module>
    sys.exit(main())
             ^^^^^^
  File "/workspace/vllm/vllm/entrypoints/cli/main.py", line 95, in main
    args.dispatch_function(args)
  File "/workspace/vllm/vllm/entrypoints/cli/serve.py", line 144, in cmd
    run_multi_api_server(args)
  File "/workspace/vllm/vllm/entrypoints/cli/serve.py", line 366, in run_multi_api_server
    api_server_manager.gather_actual_addresses()
  File "/workspace/vllm/vllm/v1/utils.py", line 288, in gather_actual_addresses
    raise RuntimeError(
RuntimeError: API server ApiServer_0 closed its address pipe without reporting its bound ZMQ addresses


Why can one API server fail to read the configuration while the other servers load the same model successfully? Fix the startup failure in `/workspace/vllm` so valid model configurations load reliably with multiple API servers.

Genuinely missing, malformed, or unsupported configurations must continue to fail instead of being silently accepted.
