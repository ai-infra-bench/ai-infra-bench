"""Trusted reference: no vLLM imports, candidate code, or Oracle execution."""

import random


class AmbiguousReference(ValueError):
    """Fresh weights cannot produce a stable, discriminating reference workload."""


def build_reference(path, seed):
    import torch
    from transformers import GPT2Config, GPT2LMHeadModel, PreTrainedTokenizerFast
    from tokenizers import AddedToken, Tokenizer
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import Whitespace

    torch.set_num_threads(1)
    torch.manual_seed(seed)
    rng = random.Random(seed)
    vocab = {"[UNK]": 0, "[PAD]": 1, "[BOS]": 2, "[EOS]": 3}
    vocab.update({f"w{i}": i for i in range(4, 48)})
    tokenizer = Tokenizer(WordLevel(vocab=vocab, unk_token="[UNK]"))
    tokenizer.pre_tokenizer = Whitespace()
    public_tokenizer = PreTrainedTokenizerFast(
        tokenizer_object=tokenizer, unk_token="[UNK]", pad_token="[PAD]",
        bos_token="[BOS]", eos_token="[EOS]",
    )
    config = GPT2Config(
        vocab_size=len(vocab), n_positions=128, n_ctx=128, n_embd=32,
        n_layer=2, n_head=2, bos_token_id=2, eos_token_id=3, pad_token_id=1,
        tie_word_embeddings=False,
    )
    model = GPT2LMHeadModel(config).eval()
    with torch.no_grad():
        model.lm_head.weight.normal_(0, 0.25)
    cache = {}
    eos_id = 3
    all_tokens = tuple(range(len(vocab)))

    def sample(prompt, budget, stops, ignore_eos=True):
        key = (tuple(prompt), budget, tuple(stops), None if ignore_eos else eos_id)
        if key in cache:
            return cache[key]
        context, generated, margin = list(prompt), [], float("inf")
        with torch.inference_mode():
            for _ in range(budget):
                logits = model(torch.tensor([context])).logits[0, -1]
                top = logits.topk(2)
                margin = min(margin, float(top.values[0] - top.values[1]))
                token = int(top.indices[0])
                generated.append(token)
                context.append(token)
                if token in stops or (not ignore_eos and token == eos_id):
                    break
        eos = not ignore_eos and generated[-1] == eos_id
        stopped = eos or generated[-1] in stops
        result = (generated, "stop" if stopped else "length",
                  generated[-1] if stopped and not eos else None, margin)
        cache[key] = result
        return result

    def paths(chunks, budget=32, stops=all_tokens, ignore_eos=True):
        states = [([], [], [])]
        for part in chunks:
            next_states = []
            for context, outputs, segments in states:
                prompt = context + part
                generated, reason, stop, margin = sample(prompt, budget, stops, ignore_eos)
                segment = {"length": len(generated), "reason": reason, "stop": stop,
                           "margin": margin}
                # The statement does not choose a generated-token retention policy.
                # Accept ordered prefixes, while checking every input and output.
                for kept in range(len(generated) + 1):
                    next_states.append((prompt + generated[:kept],
                                        outputs + generated, segments + [segment]))
            states = next_states
        unique = {}
        for _, tokens, segments in states:
            unique[tuple(tokens)] = {"tokens": tokens, "segments": segments}
        return list(unique.values())

    def chunk(length):
        return [rng.randrange(4, len(vocab)) for _ in range(length)]

    main = [chunk(3), chunk(4), chunk(2)]
    for _ in range(80):
        valid = paths(main)
        contextless = sum((sample(part, 32, all_tokens)[0] for part in main), [])
        if all(item["tokens"] != contextless for item in valid):
            break
        main = [chunk(3), chunk(4), chunk(2)]
    else:
        raise AmbiguousReference("could not construct a context-sensitive reference workload")
    a, b, fresh = [chunk(2), chunk(3)], [chunk(4), chunk(2), chunk(3)], [chunk(4)]
    for _ in range(120):
        stop_first = chunk(3)
        stop_id = sample(stop_first, 1, all_tokens)[0][0]
        stop_chunks = [stop_first, chunk(4)]
        endings = {sample(stop_first + [stop_id][:kept] + stop_chunks[1],
                          1, all_tokens)[0][0] for kept in (0, 1)}
        if len(endings) == 1 and next(iter(endings)) >= 4 and stop_id not in endings:
            eos_id = next(iter(endings))
            break
    else:
        raise AmbiguousReference("could not construct a stop-reason refresh workload")
    # Stop versus EOS checks refresh without specifying per-segment token budgets.
    model.config.eos_token_id = eos_id
    model.generation_config.eos_token_id = eos_id
    public_tokenizer.add_special_tokens({
        "eos_token": AddedToken(f"w{eos_id}", single_word=True, special=True),
    })
    public_tokenizer.save_pretrained(path)
    reloaded_tokenizer = PreTrainedTokenizerFast.from_pretrained(path, local_files_only=True)
    model.save_pretrained(path)
    cases, expected = {}, {}

    def add(name, chunks, mode="burst", rid=None, stops=all_tokens, ignore_eos=True,
            budget=None, include_stop=False):
        if budget is None:
            budget = 2 if mode == "ordinary" else 32
        if mode == "ordinary":
            stops = ()
        possibilities = paths(chunks, budget, stops, ignore_eos)
        if any(segment["margin"] < 0.0001 for item in possibilities for segment in item["segments"]):
            raise AmbiguousReference("greedy logits are too close; generate a fresh fixture")
        counts = sorted({tuple(s["length"] for s in item["segments"])
                         for item in possibilities})
        texts = [" " + " ".join(f"w{token}" for token in part) + " " for part in chunks]
        for text, token_ids in zip(texts, chunks):
            if reloaded_tokenizer.encode(text, add_special_tokens=False) != token_ids:
                raise AmbiguousReference("saved tokenizer changed the reference input")
        prefix = reloaded_tokenizer.decode(chunks[0], skip_special_tokens=True,
                                           clean_up_tokenization_spaces=False)
        if not prefix:
            raise AmbiguousReference("the prompt has no visible text prefix")
        for item in possibilities:
            visible, offset = [], 0
            for segment in item["segments"]:
                next_offset = offset + segment["length"]
                tokens = item["tokens"][offset:next_offset]
                # Explicit stop tokens remain in token_ids, but are excluded
                # from text unless requested. EOS is handled by the tokenizer.
                if segment["stop"] is not None and not include_stop:
                    tokens = tokens[:-1]
                visible.extend(tokens)
                offset = next_offset
            decoded = reloaded_tokenizer.decode(
                chunks[0] + visible, skip_special_tokens=True,
                clean_up_tokenization_spaces=False)
            assert decoded.startswith(prefix)
            item["text"] = decoded[len(prefix):]
        cases[name] = {
            "request_id": rid or f"{name}-{rng.getrandbits(64):016x}",
            "chunks": texts,
            "mode": mode, "budget": budget, "stop_ids": list(stops), "ignore_eos": ignore_eos,
            "include_stop": include_stop,
            # Descriptive workload metadata, not a restriction on the
            # candidate's context-retention policy or output frame sizes.
            "segment_lengths": list(counts[0]),
        }
        expected[name] = possibilities

    add("ordinary_before", fresh, "ordinary")
    add("burst", main)
    add("delayed", main, "delayed")
    add("single_closed", fresh)
    add("close_after_output", fresh, "delayed")
    add("solo_a", a)
    add("solo_b", b)
    add("concurrent_a", a)
    add("concurrent_b", b)
    reused = f"reused-{rng.getrandbits(64):016x}"
    add("reuse_first", a, rid=reused)
    add("reuse_second", fresh, rid=reused)
    add("fresh_comparison", fresh)
    add("stop_refresh", stop_chunks, "delayed", stops=(stop_id,), ignore_eos=False)
    add("stop_refresh_burst", stop_chunks, stops=(stop_id,), ignore_eos=False)
    add("single_multitoken", fresh, stops=(), budget=4)

    # Choose a stop condition that leaves several generated tokens before a
    # continuation. Every allowed retention policy must stop while budget is
    # still ample, avoiding a choice of per-segment versus per-session limits.
    for _ in range(120):
        first = chunk(3)
        preview = sample(first, 6, ())[0]
        stop_at = next((index for index in range(2, len(preview))
                        if preview[index] not in preview[:index]
                        and preview[index] >= 4 and preview[index] != eos_id), None)
        if stop_at is None:
            continue
        stops = tuple(token for token in all_tokens if token not in preview[:stop_at])
        multi_chunks = [first, chunk(4)]
        possibilities = paths(multi_chunks, 32, stops)
        if any(segment["reason"] != "stop" or segment["length"] > 6
               for item in possibilities for segment in item["segments"]):
            continue
        if not any(token >= 4 and token != eos_id for token in preview[:stop_at]):
            continue
        break
    else:
        raise AmbiguousReference("could not construct a multi-token continuation")
    add("multitoken_burst", multi_chunks, stops=stops)
    add("multitoken_delayed", multi_chunks, "delayed", stops=stops)
    add("multitoken_include_stop", multi_chunks, "delayed", stops=stops,
        include_stop=True)
    add("ordinary_after", fresh, "ordinary")
    if not expected["ordinary_before"][0]["text"]:
        raise AmbiguousReference("ordinary generation must exercise visible output text")
    return {"cases": cases, "vocab_size": len(vocab)}, expected


