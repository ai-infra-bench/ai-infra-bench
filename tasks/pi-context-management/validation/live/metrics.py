"""Observational live-use metrics, independent of benchmark reward.

Counts completed tool calls, not HTTP retries. Repetition is diagnostic, not an
automatic failure: recovering the same evidence after a reset may be necessary.
"""
from collections import Counter
import json


def content_text(message):
    content = message.get('content', [])
    return content if isinstance(content, str) else '\n'.join(p.get('text', '') for p in content if p.get('type') == 'text')


def completed_tools(events):
    arguments = {}
    for event in events:
        if event['type'] == 'assistant':
            for part in event['message'].get('content', []):
                if part.get('type') == 'toolCall':
                    arguments[(event['phase'], part['id'])] = part.get('arguments', {})
    seen, output = set(), []
    for event in events:
        if event['type'] != 'tool_execution_end':
            continue
        key = (event['phase'], event['toolCallId'])
        if key in seen:
            continue
        seen.add(key)
        output.append(dict(event, arguments=arguments.get(key, {})))
    return output


def phase_completion(events, phases=(0, 1)):
    result = {}
    for phase in phases:
        messages = [e['message'] for e in events if e['type'] == 'assistant' and e['phase'] == phase]
        last = messages[-1] if messages else {}
        result[str(phase)] = {
            'stop_reason': last.get('stopReason'),
            'completed': last.get('stopReason') == 'stop' and bool(content_text(last).strip()),
        }
    return result


def recovery_preconditions(events, snapshots):
    """Check the directed scenario's no-copy rule and evidence provenance.

    A history search preview can legitimately recover a value before history_read.
    Track each value separately so that partial recovery does not exempt the rest.
    These are scenario conditions, not restrictions on Pi's working-note feature.
    """
    values = {f'{name}.{field}': row[field] for name, row in snapshots.items()
              for field in ['audit_receipt', 'checksum', 'boundary_sample_id']}

    def strings(value):
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return '\n'.join(strings(v) for v in value)
        if isinstance(value, dict):
            return '\n'.join(strings(v) for v in value.values())
        return ''

    phase0 = [e for e in events if e['type'] == 'assistant' and e['phase'] == 0]
    final_text = content_text(phase0[-1]['message']) if phase0 else ''
    copied = [label for label, value in values.items() if value in final_text]
    recovered, early_values = set(), []
    requests_checked = 0
    for index, event in enumerate(events):
        if event['phase'] != 1:
            continue
        if event['type'] == 'tool_execution_end' and not event.get('isError', False):
            if event['toolName'] in ['history_search', 'history_read']:
                raw = content_text(event['result'])
                try:
                    raw = strings(json.loads(raw))
                except ValueError:
                    pass
                recovered.update(label for label, value in values.items() if value in raw)
        elif event['type'] == 'request':
            requests_checked += 1
            payload = strings(event['payload'])
            leaked = [label for label, value in values.items() if label not in recovered and value in payload]
            if leaked:
                early_values.append({'event': event.get('sequence', index), 'fields': leaked})
    return {
        'phase0_final_answer_clean': not copied,
        'copied_fields_in_final_answer': copied,
        'values_appear_only_after_history_recovery': not early_values,
        'requests_with_unrecovered_values': early_values,
        'phase1_requests_checked': requests_checked,
        'recovered_fields': sorted(recovered),
    }


def behavior_metrics(events, expected_resets=3):
    tools = completed_tools(events)
    successful = [e for e in tools if not e.get('isError', False)]
    phase0 = [e for e in successful if e['phase'] == 0]
    reset_calls = sum(e['toolName'] == 'new_context' for e in phase0)
    workflow = []
    for i, event in enumerate(phase0):
        if event['toolName'] != 'inspect_run':
            continue
        end = next((j for j in range(i + 1, len(phase0)) if phase0[j]['toolName'] == 'inspect_run'), len(phase0))
        segment = phase0[i + 1:end]
        reset = next((j for j, item in enumerate(segment) if item['toolName'] == 'new_context'), None)
        workflow.append({
            'run': event['arguments'].get('run_id'),
            'notes_then_reset': reset is not None and any(item['toolName'] == 'notes_write' for item in segment[:reset]),
            'reset_calls': sum(item['toolName'] == 'new_context' for item in segment),
        })
    current_phase, read_in_window, searched_in_window = None, set(), set()
    repeated_reads = repeated_searches = no_evidence_resets = 0
    seen_evidence, new_evidence = set(), False
    for event in successful:
        phase, name, args = event['phase'], event['toolName'], event['arguments']
        if phase != current_phase:
            current_phase = phase
            read_in_window, searched_in_window = set(), set()
            new_evidence = False
        if name == 'new_context':
            if phase == 0 and not new_evidence:
                no_evidence_resets += 1
            new_evidence = False
            read_in_window, searched_in_window = set(), set()
        elif name == 'inspect_run':
            identity = ('snapshot', args.get('run_id'))
            new_evidence |= identity not in seen_evidence
            seen_evidence.add(identity)
        elif name == 'history_read':
            identity = (args.get('window_id'), args.get('item_id'))
            if None in identity:
                continue
            repeated_reads += identity in read_in_window
            read_in_window.add(identity)
            new_evidence |= ('history', *identity) not in seen_evidence
            seen_evidence.add(('history', *identity))
        elif name == 'history_search':
            query = args.get('query')
            if query is not None:
                repeated_searches += query in searched_in_window
                searched_in_window.add(query)
    usage = Counter()
    observed_usage_messages = 0
    for event in events:
        if event['type'] != 'assistant':
            continue
        reported = event['message'].get('usage')
        if not reported:
            continue
        observed_usage_messages += 1
        for field in ['input', 'output', 'cacheRead', 'cacheWrite', 'totalTokens']:
            if isinstance(reported.get(field), (int, float)):
                usage[field] += reported[field]
    return {
        'phase0_reset_calls': reset_calls,
        'expected_phase0_reset_calls': expected_resets,
        'extra_phase0_reset_calls': max(0, reset_calls - expected_resets) if expected_resets is not None else None,
        'resets_without_new_evidence': no_evidence_resets,
        'duplicate_history_reads_same_window': repeated_reads,
        'duplicate_history_queries_same_window': repeated_searches,
        'tool_errors': sum(bool(e.get('isError')) for e in tools),
        'completed_tool_calls': len(tools),
        'tool_counts': dict(Counter(e['toolName'] for e in successful)),
        'reported_token_usage': dict(usage) if observed_usage_messages else None,
        'workflow': workflow,
        'diagnostic_only': True,
    }


def infrastructure_metrics(records, router_log=''):
    failed_requests, rate_limited_requests = set(), set()
    for index, record in enumerate(records):
        identity = record.get('trace_id', index)
        if record.get('upstream_status') == 429:
            rate_limited_requests.add(identity)
        for line in record.get('upstream_sse_blob', '').splitlines():
            if not line.startswith('data: '):
                continue
            try:
                event = json.loads(line[6:])
            except ValueError:
                continue
            if event.get('type') not in ['error', 'response.failed']:
                continue
            failed_requests.add(identity)
            error = event.get('error') or event.get('response', {}).get('error') or event
            if error.get('code') in ['rate_limit_exceeded', '429', 429] or error.get('type') == 'too_many_requests':
                rate_limited_requests.add(identity)
    return {
        'gateway_requests': len(records),
        'http_429_attempts': router_log.count('HTTP/1.1 429'),
        'stream_failed_requests': len(failed_requests),
        'rate_limited_requests': len(rate_limited_requests),
    }
