"""Verifier-side adapter: real Gym HTTP server and public converter operations.

Contains no expected answers or grading decisions. Runs as the candidate user.
"""

import argparse
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--repo", required=True)
parser.add_argument("--backend", required=True)
parser.add_argument("--port", type=int, required=True)
parser.add_argument(
    "--mode", choices=["native", "request", "override"], default="native"
)
args = parser.parse_args()
sys.path.insert(0, str(Path(args.repo).resolve()))

import uvicorn
from fastapi import Body, HTTPException, Request
from omegaconf import OmegaConf
from nemo_gym.base_responses_api_model import (
    SimpleResponsesAPIModel,
    BaseResponsesAPIModelConfig,
)
from nemo_gym.openai_utils import (
    NeMoGymResponse,
    NeMoGymResponseCreateParamsNonStreaming,
)
from nemo_gym.server_utils import (
    ServerClient,
    BaseServerConfig,
    request,
    get_response_json,
)
from responses_api_models.openai_model.app import (
    SimpleModelServer,
    SimpleModelServerConfig,
)
from nemo_gym.global_config import GlobalConfigDictParserConfig, set_global_config_dict

set_global_config_dict(
    GlobalConfigDictParserConfig(
        initial_global_config_dict=OmegaConf.create({}),
        skip_load_from_cli=True,
        skip_load_from_dotenv=True,
    )
)

client = ServerClient(
    head_server_config=BaseServerConfig(host="127.0.0.1", port=1),
    global_config_dict=OmegaConf.create({}),
)


class RequestModel(SimpleResponsesAPIModel):
    async def responses(
        self, request: Request, body: NeMoGymResponseCreateParamsNonStreaming = Body()
    ):
        payload = body.model_dump(exclude_unset=True)
        payload["request_witness"] = {
            "trace": request.headers.get("x-bridge-trace"),
            "session": dict(request.session),
        }
        response = await globals()["request"](
            "POST", args.backend + "/v1/responses", json=payload
        )
        if response.status != 200:
            raise HTTPException(status_code=response.status, detail="upstream failure")
        return NeMoGymResponse.model_validate(await get_response_json(response))

    async def chat_completions(self, body: dict = Body()):
        response = await request(
            "POST", args.backend + "/v1/chat/completions", json=body
        )
        return await get_response_json(response)


class OverrideModel(RequestModel):
    def setup_webserver(self):
        app = super().setup_webserver()
        # Override via the existing webserver extension point and public HTTP
        # route, without assuming any newly introduced handler method name.
        app.router.routes[:] = [
            route for route in app.router.routes
            if not (getattr(route, "path", None) == "/v1/messages"
                    and "POST" in (getattr(route, "methods", None) or set()))
        ]
        async def custom_messages(body: dict = Body()):
            return {"custom_messages_handler": body.get("model")}
        app.post("/v1/messages")(custom_messages)
        return app


if args.mode == "native":
    cfg = SimpleModelServerConfig(
        name="bridge",
        entrypoint="app.py",
        host="127.0.0.1",
        port=args.port,
        openai_base_url=args.backend + "/v1",
        openai_api_key="local-test",
        openai_model="local-policy",
    )
    server = SimpleModelServer(config=cfg, server_client=client)
else:
    cfg = BaseResponsesAPIModelConfig(
        name="bridge", entrypoint="app.py", host="127.0.0.1", port=args.port
    )
    server = (RequestModel if args.mode == "request" else OverrideModel)(
        config=cfg, server_client=client
    )
app = server.setup_webserver()


@app.get("/probe-ready")
def ready():
    return {"ready": True}


@app.post("/public-converter/{operation}")
def convert(operation: str, payload: dict = Body()):
    # Imported lazily so unchanged Base starts; missing functionality is an
    # observable 501 at this adapter boundary, not an environment import failure.
    try:
        from nemo_gym.anthropic_converter import AnthropicConverter
    except ModuleNotFoundError as exc:
        if exc.name != "nemo_gym.anthropic_converter":
            raise
        raise HTTPException(501, "public converter not implemented") from exc
    converter = AnthropicConverter()
    try:
        if operation == "ingress-request":
            value = converter.anthropic_request_to_responses(payload)
        elif operation == "egress-request":
            value = converter.responses_to_anthropic(
                body=NeMoGymResponseCreateParamsNonStreaming.model_validate(
                    payload["body"]
                ),
                model=payload.get("model", "local-policy"),
                max_tokens=payload.get("max_tokens", 256),
                thinking=None,
                thinking_budget_tokens=None,
                extra_body=payload.get("extra_body", {}),
            )
        elif operation == "egress-response":
            value = converter.anthropic_to_responses(
                payload["response"],
                NeMoGymResponseCreateParamsNonStreaming.model_validate(
                    payload.get("request", {"input": "hello"})
                ),
                payload.get("model", "local-policy"),
            )
        elif operation == "ingress-response":
            value = converter.responses_to_anthropic_response(
                NeMoGymResponse.model_validate(payload["response"]),
                payload.get("model", "local-policy"),
            )
        elif operation == "sse":
            from fastapi.responses import StreamingResponse

            return StreamingResponse(
                converter.anthropic_response_to_sse(payload),
                media_type="text/event-stream",
            )
        else:
            raise HTTPException(404, "unknown operation")
        # A return witness avoids letting FastAPI/Pydantic serialization mask a
        # converter that returned invalid non-finite arguments instead of raising.
        # The flag is private to this adapter and is never passed to the candidate.
        if operation in ("egress-request", "ingress-response") and payload.get("observe_return") is True:
            return {"returned": True}
        return (
            value.model_dump(mode="json", exclude_none=True)
            if hasattr(value, "model_dump")
            else value
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, f"{type(exc).__name__}: {exc}") from exc


uvicorn.run(
    app, host="127.0.0.1", port=args.port, log_level="warning", access_log=False
)