def check_results(raw, workload, expected):
    assert set(raw) == {"cases"}, "invalid public result envelope"
    assert set(raw["cases"]) == set(workload["cases"]), "missing or unexpected cases"
    sequences = {}
    for name, case in workload["cases"].items():
        record = raw["cases"][name]
        assert record["ended"] is True, f"{name}: input/output lifecycle did not finish"
        rows = record["rows"]
        assert rows, f"{name}: no public output"
        tokens, completions, text_parts = [], [], []
        for row in rows:
            assert row["request_id"] == case["request_id"], f"{name}: wrong request identity"
            for output in row["outputs"]:
                assert output["index"] == 0, f"{name}: unexpected extra completion"
                assert all(type(t) is int and 0 <= t < workload["vocab_size"]
                           for t in output["tokens"]), f"{name}: invalid token IDs"
                assert isinstance(output["text"], str), f"{name}: invalid output text"
                tokens.extend(output["tokens"])
                text_parts.append(output["text"])
                if output["finish_reason"] is not None:
                    completions.append((len(tokens), output))
        possibilities = [item for item in expected[name] if item["tokens"] == tokens]
        assert possibilities, f"{name}: tokens differ from independent continuation reference: {tokens}"
        actual_text = "".join(text_parts)
        possibilities = [item for item in possibilities if item["text"] == actual_text]
        assert possibilities, f"{name}: text differs from independent tokenizer reference: {actual_text!r}"
        # Generator exhaustion and an explicit terminal output are both valid.
        assert completions, f"{name}: missing completion metadata"
        actual = [(offset, output["finish_reason"], output["stop_reason"])
                  for offset, output in completions]
        for possibility in possibilities:
            allowed = set()
            offset = 0
            for segment in possibility["segments"]:
                offset += segment["length"]
                allowed.add((offset, segment["reason"], segment["stop"]))
            if all(completion in allowed for completion in actual):
                break
        else:
            raise AssertionError(f"{name}: stale or incorrect completion metadata: {actual}")
        sequences[name] = tokens
    for left, right in (("burst", "delayed"), ("solo_a", "concurrent_a"),
                        ("solo_b", "concurrent_b"), ("reuse_second", "fresh_comparison"),
                        ("single_closed", "close_after_output"),
                        ("stop_refresh", "stop_refresh_burst"),
                        ("multitoken_burst", "multitoken_delayed"),
                        ("multitoken_delayed", "multitoken_include_stop"),
                        ("ordinary_before", "ordinary_after")):
        assert sequences[left] == sequences[right], f"session timing or isolation changed {left}/{right}"
    return list(workload["cases"])
