import contextlib,copy,ctypes,json,os,socket,sys,tempfile,time
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import Future
from vllm.v1.engine.core import EngineCore
import fixtures as f
from vllm.distributed import init_distributed_environment, ensure_model_parallel_initialized
from vllm.distributed.kv_transfer.kv_connector.v1 import nixl_connector as nx
from vllm.forward_context import ForwardContext
from vllm.config import DeviceConfig, set_current_vllm_config

from nixl_io import IO


def configuration(model,engine,port):
    model=f.ModelConfig(model=model,dtype='float16',trust_remote_code=False,skip_tokenizer_init=True)
    cache=f.CacheConfig(block_size=16,gpu_memory_utilization=.9,cache_dtype='auto',enable_prefix_caching=True)
    cache.num_gpu_blocks=32
    config=f.VllmConfig(model_config=model,cache_config=cache,
      scheduler_config=f.SchedulerConfig(max_num_seqs=4,max_num_batched_tokens=128,max_model_len=2048,enable_chunked_prefill=True,is_encoder_decoder=False),
      device_config=DeviceConfig('cpu'),parallel_config=f.ParallelConfig(),
      kv_transfer_config=f.KVTransferConfig(kv_connector='NixlConnector',kv_role='kv_both',kv_buffer_device='cpu',engine_id=engine))
    kv=f.KVCacheConfig(num_blocks=32,kv_cache_tensors=[],kv_cache_groups=[f.KVCacheGroupSpec(['layer'],f.FullAttentionSpec(block_size=16,num_kv_heads=12,head_size=64,dtype=f.torch.float16))])
    return config,kv

def request(identity,port,*,remote=False,value=1,max_tokens=1):
    if not f._HASH_INITIALIZED:
        f.init_none_hash(f.sha256)
        f._HASH_INITIALIZED = True
    transfer = {'do_remote_prefill': True, 'remote_engine_id': 'producer',
        'remote_request_id': 'p-' + identity, 'remote_host': '127.0.0.1',
        'remote_port': port, 'remote_block_ids': [[1,2,3,4]], 'tp_size': 1}
    params=f.SamplingParams(max_tokens=max_tokens,ignore_eos=True,
        extra_args={'kv_transfer_params': transfer} if remote else None)
    params.update_from_generation_config({},50256)
    return f.Request(request_id=identity,prompt_token_ids=[value]*64,
        sampling_params=params,pooling_params=None,
        block_hasher=f.get_request_block_hasher(16,f.sha256))



