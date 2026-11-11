"""Nerdit plugin for Hermes Agent: ship what the agent builds, keep it alive."""

from pathlib import Path

from . import tools


def register(ctx):
    """Registers the tools, the two hooks, ``/apps``, the watch blueprint and the skills."""
    for schema, handler in (
        (tools.SHIP, tools.ship), (tools.APPS, tools.apps), (tools.DIAGNOSE, tools.diagnose),
        (tools.LOGS, tools.logs), (tools.CALL, tools.call),
    ):
        ctx.register_tool(name=schema["name"], toolset="nerdit", schema=schema, handler=handler, emoji="🚀")

    ctx.register_hook("pre_llm_call", tools.watch)
    ctx.register_hook("pre_tool_call", tools.guard)
    ctx.register_command(
        "apps", handler=tools.apps_command,
        description="Apps running on this machine with Nerdit", args_hint="[app]",
    )

    blueprint = getattr(ctx, "register_automation_blueprint", None)
    if blueprint:
        blueprint(
            "watch",
            title="Keep my apps alive",
            description="Check the apps Nerdit runs on this machine. When one is down, find out why, restart it if that is the fix, and report.",
            category="work",
            schedule_template="*/{every} * * * *",
            prompt_template=(
                "Call nerdit_apps. If every app is running, building or stopped, respond with [SILENT]. "
                "For each app that is failed, degraded or restarting: call nerdit_diagnose, and if the "
                "remediation is a restart, restart it once with nerdit_call (tool restart_service) and "
                "check again. Then report in three lines per app: what was wrong, what you did, and "
                "what the user must do, if anything. Never delete anything and never redeploy."
            ),
            slots=[
                {"name": "every", "type": "enum", "label": "Check every how many minutes?",
                 "default": "15", "options": ["5", "15", "30"]},
                {"name": "deliver", "type": "enum", "label": "Where to deliver?", "default": "origin",
                 "options": ["origin", "local"], "strict": False},
            ],
            tags=["devops", "monitoring"],
        )

    skills = Path(__file__).parent / "skills"
    for child in sorted(skills.iterdir()):
        if (child / "SKILL.md").exists():
            ctx.register_skill(child.name, child / "SKILL.md")
