---
name: rescue
description: Find out why an app running on Nerdit is failing, crashing, restarting or not answering, and fix it. Use when the user says an app is down or broken, or when the Nerdit plugin reports an unhealthy app.
---

# Rescue a failing Nerdit app

1. **Look.** `nerdit_diagnose` with `{name}`. Read `remediation.code` and `detail` first, then
   `error`, `forensics` (exit code, out of memory), `health` and the log tail.
2. **Decide from the evidence,** not from a guess:
   - a crash in the app's own code: fix the code, then `nerdit_ship` the folder again;
   - a missing variable or secret: name the key and ask the user to set it with
     `nerdit secrets set <app> --prompt KEY`, then restart;
   - a transient failure the engine already retries: `nerdit_call` with `restart_service`, once;
   - the engine itself (Docker stopped, disk full): say so, with the command to run. Do not
     work around it.
3. **Verify.** `nerdit_apps`, or `nerdit_call` with `wait_for_service`. Do not report success
   before the app is `running`.
4. **Report** in three lines: what was wrong, what you changed, what the user must do, if
   anything. Never delete an app or its data to "start clean" without asking.
