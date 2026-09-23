/*
MIT License

Copyright (c) 2025 Mario Zechner

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
*/
// Test-owned scripted provider, bundled from Pi Base 71dca871bc80b6bc97be37f0ca3189399d651fff.
// Model computation is substituted; candidate session, tools and communication still execute.
// packages/ai/src/utils/event-stream.ts
var FifoQueue = class {
  incoming = [];
  outgoing = [];
  get length() {
    return this.incoming.length + this.outgoing.length;
  }
  enqueue(value) {
    this.incoming.push(value);
  }
  dequeue() {
    if (this.outgoing.length === 0) {
      while (this.incoming.length > 0) {
        this.outgoing.push(this.incoming.pop());
      }
    }
    return this.outgoing.pop();
  }
};
var EventStream = class {
  queue = new FifoQueue();
  waiting = new FifoQueue();
  done = false;
  finalResultPromise;
  resolveFinalResult;
  isComplete;
  extractResult;
  constructor(isComplete, extractResult) {
    this.isComplete = isComplete;
    this.extractResult = extractResult;
    this.finalResultPromise = new Promise((resolve) => {
      this.resolveFinalResult = resolve;
    });
  }
  push(event) {
    if (this.done) return;
    if (this.isComplete(event)) {
      this.done = true;
      this.resolveFinalResult(this.extractResult(event));
    }
    const waiter = this.waiting.dequeue();
    if (waiter) {
      waiter({ value: event, done: false });
    } else {
      this.queue.enqueue(event);
    }
  }
  end(result) {
    this.done = true;
    if (result !== void 0) {
      this.resolveFinalResult(result);
    }
    while (this.waiting.length > 0) {
      const waiter = this.waiting.dequeue();
      waiter({ value: void 0, done: true });
    }
  }
  async *[Symbol.asyncIterator]() {
    while (true) {
      if (this.queue.length > 0) {
        yield this.queue.dequeue();
      } else if (this.done) {
        return;
      } else {
        const result = await new Promise((resolve) => this.waiting.enqueue(resolve));
        if (result.done) return;
        yield result.value;
      }
    }
  }
  result() {
    return this.finalResultPromise;
  }
};
var AssistantMessageEventStream = class extends EventStream {
  constructor() {
    super(
      (event) => event.type === "done" || event.type === "error",
      (event) => {
        if (event.type === "done") {
          return event.message;
        } else if (event.type === "error") {
          return event.error;
        }
        throw new Error("Unexpected event type for final result");
      }
    );
  }
};
function createAssistantMessageEventStream() {
  return new AssistantMessageEventStream();
}

// packages/ai/src/api/lazy.ts
function createSetupErrorMessage(model, error) {
  return {
    role: "assistant",
    content: [],
    api: model.api,
    provider: model.provider,
    model: model.id,
    usage: {
      input: 0,
      output: 0,
      cacheRead: 0,
      cacheWrite: 0,
      totalTokens: 0,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 }
    },
    stopReason: "error",
    errorMessage: error instanceof Error ? error.message : String(error),
    timestamp: Date.now()
  };
}
function hasResult(source) {
  return typeof source.result === "function";
}
async function forwardStream(target, source) {
  for await (const event of source) {
    target.push(event);
  }
  target.end(hasResult(source) ? await source.result() : void 0);
}
function lazyStream(model, setup) {
  const outer = new AssistantMessageEventStream();
  setup().then((inner) => forwardStream(outer, inner)).catch((error) => {
    const message = createSetupErrorMessage(model, error);
    outer.push({ type: "error", reason: "error", error: message });
    outer.end(message);
  });
  return outer;
}

// packages/ai/src/utils/diagnostics.ts
function formatThrownValue(value) {
  if (value instanceof Error) return value.message || value.name;
  if (typeof value === "string") return value;
  return String(value);
}

// packages/ai/src/auth/resolve.ts
var ModelsError = class extends Error {
  code;
  constructor(code, message, options) {
    super(withCauseDetail(message, options?.cause), options);
    this.name = "ModelsError";
    this.code = code;
  }
};
function withCauseDetail(message, cause) {
  if (cause === void 0 || cause === null) return message;
  const detail = formatThrownValue(cause).trim();
  if (!detail || message.includes(detail)) return message;
  return `${message}: ${detail}`;
}
var DEFAULT_OAUTH_MINIMUM_VALIDITY_MS = 5 * 60 * 1e3;

