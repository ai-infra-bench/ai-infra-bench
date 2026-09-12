def observe_fresh(inputs):
    """Return production observations, without deciding what should pass."""
    from vllm.sampling_params import SamplingParams
    from vllm.v1.worker.gpu_input_batch import CachedRequestState
    specs=inputs['features'];features=[];outputs=[];allocations=[]
    for i,f in enumerate(specs):
        mask=None if f['indices'] is None else sparse_mask(f['length'],f['indices'])
        rows=torch.tensor(f['rows'],dtype=torch.float32).reshape(-1,4)
        outputs.append(rows)
        features.append(MultiModalFeatureSpec(data=SimpleNamespace(modality='image',rows=rows),
            modality='image',identifier=f'fresh-{i}-item-0',
            mm_position=PlaceholderRange(f['offset'],f['length'],mask)))
        req=SparseRequest(f'fresh-{i}',[mask],dense_length=f['length'])
        n=len(rows);manager=EncoderCacheManager(cache_size=n)
        admit=manager.can_allocate(req,0,n,0)
        if admit:manager.allocate(req,0)
        short=EncoderCacheManager(cache_size=max(0,n-1))
        allocations.append(dict(admit=admit,free=manager.num_free_slots,
                               short_admit=short.can_allocate(req,0,n,0) if n else None))
    params=SamplingParams(max_tokens=1)
    request=Request(request_id='fresh',prompt_token_ids=[1]*37,sampling_params=params,
                    pooling_params=None,eos_token_id=None,mm_features=features)
    scheduler=object.__new__(Scheduler)
    scheduler.ec_connector=None;scheduler.is_encoder_decoder=False
    scheduler.scheduler_config=SimpleNamespace(disable_chunked_mm_input=False)
    n=len(outputs[0]);empty=[];nonempty=[]
    first=specs[0]['indices'][0]
    for capacity,budget in [(0,n),(n-1,n),(n,0),(n,n-1),(n,n)]:
        scheduler.encoder_cache_manager=EncoderCacheManager(cache_size=capacity)
        empty.append(Scheduler._try_schedule_encoder_inputs(scheduler,request,0,first,budget))
        scheduler.encoder_cache_manager=EncoderCacheManager(cache_size=capacity)
        nonempty.append(Scheduler._try_schedule_encoder_inputs(scheduler,request,first,1,budget))
    # Preserve the real caller's EAGLE lookahead, including mask-free inputs.
    lookahead=[]
    offset=specs[3]['offset']
    configurations=[(None,n,n,offset-2,2), (None,0,n,offset-2,2),
                    (None,n,0,offset-2,2), (None,n,n-1,offset-2,2),
                    ([1,n-1],0,0,offset-2,2), ([0,n-1],2,2,offset,1)]
    for indices,capacity,budget,start,count in configurations:
        mask=None if indices is None else sparse_mask(n,indices)
        feature=MultiModalFeatureSpec(data=None,modality='image',identifier='lookahead',
                                     mm_position=PlaceholderRange(offset,n,mask))
        look_request=Request(request_id='lookahead',prompt_token_ids=[1]*37,
            sampling_params=params,pooling_params=None,eos_token_id=None,mm_features=[feature])
        scheduler.encoder_cache_manager=EncoderCacheManager(cache_size=capacity)
        lookahead.append(Scheduler._try_schedule_encoder_inputs(
            scheduler,look_request,start,count,budget,shift_computed_tokens=1))
    profile = observe_encoder_capacity(features[0].mm_position)
    req=SparseRequest('fresh-0',[features[0].mm_position.is_embed])
    other=SparseRequest('other',[features[0].mm_position.is_embed])
    manager=EncoderCacheManager(cache_size=n);manager.allocate(req,0);manager.free_encoder_input(req,0)
    if manager.can_allocate(other,0,n,0):manager.allocate(other,0)
    eviction=dict(free=manager.num_free_slots,freed=manager.get_freed_mm_hashes())
    capacity=sum(len(x) for x in outputs)
    manager=scheduler.encoder_cache_manager=EncoderCacheManager(cache_size=capacity)
    state=CachedRequestState(req_id='fresh',prompt_token_ids=[1]*37,mm_features=features,
        sampling_params=params,generator=None,block_ids=([],),num_computed_tokens=0,output_token_ids=[])
    class Buffer:
        def __init__(self):self.cpu=torch.empty(37,dtype=torch.bool)
        def copy_to_gpu(self,count):return self.cpu[:count].clone()
    runner=object.__new__(GPUModelRunner)
    runner.input_batch=SimpleNamespace(req_ids=['fresh']);runner.requests={'fresh':state}
    runner.encoder_cache={};runner.is_mm_embed=Buffer();runner.device=torch.device('cpu')
    runner.pin_memory=False;runner.is_multimodal_pruning_enabled=False;runner.uses_mrope=False
    runner.maybe_save_ec_to_connector=lambda *args:None
    runner.model=SimpleNamespace(embed_multimodal=lambda rows:[r.clone() for r in rows])
    old=runner_module.group_mm_kwargs_by_modality
    runner_module.group_mm_kwargs_by_modality=lambda items,**kwargs:[('image',len(items),{'rows':[item.rows for item in items]})]
    def gather(a,b):
        state.num_computed_tokens=a
        output=SimpleNamespace(total_num_scheduled_tokens=b-a,num_scheduled_tokens={'fresh':b-a})
        rows,mask=GPUModelRunner._gather_mm_embeddings(runner,output)
        return dict(mask=mask.tolist(),rows=torch.cat(rows).tolist() if rows else [])
    chain=[]
    try:
        for a,b in inputs['windows']:
            ids,count,remaining,external=Scheduler._try_schedule_encoder_inputs(scheduler,request,a,b-a,capacity)
            for i in ids:manager.allocate(request,i)
            output=SimpleNamespace(scheduled_encoder_inputs={'fresh':ids} if ids else {},
                total_num_scheduled_tokens=count,num_scheduled_tokens={'fresh':count})
            GPUModelRunner._execute_mm_encoder(runner,output)
            chain.append(dict(schedule=[ids,count,remaining,external],free=manager.num_free_slots,**gather(a,a+count)))
            request.num_computed_tokens=state.num_computed_tokens=a+count
        cached=[gather(a,b) for a,b in inputs['cached_windows']]
    finally:runner_module.group_mm_kwargs_by_modality=old
    return dict(lookahead=lookahead,allocations=allocations,empty=empty,nonempty=nonempty,profile=profile,
                eviction=eviction,chain=chain,cached=cached)
