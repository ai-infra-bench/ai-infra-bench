"""Verifier-owned case inventory; contains no candidate imports."""

CONTRACT_CASES = {
    "registers bg_run, bg_logs, bg_list, bg_kill and bg_watch",
    "bg_run returns a running record and bg_logs pages output in order",
    "bg_logs bounds a page to 64 KB and serves the newest lines by default",
    "exit wakes an idle agent exactly once with the exit code",
    "ready wakes once and is delivered after the running tool batch",
    "bg_kill escalates to SIGKILL, removes grandchildren and wakes once",
    "bg_watch silences the exit wake and drops patterns",
    "cleanup runs after the group is gone and a failing cleanup is reported",
    "processes survive extension reload",
    "processes survive new session and fork and remain killable",
    "wake goes to the active session after the starting session was replaced",
    "two processes firing in one window wake in first-fire order",
    "log flood is paged from disk without growing the heap",
    "bash keeps the built-in contract for commands that finish before the silence threshold",
    "a silent bash command moves to the background and its next output and exit wake the agent",
}

LIFECYCLE_CASES = {
    "pi process exit stops managed processes and their grandchildren",
    "SIGTERM to the pi process stops managed processes",
    "a later pi process resumes the session and reads finished records",
}