// packages/ai/src/models.ts
function createProvider(input) {
  const baselineModels = input.models;
  let dynamicModels = [];
  const fetchModels = input.fetchModels;
  const currentModels = () => {
    const merged = [...baselineModels];
    for (const model of dynamicModels) {
      const index = merged.findIndex((entry) => entry.id === model.id);
      if (index >= 0) merged[index] = model;
      else merged.push(model);
    }
    return merged;
  };
  const single = typeof input.api.stream === "function" ? input.api : void 0;
  const byApi = single ? void 0 : input.api;
  const apiFor = (model) => single ?? byApi?.[model.api];
  const dispatch = (model, run) => {
    const streams2 = apiFor(model);
    if (!streams2) {
      return lazyStream(model, async () => {
        throw new ModelsError("stream", `Provider ${input.id} has no API implementation for "${model.api}"`);
      });
    }
    return run(streams2);
  };
  const provider = {
    id: input.id,
    name: input.name ?? input.id,
    baseUrl: input.baseUrl,
    headers: input.headers,
    auth: input.auth,
    getModels: currentModels,
    refreshModels: fetchModels ? async (context) => {
      if (context.stored) {
        const restored = context.stored.models.filter((model) => model.provider === input.id).map((model) => model);
        if (!await context.publish({
          update: () => {
            dynamicModels = restored;
          }
        })) {
          return;
        }
      }
      if (!context.allowNetwork || context.signal.aborted) return;
      const refreshed = await fetchModels(context);
      if (context.signal.aborted) return;
      await context.publish({
        persist: { models: refreshed, checkedAt: Date.now() },
        update: () => {
          dynamicModels = refreshed;
        }
      });
    } : void 0,
    filterModels: input.filterModels,
    stream: (model, context, options) => dispatch(model, (streams2) => streams2.stream(model, context, options)),
    streamSimple: (model, context, options) => dispatch(model, (streams2) => streams2.streamSimple(model, context, options))
  };
  const streams = single ? [single] : Object.values(byApi ?? {}).filter((entry) => entry !== void 0);
  if (streams.some((entry) => entry.fetchDeferred !== void 0)) {
    provider.fetchDeferred = (model, handle, options) => lazyStream(model, async () => {
      const implementation = apiFor(model);
      if (!implementation?.fetchDeferred) {
        throw new ModelsError(
          "provider",
          `Provider ${input.id} does not support deferred responses for "${model.api}"`
        );
      }
      return implementation.fetchDeferred(model, handle, options);
    });
  }
  if (streams.some((entry) => entry.cancelDeferred !== void 0)) {
    provider.cancelDeferred = async (model, handle, options) => {
      const implementation = apiFor(model);
      if (!implementation?.cancelDeferred) {
        throw new ModelsError(
          "provider",
          `Provider ${input.id} cannot cancel deferred responses for "${model.api}"`
        );
      }
      await implementation.cancelDeferred(model, handle, options);
    };
  }
  return provider;
}

