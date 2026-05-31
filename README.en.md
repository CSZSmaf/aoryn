# Aoryn Developer Guide

## 1. Project Positioning

Aoryn is a local-first desktop agent workbench.

It combines three layers behind one web shell:

- Chat mode: normal conversation using the configured model, with no direct desktop execution
- Agent mode: task execution, run playback, screenshots, and result review
- Advanced diagnostics: provider checks, payload inspection, and low-level debugging

The current goal is not multi-agent orchestration. The product is focused on a reliable single-task desktop agent with good observability and a clean local web UI.

## 2. Local Startup

### 2.1 Requirements

- Python 3.11+
- Windows desktop environment
- An installed browser, with `msedge` as the default channel
- Optional: LM Studio or any OpenAI-compatible model endpoint

### 2.2 Daily Source-Mode Testing

Use the development launcher when you want to test the project without building or installing a release package:

```bash
.\start_dev.bat
```

The equivalent Python entrypoint is:

```bash
python scripts/dev_start.py
```

By default this starts the source-mode workbench and tries to start the managed browser runtime on ports that are separate from an installed Aoryn session:

```text
Dashboard: http://127.0.0.1:8766
Browser Runtime: http://127.0.0.1:38992
```

Useful development flags:

```bash
python scripts/dev_start.py --ui web --no-browser-tab
python scripts/dev_start.py --no-managed-browser
python scripts/dev_start.py --port 8770 --managed-browser-port 39000
python scripts/dev_start.py --print-commands
```

The launcher writes `.tmp/source-test/config.yaml` and points the workbench at the same managed browser runtime port. Source-mode browser data stays under `.tmp/source-test/browser-profile`; packaged AppData paths are unchanged. Build and installer validation can wait until the source-mode result looks good.

### 2.3 Logic Benchmark

Run the deterministic task-logic benchmark before packaging to check common planner routes such as desktop app launch, browser follow-up clicks, calculator expressions, hotkeys, and save-as flows:

```bash
python scripts/run_logic_benchmark.py
```

### 2.4 Lower-Level Entrypoints

The direct commands are still available for debugging:

```bash
python run_agent.py
python run_agent.py ui --browser --no-browser --port 8766 --config .tmp/source-test/config.yaml
python run_browser.py --port 38992 --profile-root .tmp/source-test/browser-profile --config-path .tmp/source-test/config.yaml
```

### 2.5 Build a Windows EXE

Build artifacts are for release validation, not daily source-mode testing. The desktop shell can be packaged as a Windows app with PyInstaller:

```bash
python -m pip install --user -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File .\build_windows_exe.ps1
```

The generated application will be written to:

```text
dist/Aoryn/Aoryn.exe
```

For a full Windows release with a current-user installer and custom install path support:

```bash
powershell -ExecutionPolicy Bypass -File .\build_release.ps1
```

This produces:

```text
release/Aoryn-0.1.6-win64/
release/Aoryn-Setup-0.1.6.exe
```

### 2.6 Deploy the Official Website

The public website lives in:

```text
web/
```

It is a static React + Vite site prepared for Cloudflare Pages with:

```text
Root directory: web
Build command: npm run build
Build output directory: dist
```

Recommended production URLs:

- `https://aoryn.org` for the main site
- `https://www.aoryn.org` redirecting to `https://aoryn.org`
- `https://aoryn.org/download` for the gated download page
- `https://aoryn.org/api/downloads/windows-installer` for the authenticated installer route

Deployment details are documented in:

```text
web/DEPLOYMENT.md
web/DEPLOYMENT.zh-CN.md
```

Patch `0.1.6` keeps the display-detection diagnostics and manual override workflow, while removing the desktop sign-in gate and keeping the website download flow on the authenticated Pages Functions + R2 release pipeline.

The installed app stores user data outside the install directory:

