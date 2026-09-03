use std::future::Future;
use std::io::Write as _;
use std::pin::Pin;
use std::sync::Arc;
use std::task::{Context, Poll};
use std::time::Duration;

use vllm_chat::{
    ChatBackend, ChatLlm, ChatRenderer, ChatRequest, ChatTextBackend,
    DefaultChatOutputProcessor, DynChatOutputProcessor, DynChatRenderer,
    NewChatOutputProcessorOptions, ParserSelection, RenderedPrompt,
};
use vllm_engine_core_client::protocol::{
    EngineCoreFinishReason, EngineCoreOutput, EngineCoreOutputs, EngineCoreRequest,
};
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
struct DeterministicChatBackend {
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
        Ok(text.bytes().map(u32::from).collect())
    }

    fn decode(
        &self,
        token_ids: &[u32],
        _skip_special_tokens: bool,
    ) -> vllm_text::tokenizer::Result<String> {
        Ok(String::from_utf8_lossy(
            &token_ids.iter().map(|id| *id as u8).collect::<Vec<_>>(),
        )
        .into_owned())
    }

    fn token_to_id(&self, token: &str) -> Option<u32> {
        token.bytes().next().map(u32::from)
    }
}

impl TextBackend for DeterministicChatBackend {
    fn tokenizer(&self) -> DynTokenizer {
        Arc::new(ByteTokenizer)
    }

    fn model_id(&self) -> &str {
        &self.model_id
    }
}

impl ChatBackend for DeterministicChatBackend {
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

impl ChatRenderer for DeterministicChatBackend {
    fn render(&self, request: &ChatRequest) -> vllm_chat::Result<RenderedPrompt> {
        let mut prompt = String::new();
        for message in &request.messages {
            prompt.push_str(message.role().as_str());
            prompt.push_str(": ");
            prompt.push_str(&message.text_content()?);
            prompt.push('\n');
        }
        if request.chat_options.add_generation_prompt() {
            prompt.push_str("assistant:");
        }
        Ok(RenderedPrompt {
            prompt: Prompt::Text(prompt),
        })
    }
}

fn request_output(
    request_id: &str,
    new_token_ids: Vec<u32>,
    finish_reason: Option<EngineCoreFinishReason>,
) -> EngineCoreOutput {
    EngineCoreOutput {
        request_id: request_id.to_string(),
        new_token_ids,
        new_logprobs: None,
        new_prompt_logprobs_tensors: None,
        pooling_output: None,
        finish_reason,
        stop_reason: None,
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

fn outputs_for_request(request_id: &str, text: &str, chunk_sizes: &[usize]) -> EngineCoreOutputs {
    let mut outputs = split_text(text, chunk_sizes)
        .into_iter()
        .map(|chunk| {
            request_output(
                request_id,
                chunk.bytes().map(u32::from).collect(),
                None,
            )
        })
        .collect::<Vec<_>>();
    outputs.push(request_output(
        request_id,
        vec![b'!' as u32],
        Some(EngineCoreFinishReason::Stop),
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
    dealer.recv().await.expect("receive engine request").into_vec()
}

async fn send_outputs(push: &mut PushSocket, outputs: EngineCoreOutputs) {
    push.send(ZmqMessage::from(
        rmp_serde::to_vec_named(&outputs).expect("encode engine outputs"),
    ))
    .await
    .expect("send engine outputs");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn ai_infra_http_server() {
    let model_id = std::env::var("AI_INFRA_SERVER_MODEL").expect("server model");
    let parser_name = std::env::var("AI_INFRA_SERVER_PARSER").expect("server parser");
    let response_script: Vec<String> = serde_json::from_str(
        &std::env::var("AI_INFRA_SERVER_OUTPUTS_JSON").expect("server outputs"),
    )
    .expect("parse server outputs");
    let chunk_sizes: Vec<usize> = serde_json::from_str(
        &std::env::var("AI_INFRA_SERVER_CHUNK_SIZES_JSON")
            .unwrap_or_else(|_| "[]".to_string()),
    )
    .expect("parse chunk sizes");
    let stop_file = std::env::var("AI_INFRA_SERVER_STOP_FILE").expect("server stop file");

    let ipc = IpcNamespace::new().expect("create IPC namespace");
    let handshake_address = ipc.handshake_endpoint();
    let engine_task = MockEngineTask::new(spawn_mock_engine_task(
        handshake_address.clone(),
        b"ai-infra-http-engine".to_vec(),
        move |dealer, push| {
            boxed_test_future(async move {
                let mut response_index = 0;
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
                    let response = if prompt.contains("title generator") {
                        "Maven Central query limit"
                    } else {
                        let response = response_script
                            .get(response_index)
                            .unwrap_or_else(|| panic!("response script exhausted for {prompt:?}"));
                        response_index += 1;
                        if response == "__AI_INFRA_RESULT_TEXT__" {
                            if prompt.contains("Edit applied successfully.") {
                                "Updated the requested value."
                            } else {
                                "The edit failed because oldString was not found."
                            }
                        } else {
                            response
                        }
                    };
                    send_outputs(
                        push,
                        outputs_for_request(&request.request_id, response, &chunk_sizes),
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
    let backend: Arc<dyn ChatTextBackend> = Arc::new(DeterministicChatBackend {
        model_id: model_id.clone(),
    });
    let chat = ChatLlm::from_shared_backend(
        Llm::new(client).with_request_id_randomization(false),
        backend,
    )
    .with_tool_call_parser(ParserSelection::Explicit(parser_name))
    .with_reasoning_parser(ParserSelection::None);
    let state = Arc::new(AppState::new(vec![model_id], chat));
    let app = build_router(state);
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .expect("bind HTTP listener");
    let address = listener.local_addr().expect("HTTP address");
    let server_task = tokio::spawn(async move {
        axum::serve(listener, app).await.expect("serve vLLM HTTP router");
    });

    println!("AI_INFRA_VLLM_SERVER=http://{address}/v1");
    std::io::stdout().flush().expect("flush server address");

    for _ in 0..12_000 {
        if std::path::Path::new(&stop_file).exists() {
            server_task.abort();
            drop(engine_task);
            return;
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
    panic!("timed out waiting for stop file {stop_file}");
}