// packages/ai/src/providers/faux.ts
var DEFAULT_API = "faux";
var DEFAULT_PROVIDER = "faux";
var DEFAULT_MODEL_ID = "faux-1";
var DEFAULT_MODEL_NAME = "Faux Model";
var DEFAULT_BASE_URL = "http://localhost:0";
var DEFAULT_MIN_TOKEN_SIZE = 3;
var DEFAULT_MAX_TOKEN_SIZE = 5;
var DEFAULT_USAGE = {
  input: 0,
  output: 0,
  cacheRead: 0,
  cacheWrite: 0,
  totalTokens: 0,
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 }
};
function fauxText(text) {
  return { type: "text", text };
}
function fauxThinking(thinking) {
  return { type: "thinking", thinking };
}
function fauxToolCall(name, arguments_, options = {}) {
  return {
    type: "toolCall",
    id: options.id ?? randomId("tool"),
    name,
    arguments: arguments_
  };
}
function normalizeFauxAssistantContent(content) {
  if (typeof content === "string") {
    return [fauxText(content)];
  }
  return Array.isArray(content) ? content : [content];
}
function fauxAssistantMessage(content, options = {}) {
  return {
    role: "assistant",
    content: normalizeFauxAssistantContent(content),
    api: DEFAULT_API,
    provider: DEFAULT_PROVIDER,
    model: DEFAULT_MODEL_ID,
    usage: DEFAULT_USAGE,
    stopReason: options.stopReason ?? "stop",
    ...options.deferred === void 0 ? {} : { deferred: options.deferred },
    ...options.errorMessage === void 0 ? {} : { errorMessage: options.errorMessage },
    ...options.responseId === void 0 ? {} : { responseId: options.responseId },
    timestamp: options.timestamp ?? Date.now()
  };
}
function estimateTokens(text) {
  return Math.ceil(text.length / 4);
}
function randomId(prefix) {
  return `${prefix}:${Date.now()}:${Math.random().toString(36).slice(2)}`;
}
function contentToText(content) {
  if (typeof content === "string") {
    return content;
  }
  return content.map((block) => {
    if (block.type === "text") {
      return block.text;
    }
    return `[image:${block.mimeType}:${block.data.length}]`;
  }).join("\n");
}
function assistantContentToText(content) {
  return content.map((block) => {
    if (block.type === "text") {
      return block.text;
    }
    if (block.type === "thinking") {
      return block.thinking;
    }
    return `${block.name}:${JSON.stringify(block.arguments)}`;
  }).join("\n");
}
function toolResultToText(message) {
  return [message.toolName, ...message.content.map((block) => contentToText([block]))].join("\n");
}
function messageToText(message) {
  if (message.role === "user") {
    return contentToText(message.content);
  }
  if (message.role === "assistant") {
    return assistantContentToText(message.content);
  }
  return toolResultToText(message);
}
function serializeContext(context) {
  const parts = [];
  if (context.systemPrompt) {
    parts.push(`system:${context.systemPrompt}`);
  }
  for (const message of context.messages) {
    parts.push(`${message.role}:${messageToText(message)}`);
  }
  if (context.tools?.length) {
    parts.push(`tools:${JSON.stringify(context.tools)}`);
  }
  return parts.join("\n\n");
}
function commonPrefixLength(a, b) {
  const length = Math.min(a.length, b.length);
  let index = 0;
  while (index < length && a[index] === b[index]) {
    index++;
  }
  return index;
}
function withUsageEstimate(message, context, options, promptCache) {
  const promptText = serializeContext(context);
  const promptTokens = estimateTokens(promptText);
  const outputTokens = estimateTokens(assistantContentToText(message.content));
  let input = promptTokens;
  let cacheRead = 0;
  let cacheWrite = 0;
  const sessionId = options?.sessionId;
  if (sessionId && options?.cacheRetention !== "none") {
    const previousPrompt = promptCache.get(sessionId);
    if (previousPrompt) {
      const cachedChars = commonPrefixLength(previousPrompt, promptText);
      cacheRead = estimateTokens(previousPrompt.slice(0, cachedChars));
      cacheWrite = estimateTokens(promptText.slice(cachedChars));
      input = Math.max(0, promptTokens - cacheRead);
    } else {
      cacheWrite = promptTokens;
    }
    promptCache.set(sessionId, promptText);
  }
  return {
    ...message,
    usage: {
      input,
      output: outputTokens,
      cacheRead,
      cacheWrite,
      totalTokens: input + outputTokens + cacheRead + cacheWrite,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 }
    }
  };
}
function splitStringByTokenSize(text, minTokenSize, maxTokenSize) {
  const chunks = [];
  let index = 0;
  while (index < text.length) {
    const tokenSize = minTokenSize + Math.floor(Math.random() * (maxTokenSize - minTokenSize + 1));
    const charSize = Math.max(1, tokenSize * 4);
    chunks.push(text.slice(index, index + charSize));
    index += charSize;
  }
  return chunks.length > 0 ? chunks : [""];
}
function cloneMessage(message, api, provider, modelId) {
  const cloned = structuredClone(message);
  return {
    ...cloned,
    api,
    provider,
    model: modelId,
    timestamp: cloned.timestamp ?? Date.now(),
    usage: cloned.usage ?? DEFAULT_USAGE
  };
}
function createDeferredMessage(model, handle) {
  return {
    role: "assistant",
    content: [],
    api: model.api,
    provider: model.provider,
    model: model.id,
    usage: DEFAULT_USAGE,
    stopReason: "deferred",
    deferred: handle,
    timestamp: Date.now()
  };
}
function createErrorMessage(error, api, provider, modelId) {
  return {
    role: "assistant",
    content: [],
    api,
    provider,
    model: modelId,
    usage: DEFAULT_USAGE,
    stopReason: "error",
    errorMessage: error instanceof Error ? error.message : String(error),
    timestamp: Date.now()
  };
}
function createAbortedMessage(partial) {
  return {
    ...partial,
    stopReason: "aborted",
    errorMessage: "Request was aborted",
    timestamp: Date.now()
  };
}
function scheduleChunk(chunk, tokensPerSecond) {
  if (!tokensPerSecond || tokensPerSecond <= 0) {
    return new Promise((resolve) => queueMicrotask(resolve));
  }
  const delayMs = estimateTokens(chunk) / tokensPerSecond * 1e3;
  return new Promise((resolve) => setTimeout(resolve, delayMs));
}
async function streamWithDeltas(stream, message, minTokenSize, maxTokenSize, tokensPerSecond, signal) {
  const partial = { ...message, content: [], stopReason: "pending" };
  if (signal?.aborted) {
    const aborted = createAbortedMessage(partial);
    stream.push({ type: "error", reason: "aborted", error: aborted });
    stream.end(aborted);
    return;
  }
  stream.push({ type: "start", partial: { ...partial } });
  for (let index = 0; index < message.content.length; index++) {
    if (signal?.aborted) {
      const aborted = createAbortedMessage(partial);
      stream.push({ type: "error", reason: "aborted", error: aborted });
      stream.end(aborted);
      return;
    }
    const block = message.content[index];
    if (block.type === "thinking") {
      partial.content = [...partial.content, { type: "thinking", thinking: "" }];
      stream.push({ type: "thinking_start", contentIndex: index, partial: { ...partial } });
      for (const chunk of splitStringByTokenSize(block.thinking, minTokenSize, maxTokenSize)) {
        await scheduleChunk(chunk, tokensPerSecond);
        if (signal?.aborted) {
          const aborted = createAbortedMessage(partial);
          stream.push({ type: "error", reason: "aborted", error: aborted });
          stream.end(aborted);
          return;
        }
        partial.content[index].thinking += chunk;
        stream.push({ type: "thinking_delta", contentIndex: index, delta: chunk, partial: { ...partial } });
      }
      stream.push({
        type: "thinking_end",
        contentIndex: index,
        content: block.thinking,
        partial: { ...partial }
      });
      continue;
    }
    if (block.type === "text") {
      partial.content = [...partial.content, { type: "text", text: "" }];
      stream.push({ type: "text_start", contentIndex: index, partial: { ...partial } });
      for (const chunk of splitStringByTokenSize(block.text, minTokenSize, maxTokenSize)) {
        await scheduleChunk(chunk, tokensPerSecond);
        if (signal?.aborted) {
          const aborted = createAbortedMessage(partial);
          stream.push({ type: "error", reason: "aborted", error: aborted });
          stream.end(aborted);
          return;
        }
        partial.content[index].text += chunk;
        stream.push({ type: "text_delta", contentIndex: index, delta: chunk, partial: { ...partial } });
      }
      stream.push({ type: "text_end", contentIndex: index, content: block.text, partial: { ...partial } });
      continue;
    }
    partial.content = [...partial.content, { type: "toolCall", id: block.id, name: block.name, arguments: {} }];
    stream.push({ type: "toolcall_start", contentIndex: index, partial: { ...partial } });
    for (const chunk of splitStringByTokenSize(JSON.stringify(block.arguments), minTokenSize, maxTokenSize)) {
      await scheduleChunk(chunk, tokensPerSecond);
      if (signal?.aborted) {
        const aborted = createAbortedMessage(partial);
        stream.push({ type: "error", reason: "aborted", error: aborted });
        stream.end(aborted);
        return;
      }
      stream.push({ type: "toolcall_delta", contentIndex: index, delta: chunk, partial: { ...partial } });
    }
    partial.content[index].arguments = block.arguments;
    stream.push({ type: "toolcall_end", contentIndex: index, toolCall: block, partial: { ...partial } });
  }
  if (message.stopReason === "pending") {
    throw new Error("Faux response ended without a stop reason");
  }
  if (message.stopReason === "error" || message.stopReason === "aborted") {
    stream.push({ type: "error", reason: message.stopReason, error: message });
    stream.end(message);
    return;
  }
  stream.push({ type: "done", reason: message.stopReason, message });
  stream.end(message);
}
function createFauxCore(options) {
  const api = options.api ?? randomId(DEFAULT_API);
  const provider = options.provider ?? DEFAULT_PROVIDER;
  const minTokenSize = Math.max(
    1,
    Math.min(options.tokenSize?.min ?? DEFAULT_MIN_TOKEN_SIZE, options.tokenSize?.max ?? DEFAULT_MAX_TOKEN_SIZE)
  );
  const maxTokenSize = Math.max(minTokenSize, options.tokenSize?.max ?? DEFAULT_MAX_TOKEN_SIZE);
  let pendingResponses = [];
  const tokensPerSecond = options.tokensPerSecond;
  const state = { callCount: 0, deferredFetchCount: 0, cancelledDeferred: [] };
  const promptCache = /* @__PURE__ */ new Map();
  const deferredResponses = /* @__PURE__ */ new Map();
  const modelDefinitions = options.models?.length ? options.models : [
    {
      id: DEFAULT_MODEL_ID,
      name: DEFAULT_MODEL_NAME,
      reasoning: false,
      input: ["text", "image"],
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
      contextWindow: 128e3,
      maxTokens: 16384
    }
  ];
  const models = modelDefinitions.map((definition) => ({
    id: definition.id,
    name: definition.name ?? definition.id,
    api,
    provider,
    baseUrl: DEFAULT_BASE_URL,
    reasoning: definition.reasoning ?? false,
    input: definition.input ?? ["text", "image"],
    cost: definition.cost ?? { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    contextWindow: definition.contextWindow ?? 128e3,
    maxTokens: definition.maxTokens ?? 16384
  }));
  const resolveResponse = async (step, context, streamOptions, requestModel) => {
    const resolved = typeof step === "function" ? await step(context, streamOptions, state, requestModel) : step;
    return withUsageEstimate(
      cloneMessage(resolved, api, provider, requestModel.id),
      context,
      streamOptions,
      promptCache
    );
  };
  const stream = (requestModel, context, streamOptions) => {
    const outer = createAssistantMessageEventStream();
    const step = pendingResponses.shift();
    state.callCount++;
    queueMicrotask(async () => {
      try {
        await streamOptions?.onResponse?.({ status: 200, headers: {} }, requestModel);
        if (!step) {
          let message2 = createErrorMessage(
            new Error("No more faux responses queued"),
            api,
            provider,
            requestModel.id
          );
          message2 = withUsageEstimate(message2, context, streamOptions, promptCache);
          outer.push({ type: "error", reason: "error", error: message2 });
          outer.end(message2);
          return;
        }
        if (streamOptions?.deferred) {
          const handle = {
            provider: requestModel.provider,
            modelId: requestModel.id,
            api: requestModel.api,
            id: randomId("deferred"),
            ...options.deferred?.pollAfterMs !== void 0 ? { pollAfterMs: options.deferred.pollAfterMs } : {}
          };
          deferredResponses.set(handle.id, {
            handle,
            step,
            context,
            options: streamOptions,
            model: requestModel,
            pendingFetches: Math.max(0, Math.floor(options.deferred?.pendingFetches ?? 0)),
            cancelled: false
          });
          await streamWithDeltas(
            outer,
            createDeferredMessage(requestModel, handle),
            minTokenSize,
            maxTokenSize,
            tokensPerSecond,
            streamOptions.signal
          );
          return;
        }
        const message = await resolveResponse(step, context, streamOptions, requestModel);
        await streamWithDeltas(outer, message, minTokenSize, maxTokenSize, tokensPerSecond, streamOptions?.signal);
      } catch (error) {
        const message = createErrorMessage(error, api, provider, requestModel.id);
        outer.push({ type: "error", reason: "error", error: message });
        outer.end(message);
      }
    });
    return outer;
  };
  const streamSimple = (streamModel, context, streamOptions) => stream(streamModel, context, streamOptions);
  const fetchDeferred = (requestModel, handle, fetchOptions) => {
    const outer = createAssistantMessageEventStream();
    state.deferredFetchCount++;
    queueMicrotask(async () => {
      try {
        await fetchOptions?.onResponse?.({ status: 200, headers: {} }, requestModel);
        const entry = deferredResponses.get(handle.id);
        if (!entry || entry.handle.provider !== handle.provider || entry.handle.modelId !== handle.modelId || entry.handle.api !== handle.api) {
          throw new Error(`Unknown faux deferred response: ${handle.id}`);
        }
        if (entry.cancelled) throw new Error(`Faux deferred response was cancelled: ${handle.id}`);
        if (entry.pendingFetches > 0) {
          entry.pendingFetches--;
          await streamWithDeltas(
            outer,
            createDeferredMessage(requestModel, entry.handle),
            minTokenSize,
            maxTokenSize,
            tokensPerSecond,
            fetchOptions?.signal
          );
          return;
        }
        if (!entry.final) {
          const {
            deferred: _deferred,
            signal: _submissionSignal,
            onResponse: _submissionOnResponse,
            ...submissionOptions
          } = entry.options ?? {};
          try {
            entry.final = await resolveResponse(entry.step, entry.context, submissionOptions, entry.model);
          } catch (error) {
            entry.final = createErrorMessage(error, api, provider, entry.model.id);
          }
        }
        await streamWithDeltas(
          outer,
          entry.final,
          minTokenSize,
          maxTokenSize,
          tokensPerSecond,
          fetchOptions?.signal
        );
      } catch (error) {
        const message = createErrorMessage(error, api, provider, requestModel.id);
        outer.push({ type: "error", reason: "error", error: message });
        outer.end(message);
      }
    });
    return outer;
  };
  const cancelDeferred = async (requestModel, handle, cancelOptions) => {
    state.cancelledDeferred.push(structuredClone(handle));
    const entry = deferredResponses.get(handle.id);
    if (entry) entry.cancelled = true;
    await cancelOptions?.onResponse?.({ status: 200, headers: {} }, requestModel);
  };
  function getModel(requestedModelId) {
    if (!requestedModelId) {
      return models[0];
    }
    return models.find((candidate) => candidate.id === requestedModelId);
  }
  return {
    api,
    provider,
    models,
    stream,
    streamSimple,
    fetchDeferred,
    cancelDeferred,
    getModel,
    state,
    setResponses(responses) {
      pendingResponses = [...responses];
    },
    appendResponses(responses) {
      pendingResponses.push(...responses);
    },
    getPendingResponseCount() {
      return pendingResponses.length;
    }
  };
}
function fauxProvider(options = {}) {
  const core = createFauxCore(options);
  const provider = createProvider({
    id: core.provider,
    auth: { apiKey: { name: "Faux", resolve: async () => ({ auth: {} }) } },
    models: core.models,
    api: {
      stream: core.stream,
      streamSimple: core.streamSimple,
      fetchDeferred: core.fetchDeferred,
      cancelDeferred: core.cancelDeferred
    }
  });
  return {
    provider,
    api: core.api,
    models: core.models,
    getModel: core.getModel,
    state: core.state,
    setResponses: core.setResponses,
    appendResponses: core.appendResponses,
    getPendingResponseCount: core.getPendingResponseCount
  };
}
export {
  createFauxCore,
  fauxAssistantMessage,
  fauxProvider,
  fauxText,
  fauxThinking,
  fauxToolCall
};

// External inspector consumes this exact serialized provider input before HTTP.
// The statement observes existing data; it does not rewrite candidate context.
export function observeProviderRequest(context) {
  const payload = JSON.stringify(context);
  debugger;
  return payload;
}
export function observeFixtureReady() {
  debugger;
}