- `%APPDATA%\Aoryn\` for config and runtime preferences
- `%LOCALAPPDATA%\Aoryn\` for runs, logs, screenshots, and caches

## 3. Project Layout

```text
desktop_agent/
  dashboard.py             HTTP server, static assets, and API routes
  chat_support.py          Chat-mode prompt building, help injection, and handoff detection
  controller.py            Main agent loop and dashboard launch
  config.py                AgentConfig and config loading
  provider_tools.py        Provider probing, model catalog, and LM Studio integration
  logger.py                Run directories, step logs, and summaries
  history.py               Run history loading and serialization
  dashboard_assets/
    index.html             Frontend shell
    styles.css             Frontend styling
    app.js                 Frontend state and rendering
    icons/                 Branding and app icons
```

## 4. Mode Architecture

### 4.1 Chat Mode

Chat mode is used for:

- answering product questions
- guiding provider, model, and browser setup
- helping users turn a rough request into a better Agent task

It uses `POST /api/chat` and `POST /api/chat/stream`, but it does not execute desktop tasks directly.

If a user message clearly looks like a desktop or browser execution request, the backend may return an `agent_handoff` suggestion. The UI can then render a "Send to Agent" action.

### 4.2 Agent Mode

Agent mode reuses the existing execution core:

1. capture the screen
2. produce a plan
3. validate actions
4. execute actions
5. persist logs into `runs/<run_id>/`
6. poll and render the run back into the web UI

### 4.3 Advanced Diagnostics

The advanced diagnostics area still exists, but it is no longer exposed as the main top-level mode.

Use it for:

- provider connectivity checks
- payload inspection
- timeline debugging
- regression analysis

The recommended entry point is the advanced area inside settings.

### 4.4 Complex Tasks: Research -> Synthesize -> Author

Aoryn splits "sit at the computer and finish a complex task like a person" into three layers,
mapping to brain, eyes, and hands:

1. Research (eyes + hands): browser search, opening pages, and `browser_dom_extract`. On every
   observation, the visible page title, URL, and body text are accumulated into the research notes
   on `ExecutionState.workspace` instead of being discarded each step.
2. Synthesize (brain): `DocumentComposer` in `desktop_agent/composer.py` reuses the configured model
   endpoint (LM Studio / OpenAI-compatible) to "think" the research notes plus the goal into a
   structured long-form document (a title plus `##` sections). When the model is unavailable or
   offline, it falls back to a deterministic outline so dry-run, benchmarks, and offline runs still
   produce a readable artifact.
3. Author (hands): the `document_authoring` capability focuses the target editor (Word / Notepad /
   WPS), then writes the finished document with a single `insert_text` action. `insert_text` prefers
   a clipboard paste (Unicode, newlines, long bodies) and falls back to line-by-line typing; its size
   ceiling is `max_document_length`.

It triggers when the task contains an explicit author verb (write / compose / summarize / 整理 / 总结 ...)
or names an editor (Word / Notepad / WPS). For example, "search Beijing travel guides then write it into
Word" decomposes into a research subgoal (handled by `browser_dom`) and an authoring subgoal (handled by
`document_authoring`). A plain "open notepad and type demo" is not treated as authoring.

### 4.5 Autonomous planning: one high-level goal -> research -> author

For a high-level "produce a deliverable that needs research first" goal, the agent **plans the steps
itself** — you don't have to spell out the research/writing split. `_extract_deliverable_plan` in
`planner.py` recognizes "a produce verb (write / plan / create / 撰写 / 规划 / 整理 ...) + a deliverable
noun (report / plan / summary / guide / itinerary / 报告 / 计划 / 攻略 / 行程 ...)" in a single-sentence goal
and autonomously expands it into:

1. `search for {topic}` -> `browser_dom` (research online; results accumulate into the workspace notes)
2. `write the {topic} {deliverable}` -> `document_authoring` (synthesize the notes with the model, write into an editor)

with an explicit dependency (research before authoring). Examples:

- "规划一个北京三日游" -> search Beijing 3-day trip -> write the trip itinerary
- "write a report about EVs" -> search for EVs -> write the EV report
- "create a study plan for calculus" -> search for calculus -> write the calculus plan

