# Aoryn Developer Guide

## 1. Project Positioning

Aoryn is a local-first desktop agent workbench.

It combines three layers behind one web shell:

- Chat mode: normal conversation using the configured model, with no direct desktop execution
- Agent mode: task execution, run playback, screenshots, and result review
- Developer console: provider diagnostics, payload inspection, and low-level debugging

The current goal is not multi-agent orchestration. The product is focused on a reliable single-task desktop agent with good observability and a clean local web UI.

## 2. Local Startup

### 2.1 Requirements

- Python 3.11+
- Windows desktop environment
- An installed browser, with `msedge` as the default channel
- Optional: LM Studio or any OpenAI-compatible model endpoint

### 2.2 Run

```bash
python run_agent.py
```

This starts the local dashboard and attempts to open:

```text
http://127.0.0.1:8765
```

### 2.3 Build a Windows EXE

The desktop shell can also be packaged as a Windows app with PyInstaller:

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
release/Aoryn-0.1.4-win64/
release/Aoryn-Setup-0.1.4.exe
```

Patch `0.1.4` adds visible display-detection diagnostics plus manual runtime overrides for monitor, DPI scale, and work-area correction, while keeping automatic Windows detection as the default.

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

### 4.3 Developer Console

The developer console still exists, but it is no longer exposed as the main top-level mode.

Use it for:

- provider connectivity checks
- payload inspection
- timeline debugging
- regression analysis

The recommended entry point is the advanced area inside settings.

## 5. Core Configuration

`desktop_agent/config.py` defines `AgentConfig`, which remains the single source of truth for runtime settings.

Common fields:

- `model_provider`
- `model_base_url`
- `model_name`
- `model_api_key`
- `model_auto_discover`
- `model_structured_output`
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

- `GET /api/help?locale=zh-CN|en-US`

This route serves the developer documentation used by both:

- the in-app help center
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
