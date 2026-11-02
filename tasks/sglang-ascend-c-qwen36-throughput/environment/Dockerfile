FROM quay.io/ascend/sglang@sha256:e222360e4996e93000217ab737d88edf5b699142acdf99f7d0720546669b97c8

# Keep a shallow editable copy of the native source. No runtime packages are changed.
RUN test "$(git -C /sgl-workspace/sglang rev-parse HEAD)" = baa9befa381511cd4d56f83980951e5a45fffc6d \
    && git clone --depth 1 --no-tags file:///sgl-workspace/sglang /workspace/sglang \
    && cp /sgl-workspace/sglang/python/pyproject.toml /workspace/sglang/python/pyproject.toml \
    && rm /workspace/sglang/python/pyproject_npu.toml \
    && git -C /workspace/sglang remote remove origin \
    && rm -rf /sgl-workspace/sglang/.git
COPY app/ /workspace/task/
COPY lock/ /opt/task-lock/
RUN chmod +x /workspace/task/entrypoint.sh
ENV PYTHONPATH=/workspace/sglang/python \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    OMP_NUM_THREADS=1 PYTHONUNBUFFERED=1
WORKDIR /workspace/sglang
ENTRYPOINT ["/workspace/task/entrypoint.sh"]
CMD ["python3", "/workspace/task/launch.py"]
