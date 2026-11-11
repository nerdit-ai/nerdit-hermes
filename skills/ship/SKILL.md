---
name: ship
description: Build an app, bot, API or scheduled job and put it online on this machine with Nerdit, so that it keeps running after the session ends. Use when the user asks to build, host, deploy, ship or "keep running" something.
---

# Build something and put it online with Nerdit

Nerdit is the engine on this machine that builds a folder, runs it as a supervised service and
gives it a URL. Do not start a long-running program in the terminal: it dies with the session.

1. **Read the engine's guides first.** `nerdit_call` with `{tool: "get_guide", arguments: {topic: "index"}}`,
   then the guide the index names for what you are building (AI model, database, schedule,
   webhook). The guides give the exact `nerdit.toml` keys for the engine version installed here.
   Never write `nerdit.toml` from memory.
2. **Write the app** in its own folder, with a `requirements.txt`, `pyproject.toml`,
   `package.json` or `Dockerfile`. It must listen on `0.0.0.0` and on the port you declare.
3. **Secrets.** Never ask for a secret value in chat. Name the key and ask the user to run
   `nerdit secrets set <app> --prompt KEY` themselves, then continue.
4. **Ship it.** `nerdit_ship` with `{path, name, port}`. It waits until the app is healthy.
5. **If it failed,** the result carries the diagnosis. Fix the cause in the code or the
   `nerdit.toml` and call `nerdit_ship` again with the same name. At most three attempts, then
   show the user the error and the log tail.
6. **Answer** with the URL and one line on what runs. To give other people access, call
   `nerdit_share`: private by default (the user then allows each person in the Nerdit App),
   public only when they ask for it. It needs a linked Nerdit account; say so when the engine
   refuses.
