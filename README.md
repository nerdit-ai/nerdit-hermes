# Nerdit for Hermes Agent

**Hermes puts what it builds online on its own machine, and keeps it alive.**

Ask Hermes for an app, a bot or a scheduled job. It writes the code, then this plugin hands the
folder to [Nerdit](https://github.com/nerdit-ai/nerdit), the open-source engine running on the
same machine: Nerdit builds it, runs it as a supervised service and gives it a URL. The app
keeps running after the chat ends. When one of your apps goes down, Hermes knows on its next
turn, without being asked.

```
You (Telegram):  build me a page that shows my server's uptime, and put it online
Hermes:          ...writes the app, calls nerdit_ship...
                 It's live: https://nerdit.local/uptime/
You:             /apps
Hermes:          🟢 uptime  running  https://nerdit.local/uptime/
                 🔴 feed-bot  failed
```

## What the plugin adds

| | |
|---|---|
| **`nerdit_ship`** | One tool call that deploys a folder, waits until it is healthy and returns the URL. On failure it returns the engine's diagnosis, so Hermes fixes the cause and ships again. |
| **`nerdit_apps`, `nerdit_diagnose`, `nerdit_logs`** | What runs here, why an app is failing, and its logs. |
| **`nerdit_call`** | Every other tool of the engine by name: databases, local models, schedules, webhooks, sharing, and the engine's own guides (`get_guide`). |
| **Outage awareness** (`pre_llm_call` hook) | At the start of a session Hermes is told what runs on the machine. Later it is told once when an app becomes failed, degraded or restarting. No polling by the model, no tokens spent while everything is healthy. |
| **Standing instruction** (system prompt section) | Six lines that tell Hermes to ship through `nerdit_ship` and not to drive Docker or the `nerdit` CLI from the terminal. |
| **Approval guard** (`pre_tool_call` hook) | Deleting an app or its data, making an app public, binding a domain and running a command in a container always ask a person first, whatever the session's approval mode. |
| **`/apps`** | The status of your apps in the CLI, Telegram or Discord, answered by the plugin itself with no model call. `/apps <name>` shows why that app is failing. |
| **"Keep my apps alive"** blueprint | `/blueprint nerdit:watch` schedules a check every 5, 15 or 30 minutes. When an app is down, Hermes diagnoses it, restarts it if that is the fix, and reports. It stays silent while everything runs. |
| **Skills** | `nerdit:ship` and `nerdit:rescue`, the two workflows above written out. |

## Install

You need the Nerdit engine and Docker on the machine where Hermes runs. Follow the
[engine quickstart](https://docs.nerdit.ai/engine/quickstart), then check it with `nerdit doctor`.

```bash
hermes plugins install nerdit        # or, before it is listed: hermes plugins install nerdit-ai/nerdit-hermes
hermes plugins enable nerdit
```

Run `nerdit trust` once so that the `https://nerdit.local/...` URLs open without a certificate
warning. Start a new session and ask: *"build a hello-world web app and put it online"*.

If Hermes runs as a service with a minimal `PATH`, set `NERDIT_BIN` to the full path of the
`nerdit` executable. Without the engine the plugin stays quiet: its tools answer with a clear
"not installed" error and the hooks add nothing.

## What this plugin does on your machine

- **It starts a local process.** Each call runs `nerdit mcp`, the server that ships with the
  engine, and sends it one request over stdio. No shell is involved and the arguments are
  fixed. The outage check runs it at most once a minute, with an 8 second limit.
- **It acts with your `nerdit` CLI's rights.** The plugin never reads, stores or sends a
  credential. The `nerdit` process uses the token your CLI is configured with, which is an
  admin token by default. To narrow what Hermes can do, give the CLI a scoped token, as
  described in the [engine's security guide](https://docs.nerdit.ai/engine/security).
- **It reads the folder you ask it to deploy.** The engine zips that folder and builds it. The
  plugin reads nothing else outside its own files.
- **Network.** The plugin makes no network call. The engine listens on `127.0.0.1`. Apps you
  deploy do whatever their code does. A URL other people can open (`share_service`) goes
  through Nerdit Cloud and needs a linked account, which is optional.
- **Secrets.** The skills tell Hermes never to ask for a secret in chat. You set them yourself
  with `nerdit secrets set <app> --prompt KEY`.
- **No telemetry**, no background thread, no self-update.
- **Unattended runs.** The scheduled watch is instructed to read, diagnose and restart only,
  never to delete or redeploy.

## Develop

```bash
python3 tests/test_plugin.py                 # stdlib only, uses a fake engine
hermes plugins validate . --install-deps
```

Apache-2.0. Engine: https://github.com/nerdit-ai/nerdit · Docs: https://docs.nerdit.ai