Both subgoals are low risk (web research + local writing), so under the default `conservative` autonomy
mode they are **auto-approved and run end to end** without step-by-step confirmation. The authoring subgoal
is only marked complete once the write action actually executes into the editor (merely opening the editor
does not count), which prevents "opened Word, therefore done" false completions. For fully hands-off runs
that also skip confirmation on medium/high-risk steps, set `desktop_autonomy_mode` to `autonomous`.

### 4.6 Autonomous planning, part two: model-driven adaptive re-planning

The decomposition above is still heuristic (it reads intent from the wording). True "guide the agent to
plan" means letting the **model reflect on and revise the plan during execution**: once the agent has
gathered new information, `orchestrator.reflect_on_plan` -> `planner.reflect_on_plan` hands the model the
**goal + completed steps + remaining steps + what has been learned** (research notes / facts / world model)
and asks whether the remaining plan still reaches the goal, then **inserts/adjusts the remaining subgoals**
accordingly (e.g. gather a missing detail before writing).

Principles:

- **The model plans; the system guides.** *When* to reflect is decided from runtime state (did the agent
  just do a `browser_dom` research step, is there remaining work) — not by scraping behaviors from your
  wording. *What* the new plan is comes from the model.
- **Guardrails:** at most `max_plan_reflections` (default 2) reflections per run; completed subgoals are
  preserved; if the model returns the current plan unchanged, nothing happens; offline / no model endpoint
  -> skipped (deterministic degradation); if the revised plan raises the risk level it triggers a stage
  review.
- **Trigger:** currently for `research_summary` (research -> produce a deliverable) tasks, once a research
  subgoal completes and remaining work exists.

Example: running "write a report about EVs", the model inserts "search EV charging-station coverage" after
the first research step, so execution becomes `research -> research (model-added) -> open Word -> write`.
Toggles: `plan_reflection_enabled` / `max_plan_reflections`.

Related configuration:

- `composition_enabled`: whether the synthesis step may call the model (off uses the deterministic outline only).
- `document_default_app`: default editor target when none is named (defaults to `word`).
- `max_document_length`: maximum characters written in a single authoring step.

## 5. Core Configuration

`desktop_agent/config.py` defines `AgentConfig`, which remains the single source of truth for runtime settings.

Common fields:

- `model_provider`
- `model_base_url`
- `model_name`
- `model_api_key`
- `model_auto_discover`
- `model_structured_output`
- `composition_enabled`
- `document_default_app`
- `max_document_length`
- `max_steps`
- `pause_after_action`
- `browser_dom_backend`
- `browser_dom_timeout`
- `browser_channel`
- `browser_executable_path`
- `browser_headless`

The only built-in DOM backend right now is `playwright`.

## 6. Dashboard API Surface

### 6.1 Meta and Runs

- `GET /api/meta`
  - returns UI metadata, defaults, browser channels, provider choices, and presets
- `GET /api/overview`
  - returns `meta + active_job + jobs + runs`
- `GET /api/runs/:id`
  - returns summary, timeline, and screenshots for one run

### 6.2 Provider Endpoints

- `POST /api/provider/models`
  - fetches the model catalog, loaded models, and provider errors
- `POST /api/provider/load-model`
  - currently supported only for `lmstudio_local`

### 6.3 Chat Endpoints

- `POST /api/chat`
- `POST /api/chat/stream`

Request fields:

- `messages`
- optional `config_overrides`
- optional `session_meta`

`session_meta.locale` is used to select:

- the help document injected into the system prompt
- the response language
- the language of handoff suggestions

### 6.4 Help Content

- `GET /api/help?locale=zh-CN|en-US&audience=user|developer`

This route serves:

- user help content by default
- developer-facing documentation when `audience=developer`
- the knowledge base injected into chat mode

Locale mapping:

- `zh-CN` -> `README.md`
- `en-US` -> `README.en.md`

## 7. Frontend State Model

Most frontend state lives in `desktop_agent/dashboard_assets/app.js`.

Important state slices:

- `uiMode`
  - `chat / agent / developer`
- local chat sessions
  - stored in browser local storage
