"""Tools, the health watch and the approval guard of the Nerdit plugin."""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import daemon

UNHEALTHY = {"failed", "degraded", "restarting"}

# Engine tools that delete data, expose an app or run arbitrary commands: a
# person approves each of these, whatever the session's approval mode.
ASK_FIRST = {
    "remove_service", "delete_project", "remove_secret", "remove_domain", "add_domain",
    "unshare_service", "run_command", "system_gc", "restart_daemon", "set_config",
    "apply_config", "dump_database",
}

SHIP = {
    "name": "nerdit_ship",
    "description": (
        "Put an app folder online on this machine with the local Nerdit engine: build it, run it "
        "as a supervised service, wait until it is healthy and return its URL. Use it whenever "
        "the user wants something you built to keep running or to be reachable (a web app, a "
        "bot, an API, a scheduled job) instead of starting it by hand in a terminal, where it "
        "dies with the session. The folder needs a Dockerfile, a package.json, or a "
        "requirements.txt / pyproject.toml. Calling it again with the same name redeploys in "
        "place. On failure the result carries the diagnosis: fix the cause and call it again."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "App folder. Relative paths start at the session's working directory. Default: that directory."},
            "name": {"type": "string", "description": "App name, a lowercase DNS label. Default: the folder's name."},
            "port": {"type": "integer", "description": "Port the app listens on inside its container."},
            "start": {"type": "string", "description": "Start command, when the engine cannot detect it."},
            "health": {"type": "string", "description": "HTTP path to probe for health, such as /healthz."},
            "timeout": {"type": "integer", "description": "Seconds to wait for the app to become healthy. Default 180, at most 300."},
        },
    },
}

APPS = {
    "name": "nerdit_apps",
    "description": "List the apps, models and databases the local Nerdit engine runs on this machine, with their status and URL.",
    "parameters": {"type": "object", "properties": {}},
}

DIAGNOSE = {
    "name": "nerdit_diagnose",
    "description": (
        "Explain why a Nerdit app is failing: last deploy, crash forensics, health probe, restart "
        "history, a log tail and a remediation code. Call it before changing anything on an app "
        "that is failed, degraded or restarting."
    ),
    "parameters": {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "App name."}},
        "required": ["name"],
    },
}

LOGS = {
    "name": "nerdit_logs",
    "description": "Read the most recent log lines of a Nerdit app.",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "App name."},
            "lines": {"type": "integer", "description": "How many lines. Default 80."},
        },
        "required": ["name"],
    },
}

CALL = {
    "name": "nerdit_call",
    "description": (
        "Call any other tool of the local Nerdit engine by name: restart_service, stop_service, "
        "share_service (a private URL for named people), create_database, serve_model, "
        "add_schedule, add_hook, set_variable, get_guide and the rest. Call it with "
        "tool='list_guides' or tool='get_guide' and arguments {'topic': 'index'} to read the "
        "engine's own guides before writing a nerdit.toml. Never pass a secret value: ask the "
        "user to run `nerdit secrets set <app> --prompt KEY` themselves. Tools that delete data, "
        "make an app public or run commands ask the user first."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "tool": {"type": "string", "description": "Engine tool name."},
            "arguments": {"type": "object", "description": "The tool's arguments."},
        },
        "required": ["tool"],
    },
}


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _run(tool: str, arguments: dict | None = None, timeout: float = 120.0) -> str:
    """Runs an engine tool and returns a JSON string, also on failure."""
    try:
        return _json(daemon.call(tool, arguments, timeout=timeout))
    except daemon.NerditError as exc:
        return _json({"error": {"code": exc.code, "message": str(exc)}})


def _cwd() -> Path:
    """The session's working directory (the gateway's own cwd is not it)."""
    try:
        from agent.runtime_cwd import resolve_agent_cwd
        return Path(resolve_agent_cwd())
    except Exception:  # an older Hermes, or outside a session
        return Path.cwd()


def _summary(service: dict) -> dict:
    deploy = service.get("last_deploy") or {}
    out = {
        "name": service.get("name"),
        "kind": service.get("kind"),
        "status": service.get("status"),
        "url": service.get("public_url") or service.get("endpoint") or service.get("url"),
    }
    error = service.get("error_message") or deploy.get("error_message")
    if error:
        out["error"] = error
    return out


def services() -> list[dict]:
    """Returns a short summary of every service of the local engine.

    Raises:
        daemon.NerditError: The engine is missing or did not answer.
    """
    data = daemon.call("list_services", {"limit": 200}, timeout=8.0)
    if isinstance(data, dict) and "error" in data:
        raise daemon.NerditError("tool_error", str(data["error"].get("message", data["error"])))
    return [_summary(item) for item in (data or {}).get("items", [])]


def ship(args: dict, **kwargs) -> str:
    """Handler of ``nerdit_ship``: deploy a folder, then wait for the outcome."""
    path = Path(str(args.get("path") or ".")).expanduser()
    if not path.is_absolute():
        path = _cwd() / path
    path = path.resolve()
    if not path.is_dir():
        return _json({"error": {"code": "not_a_folder", "message": f"{path} is not a folder"}})
    request = {"path": str(path)}
    request.update({k: args[k] for k in ("name", "port", "start", "health") if args.get(k)})
    try:
        deployed = daemon.call("deploy", request, timeout=120.0)
        if not isinstance(deployed, dict) or "error" in deployed:
            return _json(deployed)
        wait = max(1, min(int(args.get("timeout") or 180), 300))
        outcome = daemon.call(
            "wait_for_service",
            {"name": deployed["name"], "version": (deployed.get("last_deploy") or {}).get("version"),
             "timeout": wait},
            timeout=wait + 30.0,
        )
    except daemon.NerditError as exc:
        return _json({"error": {"code": exc.code, "message": str(exc)}})
    _snapshot["at"] = None  # the next turn re-reads the apps
    if isinstance(outcome, dict) and outcome.get("outcome") == "converged":
        url = outcome.get("public_url")
        if not url:
            try:
                url = _summary(daemon.call("get_service", {"name": deployed["name"]}, timeout=8.0)).get("url")
            except daemon.NerditError:
                url = None
        return _json({"outcome": "converged", "name": deployed["name"], "status": outcome.get("status"), "url": url})
    return _json(outcome)


