use std::future::Future;
use std::io::Write as _;
use std::pin::Pin;
use std::sync::Arc;
use std::task::{Context, Poll};
use std::time::Duration;

use vllm_chat::{
    ChatBackend, ChatLlm, ChatRenderer, ChatRequest, ChatTextBackend, DefaultChatOutputProcessor,
    DynChatOutputProcessor, DynChatRenderer, NewChatOutputProcessorOptions, ParserSelection,
    RenderedPrompt,
};
use vllm_engine_core_client::protocol::output::{
    EngineCoreFinishReason, EngineCoreOutput, EngineCoreOutputs, StopReason,
};
use vllm_engine_core_client::protocol::request::EngineCoreRequest;
use vllm_engine_core_client::protocol::stats::PrefillStats;
use vllm_engine_core_client::test_utils::{IpcNamespace, spawn_mock_engine_task};
use vllm_engine_core_client::{EngineCoreClient, EngineCoreClientConfig};
use vllm_llm::Llm;
use vllm_text::tokenizer::{DynTokenizer, Tokenizer};
use vllm_text::{Prompt, TextBackend};
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

#[derive(Clone, Debug)]
struct DeterministicBackend {
    model_id: String,
}

#[derive(Debug)]
struct ByteTokenizer;

impl Tokenizer for ByteTokenizer {
    fn encode(
        &self,
        text: &str,
        _add_special_tokens: bool,
    ) -> vllm_text::tokenizer::Result<Vec<u32>> {
        let token_ids = text.bytes().map(u32::from).collect::<Vec<_>>();
        if let Ok(capture_path) = std::env::var("AI_INFRA_SERVER_TOKENIZER_CAPTURE_FILE") {
            let mut capture = std::fs::OpenOptions::new()
                .create(true)
                .append(true)
                .open(capture_path)
                .expect("open tokenizer capture file");
            writeln!(
                capture,
                "{}",
                serde_json::json!({"token_count": token_ids.len()})
            )
            .expect("write tokenizer capture");
        }
        Ok(token_ids)
    }

    fn decode(
        &self,
        token_ids: &[u32],
        _skip_special_tokens: bool,
    ) -> vllm_text::tokenizer::Result<String> {
        Ok(
            String::from_utf8_lossy(&token_ids.iter().map(|id| *id as u8).collect::<Vec<_>>())
                .into_owned(),
        )
    }

    fn token_to_id(&self, token: &str) -> Option<u32> {
        token.bytes().next().map(u32::from)
    }

    fn id_to_token(&self, id: u32) -> Option<String> {
        char::from_u32(id).map(|value| value.to_string())
    }
}

impl TextBackend for DeterministicBackend {
    fn tokenizer(&self) -> DynTokenizer {
        Arc::new(ByteTokenizer)
    }

    fn model_id(&self) -> &str {
        &self.model_id
    }
}

impl ChatBackend for DeterministicBackend {
    fn chat_renderer(&self) -> DynChatRenderer {
        Arc::new(self.clone())
    }

    fn new_chat_output_processor(
        &self,
        request: &mut ChatRequest,
        options: NewChatOutputProcessorOptions<'_>,
    ) -> vllm_chat::Result<DynChatOutputProcessor> {
        Ok(Box::new(DefaultChatOutputProcessor::new(
            request,
            self.model_id(),
            self.tokenizer(),
            options.tool_call_parser,
            options.reasoning_parser,
        )?))
    }
}

impl ChatRenderer for DeterministicBackend {
    fn render(&self, request: &ChatRequest) -> vllm_chat::Result<RenderedPrompt> {
        Ok(RenderedPrompt {
            prompt: Prompt::Text(
                serde_json::to_string(request).expect("serialize semantic chat request"),
            ),
            effective_template_kwargs: request.chat_options.template_kwargs.clone(),
        })
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

fn split_text(text: &str, sizes: &[usize]) -> Vec<String> {
    if sizes.is_empty() {
        return vec![text.to_string()];
    }
    let characters = text.chars().collect::<Vec<_>>();
    let mut chunks = Vec::new();
    let mut offset = 0;
    let mut size_index = 0;
    while offset < characters.len() {
        let size = sizes.get(size_index).copied().unwrap_or(1).max(1);
        let end = (offset + size).min(characters.len());
        chunks.push(characters[offset..end].iter().collect());
        offset = end;
        size_index += 1;
    }
    chunks
}

fn outputs_for_request(
    request_id: &str,
    text: &str,
    chunk_sizes: &[usize],
    terminal_reason: EngineCoreFinishReason,
    stop_text: Option<String>,
    cached_tokens: u32,
) -> EngineCoreOutputs {
    let mut outputs = split_text(text, chunk_sizes)
        .into_iter()
        .map(|chunk| {
            request_output(
                request_id,
                chunk.bytes().map(u32::from).collect(),
                None,
                None,
            )
        })
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
                    let prompt = request
                        .prompt_token_ids
                        .as_deref()
                        .map(|ids| {
                            String::from_utf8_lossy(
                                &ids.iter().map(|id| *id as u8).collect::<Vec<_>>(),
                            )
                            .into_owned()
                        })
                        .unwrap_or_default();
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
                        })
                    )
                    .expect("write capture");
                    let response = &response_script[response_index % response_script.len()];
                    response_index += 1;
                    send_outputs(
                        push,
                        outputs_for_request(
                            &request.request_id,
                            response,
                            &chunk_sizes,
                            terminal_reason,
                            stop_text.clone(),
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
    let backend: Arc<dyn ChatTextBackend> = Arc::new(DeterministicBackend {
        model_id: model_id.clone(),
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