- agent runs
  - fetched from `/api/overview` and `/api/runs/:id`
- help content
  - loaded on demand from `/api/help`
- settings
  - runtime overrides go to `config_overrides`
  - UI-only preferences stay local

The left history rail is a mixed history list:

- local chat sessions
- persisted agent runs

Both are sorted by most recent activity.

History restore rules:

- chat sessions and agent runs both remain available after restarting the app
- the frontend also persists the last selected history item and restores it first on startup
- if the saved selection is a chat session that no longer exists and the UI is in chat mode, the frontend falls back to the most recently updated non-empty chat session
- if the saved selection is a run that is no longer present in the current overview payload, the UI returns to the Agent welcome state instead of jumping to a different run

## 8. Help Center and Localization

The help center mirrors developer documentation rather than end-user onboarding copy.

Rules:

- Chinese UI loads Chinese developer docs
- English UI loads English developer docs
- chat mode uses the same locale-aware docs as product knowledge

That means changes to `README.md` or `README.en.md` directly affect:

- `/api/help`
- chat-mode product answers

## 9. Static Shell

Static frontend assets live in `desktop_agent/dashboard_assets/`.

Key files:

- `index.html`
- `styles.css`
- `app.js`

The dashboard still runs in a normal browser during source-mode development, but it is no longer installable as a browser app. Whenever the shell changes, bump the asset version to avoid stale caches.

## 10. Troubleshooting

### 10.1 The help center does not switch language

Check:

- whether `/api/help?locale=en-US` returns English markdown
- whether `loadHelpContent()` includes the current locale
- whether the previous help cache is cleared after switching UI language

### 10.2 LM Studio is running but no models appear

Check:

- `Base URL` is `http://127.0.0.1:1234/v1`
- opening settings triggers `POST /api/provider/models`
- `/v1/models` actually returns a model list
- `model_name` is not pinned to a stale value

### 10.3 The page still shows the old UI

Check shell caching first:

1. close the current dashboard tab
2. reopen the page
3. if the old shell still appears, use `Ctrl+F5`
4. verify that the asset query versions were updated together

## 11. Good Next Extensions

Useful future directions:

- finer-grained handoff classification in chat mode
- a section index and anchors for the help center
- incremental live timeline streaming
- a more explicit diagnostics surface in developer mode
- a cleaner asset pipeline for the desktop shell and favicon assets

## 12. Working Conventions

Recommended conventions for future work:

- treat the help center as developer documentation
- minimize static explanatory filler text
- do not let chat mode execute tasks automatically
- always bump shell cache versions after static UI changes
- add pytest coverage for new endpoints and run `node --check` for main frontend logic

## 13. Release Packages

The primary package for end users is:

- `Aoryn-Setup-<version>.exe`

Additional release artifacts are generated for archive and review workflows:

- `Aoryn-<version>-win64.zip`
  - zipped portable directory build
- `Aoryn-Review-<version>.zip`
  - review bundle that includes the installer, portable zip, source snapshot, release manifest, checksums, and both README files
- `Aoryn-Source-<version>.zip`
  - source snapshot without build outputs, runtime history, screenshots, logs, or caches
- `release-manifest.json`
- `SHA256SUMS.txt`

Use these packages intentionally:

- send `Setup.exe` to normal end users
- send `Review.zip` to reviewers, auditors, or model-based review workflows
- keep the portable zip for archive or manual inspection

The reviewable source snapshot is intentionally a code-and-assets snapshot, not a runtime archive:

- it keeps code, packaged frontend assets, installer scripts, and documentation
- it excludes `runs/`, historical screenshots, local logs, caches, and other machine-specific traces that could mislead reviewers

## 14. First-Launch Environment Check

The first-launch onboarding now includes a lightweight environment check.

It reports:

- browser execution readiness
- current provider selection
- current model selection
- provider connectivity and model catalog availability

Status values are:

- `Ready`
- `Needs setup`
- `Connection failed`

The check only gives repair guidance and quick links. It does not auto-install LM Studio, browsers, or other external dependencies.
