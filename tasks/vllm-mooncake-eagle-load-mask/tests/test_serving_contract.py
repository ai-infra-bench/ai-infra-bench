from __future__ import annotations

import asyncio
import json

import httpx

from vllm.entrypoints.cli import serve as serve_module
from vllm.entrypoints.openai.api_server import build_app
from vllm.entrypoints.openai.chat_completion.protocol import (
    ChatCompletionResponse,
    ChatCompletionResponseChoice,
    ChatMessage,
)
from vllm.entrypoints.openai.engine.protocol import UsageInfo
from vllm.utils.argparse_utils import FlexibleArgumentParser


TARGET_MODEL = "MiniMaxAI/MiniMax-M2.5"
EXPECTED_RECORD = {
    "region": "us-west",
    "replica_count": 4,
    "maximum_batch_size": 16,
}
MESSAGES = [
    {
        "role": "system",
        "content": (
            "You maintain a deployment record. When a setting is updated, "
            "discard its previous value and answer only from the latest record."
        ),
    },
    {
        "role": "user",
        "content": (
            "Initial rollout: region is us-east, replica count is 2, and "
            "maximum batch size is 8."
        ),
    },
    {"role": "assistant", "content": "Recorded the initial rollout."},
    {
        "role": "user",
        "content": (
            "Production update: region is now us-west, replica count is 4, "
            "and maximum batch size is 16. The initial values are superseded."
        ),
    },
    {"role": "assistant", "content": "Recorded the production update."},
    {
        "role": "user",
        "content": (
            "Return the current region, replica count, and maximum batch size "
            "as one JSON object."
        ),
    },
]


def _serve_args():
    command = serve_module.ServeSubcommand()
    parser = FlexibleArgumentParser(prog="vllm")
    subparsers = parser.add_subparsers(dest="command")
    command.subparser_init(subparsers)
    args = parser.parse_args(
        [
            "serve",
            TARGET_MODEL,
            "--revision",
            "f710177d938eff80b684d42c5aa84b382612f21f",
            "--tokenizer-revision",
            "f710177d938eff80b684d42c5aa84b382612f21f",
            "--trust-remote-code",
            "--tensor-parallel-size",
            "4",
            "--max-model-len",
            "4096",
            "--block-size",
            "16",
            "--kv-transfer-config",
            json.dumps(
                {
                    "kv_connector": "MooncakeStoreConnector",
                    "kv_role": "kv_both",
                    "kv_connector_extra_config": {"load_async": True},
                }
            ),
            "--speculative-config",
            json.dumps(
                {
                    "method": "eagle3",
                    "model": "thoughtworks/MiniMax-M2.5-Eagle3",
                    "revision": "fb4699b3d33913e6b5e2462dd7962775e44e5fea",
                    "num_speculative_tokens": 3,
                    "draft_tensor_parallel_size": 1,
                }
            ),
        ]
    )
    return command, args


def test_minimax_serve_cli_dispatches_to_api_server(monkeypatch):
    command, args = _serve_args()
    dispatched = []

    def capture_run(coroutine):
        dispatched.append(coroutine.cr_code.co_name)
        coroutine.close()

    monkeypatch.setattr(serve_module.uvloop, "run", capture_run)
    command.cmd(args)

    assert dispatched == ["run_server"]
    assert args.model == TARGET_MODEL
    assert args.api_server_count is None


def test_cold_chat_http_contract_preserves_latest_record():
    _command, args = _serve_args()
    app = build_app(args, ("generate",))
    app.state.enable_server_load_tracking = False
    app.state.server_load_metrics = 0

    class DeterministicColdModel:
        async def create_chat_completion(self, request, _raw_request):
            assert request.model == TARGET_MODEL
            assert [message["role"] for message in request.messages] == [
                message["role"] for message in MESSAGES
            ]
            return ChatCompletionResponse(
                model=request.model,
                choices=[
                    ChatCompletionResponseChoice(
                        index=0,
                        message=ChatMessage(
                            role="assistant",
                            content=json.dumps(EXPECTED_RECORD, separators=(",", ":")),
                        ),
                    )
                ],
                usage=UsageInfo(
                    prompt_tokens=1,
                    completion_tokens=1,
                    total_tokens=2,
                ),
            )

    app.state.openai_serving_chat = DeterministicColdModel()

    async def request_chat_completion():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.post(
                "/v1/chat/completions",
                json={
                    "model": TARGET_MODEL,
                    "messages": MESSAGES,
                    "temperature": 0,
                    "seed": 0,
                    "max_tokens": 80,
                    "stream": False,
                },
            )

    response = asyncio.run(request_chat_completion())
    assert response.status_code == 200
    content = response.json()["choices"][0]["message"]["content"]
    assert json.loads(content) == EXPECTED_RECORD
