use std::future::Future;
use std::io::Write as _;
use std::pin::Pin;
use std::sync::Arc;
use std::task::{Context, Poll};
use std::time::Duration;

use vllm_chat::load_model_backends;
use vllm_chat::{
    ChatBackend, ChatLlm, ChatRenderer, ChatRequest, ChatTextBackend, DynChatBackend,
    DynChatOutputProcessor, DynChatRenderer, LoadModelBackendsOptions,
    NewChatOutputProcessorOptions, ParserSelection, RenderedPrompt,
};
use vllm_engine_core_client::protocol::output::{
    EngineCoreFinishReason, EngineCoreOutput, EngineCoreOutputs, StopReason,
};
use vllm_engine_core_client::protocol::request::EngineCoreRequest;
use vllm_engine_core_client::protocol::stats::PrefillStats;
use vllm_engine_core_client::test_utils::{IpcNamespace, spawn_mock_engine_task};
use vllm_engine_core_client::{EngineCoreClient, EngineCoreClientConfig};
use vllm_llm::Llm;
use vllm_text::backend::SamplingHints;
use vllm_text::tokenizer::DynTokenizer;
use vllm_text::{DynTextBackend, TextBackend};
use zeromq::prelude::{SocketRecv, SocketSend};
use zeromq::{DealerSocket, PushSocket, ZmqMessage};

use super::build_router;
use crate::state::AppState;

type TestFuture<'a> = Pin<Box<dyn Future<Output = ()> + Send + 'a>>;

fn boxed_test_future<'a>(future: impl Future<Output = ()> + Send + 'a) -> TestFuture<'a> {
    Box::pin(future)
}

struct MockEngineTask {
    shutdown_tx: Option<tokio::sync::oneshot::Sender<()>>,
    join_handle: Option<tokio::task::JoinHandle<()>>,
}

impl MockEngineTask {
    fn new(
        (shutdown_tx, join_handle): (
            tokio::sync::oneshot::Sender<()>,
            tokio::task::JoinHandle<()>,
        ),
    ) -> Self {
        Self {
            shutdown_tx: Some(shutdown_tx),
            join_handle: Some(join_handle),
        }
    }
}

impl Future for MockEngineTask {
    type Output = Result<(), tokio::task::JoinError>;

    fn poll(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Self::Output> {
        if let Some(shutdown_tx) = self.shutdown_tx.take() {
            let _ = shutdown_tx.send(());
        }
        match self.join_handle.as_mut() {
            Some(join_handle) => Pin::new(join_handle).poll(cx),
            None => Poll::Ready(Ok(())),
        }
    }
}

impl Drop for MockEngineTask {
    fn drop(&mut self) {
        if let Some(join_handle) = &self.join_handle {
            join_handle.abort();
        }
    }
}

// Observation only: rendering, tokenization, sampling defaults, and output
// processing delegate to the production backend loaded from the frozen assets.
struct ObservedBackend {
    model_id: String,
    text: DynTextBackend,
    chat: DynChatBackend,
    render_capture: String,
}

impl TextBackend for ObservedBackend {
    fn tokenizer(&self) -> DynTokenizer {
        self.text.tokenizer()
    }

    fn model_id(&self) -> &str {
        &self.model_id
    }

    fn sampling_hints(&self) -> vllm_text::Result<SamplingHints> {
        self.text.sampling_hints()
    }

    fn model_vocab_size(&self) -> usize {
        self.text.model_vocab_size()
    }

    fn is_moe(&self) -> bool {
        self.text.is_moe()
    }
}

impl ChatBackend for ObservedBackend {
    fn chat_renderer(&self) -> DynChatRenderer {
        Arc::new(ObservedRenderer {
            inner: self.chat.chat_renderer(),
            capture_path: self.render_capture.clone(),
        })
    }

    fn new_chat_output_processor(
        &self,
        request: &mut ChatRequest,
        options: NewChatOutputProcessorOptions<'_>,
    ) -> vllm_chat::Result<DynChatOutputProcessor> {
        self.chat.new_chat_output_processor(request, options)
    }
}

struct ObservedRenderer {
    inner: DynChatRenderer,
    capture_path: String,
}

impl ChatRenderer for ObservedRenderer {
    fn render(&self, request: &ChatRequest) -> vllm_chat::Result<RenderedPrompt> {
        let rendered = self.inner.render(request)?;
        let prompt = rendered
            .prompt
            .clone()
            .into_text()
            .expect("Qwen text prompt");
        let mut capture = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.capture_path)
            .expect("open renderer capture");
        writeln!(
            capture,
            "{}",
            serde_json::json!({
                "request_id": request.request_id,
                "chat_request": request,
                "prompt": prompt,
                "template_kwargs": rendered.effective_template_kwargs,
            })
        )
        .expect("write renderer capture");
        Ok(rendered)
    }
}

fn parser_selection(name: &str) -> ParserSelection {
    if name.is_empty() || name == "none" {
        ParserSelection::None
    } else {
        ParserSelection::Explicit(name.to_string())
    }
}

