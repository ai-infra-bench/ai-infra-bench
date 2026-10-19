FROM quay.io/ascend/sglang@sha256:a586ac9311f5c95b6e5aff31c55427d91b13c96be974639e4a0eb7076447b515

# Keep a shallow editable copy of the native source. No runtime packages are changed.
RUN test "$(git -C /sgl-workspace/sglang rev-parse HEAD)" = 127b9e3283f7c2a43234b852ff5c9f1796d53624 \
    && git clone --depth 1 --no-tags file:///sgl-workspace/sglang /workspace/sglang \
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
