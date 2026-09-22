"""Verifier-owned case inventory; contains no candidate imports."""

CONTRACT_CASES = {
    "a fresh user prompt after idle overflow compaction stays a prompt and references its own user entry",
    "a user follow-up queued at agent_end opens a continuation run referencing its user entry",
    "an error response without errorMessage uses aborted for chat and turn status",
    "a child spawned after a concurrent sibling starts keeps its own tool parent through compaction",
    "a prompt with a tool call exports run, turn, chat and tool spans in OTLP/JSON tied to session entries",
    "a failing tool and an error response mark tool, chat and turn spans ERROR while the run stays OK",
    "runs started by an extension message are wakeups and runs queued at agent_end are continuations",
    "manual and threshold compactions export root compaction spans tied to compaction entries",
    "reload appends to the same file with the same trace id and no duplicate spans",
    "PI_AGENT_TRACE_FILE replaces the trace file path",
    "an aborted stream marks its chat and turn ERROR and the trace stays consistent afterwards",
    "a failed compaction exports an ERROR compaction span without an entry id",
    "a quit while a run is streaming closes the open spans with status shutdown",
    "an unwritable trace path never reaches the agent and is reported once",
    "the file updates live: start lines appear while a tool is still running and end lines complete them",
    "concurrent tool calls of one assistant message get one overlapping span each with its own status and entry",
    "steering and follow-up messages start turns inside the run and are listed on it, never as new runs",
    "overflow recovery persists the failed chat, compacts with will_retry and continues in a run without a message",
    "a child pi spawned through the documented integration joins its spawning tool trace",
}

LIFECYCLE_CASES = {
    "a later pi process appends to the same trace with the same trace id and its own process id",
    "a pi process killed during a tool execution leaves that turn's chat span on disk",
}