fn finish_reason(name: &str) -> EngineCoreFinishReason {
    match name {
        "stop" => EngineCoreFinishReason::Stop,
        "length" => EngineCoreFinishReason::Length,
        "abort" => EngineCoreFinishReason::Abort,
        "error" => EngineCoreFinishReason::Error,
        "repetition" => EngineCoreFinishReason::Repetition,
        other => panic!("unknown finish reason {other}"),
    }
}

fn request_output(
    request_id: &str,
    new_token_ids: Vec<u32>,
    finish_reason: Option<EngineCoreFinishReason>,
    stop_reason: Option<StopReason>,
) -> EngineCoreOutput {
    EngineCoreOutput {
        request_id: request_id.to_string(),
        new_token_ids,
        new_logprobs: None,
        new_prompt_logprobs_tensors: None,
        pooling_output: None,
        finish_reason,
        stop_reason,
        events: None,
        kv_transfer_params: None,
        trace_headers: None,
        prefill_stats: None,
        routed_experts: None,
        num_nans_in_logits: 0,
    }
}

fn split_tokens(tokens: &[u32], sizes: &[usize]) -> Vec<Vec<u32>> {
    if sizes.is_empty() {
        return vec![tokens.to_vec()];
    }
    let mut chunks = Vec::new();
    let mut offset = 0;
    let mut size_index = 0;
    while offset < tokens.len() {
        let size = sizes.get(size_index).copied().unwrap_or(1).max(1);
        let end = (offset + size).min(tokens.len());
        chunks.push(tokens[offset..end].to_vec());
        offset = end;
        size_index += 1;
    }
    chunks
}

fn outputs_for_request(
    request_id: &str,
    tokens: &[u32],
    chunk_sizes: &[usize],
    terminal_reason: EngineCoreFinishReason,
    stop_text: Option<String>,
    cached_tokens: u32,
) -> EngineCoreOutputs {
    let mut outputs = split_tokens(tokens, chunk_sizes)
        .into_iter()
        .map(|chunk| request_output(request_id, chunk, None, None))
        .collect::<Vec<_>>();
    if let Some(first) = outputs.first_mut()
        && cached_tokens > 0
    {
        first.prefill_stats = Some(PrefillStats {
            num_cached_tokens: cached_tokens,
            num_local_cached_tokens: cached_tokens,
            ..Default::default()
        });
    }
    outputs.push(request_output(
        request_id,
        Vec::new(),
        Some(terminal_reason),
        stop_text.map(StopReason::Text),
    ));
    EngineCoreOutputs {
        engine_index: 0,
        outputs,
        scheduler_stats: None,
        timestamp: 0.0,
        utility_output: None,
        finished_requests: None,
        wave_complete: None,
        start_wave: None,
    }
}

async fn recv_engine_message(dealer: &mut DealerSocket) -> Vec<bytes::Bytes> {
    dealer
        .recv()
        .await
        .expect("receive engine request")
        .into_vec()
}

