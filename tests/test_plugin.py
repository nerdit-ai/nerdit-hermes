"""Checks the plugin against a fake ``nerdit mcp`` process (stdlib only).

Run with ``python3 tests/test_plugin.py``. No engine, Docker or Hermes needed.
"""

import importlib.util
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FAKE = r'''#!/usr/bin/env python3
import json, sys
SERVICES = {"items": [
    {"name": "blog", "kind": "service", "status": "running", "endpoint": {
        "url": "http://127.0.0.1:9400", "public_url": "http://blog.localhost", "host_port": 9400}},
    {"name": "bot", "kind": "service", "status": "failed", "error_message": "exit code 1"},
]}
REPLIES = {
    "list_services": SERVICES,
    "deploy": {"name": "blog", "last_deploy": {"version": 2}},
    "wait_for_service": {"outcome": "converged", "status": "running", "public_url": "http://blog.localhost"},
    "diagnose_service": {"status": "failed", "remediation": {"code": "restart", "detail": "transient"},
                         "logs": [{"line": "boom"}]},
}
for line in sys.stdin:
    msg = json.loads(line)
    if msg.get("method") == "initialize":
        out = {"protocolVersion": "2025-06-18", "capabilities": {}}
    elif msg.get("method") == "tools/call":
        name = msg["params"]["name"]
        if name not in REPLIES:
            out = {"isError": True, "content": [{"type": "text", "text": "Unknown tool: " + name}]}
        else:
            out = {"content": [{"type": "text", "text": json.dumps(REPLIES[name])}],
                   "structuredContent": REPLIES[name]}
    else:
        continue
    print("not json, a log line")
    print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": out}), flush=True)
'''


def load():
    """Imports the plugin folder as the package ``nerdit_plugin``."""
    spec = importlib.util.spec_from_file_location(
        "nerdit_plugin", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    module = importlib.util.module_from_spec(spec)
    sys.modules["nerdit_plugin"] = module
    spec.loader.exec_module(module)
    return module


def main():
    """Runs every check and exits non-zero on the first failure."""
    plugin = load()
    tools, daemon = plugin.tools, sys.modules["nerdit_plugin.daemon"]
    with tempfile.TemporaryDirectory() as tmp:
        fake = Path(tmp) / "nerdit"
        fake.write_text(FAKE)
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)

        os.environ["NERDIT_BIN"] = str(Path(tmp) / "missing")
        assert json.loads(tools.apps({}))["error"]["code"] == "not_installed"
        assert tools.watch(session_id="s0", is_first_turn=True) is None  # silent without an engine
        tools._snapshot["at"] = None

        os.environ["NERDIT_BIN"] = str(fake)
        assert [a["status"] for a in tools.services()] == ["running", "failed"]
        shipped = json.loads(tools.ship({"path": tmp, "name": "blog"}))
        assert shipped == {"outcome": "converged", "name": "blog", "status": "running",
                           "url": "http://blog.localhost"}, shipped
        assert json.loads(tools.ship({"path": str(fake)}))["error"]["code"] == "not_a_folder"
        assert json.loads(tools.call({"tool": "nope"}))["error"]["code"] == "tool_error"

        first = tools.watch(session_id="s1", is_first_turn=True)["context"]
        assert "blog (running)" in first and "'bot' is failed: exit code 1" in first, first
        assert tools.watch(session_id="s1") is None  # told once, not every turn
        assert "'bot' is failed" in tools.watch(session_id="s2")["context"]  # another session still learns

        ask = "Build a tiny hello-world web page app in ./hello and put it online."
        assert "nerdit_ship" in tools.watch(session_id="s3", user_message=ask)["context"]
        assert tools.watch(session_id="s3", user_message=ask) is None  # hinted once
        other = tools.watch(session_id="s4", user_message="what time is it?")["context"]
        assert "nerdit_ship" not in other and "'bot' is failed" in other  # no hint, outage still told

        approve = lambda tool, **a: tools.guard(tool_name="nerdit_call", args={"tool": tool, "arguments": a})
        assert approve("remove_service", name="bot")["action"] == "approve"
        assert approve("share_service", name="bot", access="public")["action"] == "approve"
        assert approve("share_service", name="bot", access="private") is None
        assert approve("restart_service", name="bot") is None
        assert tools.guard(tool_name="terminal", args={"command": "ls"}) is None

        listing = tools.apps_command("")
        assert "blog  running  http://blog.localhost" in listing and "🔴 bot  failed" in listing, listing
        assert "restart: transient" in tools.apps_command("bot")

        crash = Path(tmp) / "crash"
        crash.write_text("#!/bin/sh\necho 'ModuleNotFoundError: boom' >&2\nexit 1\n")
        crash.chmod(crash.stat().st_mode | stat.S_IEXEC)
        os.environ["NERDIT_BIN"] = str(crash)
        os.environ["PYTHONPATH"] = "/hermes"
        failure = json.loads(tools.apps({}))["error"]
        assert failure["code"] == "protocol" and "boom" in failure["message"], failure  # the reason is shown
        assert "PYTHONPATH" not in daemon._clean_env() and "PATH" in daemon._clean_env()

        os.environ["NERDIT_BIN"] = ""
        os.environ["PATH"] = tmp + "/empty"
        assert json.loads(tools.apps({}))["error"]["code"] == "not_installed"
        assert tools.apps_command("").startswith("Nerdit: The nerdit CLI is not installed")
        assert daemon.binary() is None
    print("plugin ok")


if __name__ == "__main__":
    main()