def apps(args: dict, **kwargs) -> str:
    """Handler of ``nerdit_apps``."""
    try:
        return _json({"apps": services()})
    except daemon.NerditError as exc:
        return _json({"error": {"code": exc.code, "message": str(exc)}})


def diagnose(args: dict, **kwargs) -> str:
    """Handler of ``nerdit_diagnose``."""
    return _run("diagnose_service", {"name": args.get("name", "")}, timeout=30.0)


def logs(args: dict, **kwargs) -> str:
    """Handler of ``nerdit_logs``."""
    return _run("service_logs", {"name": args.get("name", ""), "tail": int(args.get("lines") or 80)}, timeout=30.0)


def call(args: dict, **kwargs) -> str:
    """Handler of ``nerdit_call``: any engine tool, by name."""
    tool = str(args.get("tool") or "")
    if not tool:
        return _json({"error": {"code": "missing_tool", "message": "tool is required"}})
    arguments = args.get("arguments") or {}
    wait = float(arguments.get("timeout") or 0) if isinstance(arguments, dict) else 0
    _snapshot["at"] = None
    return _run(tool, arguments, timeout=max(120.0, wait + 30.0))


def guard(tool_name: str = "", args: dict | None = None, **kwargs):
    """``pre_tool_call`` hook: a person approves destructive or exposing calls.

    Returns:
        An ``approve`` directive for a risky ``nerdit_call``, else None.
    """
    if tool_name != "nerdit_call":
        return None
    args = args or {}
    tool = str(args.get("tool") or "")
    arguments = args.get("arguments") if isinstance(args.get("arguments"), dict) else {}
    public = tool == "share_service" and arguments.get("access") == "public"
    if tool in ASK_FIRST or public:
        what = "make an app public on the internet" if public else tool
        target = arguments.get("name") or arguments.get("service") or ""
        return {"action": "approve", "message": f"Nerdit: {what} {target}".strip()}
    return None


# One reading of the engine shared by every session of this process.
# ponytail: per-process cache with a 60 s TTL; a push from the engine's event
# stream would be instant, add it if a minute of delay ever matters.
_snapshot: dict = {"at": None, "apps": []}
_told: dict[str, set] = {}
TTL = 60.0


def watch(session_id: str = "", is_first_turn: bool = False, **kwargs):
    """``pre_llm_call`` hook: tell the agent when one of its apps is down.

    On a session's first turn it lists what runs on the machine. On later turns
    it speaks only when an app became unhealthy, once per app and status, so the
    agent learns of an outage without being asked and is not nagged about it.

    Returns:
        ``{"context": text}`` to inject, or None. Never raises: a machine
        without the engine simply gets no context.
    """
    now = time.monotonic()
    if _snapshot["at"] is None or now - _snapshot["at"] > TTL:
        try:
            _snapshot["apps"] = services()
        except Exception:
            _snapshot["apps"] = []
        _snapshot["at"] = now
    current = _snapshot["apps"]
    if not current:
        return None
    if len(_told) > 500:
        _told.clear()
    told = _told.setdefault(session_id, set())
    down = [a for a in current if a["status"] in UNHEALTHY]
    fresh = [a for a in down if (a["name"], a["status"]) not in told]
    told.update((a["name"], a["status"]) for a in down)
    lines = []
    if is_first_turn:
        lines.append("Apps running on this machine with Nerdit: " + ", ".join(
            f"{a['name']} ({a['status']})" for a in current) + ".")
    for a in fresh:
        lines.append(
            f"Nerdit app '{a['name']}' is {a['status']}"
            + (f": {a['error'].rstrip('.')}" if a.get("error") else "")
            + ". Tell the user, and call nerdit_diagnose before changing anything."
        )
    return {"context": "\n".join(lines)} if lines else None


def apps_command(raw_args: str = "", **kwargs) -> str:
    """Handler of ``/apps``: status without a model call. ``/apps <name>`` diagnoses one app."""
    name = (raw_args or "").strip()
    try:
        if name:
            report = daemon.call("diagnose_service", {"name": name}, timeout=30.0)
            if "error" in report and "status" not in report:
                return f"Nerdit: {report['error'].get('message', report['error'])}"
            fix = report.get("remediation") or {}
            tail = [entry.get("line", "") for entry in (report.get("logs") or [])[-8:]]
            return "\n".join(
                [f"{name}: {report.get('status')}", f"{fix.get('code', '')}: {fix.get('detail', '')}".strip(": ")]
                + tail
            )
        current = services()
    except daemon.NerditError as exc:
        return f"Nerdit: {exc}"
    if not current:
        return "No app runs on this machine yet. Ask me to build one and put it online."
    marks = {"running": "🟢", "building": "🟡", "stopped": "⚪"}
    return "\n".join(
        f"{marks.get(a['status'], '🔴')} {a['name']}  {a['status']}  {a.get('url') or ''}".rstrip()
        for a in current
    )