async fn send_outputs(push: &mut PushSocket, outputs: EngineCoreOutputs) {
    push.send(ZmqMessage::from(
        rmp_serde::to_vec_named(&outputs).expect("encode engine outputs"),
    ))
    .await
    .expect("send engine outputs");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn ai_infra_anthropic_http_server() {
    let model_id = std::env::var("AI_INFRA_SERVER_MODEL").expect("server model");
    let response_script: Vec<String> = serde_json::from_str(
        &std::env::var("AI_INFRA_SERVER_OUTPUTS_JSON").expect("server outputs"),
    )
    .expect("parse server outputs");
    assert!(
        !response_script.is_empty(),
        "response script must not be empty"
    );
    let chunk_sizes: Vec<usize> = serde_json::from_str(
        &std::env::var("AI_INFRA_SERVER_CHUNK_SIZES_JSON").unwrap_or_else(|_| "[]".to_string()),
    )
    .expect("parse chunk sizes");
    let terminal_reason = finish_reason(
        &std::env::var("AI_INFRA_SERVER_FINISH_REASON").unwrap_or_else(|_| "stop".to_string()),
    );
    let stop_text = std::env::var("AI_INFRA_SERVER_STOP_TEXT").ok();
    let cached_tokens = std::env::var("AI_INFRA_SERVER_CACHED_TOKENS")
        .ok()
        .map(|value| value.parse::<u32>().expect("cached token count"))
        .unwrap_or(0);
    let capture_file = std::env::var("AI_INFRA_SERVER_CAPTURE_FILE").expect("capture file");
    let stop_file = std::env::var("AI_INFRA_SERVER_STOP_FILE").expect("server stop file");
    let tool_parser = parser_selection(
        &std::env::var("AI_INFRA_SERVER_TOOL_PARSER").unwrap_or_else(|_| "none".to_string()),
    );
    let reasoning_parser = parser_selection(
        &std::env::var("AI_INFRA_SERVER_REASONING_PARSER").unwrap_or_else(|_| "none".to_string()),
    );

    let loaded = load_model_backends(
        "/opt/models/qwen-template",
        LoadModelBackendsOptions {
            language_model_only: true,
            default_chat_template_kwargs: std::collections::HashMap::from([
                (
                    "enable_thinking".to_string(),
                    serde_json::json!(
                        std::env::var("AI_INFRA_SERVER_ENABLE_THINKING")
                            .is_ok_and(|value| value == "true")
                    ),
                ),
                ("preserve_thinking".to_string(), serde_json::json!(true)),
            ]),
            ..Default::default()
        },
    )
    .await
    .expect("load production Qwen template and tokenizer");
    let tokenizer = loaded.text_backend.tokenizer();
    let response_tokens = response_script
        .iter()
        .map(|text| {
            tokenizer
                .encode(text, false)
                .expect("encode deterministic output with Qwen")
        })
        .collect::<Vec<_>>();

    let ipc = IpcNamespace::new().expect("create IPC namespace");
    let handshake_address = ipc.handshake_endpoint();
    let capture_path = capture_file.clone();
    let engine_task = MockEngineTask::new(spawn_mock_engine_task(
        handshake_address.clone(),
        b"ai-infra-anthropic-engine".to_vec(),
        move |dealer, push| {
            boxed_test_future(async move {
                let mut response_index = 0usize;
                loop {
                    let frames = recv_engine_message(dealer).await;
                    if frames.len() < 2 || frames[0].as_ref() != [0x00] {
                        continue;
                    }
                    let request: EngineCoreRequest =
                        rmp_serde::from_slice(&frames[1]).expect("decode engine request");
                    let prompt_ids = request.prompt_token_ids.as_deref().unwrap_or_default();
                    let prompt = tokenizer
                        .decode(prompt_ids, false)
                        .expect("decode actual engine prompt with Qwen");
                    let mut capture = std::fs::OpenOptions::new()
                        .create(true)
                        .append(true)
                        .open(&capture_path)
                        .expect("open capture file");
                    writeln!(
                        capture,
                        "{}",
                        serde_json::json!({
                            "request_id": request.request_id,
                            "prompt": prompt,
                            "prompt_token_ids": prompt_ids,
                            "sampling_params": request.sampling_params,
                            "reasoning_parser_kwargs": request.reasoning_parser_kwargs,
                        })
                    )
                    .expect("write capture");
                    let response = &response_tokens[response_index % response_tokens.len()];
                    response_index += 1;
                    // Obey the limit received over the real engine protocol.
                    // Losing it changes generated output and termination.
                    let limit = request
                        .sampling_params
                        .as_ref()
                        .expect("generation sampling parameters")
                        .max_tokens as usize;
                    let hit_limit = response.len() >= limit;
                    let response = &response[..response.len().min(limit)];
                    send_outputs(
                        push,
                        outputs_for_request(
                            &request.request_id,
                            response,
                            &chunk_sizes,
                            if hit_limit {
                                EngineCoreFinishReason::Length
                            } else {
                                terminal_reason
                            },
                            if hit_limit { None } else { stop_text.clone() },
                            cached_tokens,
                        ),
                    )
                    .await;
                }
            })
        },
    ));

    let client = EngineCoreClient::connect(
        EngineCoreClientConfig::new_single(handshake_address)
            .with_model_name(model_id.clone())
            .with_local_input_output_addresses(
                Some(ipc.input_endpoint()),
                Some(ipc.output_endpoint()),
            ),
    )
    .await
    .expect("connect engine client");
    let backend: Arc<dyn ChatTextBackend> = Arc::new(ObservedBackend {
        model_id: model_id.clone(),
        text: loaded.text_backend,
        chat: loaded.chat_backend,
        render_capture: std::env::var("AI_INFRA_SERVER_RENDER_CAPTURE_FILE")
            .expect("renderer capture file"),
    });
    let chat = ChatLlm::from_shared_backend(
        Llm::new(client).with_request_id_randomization(false),
        backend,
    )
    .with_tool_call_parser(tool_parser)
    .with_reasoning_parser(reasoning_parser);
    let mut state = AppState::new(vec![model_id], chat);
    if let Ok(api_key) = std::env::var("AI_INFRA_SERVER_API_KEY") {
        state = state.with_api_keys(vec![api_key]);
    }
    let app = build_router(Arc::new(state));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .expect("bind HTTP listener");
    let address = listener.local_addr().expect("HTTP address");
    let server_task = tokio::spawn(async move {
        axum::serve(listener, app)
            .await
            .expect("serve vLLM HTTP router");
    });

    println!("AI_INFRA_VLLM_SERVER=http://{address}");
    std::io::stdout().flush().expect("flush server address");

    for _ in 0..36_000 {
        if std::path::Path::new(&stop_file).exists() {
            server_task.abort();
            drop(engine_task);
            return;
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
    panic!("timed out waiting for stop file {stop_file}");
}
