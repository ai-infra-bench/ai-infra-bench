"""Model-visible finding reader, independent of expected sender/transport.

JSON containers replace their encoded source; they are never a second text view.
Attribution follows a body container, never a roster or a sibling record. Unknown
syntax with an external identity hint is a verifier error, not a candidate score.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re


class FormatUnsupported(RuntimeError):
    """A complete body has external identity evidence we cannot safely bind."""


@dataclass(frozen=True)
class Occurrence:
    payload: str
    entry_index: int
    order: int
    path: tuple
    raw_span: tuple[int, int]
    decode_depth: int
    senders: frozenset[str]
    attribution: str
    raw_text: str

    @property
    def position(self):
        return self.entry_index, self.order


class MessageRead:
    def __init__(self, occurrences):
        self._occurrences = occurrences

    def occurrences(self, payload):
        return [item for item in self._occurrences if item.payload == payload]

    def count(self, payload):
        return len(self.occurrences(payload))

    def first_position(self, payload):
        matches = self.occurrences(payload)
        return matches[0].position if matches else None

    def has_sender(self, payload, sender):
        matches = self.occurrences(payload)
        # An already definite failure must not escape via an unknown sibling.
        if not matches or any(item.attribution != 'unsupported' and item.senders != {sender}
                              for item in matches):
            return False
        unknown = next((item for item in matches if item.attribution == 'unsupported'), None)
        if unknown:
            raise FormatUnsupported(
                f'format_unsupported: finding in entry {unknown.entry_index}, '
                f'path {unknown.path!r}, source span {unknown.raw_span!r}; '
                f'external identity cannot be associated; raw={unknown.raw_text!r}')
        return True


def text(message):
    content = message.get('content', '')
    if isinstance(content, str):
        return content
    return '\n'.join(part.get('text', '') for part in (content or [])
                     if isinstance(part, dict) and part.get('type') == 'text')


_LABELS = {'from', 'sender', 'author', '来自', '发送者', '发件人'}
_BODY_KEYS = {'text', 'body', 'content', 'message', 'messages', 'finding', 'findings',
              'payload', 'data', 'entries', 'envelope'}
_ROSTER_KEYS = {'roster', 'members', 'team_members', 'recipients', 'to', 'self'}
_HINT_KEYS = {'origin', 'source', 'sent_by', 'sender_id', 'from_id', 'identity'}
_LABEL = r'(?:\b(?:from|sender|author)\b|来自|发送者|发件人)'
_NEGATION = re.compile(r'\b(?:not|never|unknown|unattributed|no)\b|不是|并非|非来自|未知', re.I)


def _header(value, addresses, *, adjacent=False):
    """Return explicit labels and unresolved hints from a body-free prefix."""
    # Fences and roster lines do not attribute a body.
    value = re.sub(r'```(?:json)?\s*', '', value, flags=re.I)
    lines, roster = [], False
    for line in value.splitlines(keepends=True):
        if re.search(r'(?:team members|roster|成员名单|队友列表)\s*[:：]', line, re.I):
            roster = True
            continue
        if roster and (not line.strip() or re.match(r'\s+|[-*]\s', line)):
            continue
        roster = False
        lines.append(line)
    value = ''.join(lines)
    pattern = re.compile(_LABEL + r'''[\s:"'：*`<]*(?:teammate\s+)?[\s"'`<]*''', re.I)
    labels = list(pattern.finditer(value))
    if labels and re.search(r'not (?:an? )?attribution|不是归属|并非归属', value[:labels[-1].start()], re.I):
        return frozenset(), 'rejected'
    if labels:
        # A header may have punctuation and parenthetical annotations. Its
        # suffix must not contain another arbitrary message body.
        senders, ends, negative = set(), [], False
        for match in labels:
            tail = value[match.end():]
            line_start = value.rfind('\n', 0, match.start()) + 1
            lead = value[line_start:match.start()]
            if _NEGATION.search(lead) or re.match(r'(?:not\b|不是|未知)', tail, re.I):
                negative = True
            identity = None
            # Exact full known IDs have precedence; a period can be ID content
            # or sentence punctuation, so token-until-whitespace is insufficient.
            for address in sorted(addresses, key=len, reverse=True):
                if tail.startswith(address) and (len(tail) == len(address) or
                        not re.match(r'[\w-]', tail[len(address)])):
                    identity = address
                    break
            if identity is None:
                token = re.match(r'''[^\s:"'：{},\[\]<>();]+''', tail)
                if token:
                    identity = token.group().rstrip('.。')
            if identity:
                senders.add(identity)
                ends.append(match.end() + len(identity))
        if negative:
            return frozenset(), 'rejected'
        if ends:
            suffix = value[max(ends):]
            # An annotation belongs to the labelled header, not the body.
            suffix = re.sub(r'\([^()\n]*\)|（[^（）\n]*）', '', suffix)
            bare = re.fullmatch(r'''[\s:：.;。,"'\[\]{}<>*`\-]*''', suffix)
            forward = adjacent and re.search(
                r'\b(?:following|next)\s+(?:message|entry|body)\b|下[一]?条|以下.*正文', suffix, re.I)
            if bare or forward:
                return frozenset(senders), 'supported'
    # Explicit but nonstandard authorship claims are not silently failed.
    # A plain roster or an arbitrary ID mention does not qualify.
    hint = re.search(r'\b(?:origin|source|sent by|delivered by|written by)\b\s*[:：]?\s*', value, re.I)
    if hint and any(address in value[hint.end():] for address in addresses):
        line_start = value.rfind('\n', 0, hint.start()) + 1
        if _NEGATION.search(value[line_start:hint.start()]):
            return frozenset(), 'rejected'
        return frozenset(), 'unsupported'
    return frozenset(), 'missing'


class _Object(list):
    """Preserve repeated JSON keys: repeated bodies are distinct sources."""


class _Reader:
    def __init__(self, payloads, addresses):
        self.payloads = tuple(dict.fromkeys(p for p in payloads if p))
        self.addresses = tuple(addresses)
        self.output = []
        self.decoder = json.JSONDecoder(object_pairs_hook=_Object)
        self.entry = 0
        self.raw = ''

    def hits(self, value):
        # Known bodies are opaque: quotes/JSON/labels inside are never metadata.
        found = []
        for payload in self.payloads:
            start = 0
            while (offset := value.find(payload, start)) >= 0:
                found.append((offset, offset + len(payload), payload))
                start = offset + len(payload)
        return sorted(found, key=lambda hit: (hit[0], -hit[1]))

    def emit(self, value, path, span, depth, inherited, status, adjacent=None):
        hits = self.hits(value)
        for start, end, payload in hits:
            prefix = value[:start]
            previous_end = max((finish for _, finish, _ in hits if finish <= start), default=0)
            after_previous = value[previous_end:start]
            # A new header after the previous opaque body begins a new record.
            # With no new header, retain a single common batch header.
            if previous_end and re.search(_LABEL, after_previous, re.I):
                prefix = after_previous
            else:
                for begin, finish, _ in reversed(hits):
                    if finish <= start:
                        prefix = prefix[:begin] + prefix[finish:]
            local, local_status = _header(prefix, self.addresses)
            if status == 'rejected' or local_status == 'rejected':
                senders, result_status = frozenset(), 'supported'
            elif local:
                senders, result_status = inherited | local, 'supported'
            elif inherited:
                senders, result_status = inherited, status
            elif local_status == 'unsupported' or status == 'unsupported':
                senders, result_status = frozenset(), 'unsupported'
            elif adjacent and not prefix.strip():
                senders, result_status = adjacent
                if result_status == 'rejected':
                    result_status = 'supported'
            else:
                senders, result_status = frozenset(), 'missing'
            self.output.append(Occurrence(payload, self.entry, len(self.output), path,
                                          span, depth, senders, result_status, self.raw))

    def walk(self, value, path, span, depth, inherited=frozenset(), status='missing'):
        if isinstance(value, _Object):
            own = frozenset(v for k, v in value if k.lower() in _LABELS and isinstance(v, str))
            scope = inherited | own
            scope_status = 'rejected' if status == 'rejected' else ('supported' if scope else status)
            hint = any(k.lower() in _HINT_KEYS and isinstance(v, str) and
                       any(address in v for address in self.addresses) for k, v in value)
            if hint and not scope and status != 'rejected':
                scope_status = 'unsupported'
            for pair_index, (key, child) in enumerate(value):
                lower = key.lower()
                if lower in _LABELS:
                    continue
                if lower in _ROSTER_KEYS:
                    child_scope, child_status = frozenset(), 'missing'
                elif lower in _BODY_KEYS:
                    child_scope, child_status = scope, scope_status
                else:
                    # Unknown containers do not inherit a sender by assumption.
                    child_scope = scope if len(scope) > 1 else frozenset()
                    child_status = ('supported' if len(scope) > 1 else 'unsupported') if scope else scope_status
                if status == 'rejected':
                    child_status = 'rejected'
                self.walk(child, path + (key, pair_index), span, depth, child_scope, child_status)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                self.walk(child, path + (index,), span, depth, inherited, status)
        elif isinstance(value, str):
            self.string(value, path, span, depth, inherited, status)

    def string(self, value, path, span, depth, inherited=frozenset(), status='missing', adjacent=None):
        hits = self.hits(value)
        # Decode whole JSON strings (including double-encoded envelopes) only
        # when they are not themselves the complete known body.
        if depth < 12 and not any(a == 0 and b == len(value) for a, b, _ in hits):
            stripped = value.strip()
            if stripped.startswith('"'):
                try:
                    decoded = json.loads(stripped)
                except ValueError:
                    pass
                else:
                    if isinstance(decoded, str) and decoded != value:
                        return self.string(decoded, path + ('$decoded',), span, depth + 1,
                                           inherited, status, adjacent)
        end = 0
        for match in re.finditer(r'[\[{"]', value):
            start = match.start()
            if start < end or any(a <= start < b for a, b, _ in hits):
                continue
            if depth >= 12:
                continue
            try:
                decoded, finish = self.decoder.raw_decode(value, start)
            except ValueError:
                continue
            prefix = value[end:start]
            if isinstance(decoded, str) and prefix.strip():
                _, header_status = _header(prefix, self.addresses)
                if header_status == 'missing':
                    continue
            self.emit(prefix, path + (end,), span, depth, inherited, status, adjacent if end == 0 else None)
            local, local_status = _header(prefix, self.addresses)
            scope, scope_status = inherited | local, 'supported' if inherited or local else status
            if status == 'rejected' or local_status == 'rejected':
                scope_status = 'rejected'
            elif not scope and local_status == 'unsupported':
                scope_status = 'unsupported'
            if end == 0 and not prefix.strip() and adjacent and not scope:
                scope, scope_status = adjacent
            child_span = (start, finish) if depth == 0 else span
            self.walk(decoded, path + ('$json', start), child_span, depth + 1, scope, scope_status)
            end = finish
        self.emit(value[end:], path + (end,), span, depth, inherited, status, adjacent if end == 0 else None)


def read_messages(messages, payloads, addresses=()):
    reader = _Reader(payloads, addresses)
    previous = None
    for index, message in enumerate(messages):
        reader.entry, reader.raw = index, text(message)
        adjacent = None
        if previous is not None and previous.get('role') not in ('tool', 'toolResult'):
            header = text(previous)
            if not reader.hits(header):
                try:
                    value = reader.decoder.decode(header)
                except ValueError:
                    adjacent = _header(header, reader.addresses, adjacent=True)
                else:
                    if isinstance(value, _Object) and value and all(
                            key.lower() in _LABELS and isinstance(item, str) for key, item in value):
                        adjacent = frozenset(item for _, item in value), 'supported'
        reader.string(reader.raw, (), (0, len(reader.raw)), 0, adjacent=adjacent)
        previous = message
    return MessageRead(reader.output)


def contains_finding(messages, finding):
    return read_messages(messages, (finding,)).count(finding) > 0