def exercise(model_dir):
    """Real connector scheduler/worker and real core output transitions.

    Only NIXL's external IO agent is substituted. CPU buffers, registration,
    metadata construction, ZMQ handshake, zero/read transfer dispatch and
    completion collection use candidate production code. No private request
    status, receive map or helper is populated by the test.
    """
    with tempfile.TemporaryDirectory(prefix='nixl-behavior-') as tmp:
        os.environ.setdefault('GLOO_SOCKET_IFNAME', 'lo')
        init_distributed_environment(world_size=1,rank=0,
            distributed_init_method='file://'+tmp+'/group',local_rank=0,backend='gloo')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        old_port = os.environ.get('VLLM_NIXL_SIDE_CHANNEL_PORT')
        os.environ['VLLM_NIXL_SIDE_CHANNEL_PORT'] = str(port)
        pconfig,pkv=configuration(model_dir,'producer',port)
        dconfig,dkv=configuration(model_dir,'consumer',port)
        config_context=set_current_vllm_config(dconfig)
        config_context.__enter__()
        ensure_model_parallel_initialized(1,1)
        affinity=os.sched_getaffinity(0)
        producer=nx.NixlConnector(pconfig,f.KVConnectorRole.WORKER,pkv)
        consumer=nx.NixlConnector(dconfig,f.KVConnectorRole.WORKER,dkv)
        os.sched_setaffinity(0,affinity)
        for connector, config in ((producer,pconfig),(consumer,dconfig)):
            backend=nx.get_current_attn_backend(config)
            shape=backend.get_kv_cache_shape(32,16,12,64)
            connector.register_kv_caches({'layer':f.torch.zeros(shape,dtype=f.torch.float16)})
        pcontrol=nx.NixlConnector(pconfig,f.KVConnectorRole.SCHEDULER,pkv)
        pcontrol.set_xfer_handshake_metadata({0:producer.get_handshake_metadata()})
        scheduler=f.Scheduler(vllm_config=dconfig,kv_cache_config=dkv,block_size=16,
            log_stats=False,structured_output_manager=f.StructuredOutputManager(dconfig))
        ctx=ForwardContext(no_compile_layers={},attn_metadata={},slot_mapping={},virtual_engine=0)
        observations=[]

        class Runner:
            token = 0
            def execute_model(self, out, **kwargs):
                consumer.bind_connector_metadata(out.kv_connector_metadata)
                consumer.start_load_kv(ctx)
                sent, recv = consumer.get_finished(set(out.finished_req_ids))
                ids = list(out.num_scheduled_tokens)
                future = Future()
                future.set_result(f.ModelRunnerOutput(req_ids=ids,
                    req_id_to_index={rid:i for i,rid in enumerate(ids)},
                    sampled_token_ids=[[self.token] for _ in ids],
                    kv_connector_output=f.KVConnectorOutput(finished_recving=recv)))
                consumer.get_kv_connector_stats()
                return future

        runner = Runner()
        engine = SimpleNamespace(scheduler=scheduler, model_executor=runner,
            log_error_detail=lambda *a: contextlib.nullcontext(),
            log_iteration_details=lambda *a: contextlib.nullcontext(),
            _process_aborts_queue=lambda: None)

        def tick(token):
            runner.token = token
            results, _ = EngineCore.step(engine)
            return [[o.request_id,o.new_token_ids,o.finish_reason is not None]
                    for client in results.values() for o in client.outputs]

        try:
            # Complete a real non-empty receive first. This establishes the
            # remote connection through normal IO, so each later notification
            # success/failure scenario executes while that fault is selected.
            prime = request('nixl-prime', port, remote=True, value=9)
            scheduler.add_request(prime)
            prime_outputs = []
            for step in range(200):
                prime_outputs.extend(tick(299))
                if scheduler.get_request_counts() == (0, 0) and step > 1:
                    break
                time.sleep(.005)
            observations.append({'kind': 'prime', 'outputs': prime_outputs,
                                 'counts': list(scheduler.get_request_counts())})
            # Fill a real local prefix through normal scheduling, then retain
            # its public KVCacheBlocks view for the connector boundary below.
            warm=request('nixl-warm',port)
            scheduler.add_request(warm);out=scheduler.schedule()
            available=scheduler.kv_cache_manager.get_blocks(warm.request_id)
            scheduler.update_from_output(out,f.ModelRunnerOutput(req_ids=['nixl-warm'],
                req_id_to_index={'nixl-warm':0},sampled_token_ids=[[300]]))
            for failed in (False, True):
                IO.fail_notifications=failed
                req=request('nixl-hit-'+str(failed),port,remote=True)
                # A full locally computed prefix is a documented input to the
                # connector API. The frozen scheduler may recompute final
                # logits; we never manufacture a WAITING_FOR_REMOTE_KVS state.
                match=scheduler.connector.get_num_new_matched_tokens(req,64)
                # Establish a real lease for this request before invoking the
                # post-allocation connector API. Roll back that lease before
                # normal EngineCore admission; cached data remains available.
                scheduler.kv_cache_manager.allocate_slots(req, 1,
                    num_new_computed_tokens=64, new_computed_blocks=available)
                leased = scheduler.kv_cache_manager.get_blocks(req.request_id)
                scheduler.connector.update_state_after_alloc(req,leased,0)
                scheduler.kv_cache_manager.free(req)
                scheduler.add_request(req)
                calls=IO.notification_attempts
                outputs=[]
                for step in range(200):
                    outputs.extend(tick(301))
                    if IO.notification_attempts>calls and step>1:
                        break
                    time.sleep(.005)
                observations.append({'kind':'full-hit','notification_fails':failed,
                    'matched':list(match),'outputs':outputs,
                    'counts':list(scheduler.get_request_counts()),
                    'notification_attempts':IO.notification_attempts-calls})

                # Cancel a request before it starts. Production NIXL creates
                # producer-only notification metadata; a bogus receive result
                # would reach the real scheduler and raise or revive this ID.
                cancelled=request('nixl-cancel-'+str(failed),port,remote=True)
                scheduler.add_request(cancelled)
                scheduler.finish_requests(cancelled.request_id,f.RequestStatus.FINISHED_ABORTED)
                cancel_outputs=[]
                for _ in range(4):
                    cancel_outputs.extend(tick(399));time.sleep(.005)
                fresh=request('nixl-after-cancel-'+str(failed),port,value=3)
                scheduler.add_request(fresh)
                for _ in range(4):cancel_outputs.extend(tick(307))
                observations.append({'kind':'cancel','notification_fails':failed,
                    'outputs':cancel_outputs,'counts':list(scheduler.get_request_counts())})

            # A genuine non-empty receive still goes through the real worker's
            # transfer completion collector. No finished IDs are injected.
            IO.fail_notifications=False
            cold=request('nixl-read',port,remote=True,value=7)
            scheduler.add_request(cold)
            outputs=[]
            for step in range(200):
                outputs.extend(tick(311))
                if scheduler.get_request_counts()==(0,0) and step>1:break
                time.sleep(.005)
            observations.append({'kind':'read','outputs':outputs,
                'counts':list(scheduler.get_request_counts())})
        finally:
            scheduler.connector.shutdown();pcontrol.shutdown()
            producer.shutdown();consumer.shutdown()
            config_context.__exit__(None,None,None)
            if old_port is None:os.environ.pop('VLLM_NIXL_SIDE_CHANNEL_PORT',None)
            else:os.environ['VLLM_NIXL_SIDE_CHANNEL_PORT']=old_port
            os.sched_setaffinity(0,affinity)
            # Fixture-owned transport state is not part of retained candidate memory.
            IO.agents.clear();IO.lists.clear();IO.transfers.clear()
            IO.fail_notifications=False
            from vllm.distributed.parallel_state import destroy_model_parallel, destroy_distributed_environment
            destroy_model_parallel();destroy_distributed_environment()
        return observations
