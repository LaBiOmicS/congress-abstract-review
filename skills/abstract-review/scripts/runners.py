"""Headless reviewer execution through `claude -p`, `agy -p` or `gemini -p` subprocesses.

Command building, prompt delivery and environment scrubbing are vendored from academic-peer-review
(skills/paper-review/scripts/spawn_reviewers.py, commit 71fb74c). Differences: reviewers need no
tools (every prompt is self-contained), so `sandboxed` on Claude Code allows only `Read`; and tasks
run through a bounded thread pool, because a congress batch can hold hundreds of them.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

RUNNERS = ("agy", "gemini", "claude")
MAX_ARG_PROMPT_BYTES = 120_000

SCRUBBED_ENV_VARS = {
    "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "GITHUB_TOKEN", "GH_TOKEN", "GITLAB_TOKEN", "NPM_TOKEN",
    "PYPI_API_TOKEN", "DATABASE_URL", "PGPASSWORD", "MYSQL_PWD", "SLACK_BOT_TOKEN", "STRIPE_SECRET_KEY", "SSH_AUTH_SOCK",
}
SECRET_NAME_REGEX = re.compile(r"(TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|APIKEY|PRIVATE_KEY|ACCESS_KEY|CREDENTIAL)", re.IGNORECASE)
GOOGLE_RUNNER_ENV = {
    "GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION", "GOOGLE_GENAI_USE_VERTEXAI",
}
RUNNER_ENV_ALLOWLIST = {
    "agy": GOOGLE_RUNNER_ENV,
    "gemini": GOOGLE_RUNNER_ENV,
    "claude": {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"},
}


def detect_runner(requested: str) -> str:
    if requested != "auto":
        if not shutil.which(requested):
            raise RuntimeError(f"Requested runner '{requested}' not found in PATH.")
        return requested
    for candidate in ("claude", "agy", "gemini"):
        if shutil.which(candidate):
            return candidate
    raise RuntimeError("No supported CLI runner ('claude', 'agy' or 'gemini') found in PATH.")


def build_cli_cmd(runner: str, model: str | None, effort: str | None, tool_permissions: str = "sandboxed") -> list[str]:
    """Reviewer CLI command. tool_permissions: sandboxed (default) | none | unsafe (trusted input only)."""
    if runner == "agy":
        cmd = ["agy"]
        if tool_permissions == "sandboxed":
            cmd.extend(["--sandbox", "--dangerously-skip-permissions"])
        elif tool_permissions == "unsafe":
            cmd.append("--dangerously-skip-permissions")
        if model and model not in ("auto", "default", "inherit"):
            cmd.extend(["--model", model])
        if effort:
            cmd.extend(["--effort", effort])
        cmd.append("-p")  # agy takes the prompt as the value of -p: must come last
        return cmd
    if runner == "gemini":
        cmd = ["gemini"]
        if tool_permissions == "sandboxed":
            cmd.extend(["--sandbox", "-y"])
        elif tool_permissions == "unsafe":
            cmd.append("-y")
        cmd.extend(["-p", ""])
        if model and model not in ("auto", "default", "inherit"):
            cmd.extend(["-m", model])
        return cmd
    if runner == "claude":
        cmd = ["claude", "-p"]
        if tool_permissions == "sandboxed":
            cmd.extend(["--allowedTools", "Read"])
        elif tool_permissions == "unsafe":
            cmd.append("--dangerously-skip-permissions")
        if model and model not in ("auto", "default", "inherit"):
            cmd.extend(["--model", model])
        if effort:
            cmd.extend(["--effort", effort])
        return cmd
    raise ValueError(f"Unsupported runner: {runner}")


def prompt_delivery(runner: str, cmd: list[str], prompt: str, prompt_file: Path) -> tuple[list[str], str | None]:
    """(command, stdin text). agy gets the prompt as -p's value (or a pointer to the file when too long)."""
    if runner != "agy":
        return cmd, prompt
    if len(prompt.encode("utf-8")) <= MAX_ARG_PROMPT_BYTES:
        return [*cmd, prompt], None
    return [*cmd, f"Read the file {prompt_file} completely and follow its instructions exactly. Print only the finished Markdown."], None


def build_sanitized_env(runner: str) -> dict[str, str]:
    env = os.environ.copy()
    allowed = RUNNER_ENV_ALLOWLIST.get(runner, set())
    for k in list(env):
        if k not in allowed and (k in SCRUBBED_ENV_VARS or SECRET_NAME_REGEX.search(k)):
            env.pop(k, None)
    return env


def run_tasks(
    tasks: list[dict[str, Any]],
    *,
    runner: str,
    model: str | None = None,
    effort: str | None = None,
    tool_permissions: str = "sandboxed",
    parallel: int = 4,
    timeout: float = 600.0,
    retries: int = 1,
    validate: Callable[[str], bool] = lambda s: len(s) > 200,
    log: Callable[[str], None] = print,
) -> list[dict[str, Any]]:
    """Run every task (dict with prompt_file, output_file) and write stdout to output_file when valid."""
    env = build_sanitized_env(runner)
    base = build_cli_cmd(runner, model, effort, tool_permissions)

    def one(task: dict[str, Any]) -> dict[str, Any]:
        prompt_file = Path(task["prompt_file"])
        prompt = prompt_file.read_text(encoding="utf-8")
        cmd, stdin = prompt_delivery(runner, list(base), prompt, prompt_file)
        last = ""
        for attempt in range(1, retries + 2):
            t0 = time.time()
            try:
                proc = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=timeout, env=env, check=False)
                out = proc.stdout.strip()
                if proc.returncode == 0 and validate(out):
                    Path(task["output_file"]).write_text(out + "\n", encoding="utf-8")
                    return {**task, "status": "ok", "attempts": attempt, "seconds": round(time.time() - t0, 1)}
                last = f"rc={proc.returncode} stdout={len(out)}B stderr={proc.stderr.strip()[-300:]}"
            except subprocess.TimeoutExpired:
                last = f"timeout after {timeout}s"
            log(f"[runner] {task['id']} attempt {attempt} failed: {last}")
        return {**task, "status": "failed", "error": last}

    results = []
    with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
        futures = [pool.submit(one, t) for t in tasks]
        for fut in as_completed(futures):
            r = fut.result()
            log(f"[runner] {r['id']}: {r['status']}")
            results.append(r)
    return results
