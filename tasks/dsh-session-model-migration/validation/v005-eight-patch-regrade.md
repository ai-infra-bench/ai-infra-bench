# 原始 8 份 patch 在 v0.0.5 的重评分

直接使用归档的完整 `submission.patch`，逐份核对原始 SHA-256 后应用到相同 Base。未编辑模型提交，未调用模型，未新增轨迹。8 次评分均在固定 v0.0.5 镜像、Docker `--network=none` 中执行。

| 提交 | 原评分 | 原有检查（32） | 新 Chat 检查（4） | 原契约进程场景（5） | 新 Chat 进程场景（2） | 新评分 |
|---|---:|---:|---:|---:|---:|---:|
| gpt6-1 | 0 | 29/32 | 1/4 | 4/5 | 0/2 | 0 |
| gpt6-2 | 0 | 29/32 | 1/4 | 4/5 | 0/2 | 0 |
| gpt6-3 | 0 | 29/32 | 1/4 | 4/5 | 0/2 | 0 |
| gpt6-4 | 1 | 32/32 | 1/4 | 5/5 | 0/2 | 0 |
| gpt56-1 | 1 | 32/32 | 1/4 | 3/5 | 0/2 | 0 |
| gpt56-2 | 0 | 29/32 | 1/4 | 5/5 | 0/2 | 0 |
| gpt56-3 | 0 | 29/32 | 1/4 | 5/5 | 0/2 | 0 |
| gpt56-4 | 0 | 29/32 | 1/4 | 5/5 | 0/2 | 0 |

原题面没有 `chatReasoningText` 要求，因此新增 Chat 检查失败说明旧 patch 不满足新版契约，不能据此认定模型没有完成旧题。旧奖励和旧 pass@4 保留。这也不是模型在新题面上的新一次 pass@4 实验。

原契约的 5 个进程场景虽然是新增测试，检查的迁移、工具执行、磁盘恢复和调用方额度保留原本就在题面中；这些失败可以用于复核旧实现。

逐份失败信息：

## gpt6-1

Patch SHA-256: `01800454b4eca690f1a74bb6cdb09f3f008fd8a4ec0e5d1ab66ac9b3feba921f`。

- 原有检查失败：`keeps distinct tool calls paired: 'long_prefix'`。
- 原有检查失败：`keeps distinct tool calls paired: 'named_route'`。
- 原有检查失败：`keeps distinct tool calls paired: 'punctuation'`。
- 进程场景 `main`：AssertionError: foreign call IDs collided
- 进程场景 `chat-provider`：AssertionError: source tool reasoning lost or moved
- 进程场景 `chat-model`：AssertionError: source tool reasoning lost or moved

## gpt6-2

Patch SHA-256: `fd936b1ee3f22ade1c875039c7a2ae96c7bc50e2247289cc4f37c7f7fb3fad98`。

- 原有检查失败：`keeps distinct tool calls paired: 'long_prefix'`。
- 原有检查失败：`keeps distinct tool calls paired: 'named_route'`。
- 原有检查失败：`keeps distinct tool calls paired: 'punctuation'`。
- 进程场景 `main`：AssertionError: foreign call IDs collided
- 进程场景 `chat-provider`：AssertionError: source tool reasoning lost or moved
- 进程场景 `chat-model`：AssertionError: source tool reasoning lost or moved

## gpt6-3

Patch SHA-256: `5e5d46fd542fe337e3184b94013dc999dead0ba800e2c0179a18640295996818`。

- 原有检查失败：`keeps distinct tool calls paired: 'long_prefix'`。
- 原有检查失败：`keeps distinct tool calls paired: 'named_route'`。
- 原有检查失败：`keeps distinct tool calls paired: 'punctuation'`。
- 进程场景 `main`：AssertionError: foreign call IDs collided
- 进程场景 `chat-provider`：AssertionError: source tool reasoning lost or moved
- 进程场景 `chat-model`：AssertionError: source tool reasoning lost or moved

## gpt6-4

Patch SHA-256: `25c49a6273a222cd05977c6f99849abbc01929d892093d2c559dc876797698fe`。

- 进程场景 `chat-provider`：AssertionError: source tool reasoning lost or moved
- 进程场景 `chat-model`：AssertionError: source tool reasoning lost or moved

## gpt56-1

Patch SHA-256: `adfbcd2fa69234b32d054e04d2f34183acb157c353e1ed84727f9e11a8449f35`。

- 进程场景 `chat-provider`：AssertionError: source tool reasoning lost or moved
- 进程场景 `chat-model`：AssertionError: source tool reasoning lost or moved
- 进程场景 `empty-same`：AssertionError: caller/default allowance lost: expected 73, got 256
- 进程场景 `empty-third`：AssertionError: caller/default allowance lost: expected 73, got 384

## gpt56-2

Patch SHA-256: `5dfa89b0ed220ec6fe1eba349b9c88bd426b8fd140be4d96c3dc82689e7a8ce6`。

- 原有检查失败：`keeps distinct tool calls paired: 'named_route'`。
- 原有检查失败：`keeps distinct tool calls paired: 'three calls with mixed prefixes'`。
- 原有检查失败：`keeps distinct tool calls paired: 'two shared prefixes'`。
- 进程场景 `chat-provider`：AssertionError: source tool reasoning lost or moved
- 进程场景 `chat-model`：AssertionError: source tool reasoning lost or moved

## gpt56-3

Patch SHA-256: `1e86ca2c44880474dfc5ad23521bc1207bf0ea0b00691c35fe8bdecf96bee2ec`。

- 原有检查失败：`keeps distinct tool calls paired: 'named_route'`。
- 原有检查失败：`keeps distinct tool calls paired: 'three calls with mixed prefixes'`。
- 原有检查失败：`keeps distinct tool calls paired: 'two shared prefixes'`。
- 进程场景 `chat-provider`：AssertionError: source tool reasoning lost or moved
- 进程场景 `chat-model`：AssertionError: source tool reasoning lost or moved

## gpt56-4

Patch SHA-256: `c407dd809a2eaf7c497f930295a6567c8c9e434b93b62603172afaa20d847a6f`。

- 原有检查失败：`keeps distinct tool calls paired: 'named_route'`。
- 原有检查失败：`keeps distinct tool calls paired: 'three calls with mixed prefixes'`。
- 原有检查失败：`keeps distinct tool calls paired: 'two shared prefixes'`。
- 进程场景 `chat-provider`：AssertionError: source tool reasoning lost or moved
- 进程场景 `chat-model`：AssertionError: source tool reasoning lost or moved

[结构化结果](v005-eight-patch-regrade.json) · [完整原始证据](v005-eight-patch-regrade-evidence.tar.gz)

Verifier image: `sha256:54ea499b323969650ba28c996a91e075289373c4870aa2137230615cd7cf651f`。
