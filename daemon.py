"""Client for the local Nerdit daemon.

The plugin never reads Nerdit's token or talks to the daemon's HTTP API itself.
It starts the ``nerdit mcp`` process that ships with the engine, which acts with
the credentials of the user's own ``nerdit`` CLI, and sends it one tool call over
stdio (JSON-RPC, one JSON object per line).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading

PROTOCOL = "2025-06-18"


class NerditError(Exception):
    """A call to the local daemon failed. ``code`` is short and stable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def binary() -> str | None:
    """Returns the path of the ``nerdit`` CLI, or None when it is not installed.

    ``NERDIT_BIN`` wins over ``PATH``, for a gateway service that starts with a
    minimal ``PATH``.
    """
    return os.environ.get("NERDIT_BIN") or shutil.which("nerdit")


def call(tool: str, arguments: dict | None = None, timeout: float = 120.0):
    """Runs one daemon tool and returns its decoded result.

    Args:
        tool: Name of a tool of the Nerdit engine, such as ``list_services``.
        arguments: The tool's arguments.
        timeout: Seconds before the call is abandoned and the process killed.

    Returns:
        The tool's structured result (usually a dict), or its text when the
        daemon answered with plain text.

    Raises:
        NerditError: ``not_installed`` when the CLI is missing, ``timeout``,
            ``protocol`` when the process ended without an answer, or
            ``tool_error`` when the daemon refused the call (the message is the
            daemon's own, which names the fix).
    """
    exe = binary()
    if not exe:
        raise NerditError(
            "not_installed",
            "The nerdit CLI is not installed on this machine (or not on PATH; set NERDIT_BIN). "
            "Install the engine: https://docs.nerdit.ai/engine/quickstart",
        )
    try:
        proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            [exe, "mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
        )
    except OSError as exc:
        raise NerditError("not_installed", f"Cannot start {exe}: {exc}") from exc
    timed_out = threading.Event()

    def _kill():
        timed_out.set()
        proc.kill()

    timer = threading.Timer(timeout, _kill)
    timer.start()
    try:
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": PROTOCOL, "capabilities": {},
            "clientInfo": {"name": "hermes-nerdit", "version": "1"}}})
        _read(proc, 1)
        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                     "params": {"name": tool, "arguments": arguments or {}}})
        reply = _read(proc, 2)
    except (OSError, ValueError) as exc:
        if timed_out.is_set():
            raise NerditError("timeout", f"{tool} did not answer within {int(timeout)} s") from exc
        raise NerditError("protocol", f"nerdit mcp ended without an answer: {exc}") from exc
    finally:
        timer.cancel()
        proc.kill()
        proc.wait()
    if "error" in reply:
        raise NerditError("tool_error", str(reply["error"].get("message", reply["error"])))
    result = reply.get("result", {})
    text = "\n".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
    if result.get("isError"):
        raise NerditError("tool_error", text or f"{tool} failed")
    if "structuredContent" in result:
        data = result["structuredContent"]
        # FastMCP wraps a non-object return value as {"result": value}.
        return data["result"] if set(data) == {"result"} else data
    try:
        return json.loads(text)
    except ValueError:
        return text


def _send(proc, message: dict) -> None:
    proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.flush()


def _read(proc, wanted_id: int) -> dict:
    """Returns the reply to ``wanted_id``, skipping notifications and logs."""
    for line in proc.stdout:
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if isinstance(message, dict) and message.get("id") == wanted_id:
            return message
    raise ValueError("stream closed")
