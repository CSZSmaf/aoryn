import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";


class StorageMock {
  constructor(seed = {}) {
    this.store = new Map(Object.entries(seed));
  }

  getItem(key) {
    return this.store.has(key) ? this.store.get(key) : null;
  }

  setItem(key, value) {
    this.store.set(String(key), String(value));
  }

  removeItem(key) {
    this.store.delete(String(key));
  }
}


class MockElement {
  constructor(id = "") {
    this.id = id;
    this.hidden = false;
    this.disabled = false;
    this.value = "";
    this.checked = false;
    this.innerHTML = "";
    this.textContent = "";
    this.dataset = {};
    this.style = {};
    this.scrollTop = 0;
    this.scrollHeight = 0;
    this.offsetParent = {};
    this.className = "";
    this.classList = {
      add() {},
      remove() {},
      toggle() {},
      contains() {
        return false;
      },
    };
  }

  addEventListener() {}

  removeEventListener() {}

  querySelectorAll() {
    return [];
  }

  querySelector() {
    return null;
  }

  setAttribute() {}

  removeAttribute() {}

  focus() {}

  blur() {}

  closest() {
    return null;
  }

  matches() {
    return false;
  }

  requestSubmit() {}

  setSelectionRange() {}
}


function snapshot(value) {
  return value == null ? value : JSON.parse(JSON.stringify(value));
}


function getLastCssBlock(source, selector, needle = null) {
  const normalizedSource = source.replace(/\r\n/g, "\n");
  const normalizedSelector = selector.replace(/\r\n/g, "\n");
  const escapedSelector = normalizedSelector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(`${escapedSelector}\\s*\\{([\\s\\S]*?)\\}`, "g");
  const matches = [...normalizedSource.matchAll(pattern)].map((match) => match[1]);

  const block =
    needle == null
      ? matches.at(-1)
      : matches.findLast((entry) =>
          needle instanceof RegExp ? needle.test(entry) : entry.includes(needle),
        );

  assert.ok(block, `Expected CSS block for ${selector}`);
  return block ?? "";
}


function buildOverviewPayload({
  activeJob = null,
  jobs = [],
  runs = [],
  chatLaunchId = "boot-1",
  defaults = {},
  runtimePreferences = {},
  modelProviders = [],
  autonomyModePresets = {},
  structuredOutputModes = [],
  browserDomBackends = [],
  browserChannels = [],
} = {}) {
  return {
    meta: {
      chat_launch_id: chatLaunchId,
      defaults,
      model_providers: modelProviders,
      autonomy_mode_presets: autonomyModePresets,
      structured_output_modes: structuredOutputModes,
      browser_dom_backends: browserDomBackends,
      browser_channels: browserChannels,
    },
    runtime_preferences: runtimePreferences,
    active_job: activeJob,
    jobs,
    runs,
  };
}


function createHarness({ localStorageSeed = {}, sessionStorageSeed = {}, overviewPayload } = {}) {
  const elements = new Map();
  const document = {
    documentElement: { lang: "zh-CN" },
    body: new MockElement("body"),
    activeElement: null,
    referrer: "",
    getElementById(id) {
      if (!elements.has(id)) {
        elements.set(id, new MockElement(id));
      }
      return elements.get(id);
    },
    querySelectorAll() {
      return [];
    },
    querySelector() {
      return null;
    },
    addEventListener() {},
  };

  const localStorage = new StorageMock(localStorageSeed);
  const sessionStorage = new StorageMock(sessionStorageSeed);
  const windowObject = {
    document,
    localStorage,
    sessionStorage,
    crypto: { randomUUID: () => "12345678-1234-1234-1234-123456789abc" },
    location: { hostname: "127.0.0.1" },
    isSecureContext: true,
    navigator: { serviceWorker: { register: () => Promise.resolve() } },
    matchMedia: () => ({ matches: false }),
    setInterval: () => 1,
    clearInterval() {},
    setTimeout: () => 1,
    clearTimeout() {},
    requestAnimationFrame(callback) {
      if (typeof callback === "function") {
        callback();
      }
      return 1;
    },
    addEventListener() {},
    removeEventListener() {},
  };

  const context = {
    console,
    window: windowObject,
    document,
    navigator: windowObject.navigator,
    localStorage,
    sessionStorage,
    HTMLElement: MockElement,
    Node: MockElement,
    TextDecoder,
    URL,
    URLSearchParams,
    fetch: async () => {
      throw new Error("Unexpected fetch call in history restore test.");
    },
    setTimeout: windowObject.setTimeout,
    clearTimeout: windowObject.clearTimeout,
    setInterval: windowObject.setInterval,
    clearInterval: windowObject.clearInterval,
    performance: { now: () => 0 },
  };
  context.globalThis = context;
  vm.createContext(context);

  const appPath = path.resolve(import.meta.dirname, "../app.js");
  const source = fs.readFileSync(appPath, "utf8");
  vm.runInContext(
    `${source}
globalThis.__appTest = {
  state,
  initializeState,
  initializeApp,
  renderAll,
  renderAboutPanel,
  renderCompletedConversation,
  renderDeveloper,
  renderHelpCenter,
  renderInspector,
  renderRunOverview,
  renderRunTimeline,
  renderRunGallery,
  renderTaskPreviewMessage,
  renderRunningMessage,
  renderAgentPlanHealth,
  buildRecordState,
  canResumeRun,
  needsHumanVerification,
  applyAutonomyModePreset,
  submitAgentTask,
  resumeRun,
  handleInteractiveClick,
  handleJobDecision,
  renderPendingMessage,
  renderUserMessage,
  renderNormalAssistantMessage,
  summarizeOverviewJob,
  summarizeOverviewPlanHealth,
  summarizeOverviewStepProposal,
  summarizeOverviewRun,
  normalizeRunExecutionStateCandidate,
  refreshOverview,
  buildConfigSignature,
  buildSidebarHistoryItems,
  handleRunLimitChange,
  scheduleRuntimePreferencesSync,
  syncChatLaunchState,
  syncAgentSessionsWithRuns,
  loadPersistedHistorySelection,
  formatTimestamp,
  originals: {
    hydrateDefaults,
    restoreOverviewSnapshot,
    renderAvailableModels,
    updateProviderActionButtons,
    updateProviderStatusHints,
    scheduleProviderInspection,
    buildConfigOverrides,
    buildRunConfigOverrides,
    fillSelect,
    renderAboutPanel,
    syncCustomSelect,
  },
};`,
    context,
    { filename: appPath }
  );

  context.__overviewPayload = overviewPayload || buildOverviewPayload();
  context.__displayDetectionPayload = {
    detected: { platform: "windows", monitors: [], current_monitor: null, virtual_bounds: { left: 0, top: 0, right: 0, bottom: 0 }, dpi_scale: 1 },
    effective: { platform: "windows", monitors: [], current_monitor: null, virtual_bounds: { left: 0, top: 0, right: 0, bottom: 0 }, dpi_scale: 1 },
    override: { status: "auto", enabled: false, editable: true, warnings: [], applied: [] },
    checked_at: 0,
  };
  context.__loadRunDetailsCalls = [];
  vm.runInContext(
    `
renderAll = () => {};
hydrateDefaults = () => {};
persistOverviewSnapshot = () => {};
maybeAutoOpenOnboarding = () => {};
scheduleEnvironmentCheck = () => {};
handleProviderChange = () => {};
updateProviderStatusHints = () => {};
updateProviderActionButtons = () => {};
fillLanguageOptions = () => {};
fillSendShortcutOptions = () => {};
fillSelect = () => {};
localizeBrowserChannels = (items) => items;
updateModelBaseUrlAutofillState = () => {};
fetchJson = async (url) => {
  if (url === "/api/overview") {
    return globalThis.__overviewPayload;
  }
  if (url === "/api/system/display-detection") {
    return globalThis.__displayDetectionPayload;
  }
  throw new Error("Unexpected fetchJson URL: " + url);
};
loadRunDetails = async (runId) => {
  globalThis.__loadRunDetailsCalls.push(runId);
  state.selectedRunDetails = { id: runId, task: runId };
  state.loadingRunDetails = false;
};
`,
    context
  );

  return context;
}


async function runTest(name, fn) {
  try {
    await fn();
    console.log(`PASS ${name}`);
  } catch (error) {
    console.error(`FAIL ${name}`);
    throw error;
  }
}

await runTest("restores a persisted chat history selection on startup", async () => {
  const chatSessions = [
    {
      id: "chat-older",
      title: "older",
      created_at: 100,
      updated_at: 120,
      messages: [{ id: "msg-1", role: "user", content: "older", created_at: 120 }],
    },
    {
      id: "chat-latest",
      title: "latest",
      created_at: 130,
      updated_at: 180,
      messages: [{ id: "msg-2", role: "user", content: "latest", created_at: 180 }],
    },
  ];
  const context = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.mode": "agent",
      "desktop-agent-workspace.chat-sessions": JSON.stringify(chatSessions),
      "desktop-agent-workspace.history-selection": JSON.stringify({ kind: "chat", id: "chat-latest" }),
    },
    overviewPayload: buildOverviewPayload({
      runs: [{ id: "run-1", task: "visit openai", created_at: 150, started_at: 150, finished_at: 160 }],
    }),
  });

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  assert.equal(context.__appTest.state.uiMode, "chat");
  assert.equal(context.__appTest.state.selectedChatSessionId, "chat-latest");
  assert.deepEqual(context.__loadRunDetailsCalls, []);
});


await runTest("restores a persisted run history selection and loads details", async () => {
  const context = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.mode": "chat",
      "desktop-agent-workspace.history-selection": JSON.stringify({ kind: "run", id: "run-2" }),
    },
    overviewPayload: buildOverviewPayload({
      runs: [
        { id: "run-1", task: "older run", created_at: 120, started_at: 120, finished_at: 130 },
        { id: "run-2", task: "latest run", created_at: 200, started_at: 200, finished_at: 210 },
      ],
    }),
  });

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  assert.equal(context.__appTest.state.uiMode, "agent");
  assert.equal(context.__appTest.state.selectedRunId, "run-2");
  assert.deepEqual(context.__loadRunDetailsCalls, ["run-2"]);
});

await runTest("restores a persisted pending agent session as queued work", async () => {
  const context = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.agent-sessions": JSON.stringify([
        {
          id: "agent-pending",
          title: "Open calculator",
          created_at: 100,
          updated_at: 120,
          run_ids: [],
          pending_task: "",
          pending_job_id: "job-pending",
        },
      ]),
      "desktop-agent-workspace.history-selection": JSON.stringify({ kind: "agent", id: "agent-pending" }),
    },
    overviewPayload: buildOverviewPayload({
      jobs: [
        {
          id: "job-pending",
          task: "Open calculator",
          status: "queued",
        },
      ],
    }),
  });

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  assert.equal(context.__appTest.state.uiMode, "agent");
  assert.equal(context.__appTest.state.selectedAgentSessionId, "agent-pending");
  assert.equal(context.__appTest.state.pendingTask, "Open calculator");
  assert.equal(context.__appTest.state.showWelcome, false);
  assert.deepEqual(snapshot(context.__appTest.buildSidebarHistoryItems().map((item) => item.id)), ["agent-pending"]);
  context.__appTest.state.hydrated = true;
  vm.runInContext("renderComposerState({ type: 'pending', task: state.pendingTask })", context);
  assert.equal(context.document.getElementById("taskInput").disabled, true);
  assert.equal(context.document.getElementById("submitButton").disabled, true);
  assert.equal(context.document.getElementById("previewTaskButton").disabled, true);
});

await runTest("restores pending agent task text from backend job payload", async () => {
  const context = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.agent-sessions": JSON.stringify([
        {
          id: "agent-backend-pending",
          title: "",
          created_at: 100,
          updated_at: 120,
          run_ids: [],
          pending_task: "",
          pending_job_id: "job-backend-pending",
        },
      ]),
      "desktop-agent-workspace.history-selection": JSON.stringify({ kind: "agent", id: "agent-backend-pending" }),
    },
    overviewPayload: buildOverviewPayload({
      jobs: [
        {
          id: "job-backend-pending",
          task: "Open calculator from backend",
          status: "queued",
        },
      ],
    }),
  });

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  assert.equal(context.__appTest.state.selectedAgentSessionId, "agent-backend-pending");
  assert.equal(context.__appTest.state.pendingTask, "Open calculator from backend");
  const sidebarItems = snapshot(context.__appTest.buildSidebarHistoryItems());
  assert.equal(sidebarItems[0].title, "Open calculator from backend");
});

await runTest("agent mode falls back to a pending session when history selection is missing", async () => {
  const context = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.mode": "agent",
      "desktop-agent-workspace.agent-sessions": JSON.stringify([
        {
          id: "agent-pending-fallback",
          title: "Submit the browser checkout",
          created_at: 100,
          updated_at: 180,
          run_ids: [],
          pending_task: "",
          pending_job_id: "job-checkout",
        },
      ]),
    },
    overviewPayload: buildOverviewPayload({
      jobs: [
        {
          id: "job-checkout",
          task: "Submit the browser checkout",
          status: "queued",
        },
      ],
    }),
  });

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  assert.equal(context.__appTest.state.uiMode, "agent");
  assert.equal(context.__appTest.state.selectedAgentSessionId, "agent-pending-fallback");
  assert.equal(context.__appTest.state.pendingTask, "Submit the browser checkout");
  assert.equal(context.__appTest.state.showWelcome, false);
  assert.deepEqual(snapshot(context.__appTest.loadPersistedHistorySelection()), {
    kind: "agent",
    id: "agent-pending-fallback",
  });
});

await runTest("composer disables controls from the selected pending session state", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.uiMode = "agent";
  context.__appTest.state.hydrated = true;
  context.__appTest.state.selectedAgentSessionId = "agent-pending-only";
  context.__appTest.state.agentSessions = [
    {
      id: "agent-pending-only",
      title: "Submit the browser checkout",
      created_at: 100,
      updated_at: 180,
      run_ids: [],
      pending_task: "",
      pending_job_id: "job-checkout",
    },
  ];
  context.__appTest.state.pendingTask = null;

  vm.runInContext("renderComposerState(getAgentConversationContext())", context);

  assert.equal(context.document.getElementById("taskInput").disabled, true);
  assert.equal(context.document.getElementById("submitButton").disabled, true);
  assert.equal(context.document.getElementById("previewTaskButton").disabled, true);
  assert.equal(context.document.getElementById("submitHint").textContent, "Queued");
});


await runTest("falls back cleanly when the persisted selection is invalid", async () => {
  const chatSessions = [
    {
      id: "chat-a",
      title: "older",
      created_at: 100,
      updated_at: 120,
      messages: [{ id: "msg-1", role: "user", content: "older", created_at: 120 }],
    },
    {
      id: "chat-b",
      title: "newer",
      created_at: 130,
      updated_at: 190,
      messages: [{ id: "msg-2", role: "user", content: "newer", created_at: 190 }],
    },
  ];

  const chatContext = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.mode": "chat",
      "desktop-agent-workspace.chat-sessions": JSON.stringify(chatSessions),
      "desktop-agent-workspace.history-selection": JSON.stringify({ kind: "chat", id: "missing-chat" }),
    },
  });
  chatContext.__appTest.initializeState();
  await chatContext.__appTest.refreshOverview({ initial: true });

  assert.equal(chatContext.__appTest.state.selectedChatSessionId, "chat-b");
  assert.deepEqual(snapshot(chatContext.__appTest.loadPersistedHistorySelection()), { kind: "chat", id: "chat-b" });

  const runContext = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.mode": "chat",
      "desktop-agent-workspace.history-selection": JSON.stringify({ kind: "run", id: "missing-run" }),
    },
  });
  runContext.__appTest.initializeState();
  await runContext.__appTest.refreshOverview({ initial: true });

  assert.equal(runContext.__appTest.state.uiMode, "agent");
  assert.equal(runContext.__appTest.state.showWelcome, true);
  assert.equal(runContext.__appTest.state.selectedRunId, null);
  assert.equal(snapshot(runContext.__appTest.loadPersistedHistorySelection()), null);
});


await runTest("chat launch changes stop pending replies without clearing saved history selection", async () => {
  const context = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.chat-sessions": JSON.stringify([
        {
          id: "chat-kept",
          title: "kept",
          created_at: 100,
          updated_at: 120,
          messages: [{ id: "msg-1", role: "user", content: "kept", created_at: 120 }],
        },
      ]),
      "desktop-agent-workspace.history-selection": JSON.stringify({ kind: "chat", id: "chat-kept" }),
    },
    sessionStorageSeed: {
      "desktop-agent-workspace.session-chat-launch-id": "boot-old",
      "desktop-agent-workspace.session-active-chat-session": "chat-kept",
    },
  });

  context.__appTest.initializeState();
  context.__appTest.state.selectedChatSessionId = "chat-kept";
  context.__appTest.syncChatLaunchState({ chat_launch_id: "boot-new" });

  assert.equal(context.__appTest.state.selectedChatSessionId, "chat-kept");
  assert.deepEqual(snapshot(context.__appTest.loadPersistedHistorySelection()), { kind: "chat", id: "chat-kept" });
});


await runTest("mixed history items keep stable sorting while active state follows the selected item", async () => {
  const context = createHarness();
  context.__appTest.state.chatSessions = [
    {
      id: "chat-1",
      title: "chat one",
      created_at: 100,
      updated_at: 400,
      messages: [{ id: "msg-1", role: "user", content: "chat one", created_at: 400 }],
    },
  ];
  context.__appTest.state.runs = [
    { id: "run-1", task: "visit openai", created_at: 100, started_at: 100, finished_at: 300 },
    { id: "run-2", task: "open calculator", created_at: 100, started_at: 100, finished_at: 200 },
  ];
  context.__appTest.state.agentSessions = [
    { id: "agent-1", title: "visit openai", created_at: 100, updated_at: 300, run_ids: ["run-1"] },
    { id: "agent-2", title: "open calculator", created_at: 100, updated_at: 200, run_ids: ["run-2"] },
  ];
  context.__appTest.state.agentRunSessionMap = { "run-1": "agent-1", "run-2": "agent-2" };

  context.__appTest.state.uiMode = "chat";
  context.__appTest.state.selectedChatSessionId = "chat-1";
  let items = context.__appTest.buildSidebarHistoryItems();
  assert.deepEqual(snapshot(items.map((item) => item.id)), ["chat-1", "agent-1", "agent-2"]);
  assert.equal(items[0].active, true);
  assert.equal(items[1].active, false);

  context.__appTest.state.uiMode = "agent";
  context.__appTest.state.showWelcome = false;
  context.__appTest.state.selectedAgentSessionId = "agent-1";
  items = context.__appTest.buildSidebarHistoryItems();
  assert.deepEqual(snapshot(items.map((item) => item.id)), ["chat-1", "agent-1", "agent-2"]);
  assert.equal(items[0].active, false);
  assert.equal(items[1].active, true);
});


await runTest("initial render clears skeleton placeholders before overview resolves", async () => {
  const context = createHarness();
  vm.runInContext(
    `
initializeEnhancedControls = () => {};
renderAll = globalThis.__appTest.renderAll;
fetchJson = async (url) => {
  if (url === "/api/overview") {
    return new Promise(() => {});
  }
  if (url === "/api/system/display-detection") {
    return globalThis.__displayDetectionPayload;
  }
  return null;
};
`,
    context
  );

  const initPromise = context.__appTest.initializeApp();
  assert.equal(typeof initPromise?.then, "function");

  const sidebarHtml = context.document.getElementById("sidebarRunList").innerHTML;
  assert.match(sidebarHtml, /empty-state/);
  assert.equal(sidebarHtml.includes("sidebar-skeleton"), false);

  const chatHtml = context.document.getElementById("chatStream").innerHTML;
  assert.equal(chatHtml.includes("chat-welcome"), false);
  assert.equal(chatHtml.includes("welcome-card"), false);
  assert.equal(context.document.getElementById("chatStream").dataset.context, "agent-welcome");
  assert.equal(context.document.getElementById("chatScroll").dataset.context, "agent-welcome");
});


await runTest("hydrates provider settings from runtime preferences before meta defaults", async () => {
  const context = createHarness();
  const overview = buildOverviewPayload({
    defaults: {
      model_provider: "lmstudio_local",
      model_base_url: "http://127.0.0.1:1234/v1",
      model_name: "auto",
      model_auto_discover: true,
      model_structured_output: "auto",
      browser_dom_backend: "playwright",
      browser_channel: "msedge",
      browser_headless: false,
      cursor_motion_enabled: true,
      cursor_motion_duration: 0.2,
      desktop_autonomy_mode: "conservative",
      complex_task_planning: "hybrid",
      plan_review_policy: "low_risk_auto",
      approval_policy: "tiered",
      stage_review_policy: "risk_change",
      max_task_subgoals: 12,
      max_subgoal_retries: 2,
      max_replans_per_run: 3,
      max_failures_per_subgoal: 3,
      replan_on_recoverable_error: true,
      recoverable_error_retry_limit: 2,
      task_workspace_enabled: true,
    },
    runtimePreferences: {
      config_overrides: {
        model_provider: "openai_compatible",
        model_base_url: "https://api.runtime.example/v1",
        model_name: "gpt-runtime",
        model_auto_discover: "false",
        model_structured_output: "json_object",
        max_steps: 11,
        max_run_seconds: 480,
        pause_after_action: 0.4,
        task_graph_request_timeout: 18.5,
        browser_dom_backend: "playwright",
        browser_channel: "chrome",
        browser_headless: "true",
        cursor_motion_enabled: "false",
        cursor_motion_duration: 0.35,
        desktop_autonomy_mode: "review_first",
        complex_task_planning: "model",
        plan_review_policy: "always",
        approval_policy: "autonomous",
        stage_review_policy: "always",
        max_task_subgoals: 8,
        max_subgoal_retries: 4,
        max_replans_per_run: 5,
        max_failures_per_subgoal: 6,
        replan_on_recoverable_error: "false",
        recoverable_error_retry_limit: 7,
        task_workspace_enabled: "false",
      },
      ui_preferences: {},
      updated_at: 123,
    },
    modelProviders: [
      { value: "lmstudio_local", label: "Local LM Studio", supports_model_refresh: true, supports_model_load: true, portal_url: "http://127.0.0.1:1234", docs_url: "" },
      { value: "openai_compatible", label: "OpenAI-Compatible API", supports_model_refresh: true, supports_model_load: false, portal_url: "", docs_url: "" },
    ],
    structuredOutputModes: [
      { value: "auto", label: "Auto" },
      { value: "json_object", label: "JSON Object" },
    ],
    browserDomBackends: [{ value: "playwright", label: "Playwright" }],
    browserChannels: [
      { value: "", label: "System default" },
      { value: "msedge", label: "Microsoft Edge" },
      { value: "chrome", label: "Google Chrome" },
    ],
  });
  vm.runInContext(
    `
fillSelect = globalThis.__appTest.originals.fillSelect;
hydrateDefaults = globalThis.__appTest.originals.hydrateDefaults;
updateProviderActionButtons = globalThis.__appTest.originals.updateProviderActionButtons;
renderAvailableModels = globalThis.__appTest.originals.renderAvailableModels;
`,
    context
  );

  context.__appTest.state.locale = "en-US";
  context.__appTest.state.meta = snapshot(overview.meta);
  context.__appTest.state.runtimePreferences = snapshot(overview.runtime_preferences);
  context.__appTest.state.hydrated = false;

  context.__appTest.originals.hydrateDefaults();

  assert.equal(context.document.getElementById("modelProvider").value, "openai_compatible");
  assert.equal(context.document.getElementById("modelBaseUrl").value, "https://api.runtime.example/v1");
  assert.equal(context.document.getElementById("modelName").value, "gpt-runtime");
  assert.equal(context.document.getElementById("modelAutoDiscover").checked, false);
  assert.equal(context.document.getElementById("structuredOutput").value, "json_object");
  assert.equal(context.document.getElementById("maxStepsInput").value, 11);
  assert.equal(context.document.getElementById("maxRunSecondsInput").value, 480);
  assert.equal(context.document.getElementById("pauseInput").value, 0.4);
  assert.equal(context.document.getElementById("taskGraphRequestTimeoutInput").value, 18.5);
  assert.equal(context.document.getElementById("browserChannel").value, "chrome");
  assert.equal(context.document.getElementById("browserHeadless").checked, true);
  assert.equal(context.document.getElementById("cursorMotionEnabled").checked, false);
  assert.equal(context.document.getElementById("cursorMotionDuration").value, 0.35);
  assert.equal(context.document.getElementById("autonomyModeSelect").value, "review_first");
  assert.equal(context.document.getElementById("planningModeSelect").value, "model");
  assert.equal(context.document.getElementById("planReviewPolicySelect").value, "always");
  assert.equal(context.document.getElementById("approvalPolicySelect").value, "autonomous");
  assert.equal(context.document.getElementById("stageReviewPolicySelect").value, "always");
  assert.equal(context.document.getElementById("maxTaskSubgoalsInput").value, 8);
  assert.equal(context.document.getElementById("maxSubgoalRetriesInput").value, 4);
  assert.equal(context.document.getElementById("maxReplansInput").value, 5);
  assert.equal(context.document.getElementById("maxFailuresInput").value, 6);
  assert.equal(context.document.getElementById("recoverableRetryLimitInput").value, 7);
  assert.equal(context.document.getElementById("replanOnRecoverableError").checked, false);
  assert.equal(context.document.getElementById("taskWorkspaceEnabled").checked, false);

  const overrides = snapshot(context.__appTest.originals.buildConfigOverrides());
  assert.equal(overrides.model_provider, "openai_compatible");
  assert.equal(overrides.model_base_url, "https://api.runtime.example/v1");
  assert.equal(overrides.model_name, "gpt-runtime");
  assert.equal(overrides.max_steps, 11);
  assert.equal(overrides.max_run_seconds, 480);
  assert.equal(overrides.pause_after_action, 0.4);
  assert.equal(overrides.task_graph_request_timeout, 18.5);
  assert.equal(overrides.cursor_motion_enabled, false);
  assert.equal(overrides.cursor_motion_duration, 0.35);
  assert.equal(overrides.desktop_autonomy_mode, "review_first");
  assert.equal(overrides.complex_task_planning, "model");
  assert.equal(overrides.plan_review_policy, "always");
  assert.equal(overrides.approval_policy, "autonomous");
  assert.equal(overrides.stage_review_policy, "always");
  assert.equal(overrides.max_task_subgoals, 8);
  assert.equal(overrides.max_subgoal_retries, 4);
  assert.equal(overrides.max_replans_per_run, 5);
  assert.equal(overrides.max_failures_per_subgoal, 6);
  assert.equal(overrides.replan_on_recoverable_error, false);
  assert.equal(overrides.recoverable_error_retry_limit, 7);
  assert.equal(overrides.task_workspace_enabled, false);
});

await runTest("autonomy mode preset updates planning and recovery controls", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.document.getElementById("autonomyModeSelect").value = "autonomous";

  context.__appTest.applyAutonomyModePreset("autonomous");

  assert.equal(context.document.getElementById("autonomyModeSelect").value, "autonomous");
  assert.equal(context.document.getElementById("planReviewPolicySelect").value, "never");
  assert.equal(context.document.getElementById("approvalPolicySelect").value, "autonomous");
  assert.equal(context.document.getElementById("stageReviewPolicySelect").value, "never");
  assert.equal(context.document.getElementById("replanOnRecoverableError").checked, true);
  assert.equal(context.document.getElementById("recoverableRetryLimitInput").value, 4);
  assert.equal(context.document.getElementById("maxReplansInput").value, 5);
  assert.equal(context.document.getElementById("maxFailuresInput").value, 5);

  const overrides = snapshot(context.__appTest.originals.buildConfigOverrides());
  assert.equal(overrides.desktop_autonomy_mode, "autonomous");
  assert.equal(overrides.plan_review_policy, "never");
  assert.equal(overrides.approval_policy, "autonomous");
  assert.equal(overrides.stage_review_policy, "never");
  assert.equal(overrides.recoverable_error_retry_limit, 4);
});

await runTest("autonomy mode preset prefers backend meta contract", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.meta = {
    autonomy_mode_presets: {
      autonomous: {
        plan_review_policy: "low_risk_auto",
        approval_policy: "tiered",
        stage_review_policy: "risk_change",
        replan_on_recoverable_error: false,
        recoverable_error_retry_limit: 8,
        max_replans_per_run: 6,
        max_failures_per_subgoal: 7,
      },
    },
  };

  context.__appTest.applyAutonomyModePreset("autonomous");

  assert.equal(context.document.getElementById("autonomyModeSelect").value, "autonomous");
  assert.equal(context.document.getElementById("planReviewPolicySelect").value, "low_risk_auto");
  assert.equal(context.document.getElementById("approvalPolicySelect").value, "tiered");
  assert.equal(context.document.getElementById("stageReviewPolicySelect").value, "risk_change");
  assert.equal(context.document.getElementById("replanOnRecoverableError").checked, false);
  assert.equal(context.document.getElementById("recoverableRetryLimitInput").value, 8);
  assert.equal(context.document.getElementById("maxReplansInput").value, 6);
  assert.equal(context.document.getElementById("maxFailuresInput").value, 7);
});


await runTest("cached overview restore also restores runtime provider preferences", async () => {
  const overview = buildOverviewPayload({
    defaults: {
      model_provider: "lmstudio_local",
      model_base_url: "http://127.0.0.1:1234/v1",
      model_name: "auto",
      model_auto_discover: true,
      browser_dom_backend: "playwright",
      browser_channel: "msedge",
    },
    runtimePreferences: {
      config_overrides: {
        model_provider: "openai_compatible",
        model_base_url: "https://cached.example/v1",
        model_name: "cached-model",
        model_auto_discover: false,
      },
      ui_preferences: { onboarding_completed: true },
      updated_at: 456,
    },
    modelProviders: [
      { value: "lmstudio_local", label: "Local LM Studio", supports_model_refresh: true, supports_model_load: true, portal_url: "http://127.0.0.1:1234", docs_url: "" },
      { value: "openai_compatible", label: "OpenAI-Compatible API", supports_model_refresh: true, supports_model_load: false, portal_url: "", docs_url: "" },
    ],
  });
  const context = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.overview-cache": JSON.stringify(overview),
    },
  });
  vm.runInContext(
    `
fillSelect = globalThis.__appTest.originals.fillSelect;
hydrateDefaults = globalThis.__appTest.originals.hydrateDefaults;
updateProviderActionButtons = globalThis.__appTest.originals.updateProviderActionButtons;
renderAvailableModels = globalThis.__appTest.originals.renderAvailableModels;
`,
    context
  );

  context.__appTest.state.locale = "en-US";
  const restored = context.__appTest.originals.restoreOverviewSnapshot();

  assert.equal(restored, true);
  assert.equal(context.__appTest.state.runtimePreferences.config_overrides.model_provider, "openai_compatible");
  assert.equal(context.document.getElementById("modelProvider").value, "openai_compatible");
  assert.equal(context.document.getElementById("modelBaseUrl").value, "https://cached.example/v1");
  assert.equal(context.document.getElementById("modelName").value, "cached-model");
});


await runTest("onboarding preference parses string booleans", async () => {
  const context = createHarness();
  context.__appTest.state.runtimePreferences = { ui_preferences: { onboarding_completed: "false" } };

  assert.equal(vm.runInContext("isOnboardingComplete()", context), false);

  context.__appTest.state.runtimePreferences = { ui_preferences: { onboarding_completed: "true" } };

  assert.equal(vm.runInContext("isOnboardingComplete()", context), true);
});


await runTest("provider actions stay disabled and skip inspection before config hydration", async () => {
  const context = createHarness();
  vm.runInContext(
    `
renderAvailableModels = globalThis.__appTest.originals.renderAvailableModels;
updateProviderActionButtons = globalThis.__appTest.originals.updateProviderActionButtons;
scheduleProviderInspection = globalThis.__appTest.originals.scheduleProviderInspection;
globalThis.__providerPostCount = 0;
postJson = async () => {
  globalThis.__providerPostCount += 1;
  return { ok: true, payload: {} };
};
`,
    context
  );

  context.__appTest.state.locale = "en-US";
  context.__appTest.state.meta = snapshot(
    buildOverviewPayload({
      modelProviders: [
        {
          value: "lmstudio_local",
          label: "Local LM Studio",
          supports_model_refresh: true,
          supports_model_load: true,
          portal_url: "http://127.0.0.1:1234",
          docs_url: "https://example.com/docs",
        },
      ],
    }).meta
  );
  context.__appTest.state.hydrated = false;
  context.document.getElementById("modelProvider").value = "lmstudio_local";

  context.__appTest.originals.scheduleProviderInspection({ immediate: true, force: true, message: "Loading provider" });

  assert.equal(context.__providerPostCount, 0);
  assert.match(context.document.getElementById("availableModels").innerHTML, /Loading configuration/);
  assert.equal(context.document.getElementById("testProviderButton").disabled, true);
  assert.equal(context.document.getElementById("refreshModelsButton").disabled, true);
  assert.equal(context.document.getElementById("refreshCatalogButton").disabled, true);
  assert.equal(context.document.getElementById("openProviderPortalButton").disabled, true);
});


await runTest("provider error placeholder shows the real error instead of a fake empty state", async () => {
  const context = createHarness();
  vm.runInContext(
    `
renderAvailableModels = globalThis.__appTest.originals.renderAvailableModels;
updateProviderActionButtons = globalThis.__appTest.originals.updateProviderActionButtons;
`,
    context
  );

  context.__appTest.state.locale = "en-US";
  context.__appTest.state.hydrated = true;
  context.__appTest.state.meta = snapshot(
    buildOverviewPayload({
      modelProviders: [
        {
          value: "lmstudio_local",
          label: "Local LM Studio",
          supports_model_refresh: true,
          supports_model_load: true,
          portal_url: "",
          docs_url: "",
        },
      ],
      defaults: { model_provider: "lmstudio_local" },
    }).meta
  );
  context.document.getElementById("modelProvider").value = "lmstudio_local";

  context.__appTest.originals.renderAvailableModels({
    ok: false,
    provider: "lmstudio_local",
    error: "Provider inspection failed hard.",
    catalog_models: [],
    loaded_models: [],
  });

  const html = context.document.getElementById("availableModels").innerHTML;
  assert.match(html, /Provider inspection failed hard\./);
  assert.equal(html.includes("No models available"), false);
  assert.equal(context.document.getElementById("availableModels").disabled, true);
});


await runTest("about panel renders recent runs without throwing when timestamps are present", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.meta = snapshot(
    buildOverviewPayload({
      defaults: { model_provider: "lmstudio_local" },
    }).meta
  );
  context.__appTest.state.runs = [
    {
      id: "run-1",
      task: "visit openai",
      created_at: 1711000000,
      started_at: 1711000000,
      finished_at: 1711000060,
      completed: true,
      cancelled: false,
      requires_human: false,
      error: null,
      cancel_reason: null,
      interruption_reason: null,
    },
  ];

  assert.equal(typeof context.__appTest.formatTimestamp, "function");
  context.__appTest.renderAboutPanel();

  const aboutHtml = context.document.getElementById("aboutContent").innerHTML;
  assert.match(aboutHtml, /about-grid/);
  assert.match(aboutHtml, /visit openai/);
  assert.equal(aboutHtml.includes("formatTimestamp"), false);
});


await runTest("completed run renders as one unified result block", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";

  const messages = context.__appTest.renderCompletedConversation({
    id: "run-hero",
    task: "Open the pricing page and summarize the tiers",
    started_at: 1711000000,
    finished_at: 1711000125,
    steps: 4,
    completed: true,
    cancelled: false,
    requires_human: false,
    error: null,
    cancel_reason: null,
    interruption_reason: null,
    dry_run: false,
    max_steps: 8,
    max_run_seconds: 120,
    pause_after_action: 0.25,
    desktop_autonomy_mode: "autonomous",
    complex_task_planning: "model",
    approval_policy: "autonomous",
    plan_review_policy: "never",
    stage_review_policy: "risk_change",
    max_task_subgoals: 6,
    max_subgoal_retries: 2,
    max_replans_per_run: 3,
    max_failures_per_subgoal: 4,
    replan_on_recoverable_error: true,
    recoverable_error_retry_limit: 4,
    browser_control_mode: "hybrid",
    browser_dom_backend: "playwright",
    browser_dom_timeout: 4,
    browser_headless: true,
    browser_channel: "chrome",
    cursor_motion_enabled: true,
    cursor_motion_duration: 0.35,
    display_override_enabled: true,
    display_override_monitor_device_name: "DISPLAY2",
    generic_app_launch_enabled: false,
    shell_recipe_policy: "approval_required",
    execution_state: {
      plan_health: {
        counts: { total: 2, completed: 1, blocked: 0, ready: 1 },
        next_subgoal_id: "subgoal_02",
        items: [
          { id: "subgoal_01", title: "Open the homepage", status: "completed", capability_preference: "browser_dom" },
          { id: "subgoal_02", title: "Open pricing", status: "pending", capability_preference: "browser_dom", is_next: true },
        ],
      },
      workspace_summary: {
        facts: [{ key: "note-status", value: "Local note context collected." }],
        sources: [{ title: "Local note draft", url: "file:///notes.md" }],
      },
    },
    timeline: [
      {
        step: 1,
        task: "Open the website",
        captured_at: 1711000005,
        screenshot: "shot-1.png",
        executed_actions: [{ type: "launch_browser" }],
        plan: { status_summary: "Opened the website" },
      },
      {
        step: 2,
        task: "Navigate to pricing",
        captured_at: 1711000060,
        screenshot: "shot-2.png",
        executed_actions: [{ type: "click", text: "Pricing" }],
        plan: { status_summary: "Reached the pricing page" },
      },
      {
        step: 3,
        task: "Inspect the pricing tiers",
        captured_at: 1711000105,
        screenshot: "shot-3.png",
        executed_actions: [{ type: "scroll" }],
        plan: { status_summary: "Reviewed the available tiers" },
      },
    ],
  });

  assert.equal(messages.length, 1);
  assert.match(messages[0], /assistant-card--run/);
  assert.match(messages[0], /assistant-run__hero/);
  assert.match(messages[0], /assistant-run__section--timeline/);
  assert.match(messages[0], /assistant-run__followups/);
  assert.match(messages[0], /Max steps: 8/);
  assert.match(messages[0], /Run limit: 2m/);
  assert.match(messages[0], /Action pause: 0\.25s/);
  assert.match(messages[0], /Autonomy: Autonomous/);
  assert.match(messages[0], /Planning: Model/);
  assert.match(messages[0], /Approval: High autonomy/);
  assert.match(messages[0], /Plan review: No review/);
  assert.match(messages[0], /Stage review: Risk change/);
  assert.match(messages[0], /Subgoals: 6/);
  assert.match(messages[0], /Retries: 2/);
  assert.match(messages[0], /Replans: 3/);
  assert.match(messages[0], /Failures: 4/);
  assert.match(messages[0], /Recovery: on x4/);
  assert.match(messages[0], /Browser: hybrid \/ playwright/);
  assert.match(messages[0], /DOM timeout: 4s/);
  assert.match(messages[0], /Launch: chrome headless/);
  assert.match(messages[0], /Pointer: on 0\.35s/);
  assert.match(messages[0], /Display: DISPLAY2/);
  assert.match(messages[0], /Known apps only/);
  assert.match(messages[0], /Shell: Approval required/);
});


await runTest("completed run prefers display state plan health over full execution payload", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  const details = {
    id: "run-display-state",
    task: "Continue the saved local plan",
    started_at: 1711000000,
    finished_at: 1711000125,
    steps: 2,
    completed: true,
    cancelled: false,
    requires_human: false,
    error: null,
    dry_run: false,
    state: {
      current_goal: "Continue local notes",
      active_specialist: "desktop_operator",
      current_surface_kind: "managed_aoryn_browser",
      last_progress_at: 1711000100,
      app_context: {
        human_handoff_kind: "login",
        human_handoff_reason: "Complete the login prompt.",
        manual_resume_status: "resumed",
        manual_resume_reason: "Login completed by user.",
        standard_recovery_kind: "requires_user",
      },
      repair_history: [
        {
          mode: "repair",
          subgoal_id: "subgoal_02",
          failure_kind: "stale_target",
          capability: "desktop_gui",
          message: "Window target became stale.",
          step: 2,
        },
      ],
      capability_failures: { "subgoal_02:desktop_gui": ["stale_target"] },
      last_verification: {
        status: "partial_progress",
        failure_kind: "needs_more_evidence",
        message: "The note editor was focused but final text evidence is missing.",
      },
      evidence_ledger: [
        {
          subgoal_id: "subgoal_02",
          capability: "browser_dom",
          status: "partial_progress",
          kind: "selector",
          selector: "#continue-note",
        },
      ],
      workspace_summary: {
        facts: [{ key: "note-status", value: "Local note context collected." }],
        sources: [{ title: "Local note draft", url: "file:///notes.md" }],
      },
      plan_health: {
        counts: { total: 2, completed: 1, blocked: 0, ready: 1 },
        next_subgoal_id: "subgoal_02",
        autonomy: {
          status: "ready",
          can_continue: true,
          next_action: "execute",
        },
        items: [
          { id: "subgoal_01", title: "Read current note", status: "completed", capability_preference: "desktop_gui" },
          { id: "subgoal_02", title: "Continue local notes", status: "pending", capability_preference: "desktop_gui", ready: true, is_next: true },
        ],
      },
    },
    execution_state: {
      orchestration_phase: "stage_ready",
      last_step: {
        capability: "browser_dom",
        intent: "Use DOM automation to continue the saved local note plan.",
        risk_level: "medium",
        surface_kind: "managed_aoryn_browser",
        progress_signals: ["The note editor is focused."],
        actions: [{ type: "click", selector: "#continue-note", button: "left" }],
      },
      task_graph: {
        subgoals: [
          { id: "subgoal_full", title: "Full payload fallback only", status: "pending", capability_preference: "browser_dom" },
        ],
      },
    },
    timeline: [],
  };

  const messages = context.__appTest.renderCompletedConversation(details);

  assert.equal(messages.length, 1);
  assert.match(messages[0], /Continue local notes/);
  assert.match(messages[0], /Autonomy/);
  assert.match(messages[0], /Ready to continue/);
  assert.match(messages[0], /Execution context/);
  assert.match(messages[0], /Local note context collected/);
  assert.match(messages[0], /Managed browser/);
  assert.match(messages[0], /desktop_operator/);
  assert.match(messages[0], /Next step/);
  assert.match(messages[0], /Use DOM automation to continue the saved local note plan/);
  assert.match(messages[0], /selector=#continue-note/);
  assert.match(messages[0], /Recovery trace/);
  assert.match(messages[0], /stale_target/);
  assert.match(messages[0], /Handoff: login/);
  assert.match(messages[0], /Resume: resumed/);
  assert.match(messages[0], /Login completed by user/);
  assert.match(messages[0], /Verification: partial_progress/);
  assert.match(messages[0], /Failure: needs_more_evidence/);
  assert.match(messages[0], /Evidence: selector/);
  assert.doesNotMatch(messages[0], /Full payload fallback only/);

  context.__appTest.state.selectedRunDetails = snapshot(details);
  context.__appTest.state.detailView = "overview";
  context.__appTest.renderInspector();
  const inspectorHtml = context.document.getElementById("runDetail").innerHTML;
  assert.match(inspectorHtml, /inspector-section-card--plan/);
  assert.match(inspectorHtml, /inspector-section-card--workspace/);
  assert.match(inspectorHtml, /inspector-section-card--step/);
  assert.match(inspectorHtml, /inspector-section-card--recovery/);
  assert.match(inspectorHtml, /Continue local notes/);
  assert.match(inspectorHtml, /Use DOM automation to continue the saved local note plan/);
  assert.match(inspectorHtml, /Local note draft/);
  assert.match(inspectorHtml, /Managed browser/);
  assert.match(inspectorHtml, /Window target became stale/);
  assert.match(inspectorHtml, /Handoff: login/);
  assert.match(inspectorHtml, /Resume: resumed/);
  assert.match(inspectorHtml, /Verification: partial_progress/);
  assert.doesNotMatch(inspectorHtml, /Full payload fallback only/);
});


await runTest("agent history replay renders plan health from overview state summary", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  const summaryRun = {
    id: "run-summary-state",
    task: "Continue the saved local plan",
    started_at: 1711000000,
    finished_at: 1711000125,
    steps: 2,
    completed: false,
    cancelled: false,
    requires_human: false,
    can_resume: true,
    resume_mode: "execution_state",
    error: "The route stalled before completion.",
    dry_run: false,
    current_goal: "Continue local notes",
    recovery_reason: "Recover blocked page",
    state: {
      current_goal: "Continue local notes",
      recovery_reason: "Recover blocked page",
      active_specialist: "desktop_operator",
      current_surface_kind: "managed_aoryn_browser",
      last_progress_at: 1711000110,
      repair_history: [{ mode: "repair", subgoal_id: "subgoal_02", failure_kind: "stale_target", step: 2 }],
      capability_failures: { "subgoal_02:desktop_gui": ["stale_target"] },
      workspace_summary: {
        facts: [{ key: "resume-context", value: "Saved workspace context is available." }],
      },
      plan_health: {
        counts: { total: 2, completed: 1, blocked: 0, ready: 1 },
        next_subgoal_id: "subgoal_02",
        autonomy: {
          status: "recovering",
          can_continue: true,
          next_action: "repair",
        },
        items: [
          { id: "subgoal_01", title: "Recover blocked page", status: "completed", capability_preference: "desktop_gui" },
          { id: "subgoal_02", title: "Continue local notes", status: "pending", capability_preference: "desktop_gui", ready: true, is_next: true },
        ],
      },
    },
    timeline: [],
  };

  context.__appTest.state.uiMode = "agent";
  context.__appTest.state.showWelcome = false;
  context.__appTest.state.selectedRunId = summaryRun.id;
  context.__appTest.state.loadingRunDetails = true;
  context.__appTest.state.selectedRunDetails = null;
  context.__appTest.state.runs = [summaryRun];
  context.__appTest.state.agentSessions = [
    { id: "agent-summary", title: summaryRun.task, created_at: 1711000000, updated_at: 1711000125, run_ids: [summaryRun.id] },
  ];
  context.__appTest.state.agentRunSessionMap = { [summaryRun.id]: "agent-summary" };
  context.__appTest.state.selectedAgentSessionId = "agent-summary";

  context.__appTest.renderAll();

  const chatHtml = context.document.getElementById("chatStream").innerHTML;
  assert.match(chatHtml, /assistant-run__section--plan/);
  assert.match(chatHtml, /data-next-subgoal="subgoal_02"/);
  assert.match(chatHtml, /Continue local notes/);
  assert.match(chatHtml, /Recover blocked page/);
  assert.match(chatHtml, /Saved workspace context is available/);
  assert.match(chatHtml, /Managed browser/);
  assert.match(chatHtml, /Recovery trace/);
  assert.match(chatHtml, /Resume repair/);
  assert.match(chatHtml, /queued repair path/);
  assert.match(chatHtml, /data-resume-run-id="run-summary-state"/);
});

await runTest("resumable follow-up reflects autonomy replan action", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  const messages = context.__appTest.renderCompletedConversation({
    id: "run-replan-action",
    task: "Recover stalled browser flow",
    started_at: 1711000000,
    finished_at: 1711000125,
    steps: 3,
    completed: false,
    cancelled: false,
    requires_human: false,
    can_resume: true,
    resume_mode: "execution_state",
    dry_run: false,
    state: {
      plan_health: {
        autonomy: {
          status: "blocked",
          can_continue: false,
          next_action: "recover_or_replan",
          blockers: ["No continuable subgoal is ready."],
        },
      },
    },
    timeline: [],
  });

  assert.equal(messages.length, 1);
  assert.match(messages[0], /Resume replan/);
  assert.match(messages[0], /recover or replan the next stage/);
  assert.match(messages[0], /data-resume-run-id="run-replan-action"/);
});

await runTest("resumable follow-up reflects autonomy review and inspection actions", async () => {
  const cases = [
    { action: "approve_plan", label: /Resume plan review/, copy: /pending plan review/ },
    { action: "approve_stage", label: /Resume stage review/, copy: /review the replanned stage/ },
    { action: "approve_step", label: /Resume approval/, copy: /pending action approval/ },
    { action: "ask_user", label: /Resume clarification/, copy: /answer the clarification/ },
    { action: "inspect_failure", label: /Resume inspection/, copy: /inspect the failure/ },
  ];

  for (const item of cases) {
    const context = createHarness();
    context.__appTest.state.locale = "en-US";
    const messages = context.__appTest.renderCompletedConversation({
      id: `run-${item.action}`,
      task: `Resume ${item.action}`,
      started_at: 1711000000,
      finished_at: 1711000125,
      steps: 3,
      completed: false,
      cancelled: false,
      requires_human: false,
      can_resume: true,
      resume_mode: "execution_state",
      dry_run: false,
      state: {
        plan_health: {
          autonomy: {
            status: item.action === "inspect_failure" ? "blocked" : "review_required",
            can_continue: false,
            next_action: item.action,
            blockers: ["Saved state needs a checkpoint action."],
          },
        },
      },
      timeline: [],
    });

    assert.equal(messages.length, 1, item.action);
    assert.match(messages[0], item.label, item.action);
    assert.match(messages[0], item.copy, item.action);
    assert.match(messages[0], new RegExp(`data-resume-run-id="run-${item.action}"`), item.action);
  }
});


await runTest("completed run can render a plan from full execution task graph fallback", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";

  const messages = context.__appTest.renderCompletedConversation({
    id: "run-full-state",
    task: "Continue from a full execution state",
    started_at: 1711000000,
    finished_at: 1711000125,
    steps: 2,
    completed: true,
    cancelled: false,
    requires_human: false,
    error: null,
    dry_run: false,
    execution_state: {
      task: "Continue from a full execution state",
      orchestration_phase: "stage_ready",
      app_context: { active_subgoal_id: "subgoal_02" },
      task_graph: {
        task: "Continue from a full execution state",
        subgoals: [
          { id: "subgoal_01", title: "Review current page", status: "completed", capability_preference: "browser_dom" },
          { id: "subgoal_02", title: "Continue from graph", status: "pending", capability_preference: "desktop_gui" },
        ],
      },
    },
    timeline: [],
  });

  assert.equal(messages.length, 1);
  assert.match(messages[0], /assistant-run__section--plan/);
  assert.match(messages[0], /data-next-subgoal="subgoal_02"/);
  assert.match(messages[0], /Continue from graph/);
});


await runTest("completed run collapses repeated steps and keeps one follow-up action", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";

  const messages = context.__appTest.renderCompletedConversation({
    id: "run-dedupe",
    task: "Search the web for openai",
    started_at: 1711000000,
    finished_at: 1711000125,
    steps: 5,
    completed: true,
    cancelled: false,
    requires_human: false,
    error: null,
    cancel_reason: null,
    interruption_reason: null,
    dry_run: false,
    execution_state: {
      last_step: {
        capability: "browser_dom",
        intent: "Open the pricing page from the current navigation.",
        risk_level: "low",
        surface_kind: "managed_aoryn_browser",
        actions: [{ type: "click", text: "Pricing" }],
      },
      plan_health: {
        counts: { total: 2, completed: 1, blocked: 0, ready: 1 },
        next_subgoal_id: "subgoal_02",
        items: [
          { id: "subgoal_01", title: "Open the homepage", status: "completed", capability_preference: "browser_dom" },
          { id: "subgoal_02", title: "Open pricing", status: "pending", capability_preference: "browser_dom", is_next: true },
        ],
      },
    },
    timeline: [
      {
        step: 1,
        task: "Search the web for openai",
        captured_at: 1711000005,
        screenshot: "shot-1.png",
        executed_actions: [{ type: "browser_search", text: "openai" }],
        plan: { status_summary: "Search the web for openai." },
      },
      {
        step: 2,
        task: "Search the web for openai",
        captured_at: 1711000020,
        screenshot: "shot-2.png",
        executed_actions: [{ type: "browser_search", text: "openai" }],
        plan: { status_summary: "Search the web for openai." },
      },
      {
        step: 3,
        task: "Search the web for openai",
        captured_at: 1711000040,
        screenshot: "shot-3.png",
        executed_actions: [{ type: "browser_search", text: "openai" }],
        plan: { status_summary: "Search the web for openai." },
      },
      {
        step: 4,
        task: "Search the web for openai",
        captured_at: 1711000060,
        screenshot: "shot-4.png",
        executed_actions: [{ type: "browser_search", text: "openai" }],
        plan: { status_summary: "Search the web for openai." },
      },
      {
        step: 5,
        task: "Open the first result",
        captured_at: 1711000105,
        screenshot: "shot-5.png",
        executed_actions: [{ type: "click", text: "OpenAI" }],
        plan: { status_summary: "Open the first result." },
      },
    ],
  });

  assert.equal(messages.length, 1);
  assert.equal((messages[0].match(/assistant-run__step-item/g) || []).length, 2);
  assert.equal((messages[0].match(/assistant-run__followup-card/g) || []).length, 1);
  assert.equal((messages[0].match(/data-prefill-task=/g) || []).length, 1);
  assert.match(messages[0], /Continue task/);
});


await runTest("interrupted run follow-up resumes the saved execution state", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.hydrated = true;
  const details = {
    id: "run-human",
    task: "Finish the blocked browser checkout",
    started_at: 1711000000,
    finished_at: null,
    steps: 3,
    completed: false,
    cancelled: false,
    requires_human: true,
    can_resume: true,
    resume_mode: "manual",
    interruption_kind: "login",
    interruption_reason: "A login prompt needs user input.",
    dry_run: false,
    timeline: [],
  };

  const messages = context.__appTest.renderCompletedConversation(details);

  assert.equal(messages.length, 1);
  assert.match(messages[0], /data-resume-run-id="run-human"/);
  assert.doesNotMatch(messages[0], /data-prefill-task=/);
  assert.match(messages[0], /Resume run/);
  assert.match(messages[0], /human checkpoint/);

  context.__appTest.state.selectedRunDetails = snapshot(details);
  context.__appTest.state.selectedRunId = "run-human";
  context.__appTest.state.runs = [snapshot(details)];
  context.__appTest.state.taskPreviewTask = "Open calculator";
  context.__appTest.state.taskPreviewConfigSignature = "stale-preview-signature";
  context.__appTest.state.taskPreviewError = "Refresh the plan preview before starting.";
  context.__appTest.state.taskPreviewStartError = "The preview is not ready to start.";
  context.__appTest.state.taskPreview = {
    task: "Open calculator",
    task_graph_signature: "stale-preview-signature",
    task_graph: {
      task: "Open calculator",
      subgoals: [{ id: "subgoal_01", title: "Open calculator", status: "pending" }],
    },
  };
  context.document.getElementById("maxStepsInput").value = "7";
  context.document.getElementById("maxRunSecondsInput").value = "120";
  context.document.getElementById("pauseInput").value = "0.25";
  context.__postJsonCalls = [];
  context.__refreshCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
  return { ok: true, payload: { id: "job-resume", task: "Finish the blocked browser checkout", status: "running", resume_run_id: "run-human" } };
};
refreshOverview = async (options) => {
  globalThis.__refreshCalls.push(JSON.parse(JSON.stringify(options || {})));
  globalThis.__activeJobAtRefresh = JSON.parse(JSON.stringify(state.activeJob || null));
};
`,
    context
  );

  const event = {
    target: {
      closest(selector) {
        if (selector === "[data-resume-run-id]") {
          return { dataset: { resumeRunId: "run-human" } };
        }
        return null;
      },
    },
  };

  await context.__appTest.handleInteractiveClick(event);

  assert.equal(context.__postJsonCalls.length, 1);
  assert.equal(context.__postJsonCalls[0].url, "/api/runs/run-human/resume");
  assert.equal(context.__postJsonCalls[0].payload.max_steps, 7);
  assert.equal(context.__postJsonCalls[0].payload.pause_after_action, 0.25);
  assert.equal(context.__postJsonCalls[0].payload.config_overrides.max_run_seconds, 120);
  assert.equal(context.__appTest.state.pendingTask, null);
  assert.equal(context.__activeJobAtRefresh.id, "job-resume");
  assert.equal(context.__activeJobAtRefresh.status, "running");
  assert.equal(context.__appTest.state.resumePendingRunId, "");
  assert.equal(context.__appTest.state.taskPreview, null);
  assert.equal(context.__appTest.state.taskPreviewTask, "");
  assert.equal(context.__appTest.state.taskPreviewConfigSignature, "");
  assert.equal(context.__appTest.state.taskPreviewError, "");
  assert.equal(context.__appTest.state.taskPreviewStartError, "");
  assert.equal(context.__appTest.state.selectedRunId, "run-human");
  assert.equal(context.__appTest.state.agentRunSessionMap["run-human"], context.__appTest.state.selectedAgentSessionId);
  assert.equal(JSON.stringify(context.__refreshCalls), '[{"forceLatest":true}]');
});


await runTest("resume success hint reflects approval jobs immediately", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.hydrated = true;
  context.__appTest.state.selectedRunDetails = {
    id: "run-review",
    task: "Review the saved plan",
    completed: false,
    can_resume: true,
    resume_mode: "manual",
  };
  context.__appTest.state.selectedRunId = "run-review";
  context.__appTest.state.runs = [snapshot(context.__appTest.state.selectedRunDetails)];
  context.__postJsonCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
  return {
    ok: true,
    payload: {
      id: "job-review-resume",
      task: "Review the saved plan",
      status: "running",
      resume_run_id: "run-review",
      result: {
        execution_state: {
          pending_decision: {
            decision_type: "plan_review",
            summary: "Review the saved plan before continuing.",
          },
        },
      },
    },
  };
};
refreshOverview = async () => {};
renderAll = () => {};
`,
    context
  );

  await context.__appTest.resumeRun("run-review");

  assert.equal(context.__postJsonCalls.length, 1);
  assert.equal(context.__appTest.state.activeJob.id, "job-review-resume");
  assert.equal(context.__appTest.state.pendingTask, null);
  assert.equal(context.__appTest.state.resumePendingRunId, "");
  assert.equal(context.document.getElementById("submitHint").textContent, "Awaiting approval");
});

await runTest("resume response without a job id clears pending state", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.hydrated = true;
  context.__appTest.state.selectedRunDetails = {
    id: "run-resume-no-id",
    task: "Resume a saved checkout",
    completed: false,
    can_resume: true,
    resume_mode: "manual",
  };
  context.__appTest.state.selectedRunId = "run-resume-no-id";
  context.__appTest.state.runs = [snapshot(context.__appTest.state.selectedRunDetails)];
  context.__postJsonCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
  return { ok: true, payload: { task: "Resume a saved checkout", status: "queued", resume_run_id: "run-resume-no-id" } };
};
refreshOverview = async () => {
  throw new Error("Malformed resume responses should not refresh overview.");
};
renderAll = () => {};
`,
    context
  );

  await context.__appTest.resumeRun("run-resume-no-id");

  assert.equal(context.__postJsonCalls.length, 1);
  assert.equal(context.__postJsonCalls[0].url, "/api/runs/run-resume-no-id/resume");
  assert.equal(context.__appTest.state.activeJob, null);
  assert.equal(context.__appTest.state.pendingTask, null);
  assert.equal(context.__appTest.state.resumePendingRunId, "");
  assert.equal(context.__appTest.state.selectedRunId, "run-resume-no-id");
  assert.equal(context.__appTest.state.selectedAgentSessionId !== null, true);
  const session = context.__appTest.state.agentSessions.find((item) => item.id === context.__appTest.state.selectedAgentSessionId);
  assert.ok(session);
  assert.deepEqual(snapshot(session.run_ids), ["run-resume-no-id"]);
  assert.equal(session.pending_task, "");
  assert.equal(session.pending_job_id, "");
  assert.equal(context.document.getElementById("submitHint").textContent, "Resume did not return a trackable job id.");
  vm.runInContext("renderComposerState(getAgentConversationContext())", context);
  assert.equal(context.document.getElementById("taskInput").disabled, false);
  assert.equal(context.document.getElementById("submitButton").disabled, false);
  assert.equal(context.document.getElementById("previewTaskButton").disabled, false);
});

await runTest("resume skips submission when current run details are not resumable", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.hydrated = true;
  context.__appTest.state.selectedRunDetails = {
    id: "run-not-resumable",
    task: "Finished local cleanup",
    completed: false,
    can_resume: false,
    resume_mode: null,
  };
  context.__appTest.state.selectedRunId = "run-not-resumable";
  context.__appTest.state.runs = [snapshot(context.__appTest.state.selectedRunDetails)];
  context.__postJsonCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload });
  throw new Error("Non-resumable runs should not post.");
};
renderAll = () => {};
`,
    context
  );

  await context.__appTest.resumeRun("run-not-resumable");

  assert.equal(context.__postJsonCalls.length, 0);
  assert.equal(context.__appTest.state.pendingTask, null);
  assert.equal(context.__appTest.state.resumePendingRunId, "");
  assert.equal(context.__appTest.state.agentSessions.length, 0);
  assert.equal(context.document.getElementById("submitHint").textContent, "This run has no saved execution state to resume.");
});


await runTest("manual resume mode renders attention without legacy interruption fields", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  const details = {
    id: "run-manual-mode-only",
    task: "Continue after a saved manual checkpoint",
    started_at: 1711000000,
    finished_at: null,
    steps: 2,
    completed: false,
    cancelled: false,
    requires_human: false,
    can_resume: true,
    resume_mode: "manual",
    interruption_kind: null,
    interruption_reason: null,
    dry_run: false,
    timeline: [],
  };

  const messages = context.__appTest.renderCompletedConversation(details);

  assert.equal(messages.length, 1);
  assert.match(messages[0], /Attention/);
  assert.match(messages[0], /currently needs attention/);
  assert.match(messages[0], /data-resume-run-id="run-manual-mode-only"/);
  assert.doesNotMatch(messages[0], /data-prefill-task=/);
  assert.match(messages[0], /human checkpoint/);
});


await runTest("saved step approval phase renders awaiting approval without backend flags", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  const details = {
    id: "run-saved-step-approval",
    task: "Continue guarded confirmation",
    started_at: 1711000000,
    finished_at: null,
    steps: 1,
    completed: false,
    cancelled: false,
    requires_human: false,
    dry_run: false,
    execution_state: {
      orchestration_phase: "awaiting_approval",
      task_graph: {
        task: "Continue guarded confirmation",
        subgoals: [{ id: "subgoal_01", title: "Click the guarded confirmation", status: "pending" }],
      },
    },
    timeline: [],
  };
  const summary = context.__appTest.summarizeOverviewRun(details);
  const messages = context.__appTest.renderCompletedConversation(details);

  assert.equal(context.__appTest.buildRecordState(details).label, "Awaiting approval");
  assert.equal(context.__appTest.needsHumanVerification(details), true);
  assert.equal(context.__appTest.canResumeRun(details), true);
  assert.equal(summary.orchestration_phase, "awaiting_approval");
  assert.equal(context.__appTest.buildRecordState(summary).label, "Awaiting approval");
  assert.match(messages[0], /Awaiting approval/);
  assert.match(messages[0], /Waiting for approval/);
  assert.match(messages[0], /data-resume-run-id="run-saved-step-approval"/);
});


await runTest("pending handoff context renders attention without top-level flags", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  const details = {
    id: "run-handoff-context-only",
    task: "Continue after sign-in",
    started_at: 1711000000,
    finished_at: null,
    steps: 2,
    completed: false,
    cancelled: false,
    requires_human: false,
    can_resume: true,
    resume_mode: "execution_state",
    interruption_kind: null,
    interruption_reason: null,
    dry_run: false,
    state: {
      app_context: {
        human_handoff_kind: "login",
        human_handoff_reason: "Complete sign-in before continuing.",
        standard_recovery_kind: "requires_user",
      },
    },
    timeline: [],
  };

  const messages = context.__appTest.renderCompletedConversation(details);

  assert.equal(messages.length, 1);
  assert.match(messages[0], /Attention/);
  assert.match(messages[0], /currently needs attention/);
  assert.match(messages[0], /data-resume-run-id="run-handoff-context-only"/);
  assert.doesNotMatch(messages[0], /data-prefill-task=/);
});


await runTest("historical pending decision renders awaiting approval from nested state", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  const details = {
    id: "run-nested-decision",
    task: "Review the generated plan before execution",
    started_at: 1711000000,
    finished_at: null,
    steps: 1,
    completed: false,
    cancelled: false,
    requires_human: false,
    can_resume: false,
    dry_run: false,
    execution_state: {
      pending_decision: {
        id: "decision-1",
        decision_type: "plan_review",
        summary: "Review the generated task plan.",
        reason: "Plan review is configured before execution.",
        risk_level: "medium",
      },
    },
    timeline: [],
  };

  const messages = context.__appTest.renderCompletedConversation(details);

  assert.equal(messages.length, 1);
  assert.match(messages[0], /Awaiting approval/);
  assert.match(messages[0], /Waiting for approval/);
  assert.doesNotMatch(messages[0], /Running/);
});


await runTest("legacy interrupted run follow-up can resume from interruption markers", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  const details = {
    id: "run-legacy-human",
    task: "Finish the legacy login flow",
    started_at: 1711000000,
    finished_at: null,
    steps: 2,
    completed: false,
    cancelled: false,
    requires_human: false,
    interruption_kind: "login",
    interruption_reason: "A login prompt needs user input.",
    dry_run: false,
    timeline: [],
  };

  const messages = context.__appTest.renderCompletedConversation(details);

  assert.equal(messages.length, 1);
  assert.match(messages[0], /data-resume-run-id="run-legacy-human"/);
  assert.doesNotMatch(messages[0], /data-prefill-task=/);
  assert.match(messages[0], /Resume run/);
});


await runTest("failed run with saved execution graph resumes instead of creating a new task", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  const details = {
    id: "run-failed-graph",
    task: "Recover the blocked checkout",
    started_at: 1711000000,
    finished_at: 1711000200,
    steps: 4,
    completed: false,
    cancelled: false,
    requires_human: false,
    error: "Subgoal became stuck after repeated failed attempts.",
    dry_run: false,
    timeline: [],
    execution_state: {
      task_graph: {
        task: "Recover the blocked checkout",
        subgoals: [
          { id: "subgoal_01", title: "Recover blocked checkout", status: "blocked" },
          { id: "subgoal_02", title: "Finish checkout", status: "pending" },
        ],
        dependencies: { subgoal_01: [], subgoal_02: ["subgoal_01"] },
      },
      plan_health: {
        counts: { total: 2, completed: 0, blocked: 1, ready: 1 },
        autonomy: { status: "recovering", can_continue: true, next_action: "repair" },
      },
    },
  };

  const messages = context.__appTest.renderCompletedConversation(details);

  assert.equal(messages.length, 1);
  assert.match(messages[0], /data-resume-run-id="run-failed-graph"/);
  assert.doesNotMatch(messages[0], /data-prefill-task=/);
  assert.match(messages[0], /Resume repair/);
  assert.match(messages[0], /queued repair path/);
});

await runTest("run summary uses backend can_resume flag before details are loaded", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  const details = {
    id: "run-summary-resumable",
    task: "Recover saved checkout",
    started_at: 1711000000,
    finished_at: 1711000200,
    steps: 4,
    completed: false,
    cancelled: false,
    requires_human: false,
    can_resume: true,
    resume_mode: "plan",
    error: "Subgoal became stuck after repeated failed attempts.",
    dry_run: false,
    timeline: [],
  };

  const messages = context.__appTest.renderCompletedConversation(details);

  assert.equal(messages.length, 1);
  assert.match(messages[0], /data-resume-run-id="run-summary-resumable"/);
  assert.doesNotMatch(messages[0], /data-prefill-task=/);
  assert.match(messages[0], /Resume run/);
  assert.match(messages[0], /saved task plan/);
});

await runTest("cancelled review with saved execution state renders resume action", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  const details = {
    id: "run-cancelled-review",
    task: "Continue a cancelled review",
    started_at: 1711000000,
    finished_at: 1711000200,
    steps: 1,
    completed: false,
    cancelled: true,
    cancel_reason: "Review later.",
    requires_human: false,
    can_resume: true,
    resume_mode: "execution_state",
    execution_state: {
      orchestration_phase: "plan_review",
      app_context: { plan_review_status: "pending" },
      task_graph: {
        task: "Continue a cancelled review",
        subgoals: [{ id: "subgoal_01", title: "Continue reviewed task", status: "pending" }],
      },
    },
    timeline: [],
  };

  const messages = context.__appTest.renderCompletedConversation(details);

  assert.equal(messages.length, 1);
  assert.equal(context.__appTest.canResumeRun(details), true);
  assert.match(messages[0], /data-resume-run-id="run-cancelled-review"/);
  assert.doesNotMatch(messages[0], /data-prefill-task=/);
  assert.match(messages[0], /Resume run/);
  assert.match(messages[0], /saved execution state/);
});

await runTest("backend can_resume false suppresses local resume fallback", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  const details = {
    id: "run-summary-not-resumable",
    task: "Failed before planning",
    started_at: 1711000000,
    finished_at: 1711000200,
    steps: 1,
    completed: false,
    cancelled: false,
    requires_human: false,
    can_resume: false,
    error: "Failed before the execution graph was saved.",
    dry_run: false,
    execution_state: {
      task_graph: {
        task: "Failed before planning",
        subgoals: [{ id: "subgoal_01", title: "Stale local fallback", status: "pending" }],
      },
    },
    timeline: [],
  };

  const messages = context.__appTest.renderCompletedConversation(details);

  assert.equal(messages.length, 1);
  assert.doesNotMatch(messages[0], /data-resume-run-id="run-summary-not-resumable"/);
  assert.match(messages[0], /data-prefill-task=/);
});

await runTest("terminal stale manual flags do not create local resume fallback", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  const failedWithoutState = {
    id: "run-stale-manual-no-state",
    task: "Failed after stale manual checkpoint",
    started_at: 1711000000,
    finished_at: 1711000200,
    steps: 2,
    completed: false,
    cancelled: false,
    requires_human: true,
    resume_mode: "manual",
    error: "Planner crashed after approval cleanup.",
    state: {
      pending_decision: {
        decision_type: "plan_review",
        summary: "Stale approval should not be treated as live.",
      },
    },
    timeline: [],
  };
  const failedWithState = {
    ...failedWithoutState,
    id: "run-stale-manual-with-state",
    execution_state: {
      task_graph: {
        task: "Failed after stale manual checkpoint",
        subgoals: [{ id: "subgoal_01", title: "Recover saved state", status: "pending" }],
      },
    },
  };

  assert.equal(context.__appTest.needsHumanVerification(failedWithoutState), false);
  assert.equal(context.__appTest.canResumeRun(failedWithoutState), false);
  assert.equal(context.__appTest.buildRecordState(failedWithoutState).label, "Failed");
  const fallbackMessages = context.__appTest.renderCompletedConversation(failedWithoutState);
  assert.doesNotMatch(fallbackMessages[0], /data-resume-run-id=/);
  assert.match(fallbackMessages[0], /data-prefill-task=/);

  assert.equal(context.__appTest.needsHumanVerification(failedWithState), false);
  assert.equal(context.__appTest.canResumeRun(failedWithState), true);
  const resumeMessages = context.__appTest.renderCompletedConversation(failedWithState);
  assert.match(resumeMessages[0], /data-resume-run-id="run-stale-manual-with-state"/);
});

await runTest("missing backend can_resume keeps local resume fallback", async () => {
  const context = createHarness({
    overviewPayload: buildOverviewPayload({
      runs: [
        {
          id: "run-summary-local-resume",
          task: "Recover saved local graph",
          completed: false,
          error: "Paused before the final saved step.",
          execution_state: {
            task_graph: {
              task: "Recover saved local graph",
              subgoals: [{ id: "subgoal_01", title: "Continue saved graph", status: "pending" }],
            },
          },
          timeline: [],
        },
      ],
    }),
  });
  context.__appTest.state.locale = "en-US";

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  assert.equal(context.__appTest.summarizeOverviewRun(context.__overviewPayload.runs[0]).can_resume, null);
  const summaryRun = context.__appTest.state.runs[0];
  assert.notEqual(summaryRun.can_resume, false);
  const messages = context.__appTest.renderCompletedConversation(summaryRun);
  assert.match(messages[0], /data-resume-run-id="run-summary-local-resume"/);
  assert.doesNotMatch(messages[0], /data-prefill-task=/);
});

await runTest("overview plan item summary parses string booleans", async () => {
  const context = createHarness();

  assert.equal(context.__appTest.summarizeOverviewPlanHealth({ autonomy: {} }), null);
  assert.equal(
    context.__appTest.summarizeOverviewPlanHealth({
      counts: {
        total: null,
        completed: null,
        pending: null,
        in_progress: null,
        blocked: null,
        failed: null,
        ready: null,
        exhausted: null,
      },
      autonomy: {},
    }),
    null
  );

  const summary = context.__appTest.summarizeOverviewPlanHealth({
    items: [
      {
        id: "subgoal_01",
        title: "Wait for approval",
        status: "pending",
        ready: "false",
        is_next: "false",
        exhausted: "false",
      },
      {
        id: "subgoal_02",
        title: "Run confirmed action",
        status: "pending",
        ready: "true",
        is_next: "true",
        exhausted: "true",
      },
    ],
  });

  assert.equal(summary.items[0].ready, false);
  assert.equal(summary.items[0].is_next, false);
  assert.equal(summary.items[0].exhausted, false);
  assert.equal(summary.items[1].ready, true);
  assert.equal(summary.items[1].is_next, true);
  assert.equal(summary.items[1].exhausted, true);
});

await runTest("plan health renderer parses string booleans", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";

  const html = context.__appTest.renderAgentPlanHealth({
    plan_health: {
      items: [
        {
          id: "subgoal_01",
          title: "Wait for approval",
          status: "pending",
          ready: "false",
          is_next: "false",
          exhausted: "false",
        },
      ],
    },
  });

  assert.match(html, /0 ready/);
  assert.doesNotMatch(html, /is-next/);
  assert.doesNotMatch(html, /is-exhausted/);
});

await runTest("autonomy renderer shows blockers and next action together", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";

  const html = context.__appTest.renderAgentPlanHealth({
    plan_health: {
      autonomy: {
        status: "recovering",
        can_continue: true,
        next_action: "repair",
        blockers: ["Click target was stale."],
      },
    },
  });

  assert.match(html, /Click target was stale\./);
  assert.match(html, /Next: Repair is queued\./);
  assert.match(html, /assistant-run__autonomy-next/);
});

await runTest("autonomy renderer labels failure inspection next action", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";

  const html = context.__appTest.renderAgentPlanHealth({
    plan_health: {
      autonomy: {
        status: "blocked",
        can_continue: false,
        next_action: "inspect_failure",
        blockers: ["Planner crashed after review progress."],
      },
    },
  });

  assert.match(html, /Planner crashed after review progress\./);
  assert.match(html, /Next: Inspect the failure\./);
});

await runTest("overview run and job summaries parse terminal string booleans", async () => {
  const context = createHarness();

  const runSummary = context.__appTest.summarizeOverviewRun({
    id: "run-string-booleans",
    dry_run: "false",
    completed: "false",
    cancelled: "false",
    requires_human: "false",
    execution_budget: {
      task_graph_request_timeout: 9.5,
      max_steps: 8,
      max_run_seconds: 120,
      desktop_autonomy_mode: "autonomous",
      replan_on_recoverable_error: "true",
      recoverable_error_retry_limit: 4,
    },
    browser_control_mode: "hybrid",
    browser_dom_backend: "playwright",
    browser_dom_timeout: 4,
    browser_headless: "true",
    cursor_motion_enabled: "false",
    generic_app_launch_enabled: "false",
    shell_recipe_policy: "approval_required",
  });
  assert.equal(runSummary.dry_run, false);
  assert.equal(runSummary.completed, false);
  assert.equal(runSummary.cancelled, false);
  assert.equal(runSummary.requires_human, false);
  assert.equal(runSummary.max_steps, 8);
  assert.equal(runSummary.max_run_seconds, 120);
  assert.equal(runSummary.desktop_autonomy_mode, "autonomous");
  assert.equal(runSummary.replan_on_recoverable_error, true);
  assert.equal(runSummary.recoverable_error_retry_limit, 4);
  assert.equal(runSummary.execution_budget.max_steps, 8);
  assert.equal(runSummary.execution_budget.replan_on_recoverable_error, true);
  assert.equal(runSummary.browser_control_mode, "hybrid");
  assert.equal(runSummary.browser_dom_backend, "playwright");
  assert.equal(runSummary.browser_dom_timeout, 4);
  assert.equal(runSummary.browser_headless, true);
  assert.equal(runSummary.cursor_motion_enabled, false);
  assert.equal(runSummary.generic_app_launch_enabled, false);
  assert.equal(runSummary.shell_recipe_policy, "approval_required");
  assert.equal(runSummary.execution_environment.browser_headless, true);
  assert.equal(runSummary.execution_environment.generic_app_launch_enabled, false);

  const jobSummary = context.__appTest.summarizeOverviewJob({
    id: "job-string-booleans",
    status: "running",
    cancel_requested: "false",
    cancelled: "false",
    completed: "false",
    requires_human: "false",
    config_overrides: {
      browser_control_mode: "dom",
      browser_dom_backend: "playwright",
      browser_dom_timeout: 6,
      browser_headless: "true",
      cursor_motion_enabled: "true",
      generic_app_launch_enabled: "false",
      shell_recipe_policy: "approval_required",
    },
    result: {
      dry_run: "false",
      cancelled: "false",
      completed: "false",
      requires_human: "false",
      execution_budget: {
        max_steps: 9,
        max_run_seconds: 240,
        desktop_autonomy_mode: "autonomous",
        replan_on_recoverable_error: "true",
        recoverable_error_retry_limit: 4,
      },
      execution_environment: {
        browser_dom_timeout: 7,
        browser_channel: "msedge",
      },
    },
  });
  assert.equal(jobSummary.dry_run, false);
  assert.equal(jobSummary.cancel_requested, false);
  assert.equal(jobSummary.cancelled, false);
  assert.equal(jobSummary.completed, false);
  assert.equal(jobSummary.requires_human, false);
  assert.equal(jobSummary.max_steps, 9);
  assert.equal(jobSummary.max_run_seconds, 240);
  assert.equal(jobSummary.desktop_autonomy_mode, "autonomous");
  assert.equal(jobSummary.replan_on_recoverable_error, true);
  assert.equal(jobSummary.recoverable_error_retry_limit, 4);
  assert.equal(jobSummary.execution_budget.max_steps, 9);
  assert.equal(jobSummary.execution_budget.replan_on_recoverable_error, true);
  assert.equal(jobSummary.browser_control_mode, "dom");
  assert.equal(jobSummary.browser_dom_backend, "playwright");
  assert.equal(jobSummary.browser_dom_timeout, 7);
  assert.equal(jobSummary.browser_channel, "msedge");
  assert.equal(jobSummary.browser_headless, true);
  assert.equal(jobSummary.cursor_motion_enabled, true);
  assert.equal(jobSummary.generic_app_launch_enabled, false);
  assert.equal(jobSummary.shell_recipe_policy, "approval_required");
  assert.equal(jobSummary.execution_environment.browser_headless, true);
  assert.equal(jobSummary.execution_environment.generic_app_launch_enabled, false);

  const handoffJobSummary = context.__appTest.summarizeOverviewJob({
    id: "job-pending-decision",
    status: "approval",
    requires_human: "false",
    result: {
      pending_decision: { decision_type: "stage_review" },
    },
  });
  assert.equal(handoffJobSummary.requires_human, true);

  const terminalJobSummary = context.__appTest.summarizeOverviewJob({
    id: "job-terminal-stale-decision",
    status: "failed",
    requires_human: "true",
    result: {
      error: "crashed",
      requires_human: "true",
      pending_decision: { decision_type: "stage_review" },
    },
  });
  assert.equal(terminalJobSummary.requires_human, false);
  assert.equal(terminalJobSummary.pending_decision, null);

  const terminalRunSummary = context.__appTest.summarizeOverviewRun({
    id: "run-terminal-stale-decision",
    error: "crashed",
    requires_human: "true",
    state: {
      pending_decision: { decision_type: "plan_review" },
    },
  });
  assert.equal(terminalRunSummary.requires_human, false);
  assert.equal(terminalRunSummary.pending_decision, null);
});

await runTest("overview pending decision ignores empty shell candidates", async () => {
  const context = createHarness();
  const jobSummary = context.__appTest.summarizeOverviewJob({
    id: "job-empty-shell-decision",
    status: "approval",
    result: {
      pending_decision: {},
      execution_state: {
        pending_decision: {
          decision_type: "plan_review",
          summary: "Review the nested task plan.",
        },
      },
      state: {
        pending_decision: {},
      },
    },
  });
  assert.equal(jobSummary.requires_human, true);
  assert.equal(jobSummary.pending_decision.summary, "Review the nested task plan.");

  const runSummary = context.__appTest.summarizeOverviewRun({
    id: "run-empty-shell-decision",
    execution_state: {
      pending_decision: {
        decision_type: "stage_review",
        actions: [{ selector: "#approve-stage" }],
      },
    },
    state: {
      pending_decision: {},
    },
  });
  assert.equal(runSummary.pending_decision.decision_type, "stage_review");
  assert.equal(runSummary.pending_decision.actions[0].selector, "#approve-stage");

  const emptyJobSummary = context.__appTest.summarizeOverviewJob({
    id: "job-only-empty-decision",
    status: "approval",
    result: { pending_decision: {} },
  });
  assert.equal(emptyJobSummary.requires_human, false);
  assert.equal(emptyJobSummary.pending_decision, null);
});

await runTest("execution mode chip parses string booleans", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";

  const liveChip = vm.runInContext('renderExecutionModeChip("false")', context);
  const dryRunChip = vm.runInContext('renderExecutionModeChip("true")', context);

  assert.match(liveChip, /Live/);
  assert.doesNotMatch(liveChip, /Dry Run/);
  assert.match(dryRunChip, /Dry Run/);
});

await runTest("detail and running views parse terminal string booleans", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";

  const liveRecord = {
    id: "run-string-live",
    status: "running",
    completed: "false",
    cancelled: "false",
    cancel_requested: "false",
    requires_human: "false",
    can_resume: "true",
    result: {
      completed: "false",
      cancelled: "false",
      requires_human: "false",
    },
  };

  assert.equal(context.__appTest.canResumeRun(liveRecord), true);
  assert.equal(context.__appTest.needsHumanVerification(liveRecord), false);
  const liveState = context.__appTest.buildRecordState(liveRecord);
  assert.equal(liveState.label, "Running");
  assert.equal(liveState.tone, "ok");
  const stoppingState = context.__appTest.buildRecordState({ ...liveRecord, can_resume: "false", cancel_requested: "true" });
  assert.equal(stoppingState.label, "Stopping");
  assert.equal(stoppingState.tone, "warn");

  const agentHtml = context.__appTest.renderRunningMessage({
    id: "job-string-live",
    task: "Continue without false terminal flags",
    status: "running",
    started_at: 1711000000,
    cancel_requested: "false",
    cancelled: "false",
    completed: "false",
    requires_human: "false",
    result: {
      run_id: "run-string-live",
      latest_summary: "Still executing.",
      steps: 2,
      dry_run: false,
      cancelled: "false",
      completed: "false",
      requires_human: "false",
    },
  });

  assert.match(agentHtml, /Running/);
  assert.match(agentHtml, /Goal-driven execution/);
  assert.match(agentHtml, /data-stop-active-task/);
  assert.doesNotMatch(agentHtml, /Cancelled/);
  assert.doesNotMatch(agentHtml, /Needs attention/);
});

await runTest("step proposal summary parses string booleans", async () => {
  const context = createHarness();

  const summary = context.__appTest.summarizeOverviewStepProposal({
    intent: "Click the visible button",
    requires_approval: "false",
    completes_subgoal: "false",
  });

  assert.equal(summary.requires_approval, false);
  assert.equal(summary.completes_subgoal, false);
});

await runTest("execution state normalization parses string next flags", async () => {
  const context = createHarness();

  const normalized = context.__appTest.normalizeRunExecutionStateCandidate({
    task_graph: {
      subgoals: [
        { id: "subgoal_01", title: "Not explicitly next", status: "completed", is_next: "false", exhausted: "false" },
        { id: "subgoal_02", title: "Explicit next", status: "pending", is_next: "true", exhausted: "true" },
      ],
    },
  });

  assert.equal(normalized.current_goal, "Explicit next");
  assert.equal(normalized.plan_health.next_subgoal_id, "subgoal_02");
  assert.equal(normalized.plan_health.items[0].is_next, false);
  assert.equal(normalized.plan_health.items[0].exhausted, false);
  assert.equal(normalized.plan_health.items[1].is_next, true);
  assert.equal(normalized.plan_health.items[1].exhausted, true);
  assert.equal(normalized.plan_health.counts.exhausted, 1);
});


await runTest("resumed run session clears pending state from refreshed activity time", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.agentSessions = [
    {
      id: "agent-resume",
      title: "Finish the blocked browser checkout",
      created_at: 100,
      updated_at: 200,
      run_ids: ["run-human"],
      pending_task: "Finish the blocked browser checkout",
      pending_job_id: "job-resume",
    },
  ];
  context.__appTest.state.agentRunSessionMap = { "run-human": "agent-resume" };
  context.__appTest.state.runs = [
    {
      id: "run-human",
      task: "Finish the blocked browser checkout",
      started_at: 100,
      finished_at: 220,
      completed: true,
    },
  ];

  context.__appTest.syncAgentSessionsWithRuns();

  assert.equal(context.__appTest.state.agentSessions.length, 1);
  assert.equal(context.__appTest.state.agentSessions[0].pending_task, "");
  assert.equal(context.__appTest.state.agentSessions[0].pending_job_id, "");
  assert.equal(JSON.stringify(context.__appTest.state.agentSessions[0].run_ids), '["run-human"]');
});

await runTest("pending job sessions attach to matching backend run tasks", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.agentSessions = [
    {
      id: "agent-calc",
      title: "",
      created_at: 100,
      updated_at: 100,
      run_ids: [],
      pending_task: "",
      pending_job_id: "job-calc",
    },
    {
      id: "agent-notes",
      title: "",
      created_at: 101,
      updated_at: 101,
      run_ids: [],
      pending_task: "",
      pending_job_id: "job-notes",
    },
  ];
  context.__appTest.state.jobs = [
    { id: "job-calc", task: "Open calculator", status: "queued" },
    { id: "job-notes", task: "Open notes", status: "queued" },
  ];
  context.__appTest.state.runs = [
    { id: "run-notes", task: "Open notes", started_at: 120, completed: true },
    { id: "run-calc", task: "Open calculator", started_at: 121, completed: true },
  ];

  context.__appTest.syncAgentSessionsWithRuns();

  assert.equal(context.__appTest.state.agentRunSessionMap["run-calc"], "agent-calc");
  assert.equal(context.__appTest.state.agentRunSessionMap["run-notes"], "agent-notes");
  const calcSession = context.__appTest.state.agentSessions.find((session) => session.id === "agent-calc");
  const notesSession = context.__appTest.state.agentSessions.find((session) => session.id === "agent-notes");
  assert.deepEqual(snapshot(calcSession.run_ids), ["run-calc"]);
  assert.deepEqual(snapshot(notesSession.run_ids), ["run-notes"]);
  assert.equal(calcSession.pending_job_id, "");
  assert.equal(notesSession.pending_job_id, "");
});

await runTest("terminal backend jobs clear stale pending agent sessions", async () => {
  const context = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.mode": "agent",
      "desktop-agent-workspace.agent-sessions": JSON.stringify([
        {
          id: "agent-failed-pending",
          title: "Open calculator",
          created_at: 100,
          updated_at: 120,
          run_ids: [],
          pending_task: "Open calculator",
          pending_job_id: "job-failed-pending",
        },
      ]),
      "desktop-agent-workspace.history-selection": JSON.stringify({ kind: "agent", id: "agent-failed-pending" }),
    },
    overviewPayload: buildOverviewPayload({
      jobs: [
        {
          id: "job-failed-pending",
          task: "Open calculator",
          status: "failed",
          error: "Planner crashed before creating a run.",
        },
      ],
    }),
  });

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  assert.equal(context.__appTest.state.pendingTask, null);
  assert.equal(context.__appTest.state.selectedAgentSessionId, null);
  assert.equal(context.__appTest.state.showWelcome, true);
  assert.deepEqual(snapshot(context.__appTest.state.agentSessions), []);
  context.__appTest.state.hydrated = true;
  vm.runInContext("renderComposerState(getAgentConversationContext())", context);
  assert.equal(context.document.getElementById("taskInput").disabled, false);
  assert.equal(context.document.getElementById("submitButton").disabled, false);
  assert.equal(context.document.getElementById("previewTaskButton").disabled, false);
});

await runTest("missing backend jobs clear orphaned pending agent sessions", async () => {
  const context = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.mode": "agent",
      "desktop-agent-workspace.agent-sessions": JSON.stringify([
        {
          id: "agent-orphan-pending",
          title: "Open calculator",
          created_at: 100,
          updated_at: 120,
          run_ids: [],
          pending_task: "",
          pending_job_id: "job-lost-after-restart",
        },
      ]),
      "desktop-agent-workspace.history-selection": JSON.stringify({ kind: "agent", id: "agent-orphan-pending" }),
    },
    overviewPayload: buildOverviewPayload(),
  });

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  assert.equal(context.__appTest.state.pendingTask, null);
  assert.equal(context.__appTest.state.selectedAgentSessionId, null);
  assert.equal(context.__appTest.state.showWelcome, true);
  assert.deepEqual(snapshot(context.__appTest.state.agentSessions), []);
  context.__appTest.state.hydrated = true;
  vm.runInContext("renderComposerState(getAgentConversationContext())", context);
  assert.equal(context.document.getElementById("taskInput").disabled, false);
  assert.equal(context.document.getElementById("submitButton").disabled, false);
  assert.equal(context.document.getElementById("previewTaskButton").disabled, false);
});

await runTest("background refresh clears selected orphaned pending sessions", async () => {
  const context = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.mode": "agent",
      "desktop-agent-workspace.agent-sessions": JSON.stringify([
        {
          id: "agent-orphan-selected",
          title: "Open calculator",
          created_at: 100,
          updated_at: 120,
          run_ids: [],
          pending_task: "",
          pending_job_id: "job-selected-before-restart",
        },
      ]),
      "desktop-agent-workspace.history-selection": JSON.stringify({ kind: "agent", id: "agent-orphan-selected" }),
    },
    overviewPayload: buildOverviewPayload({
      jobs: [
        {
          id: "job-selected-before-restart",
          task: "Open calculator",
          status: "queued",
        },
      ],
    }),
  });
  context.__appTest.state.locale = "en-US";

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  assert.equal(context.__appTest.state.selectedAgentSessionId, "agent-orphan-selected");
  assert.equal(context.__appTest.state.pendingTask, "Open calculator");
  assert.equal(context.__appTest.state.showWelcome, false);

  context.__overviewPayload = buildOverviewPayload();
  await context.__appTest.refreshOverview({ background: true });

  assert.equal(context.__appTest.state.pendingTask, null);
  assert.equal(context.__appTest.state.selectedAgentSessionId, null);
  assert.equal(context.__appTest.state.showWelcome, true);
  assert.deepEqual(snapshot(context.__appTest.state.agentSessions), []);
  assert.equal(context.__appTest.loadPersistedHistorySelection(), null);
  context.__appTest.state.hydrated = true;
  vm.runInContext("renderComposerState(getAgentConversationContext())", context);
  assert.equal(context.document.getElementById("taskInput").disabled, false);
  assert.equal(context.document.getElementById("submitButton").disabled, false);
  assert.equal(context.document.getElementById("previewTaskButton").disabled, false);
});

await runTest("orphaned pending jobs still attach to fresh backend runs", async () => {
  const context = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.mode": "agent",
      "desktop-agent-workspace.agent-sessions": JSON.stringify([
        {
          id: "agent-orphan-with-run",
          title: "Open calculator",
          created_at: 100,
          updated_at: 120,
          run_ids: [],
          pending_task: "",
          pending_job_id: "job-lost-after-run-created",
        },
      ]),
      "desktop-agent-workspace.history-selection": JSON.stringify({ kind: "agent", id: "agent-orphan-with-run" }),
    },
    overviewPayload: buildOverviewPayload({
      runs: [
        {
          id: "run-orphan-fresh",
          task: "Open calculator",
          started_at: 121,
          finished_at: 140,
          completed: true,
        },
      ],
    }),
  });

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  const restoredSession = context.__appTest.state.agentSessions.find((session) => session.id === "agent-orphan-with-run");
  assert.ok(restoredSession);
  assert.equal(context.__appTest.state.pendingTask, null);
  assert.equal(context.__appTest.state.selectedAgentSessionId, "agent-orphan-with-run");
  assert.equal(context.__appTest.state.selectedRunId, "run-orphan-fresh");
  assert.equal(context.__appTest.state.showWelcome, false);
  assert.deepEqual(snapshot(restoredSession.run_ids), ["run-orphan-fresh"]);
  assert.equal(restoredSession.pending_task, "");
  assert.equal(restoredSession.pending_job_id, "");
  assert.equal(context.__appTest.state.agentRunSessionMap["run-orphan-fresh"], "agent-orphan-with-run");
  assert.deepEqual(context.__loadRunDetailsCalls, ["run-orphan-fresh"]);
});


await runTest("chat and agent renderers both use the refreshed card shell", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";

  const chatHtml = context.__appTest.renderNormalAssistantMessage(
    {
      id: "assistant-1",
      role: "assistant",
      content: "Here is a polished answer.",
      status: "complete",
    },
    { showActions: false, sessionMessages: [] }
  );

  const agentHtml = context.__appTest.renderRunningMessage({
    task: "Open calculator and type 7+8",
    started_at: 1711000000,
    cancel_requested: false,
    result: {
      run_id: "run-live",
      latest_summary: "Calculator is open and the expression is typed in.",
      latest_screenshot: "live-shot.png",
      latest_actions: [
        { type: "launch_app", app: "calculator" },
        { type: "type", text: "7+8" },
      ],
      live_pointer: { norm_x: 0.45, norm_y: 0.4, phase: "moving" },
      live_pointer_trail: [
        { norm_x: 0.3, norm_y: 0.28, updated_at: 1711000001 },
        { norm_x: 0.38, norm_y: 0.34, updated_at: 1711000002 },
      ],
      live_action: { type: "click", label: "click(640,360)", status: "running" },
      steps: 2,
      dry_run: false,
    },
  });

  assert.match(chatHtml, /assistant-shell/);
  assert.match(chatHtml, /assistant-card--chat/);
  assert.match(chatHtml, /aoryn-mark\.png/);
  assert.match(agentHtml, /assistant-shell/);
  assert.match(agentHtml, /assistant-card--run/);
  assert.match(agentHtml, /assistant-run__hero/);
  assert.match(agentHtml, /live-pointer-layer/);
  assert.match(agentHtml, /aoryn-mark\.png/);
});

await runTest("running agent card renders backend plan health", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";

  const agentHtml = context.__appTest.renderRunningMessage({
    id: "job-plan",
    task: "Recover page and continue notes",
    started_at: 1711000000,
    cancel_requested: false,
    result: {
      run_id: "run-plan",
      latest_summary: "Recovering after a stale target.",
      latest_screenshot: "live-shot.png",
      steps: 3,
      dry_run: false,
      execution_state: {
        orchestration_phase: "stage_ready",
        active_specialist: "desktop_operator",
        current_subgoal: { id: "subgoal_02", title: "Continue with independent local notes" },
        plan_health: {
          counts: { total: 2, completed: 0, blocked: 1, ready: 1, exhausted: 1 },
          next_subgoal_id: "subgoal_02",
          autonomy: {
            status: "recovering",
            can_continue: true,
            next_action: "repair",
            blockers: [],
            warnings: ["Retry budget exhausted for subgoal_01."],
          },
          items: [
            {
              id: "subgoal_01",
              title: "Recover blocked page",
              status: "blocked",
              capability_preference: "browser_dom",
              retry_remaining: 0,
              exhausted: true,
            },
            {
              id: "subgoal_02",
              title: "Continue with independent local notes",
              status: "pending",
              capability_preference: "desktop_gui",
              retry_remaining: 2,
              is_next: true,
            },
          ],
        },
      },
    },
  });

  assert.match(agentHtml, /assistant-run__section--plan/);
  assert.match(agentHtml, /data-next-subgoal="subgoal_02"/);
  assert.match(agentHtml, /Recover blocked page/);
  assert.match(agentHtml, /Continue with independent local notes/);
  assert.match(agentHtml, /Autonomy/);
  assert.match(agentHtml, /Recovering/);
  assert.match(agentHtml, /0\/2/);
});

await runTest("overview plan health preserves autonomy without counts or items", async () => {
  const context = createHarness();

  const summary = context.__appTest.summarizeOverviewPlanHealth({
    autonomy: {
      status: "blocked",
      can_continue: "false",
      requires_user: "true",
      next_action: "ask_user",
      blockers: ["Clarify the destination folder."],
    },
  });

  assert.equal(summary.autonomy.status, "blocked");
  assert.equal(summary.autonomy.can_continue, false);
  assert.equal(summary.autonomy.requires_user, true);
  assert.deepEqual(snapshot(summary.autonomy.blockers), ["Clarify the destination folder."]);
  assert.deepEqual(snapshot(summary.items), []);
});

await runTest("running agent card renders autonomy-only plan health", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";

  const agentHtml = context.__appTest.renderRunningMessage({
    id: "job-autonomy-only",
    task: "Clarify destination and continue",
    started_at: 1711000000,
    cancel_requested: false,
    result: {
      run_id: "run-autonomy-only",
      latest_summary: "Waiting for the missing destination.",
      steps: 1,
      execution_state: {
        current_goal: "Clarify destination",
        plan_health: {
          autonomy: {
            status: "needs_clarification",
            can_continue: false,
            requires_user: true,
            next_action: "ask_user",
            blockers: ["Clarify the destination folder."],
          },
        },
      },
    },
  });

  assert.match(agentHtml, /assistant-run__section--plan/);
  assert.match(agentHtml, /Autonomy/);
  assert.match(agentHtml, /Needs clarification/);
  assert.match(agentHtml, /Clarify the destination folder/);
  assert.doesNotMatch(agentHtml, /assistant-run__plan-list/);
});

await runTest("running agent card infers autonomy status from simplified readiness", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";

  const agentHtml = context.__appTest.renderRunningMessage({
    id: "job-simplified-readiness",
    task: "Wait for missing input",
    started_at: 1711000000,
    result: {
      run_id: "run-simplified-readiness",
      latest_summary: "Waiting for a destination choice.",
      execution_state: {
        plan_health: {
          autonomy: {
            can_continue: "false",
            requires_user: "true",
            next_action: "ask_user",
            blockers: ["Choose the destination folder."],
          },
        },
      },
    },
  });

  assert.match(agentHtml, /assistant-run__section--plan/);
  assert.match(agentHtml, /Autonomy/);
  assert.match(agentHtml, /Needs clarification/);
  assert.match(agentHtml, /Choose the destination folder/);
  assert.doesNotMatch(agentHtml, /assistant-run__plan-list/);
});

await runTest("running agent card renders blocked reason without plan items", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";

  const summary = context.__appTest.summarizeOverviewPlanHealth({
    blocked_reason: "No continuable subgoal is ready.",
  });
  assert.equal(summary.blocked_reason, "No continuable subgoal is ready.");
  assert.equal(summary.counts.total, null);

  const agentHtml = context.__appTest.renderRunningMessage({
    id: "job-blocked-reason-only",
    task: "Recover a blocked run",
    started_at: 1711000000,
    result: {
      run_id: "run-blocked-reason-only",
      latest_summary: "The plan is blocked.",
      execution_state: {
        plan_health: {
          blocked_reason: "No continuable subgoal is ready.",
        },
      },
    },
  });

  assert.match(agentHtml, /assistant-run__section--plan/);
  assert.match(agentHtml, /Autonomy/);
  assert.match(agentHtml, /Blocked/);
  assert.match(agentHtml, /No continuable subgoal is ready/);
  assert.doesNotMatch(agentHtml, /assistant-run__plan-list/);
});

await runTest("running agent card preserves explicit not-ready next subgoal", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";

  const agentHtml = context.__appTest.renderRunningMessage({
    id: "job-plan-not-ready",
    task: "Wait for review before continuing",
    started_at: 1711000000,
    cancel_requested: false,
    result: {
      run_id: "run-plan-not-ready",
      latest_summary: "The next subgoal is selected but not executable yet.",
      steps: 1,
      dry_run: false,
      execution_state: {
        current_goal: "Review the selected subgoal",
        plan_health: {
          next_subgoal_id: "subgoal_01",
          autonomy: {
            status: "review_required",
            can_continue: false,
            requires_review: true,
            next_action: "approve_plan",
          },
          items: [
            {
              id: "subgoal_01",
              title: "Review the selected subgoal",
              status: "pending",
              capability_preference: "browser_dom",
              ready: false,
              is_next: true,
            },
          ],
        },
      },
    },
  });

  assert.match(agentHtml, /data-next-subgoal="subgoal_01"/);
  assert.match(agentHtml, /0 ready/);
  assert.doesNotMatch(agentHtml, /1 ready/);
  assert.match(agentHtml, /Review required/);
});

await runTest("running agent card renders state summary fallback for active jobs", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";

  const agentHtml = context.__appTest.renderRunningMessage({
    id: "job-state-summary",
    task: "Review summarized active state",
    status: "approval",
    started_at: 1711000000,
    cancel_requested: false,
    result: {
      run_id: "run-state-summary",
      latest_summary: "Waiting for summarized approval.",
      steps: 2,
      dry_run: false,
      state: {
        current_goal: "Submit summarized recovery",
        orchestration_phase: "stage_review",
        stage_review_status: "pending",
        pending_decision: {
          decision_type: "stage_review",
          summary: "Review summarized stage.",
          reason: "The active job only sent a display state summary.",
          risk_level: "high",
        },
        plan_health: {
          counts: { total: 2, completed: 1, ready: 1 },
          next_subgoal_id: "subgoal_02",
          autonomy: { status: "review_required", can_continue: false, requires_review: true },
          items: [
            { id: "subgoal_01", title: "Recover from stale target", status: "completed" },
            { id: "subgoal_02", title: "Submit summarized recovery", status: "pending", is_next: true },
          ],
        },
        last_step: {
          capability: "browser_dom",
          intent: "Use the summarized state fallback step.",
          risk_level: "medium",
          surface_kind: "managed_aoryn_browser",
          actions: [{ type: "click", selector: "#submit-summary", button: "left" }],
        },
      },
    },
  });

  assert.match(agentHtml, /Awaiting approval/);
  assert.match(agentHtml, /Review summarized stage/);
  assert.match(agentHtml, /The active job only sent a display state summary/);
  assert.match(agentHtml, /assistant-run__section--plan/);
  assert.match(agentHtml, /data-next-subgoal="subgoal_02"/);
  assert.match(agentHtml, /Submit summarized recovery/);
  assert.match(agentHtml, /Stage review: pending/);
  assert.match(agentHtml, /Next step/);
  assert.match(agentHtml, /Use the summarized state fallback step/);
  assert.match(agentHtml, /selector=#submit-summary/);
});

await runTest("running and developer views render full execution task graph fallback", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  const activeJob = {
    id: "job-full-state",
    task: "Continue from a full execution state",
    status: "running",
    started_at: 1711000000,
    cancel_requested: false,
    result: {
      run_id: "run-full-state",
      latest_summary: "Continuing from saved full state.",
      steps: 2,
      dry_run: false,
      execution_state: {
        task: "Continue from a full execution state",
        orchestration_phase: "stage_ready",
        app_context: { active_subgoal_id: "subgoal_02" },
        task_graph: {
          task: "Continue from a full execution state",
          subgoals: [
            { id: "subgoal_01", title: "Review current page", status: "completed", capability_preference: "browser_dom" },
            { id: "subgoal_02", title: "Continue from graph", status: "pending", capability_preference: "desktop_gui" },
          ],
        },
      },
    },
  };

  const agentHtml = context.__appTest.renderRunningMessage(activeJob);

  assert.match(agentHtml, /assistant-run__section--plan/);
  assert.match(agentHtml, /data-next-subgoal="subgoal_02"/);
  assert.match(agentHtml, /Continue from graph/);

  context.__appTest.state.activeJob = activeJob;
  context.__appTest.state.jobs = [activeJob];
  context.__appTest.renderDeveloper();
  const timelineHtml = context.document.getElementById("developerTimeline").innerHTML;
  assert.match(timelineHtml, /timeline-item--plan/);
  assert.match(timelineHtml, /Continue from graph/);
});

await runTest("running agent card renders current step proposal details", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";

  const agentHtml = context.__appTest.renderRunningMessage({
    id: "job-step-proposal-card",
    task: "Continue with a visible next step",
    status: "running",
    started_at: 1711000000,
    cancel_requested: false,
    result: {
      run_id: "run-step-proposal-card",
      latest_summary: "Choosing the next action.",
      steps: 1,
      dry_run: false,
      step_proposal: {
        capability: "browser_dom",
        intent: "Use DOM automation after the desktop target became stale.",
        risk_level: "medium",
        target_scope: "subgoal",
        surface_kind: "managed_aoryn_browser",
        progress_signals: ["Wait for the continue button to become enabled."],
        actions: [{ type: "click", selector: "#continue", button: "left" }],
      },
      execution_state: {
        current_goal: "Continue with a visible next step",
        plan_health: {
          counts: { total: 1, completed: 0, ready: 1 },
          next_subgoal_id: "subgoal_01",
          items: [
            { id: "subgoal_01", title: "Continue with a visible next step", status: "pending", ready: true, is_next: true },
          ],
        },
      },
    },
  });

  assert.match(agentHtml, /Next step/);
  assert.match(agentHtml, /Use DOM automation after the desktop target became stale/);
  assert.match(agentHtml, /Capability: browser_dom/);
  assert.match(agentHtml, /Risk: medium/);
  assert.match(agentHtml, /Managed browser/);
  assert.match(agentHtml, /selector=#continue/);
  assert.match(agentHtml, /Wait for the continue button/);
});

await runTest("running agent card falls back to execution last step proposal", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";

  const agentHtml = context.__appTest.renderRunningMessage({
    id: "job-last-step-card",
    task: "Continue from saved last step",
    status: "running",
    started_at: 1711000000,
    cancel_requested: false,
    result: {
      run_id: "run-last-step-card",
      latest_summary: "Continuing the saved step.",
      steps: 2,
      dry_run: false,
      execution_state: {
        current_goal: "Continue from saved last step",
        last_step: {
          capability: "desktop_gui",
          intent: "Click the saved desktop target.",
          risk_level: "low",
          surface_kind: "current_user_desktop",
          actions: [{ type: "click", x: 320, y: 240, button: "left" }],
        },
      },
    },
  });

  assert.match(agentHtml, /Next step/);
  assert.match(agentHtml, /Click the saved desktop target/);
  assert.match(agentHtml, /Capability: desktop_gui/);
  assert.match(agentHtml, /@320,240/);
});

await runTest("running agent card renders merged resume summary and full task graph", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";

  const agentHtml = context.__appTest.renderRunningMessage({
    id: "job-resume-merged",
    task: "Resume saved checkout",
    status: "running",
    started_at: 1711000000,
    cancel_requested: false,
    result: {
      run_id: "run-resume-merged",
      latest_summary: "Paused at manual verification.",
      steps: 3,
      dry_run: false,
      execution_state: {
        current_goal: "Resume after verification",
        plan_health: {
          counts: { total: 2, completed: 1, ready: 1, blocked: 0 },
          next_subgoal_id: "subgoal_02",
          autonomy: { status: "waiting_user", can_continue: false, next_action: "resume_after_user" },
        },
        task_graph: {
          task: "Resume saved checkout",
          subgoals: [
            { id: "subgoal_01", title: "Open checkout", status: "completed", capability_preference: "browser_dom" },
            { id: "subgoal_02", title: "Resume after verification", status: "pending", capability_preference: "desktop_gui" },
          ],
        },
      },
    },
  });

  assert.match(agentHtml, /assistant-run__section--plan/);
  assert.match(agentHtml, /data-next-subgoal="subgoal_02"/);
  assert.match(agentHtml, /Resume after verification/);
  assert.match(agentHtml, /Open checkout/);
  assert.match(agentHtml, /Waiting for user/);
  assert.match(agentHtml, /Resume after the user step\./);
});

await runTest("running agent card renders execution limit chips", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";

  const agentHtml = context.__appTest.renderRunningMessage({
    id: "job-limits",
    task: "Run with explicit execution limits",
    status: "running",
    started_at: 1711000000,
    cancel_requested: false,
    max_steps: 7,
    max_run_seconds: 120,
    pause_after_action: 0.25,
    config_overrides: {
      max_run_seconds: 30,
      task_graph_request_timeout: 9.5,
      desktop_autonomy_mode: "review_first",
      complex_task_planning: "hybrid",
      approval_policy: "strict",
      plan_review_policy: "always",
      stage_review_policy: "risk_change",
      max_task_subgoals: 5,
      max_subgoal_retries: 1,
      max_replans_per_run: 2,
      max_failures_per_subgoal: 3,
      replan_on_recoverable_error: false,
      recoverable_error_retry_limit: 1,
      browser_control_mode: "hybrid",
      browser_dom_backend: "playwright",
      browser_dom_timeout: 4,
      browser_headless: true,
      browser_channel: "chrome",
      cursor_motion_enabled: true,
      cursor_motion_duration: 0.35,
      display_override_enabled: true,
      display_override_monitor_device_name: "DISPLAY2",
      generic_app_launch_enabled: false,
      shell_recipe_policy: "approval_required",
    },
    result: {
      run_id: "run-limits",
      latest_summary: "Working within configured limits.",
      steps: 1,
      dry_run: false,
      execution_state: {
        current_goal: "Continue bounded execution",
        plan_health: {
          counts: { total: 1, completed: 0, ready: 1 },
          next_subgoal_id: "subgoal_01",
          autonomy: { status: "ready", can_continue: true, next_action: "execute" },
          items: [
            { id: "subgoal_01", title: "Continue bounded execution", status: "pending", ready: true, is_next: true },
          ],
        },
      },
    },
  });

  assert.match(agentHtml, /Max steps: 7/);
  assert.match(agentHtml, /Run limit: 2m/);
  assert.match(agentHtml, /Action pause: 0\.25s/);
  assert.match(agentHtml, /Plan timeout: 9\.5s/);
  assert.match(agentHtml, /Autonomy: Review first/);
  assert.match(agentHtml, /Planning: Hybrid/);
  assert.match(agentHtml, /Approval: Every step/);
  assert.match(agentHtml, /Plan review: Always/);
  assert.match(agentHtml, /Stage review: Risk change/);
  assert.match(agentHtml, /Subgoals: 5/);
  assert.match(agentHtml, /Retries: 1/);
  assert.match(agentHtml, /Replans: 2/);
  assert.match(agentHtml, /Failures: 3/);
  assert.match(agentHtml, /Recovery: off x1/);
  assert.match(agentHtml, /Browser: hybrid \/ playwright/);
  assert.match(agentHtml, /DOM timeout: 4s/);
  assert.match(agentHtml, /Launch: chrome headless/);
  assert.match(agentHtml, /Pointer: on 0\.35s/);
  assert.match(agentHtml, /Display: DISPLAY2/);
  assert.match(agentHtml, /Known apps only/);
  assert.match(agentHtml, /Shell: Approval required/);
});

await runTest("running agent card renders effective result budget chips", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";

  const agentHtml = context.__appTest.renderRunningMessage({
    id: "job-result-budget",
    task: "Run with backend effective budget",
    status: "running",
    started_at: 1711000000,
    cancel_requested: false,
    result: {
      run_id: "run-result-budget",
      latest_summary: "Backend returned effective execution budget.",
      steps: 1,
      dry_run: false,
      execution_budget: {
        max_steps: 9,
        max_run_seconds: 180,
        pause_after_action: 0.4,
        desktop_autonomy_mode: "autonomous",
        complex_task_planning: "model",
        approval_policy: "autonomous",
        plan_review_policy: "never",
        stage_review_policy: "risk_change",
        max_task_subgoals: 7,
        max_subgoal_retries: 2,
        max_replans_per_run: 4,
        max_failures_per_subgoal: 5,
        replan_on_recoverable_error: true,
        recoverable_error_retry_limit: 4,
      },
      execution_state: {
        current_goal: "Continue with backend budget",
        plan_health: {
          counts: { total: 1, completed: 0, ready: 1 },
          autonomy: { status: "ready", can_continue: true, next_action: "execute" },
          items: [{ id: "subgoal_01", title: "Continue with backend budget", status: "pending", ready: true }],
        },
      },
    },
  });

  assert.match(agentHtml, /Max steps: 9/);
  assert.match(agentHtml, /Run limit: 3m/);
  assert.match(agentHtml, /Action pause: 0\.4s/);
  assert.match(agentHtml, /Autonomy: Autonomous/);
  assert.match(agentHtml, /Planning: Model/);
  assert.match(agentHtml, /Approval: High autonomy/);
  assert.match(agentHtml, /Plan review: No review/);
  assert.match(agentHtml, /Stage review: Risk change/);
  assert.match(agentHtml, /Subgoals: 7/);
  assert.match(agentHtml, /Retries: 2/);
  assert.match(agentHtml, /Replans: 4/);
  assert.match(agentHtml, /Failures: 5/);
  assert.match(agentHtml, /Recovery: on x4/);
});

await runTest("running agent card can show queued preview graph before progress", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";

  const agentHtml = context.__appTest.renderRunningMessage({
    id: "job-preview",
    task: "Open calculator and type 7+8",
    status: "queued",
    started_at: 1711000000,
    cancel_requested: false,
    initial_task_graph: {
      task: "Open calculator and type 7+8",
      subgoals: [
        { id: "subgoal_01", title: "Open calculator", status: "pending", capability_preference: "desktop_gui" },
        { id: "subgoal_02", title: "Type 7+8", status: "pending", capability_preference: "desktop_gui" },
      ],
    },
    result: null,
  });

  assert.match(agentHtml, /assistant-run__section--plan/);
  assert.match(agentHtml, /assistant-card--run-queued/);
  assert.match(agentHtml, /Queued/);
  assert.match(agentHtml, /Plan staged/);
  assert.match(agentHtml, /Open calculator/);
  assert.match(agentHtml, /Type 7\+8/);
});

await runTest("approval buttons submit job decisions through the chat card", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.activeJob = {
    id: "job-approval",
    task: "Review generated plan",
    status: "approval",
    result: {
      execution_state: {
        pending_decision: {
          decision_type: "plan_review",
          summary: "Review the task plan.",
        },
      },
    },
  };
  context.__appTest.state.jobs = [snapshot(context.__appTest.state.activeJob)];
  context.__appTest.state.agentSessions = [
    {
      id: "agent-approval",
      title: "Review generated plan",
      created_at: 100,
      updated_at: 100,
      run_ids: [],
      pending_task: "Review generated plan",
      pending_job_id: "job-approval",
    },
  ];
  context.__appTest.state.selectedAgentSessionId = "agent-approval";
  context.__postJsonCalls = [];
  context.__refreshCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
  return {
    ok: true,
    payload: {
      id: "job-approval",
      task: "Review generated plan",
      status: "running",
      result: { execution_state: { plan_health: { autonomy: { status: "ready", can_continue: true } } } },
    },
  };
};
refreshOverview = async (options) => {
  globalThis.__refreshCalls.push(JSON.parse(JSON.stringify(options || {})));
  globalThis.__activeJobAtRefresh = JSON.parse(JSON.stringify(state.activeJob || null));
};
renderAll = () => {};
`,
    context
  );
  const event = {
    target: {
      closest(selector) {
        if (selector === "[data-job-decision]") {
          return { dataset: { jobId: "job-approval", jobDecision: "approve" } };
        }
        return null;
      },
    },
  };

  await context.__appTest.handleInteractiveClick(event);

  assert.equal(context.__postJsonCalls.length, 1);
  assert.equal(context.__postJsonCalls[0].url, "/api/jobs/job-approval/decision");
  assert.equal(context.__postJsonCalls[0].payload.decision, "approve");
  assert.equal(context.__postJsonCalls[0].payload.note, undefined);
  assert.equal(context.__activeJobAtRefresh.status, "running");
  assert.equal(context.__activeJobAtRefresh.result.execution_state.pending_decision, undefined);
  assert.equal(context.__activeJobAtRefresh.result.execution_state.plan_health.autonomy.status, "ready");
  assert.equal(context.__activeJobAtRefresh.result.execution_state.plan_health.autonomy.can_continue, true);
  assert.equal(context.__appTest.state.jobs[0].status, "running");
  assert.equal(context.__appTest.state.agentSessions[0].pending_job_id, "job-approval");
  assert.equal(context.__appTest.state.agentSessions[0].pending_task, "");
  assert.ok(context.__appTest.state.agentSessions[0].updated_at >= 100);
  const persistedAgentSessions = JSON.parse(
    context.localStorage.getItem("desktop-agent-workspace.agent-sessions")
  );
  assert.equal(persistedAgentSessions[0].pending_job_id, "job-approval");
  assert.equal(persistedAgentSessions[0].pending_task, "");
  assert.equal(JSON.stringify(context.__refreshCalls), '[{"forceDetailRefresh":true}]');
  assert.equal(context.__appTest.state.decisionPendingJobId, "");
});

await runTest("operator-present approval submits an audit note", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.activeJob = {
    id: "job-operator-approval",
    task: "Open elevated PowerShell",
    status: "approval",
    result: {
      execution_state: {
        pending_decision: {
          decision_type: "step_approval",
          summary: "Open PowerShell with administrator privileges.",
          risk_level: "critical",
          approval_policy: "autonomous",
          requires_user_presence: true,
          operator_hint: "Keep a person at the screen before approving.",
        },
      },
    },
  };
  context.__postJsonCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
  return { ok: true, payload: { id: "job-operator-approval", status: "running", result: {} } };
};
refreshOverview = async () => {};
renderAll = () => {};
`,
    context
  );
  const event = {
    target: {
      closest(selector) {
        if (selector === "[data-job-decision]") {
          return { dataset: { jobId: "job-operator-approval", jobDecision: "approve" } };
        }
        return null;
      },
    },
  };

  await context.__appTest.handleInteractiveClick(event);

  assert.equal(context.__postJsonCalls.length, 1);
  assert.equal(context.__postJsonCalls[0].url, "/api/jobs/job-operator-approval/decision");
  assert.equal(context.__postJsonCalls[0].payload.decision, "approve");
  assert.match(context.__postJsonCalls[0].payload.note, /Operator is present/);
  assert.match(context.__postJsonCalls[0].payload.note, /administrator or UAC/);
});

await runTest("stale approval buttons are ignored after the active job changes", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.activeJob = {
    id: "job-current",
    task: "Current approval",
    status: "approval",
    result: {
      execution_state: {
        pending_decision: {
          decision_type: "plan_review",
          summary: "Review the current task plan.",
        },
      },
    },
  };
  context.__postJsonCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
  return { ok: true, payload: { id: "job-stale", status: "running" } };
};
renderAll = () => {};
`,
    context
  );
  const event = {
    target: {
      closest(selector) {
        if (selector === "[data-job-decision]") {
          return { dataset: { jobId: "job-stale", jobDecision: "approve" } };
        }
        return null;
      },
    },
  };

  await context.__appTest.handleInteractiveClick(event);

  assert.equal(context.__postJsonCalls.length, 0);
  assert.equal(context.__appTest.state.decisionPendingJobId, "");
  assert.equal(
    context.document.getElementById("submitHint").textContent,
    "This approval request is no longer current; wait for the latest state."
  );
});

await runTest("approval dock disables duplicate decisions while submitting", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.decisionPendingJobId = "job-plan";
  context.__appTest.state.decisionPendingChoice = "approve";

  const agentHtml = context.__appTest.renderRunningMessage({
    id: "job-plan",
    task: "Review a plan",
    started_at: 1711000000,
    cancel_requested: false,
    result: {
      latest_summary: "Waiting for approval.",
      steps: 0,
      execution_state: {
        pending_decision: {
          id: "plan-review",
          decision_type: "step_approval",
          summary: "Review the administrator action.",
          reason: "Critical actions still require approval in autonomous mode.",
          risk_level: "critical",
          approval_policy: "autonomous",
          requires_user_presence: true,
          operator_hint: "Keep a person at the screen before approving; a UAC prompt may appear.",
          actions: [{ type: "open_app_if_needed", app: "PowerShell" }],
        },
      },
    },
  });

  assert.match(agentHtml, /Approving/);
  assert.match(agentHtml, /Review the administrator action/);
  assert.match(agentHtml, /Risk: Critical/);
  assert.match(agentHtml, /Type: step_approval/);
  assert.match(agentHtml, /Approval: High autonomy/);
  assert.match(agentHtml, /Operator: present/);
  assert.match(agentHtml, /person at the screen/);
  assert.match(agentHtml, /open_app_if_needed/);
  assert.match(agentHtml, /app=PowerShell/);
  assert.match(agentHtml, /data-job-decision="approve"[^>]* disabled/);
  assert.match(agentHtml, /data-job-decision="reject"[^>]* disabled/);
});

await runTest("running agent card renders stage review approval context", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";

  const agentHtml = context.__appTest.renderRunningMessage({
    id: "job-stage-review",
    task: "Recover and submit the form",
    status: "approval",
    started_at: 1711000000,
    cancel_requested: false,
    result: {
      latest_summary: "Waiting for replanned stage review.",
      steps: 3,
      execution_state: {
        current_goal: "Submit the recovered form",
        current_subgoal: { id: "subgoal_01", title: "Submit the recovered form" },
        stage_review_status: "pending",
        last_replan_reason: "Risk increased after recovery.",
        pending_decision: {
          id: "stage-review",
          decision_type: "stage_review",
          summary: "Review the replanned stage before execution.",
          reason: "The recovered route now submits a form.",
          risk_level: "high",
        },
      },
    },
  });

  assert.match(agentHtml, /Awaiting approval/);
  assert.match(agentHtml, /Review the replanned stage/);
  assert.match(agentHtml, /The recovered route now submits a form/);
  assert.match(agentHtml, /Risk: High/);
  assert.match(agentHtml, /Type: stage_review/);
  assert.match(agentHtml, /Risk increased after recovery/);
  assert.match(agentHtml, /Stage review: pending/);
  assert.match(agentHtml, /data-job-decision="approve"/);
  assert.match(agentHtml, /data-job-decision="reject"/);
});

await runTest("running agent card renders result-only handoff as attention", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";

  const agentHtml = context.__appTest.renderRunningMessage({
    id: "job-result-handoff-active",
    task: "Resume after sign-in",
    status: "running",
    started_at: 1711000000,
    requires_human: false,
    result: {
      run_id: "run-result-handoff-active",
      latest_summary: "Waiting for sign-in.",
      steps: 1,
      requires_human: true,
      interruption_kind: "requires_auth",
      interruption_reason: "Complete sign-in before continuing.",
    },
  });

  assert.match(agentHtml, /Needs attention/);
  assert.match(agentHtml, /Complete sign-in before continuing\./);
  assert.match(agentHtml, /metric-pill warn/);
});

await runTest("running agent card renders result-only terminal states", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";

  const failedHtml = context.__appTest.renderRunningMessage({
    id: "job-result-failed",
    task: "Recover route",
    status: "running",
    started_at: 1711000000,
    result: {
      run_id: "run-result-failed",
      steps: 2,
      error: "Planner crashed after approval cleanup.",
      pending_decision: {
        summary: "This stale decision should be ignored.",
      },
    },
  });
  assert.match(failedHtml, /Failed/);
  assert.match(failedHtml, /Planner crashed after approval cleanup\./);
  assert.doesNotMatch(failedHtml, /Awaiting approval/);
  assert.doesNotMatch(failedHtml, /data-stop-active-task/);

  const cancelledHtml = context.__appTest.renderRunningMessage({
    id: "job-result-cancelled",
    task: "Stop route",
    status: "running",
    started_at: 1711000000,
    result: {
      run_id: "run-result-cancelled",
      steps: 2,
      cancelled: true,
      cancel_reason: "Stopped by user.",
    },
  });
  assert.match(cancelledHtml, /Cancelled/);
  assert.match(cancelledHtml, /Stopped by user\./);
  assert.doesNotMatch(cancelledHtml, /data-stop-active-task/);

  const completedHtml = context.__appTest.renderRunningMessage({
    id: "job-result-completed",
    task: "Finish route",
    status: "running",
    started_at: 1711000000,
    result: {
      run_id: "run-result-completed",
      steps: 3,
      completed: true,
      latest_summary: "Finished cleanup.",
    },
  });
  assert.match(completedHtml, /Done/);
  assert.match(completedHtml, /Finished cleanup\./);
  assert.doesNotMatch(completedHtml, /data-stop-active-task/);
});

await runTest("stopping approval job hides approval controls", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";

  const agentHtml = context.__appTest.renderRunningMessage({
    id: "job-plan-stop",
    task: "Review a plan",
    status: "stopping",
    started_at: 1711000000,
    cancel_requested: true,
    result: {
      latest_summary: "Waiting for approval.",
      steps: 0,
      execution_state: {
        pending_decision: {
          id: "plan-review",
          decision_type: "plan_review",
          summary: "Review the task plan.",
          reason: "Plan review is required.",
          risk_level: "medium",
        },
      },
    },
  });

  assert.match(agentHtml, /Stopping/);
  assert.doesNotMatch(agentHtml, /Awaiting approval/);
  assert.doesNotMatch(agentHtml, /data-job-decision=/);
});

await runTest("task preview card renders generated plan before execution", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.taskPreviewTask = "Open calculator and type 7+8";
  context.__appTest.state.taskPreview = {
    task: "Open calculator and type 7+8",
    task_graph_signature: "preview-render-ready",
    risk_level: "low",
    ambiguous: "false",
    requires_review: "false",
    execution_budget: {
      task_graph_request_timeout: 9.5,
      max_steps: 8,
      max_run_seconds: 120,
      pause_after_action: 0.25,
      desktop_autonomy_mode: "autonomous",
      approval_policy: "autonomous",
      complex_task_planning: "hybrid",
      plan_review_policy: "never",
      max_task_subgoals: 3,
      max_subgoal_retries: 2,
      stage_review_policy: "risk_change",
      max_replans_per_run: 4,
      max_failures_per_subgoal: 5,
      replan_on_recoverable_error: true,
      recoverable_error_retry_limit: 2,
    },
    execution_environment: {
      browser_control_mode: "hybrid",
      browser_dom_backend: "playwright",
      browser_dom_timeout: 4,
      browser_headless: true,
      browser_channel: "chrome",
      cursor_motion_enabled: true,
      cursor_motion_duration: 0.35,
      display_override_enabled: true,
      display_override_monitor_device_name: "DISPLAY2",
      generic_app_launch_enabled: false,
      shell_recipe_policy: "approval_required",
    },
    intent: { task_type: "desktop_app", risk_level: "low" },
    task_graph: {
      subgoals: [
        { id: "subgoal_01", title: "Open calculator", status: "pending", capability_preference: "desktop_gui" },
        { id: "subgoal_02", title: "Type 7+8", status: "pending", capability_preference: "desktop_gui" },
      ],
    },
    plan_health: {
      counts: { total: 2, completed: 0, ready: 1, blocked: 0 },
      next_subgoal_id: "subgoal_01",
      autonomy: {
        status: "ready",
        can_continue: true,
        next_action: "execute",
        blockers: [],
        warnings: [],
      },
      items: [
        { id: "subgoal_01", title: "Open calculator", status: "pending", capability_preference: "desktop_gui", ready: true, is_next: true },
        { id: "subgoal_02", title: "Type 7+8", status: "pending", capability_preference: "desktop_gui", ready: false },
      ],
    },
  };
  context.__appTest.state.taskPreviewConfigSignature = context.__appTest.buildConfigSignature(
    context.__appTest.originals.buildRunConfigOverrides()
  );

  const html = context.__appTest.renderTaskPreviewMessage();

  assert.match(html, /Agent preview/);
  assert.match(html, /assistant-card--run-preview/);
  assert.match(html, /Open calculator/);
  assert.match(html, /Type 7\+8/);
  assert.match(html, /Budget/);
  assert.match(html, /8 steps \/ 2m/);
  assert.match(html, /Action pause: 0\.25s/);
  assert.match(html, /Autonomy: Autonomous/);
  assert.match(html, /Planning: Hybrid/);
  assert.match(html, /Approval: High autonomy/);
  assert.match(html, /Plan review: No review/);
  assert.match(html, /Stage review: Risk change/);
  assert.match(html, /Subgoals: 3/);
  assert.match(html, /Retries: 2/);
  assert.match(html, /Replans: 4/);
  assert.match(html, /Failures: 5/);
  assert.match(html, /Plan timeout: 9\.5s/);
  assert.match(html, /Recovery: on x2/);
  assert.match(html, /Browser: hybrid \/ playwright/);
  assert.match(html, /DOM timeout: 4s/);
  assert.match(html, /Launch: chrome headless/);
  assert.match(html, /Pointer: on 0\.35s/);
  assert.match(html, /Display: DISPLAY2/);
  assert.match(html, /Known apps only/);
  assert.match(html, /Shell: Approval required/);
  assert.match(html, /Autonomy/);
  assert.match(html, /Ready to continue/);
  assert.match(html, /data-submit-preview-task=/);
  assert.match(html, /data-preview-task=/);
  assert.match(html, /data-next-subgoal="subgoal_01"/);
  assert.match(html, /Start run/);
  assert.doesNotMatch(html, /Approve and start/);
  assert.doesNotMatch(html, /Ambiguous/);
});

await runTest("task preview card makes review-required launch explicit", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.taskPreviewTask = "Submit the payment form";
  context.__appTest.state.taskPreview = {
    task: "Submit the payment form",
    task_graph_signature: "preview-render-review",
    risk_level: "high",
    ambiguous: false,
    requires_review: true,
    execution_budget: {
      max_steps: 5,
      max_run_seconds: 60,
      pause_after_action: 0.1,
    },
    intent: { task_type: "web_action", risk_level: "high" },
    task_graph: {
      subgoals: [
        { id: "subgoal_01", title: "Review payment form", status: "pending", capability_preference: "browser_dom" },
      ],
    },
    plan_health: {
      counts: { total: 1, completed: 0, ready: 0, blocked: 0 },
      next_subgoal_id: "subgoal_01",
      autonomy: {
        status: "review_required",
        can_continue: false,
        requires_review: true,
        next_action: "approve_plan",
        blockers: ["Plan review is required before execution."],
        warnings: [],
      },
      items: [
        { id: "subgoal_01", title: "Review payment form", status: "pending", capability_preference: "browser_dom", ready: false, is_next: true },
      ],
    },
  };
  context.__appTest.state.taskPreviewConfigSignature = context.__appTest.buildConfigSignature(
    context.__appTest.originals.buildRunConfigOverrides()
  );

  const html = context.__appTest.renderTaskPreviewMessage();

  assert.match(html, /Review/);
  assert.match(html, /Approval before execution/);
  assert.match(html, /Approve and start/);
  assert.doesNotMatch(html, /Start run/);
});

await runTest("task preview infers review-required launch from autonomy health", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.taskPreviewTask = "Review a staged browser change";
  context.__appTest.state.taskPreview = {
    task: "Review a staged browser change",
    task_graph_signature: "preview-render-autonomy-review",
    risk_level: "medium",
    requires_review: false,
    task_graph: {
      subgoals: [
        { id: "subgoal_01", title: "Review staged change", status: "pending", capability_preference: "browser_dom" },
      ],
    },
    plan_health: {
      counts: { total: 1, completed: 0, ready: 0, blocked: 0 },
      next_subgoal_id: "subgoal_01",
      autonomy: {
        status: "review_required",
        can_continue: false,
        next_action: "approve_plan",
        blockers: ["Plan review is required before execution."],
      },
      items: [
        { id: "subgoal_01", title: "Review staged change", status: "pending", ready: false, is_next: true },
      ],
    },
  };
  context.__appTest.state.taskPreviewConfigSignature = context.__appTest.buildConfigSignature(
    context.__appTest.originals.buildRunConfigOverrides()
  );

  const html = context.__appTest.renderTaskPreviewMessage();

  assert.match(html, /Review/);
  assert.match(html, /Approval before execution/);
  assert.match(html, /Approve and start/);
  assert.doesNotMatch(html, /Start run/);
});

await runTest("task preview blocks launch when autonomy needs clarification", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.uiMode = "agent";
  context.__appTest.state.taskPreviewTask = "Do the thing";
  context.__appTest.state.taskPreview = {
    task: "Do the thing",
    task_graph_signature: "preview-needs-clarification",
    requires_review: false,
    task_graph: {
      task: "Do the thing",
      subgoals: [
        { id: "subgoal_01", title: "Clarify the missing target", status: "pending", goal_type: "clarify" },
      ],
      dependencies: { subgoal_01: [] },
    },
    plan_health: {
      counts: { total: 1, completed: 0, ready: 1, blocked: 0 },
      next_subgoal_id: "subgoal_01",
      autonomy: {
        status: "needs_clarification",
        can_continue: false,
        requires_user: true,
        next_action: "ask_user",
        blockers: ["Choose a destination folder before starting."],
      },
      items: [
        { id: "subgoal_01", title: "Clarify the missing target", status: "pending", ready: true, is_next: true },
      ],
    },
  };
  context.__appTest.state.taskPreviewConfigSignature = context.__appTest.buildConfigSignature(
    context.__appTest.originals.buildConfigOverrides()
  );

  const html = context.__appTest.renderTaskPreviewMessage();

  assert.match(html, /Needs input/);
  assert.match(html, /Choose a destination folder before starting\./);
  assert.match(html, /Refresh preview/);
  assert.doesNotMatch(html, /data-submit-preview-task=/);
  assert.doesNotMatch(html, /Start run/);

  context.__postJsonCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload });
  throw new Error("Clarification preview should not submit.");
};
renderAll = () => {};
`,
    context
  );

  await context.__appTest.handleInteractiveClick({
    target: {
      closest(selector) {
        if (selector === "[data-submit-preview-task]") {
          return { dataset: { submitPreviewTask: "Do the thing" } };
        }
        return null;
      },
    },
  });

  assert.equal(context.__postJsonCalls.length, 0);
  assert.equal(context.__appTest.state.taskPreviewError, "");
  assert.equal(context.__appTest.state.taskPreviewStartError, "Choose a destination folder before starting.");
  assert.equal(context.document.getElementById("submitHint").textContent, "Choose a destination folder before starting.");

  await context.__appTest.submitAgentTask("Do the thing");

  assert.equal(context.__postJsonCalls.length, 0);
  assert.equal(context.document.getElementById("submitHint").textContent, "Choose a destination folder before starting.");
  assert.match(context.__appTest.renderTaskPreviewMessage(), /Needs input/);
  assert.doesNotMatch(context.__appTest.renderTaskPreviewMessage(), /Preview failed/);
});

await runTest("task preview honors backend start blocker even when local health looks ready", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.uiMode = "agent";
  context.__appTest.state.taskPreviewTask = "Open calculator and type 7+8";
  context.__appTest.state.taskPreview = {
    task: "Open calculator and type 7+8",
    task_graph_signature: "preview-backend-blocked",
    can_start: false,
    start_blocker: "The backend planner requires a refreshed preview before starting.",
    task_graph: {
      task: "Open calculator and type 7+8",
      subgoals: [{ id: "subgoal_01", title: "Open calculator", status: "pending", capability_preference: "desktop_gui" }],
      dependencies: { subgoal_01: [] },
    },
    plan_health: {
      counts: { total: 1, completed: 0, ready: 1, blocked: 0 },
      next_subgoal_id: "subgoal_01",
      autonomy: { status: "ready", can_continue: true, next_action: "execute", blockers: [] },
      items: [{ id: "subgoal_01", title: "Open calculator", status: "pending", ready: true, is_next: true }],
    },
  };
  context.__appTest.state.taskPreviewConfigSignature = context.__appTest.buildConfigSignature(
    context.__appTest.originals.buildConfigOverrides()
  );

  const html = context.__appTest.renderTaskPreviewMessage();

  assert.match(html, /Needs refresh/);
  assert.match(html, /The backend planner requires a refreshed preview before starting\./);
  assert.match(html, /Blocked/);
  assert.doesNotMatch(html, /Ready to continue/);
  assert.doesNotMatch(html, /data-submit-preview-task=/);

  context.__postJsonCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload });
  throw new Error("Backend-blocked preview should not submit.");
};
renderAll = () => {};
`,
    context
  );

  await context.__appTest.submitAgentTask("Open calculator and type 7+8");

  assert.equal(context.__postJsonCalls.length, 0);
  assert.equal(context.__appTest.state.taskPreviewStartError, "The backend planner requires a refreshed preview before starting.");
  assert.equal(context.document.getElementById("submitHint").textContent, "The backend planner requires a refreshed preview before starting.");
});

await runTest("task preview request surfaces backend start blocker in the composer hint", async () => {
  const context = createHarness();
  const task = "Open calculator and type 7+8";
  const blocker = "The backend planner requires a refreshed preview before starting.";
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.uiMode = "agent";
  context.__appTest.state.hydrated = true;
  context.__postJsonCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
  return {
    ok: true,
    payload: {
      task: payload.task,
      task_graph_signature: "preview-backend-blocked-live",
      can_start: false,
      start_blocker: ${JSON.stringify(blocker)},
      task_graph: {
        task: payload.task,
        subgoals: [{ id: "subgoal_01", title: "Open calculator", status: "pending", capability_preference: "desktop_gui" }],
        dependencies: { subgoal_01: [] },
      },
      plan_health: {
        counts: { total: 1, completed: 0, ready: 1, blocked: 0 },
        next_subgoal_id: "subgoal_01",
        autonomy: { status: "ready", can_continue: true, next_action: "execute", blockers: [] },
        items: [{ id: "subgoal_01", title: "Open calculator", status: "pending", ready: true, is_next: true }],
      },
    },
  };
};
renderAll = () => {};
`,
    context
  );

  await context.__appTest.handleInteractiveClick({
    target: {
      closest(selector) {
        if (selector === "[data-preview-task]") {
          return { dataset: { previewTask: task } };
        }
        return null;
      },
    },
  });

  assert.equal(context.__postJsonCalls.length, 1);
  assert.equal(context.__postJsonCalls[0].url, "/api/tasks/preview");
  assert.equal(context.__appTest.state.taskPreview.task_graph_signature, "preview-backend-blocked-live");
  assert.equal(context.__appTest.state.taskPreviewStartError, "");
  assert.equal(context.document.getElementById("submitHint").textContent, blocker);
  const html = context.__appTest.renderTaskPreviewMessage();
  assert.match(html, /Needs refresh/);
  assert.match(html, /The backend planner requires a refreshed preview before starting\./);
  assert.doesNotMatch(html, /data-submit-preview-task=/);
});

await runTest("plan preview from welcome opens a visible agent session", async () => {
  const context = createHarness();
  const task = "Open calculator and type 7+8";
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.uiMode = "agent";
  context.__appTest.state.hydrated = true;
  context.__appTest.state.showWelcome = true;
  context.__appTest.state.agentSessions = [];
  context.__appTest.state.selectedAgentSessionId = null;
  context.__postJsonCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
  return {
    ok: true,
    payload: {
      task: payload.task,
      task_graph_signature: "preview-visible-session",
      risk_level: "low",
      execution_budget: {
        max_steps: 8,
        max_run_seconds: 120,
        pause_after_action: 0.25,
        desktop_autonomy_mode: "autonomous",
        approval_policy: "autonomous",
        complex_task_planning: "heuristic",
        plan_review_policy: "never",
        max_task_subgoals: 3,
        stage_review_policy: "risk_change",
        max_replans_per_run: 4,
        replan_on_recoverable_error: true,
        recoverable_error_retry_limit: 2,
      },
      task_graph: {
        task: payload.task,
        subgoals: [{ id: "subgoal_01", title: "Open calculator", status: "pending", capability_preference: "desktop_gui" }],
        dependencies: { subgoal_01: [] },
      },
      plan_health: {
        counts: { total: 1, completed: 0, ready: 1, blocked: 0 },
        next_subgoal_id: "subgoal_01",
        autonomy: { status: "ready", can_continue: true, next_action: "execute", blockers: [] },
        items: [{ id: "subgoal_01", title: "Open calculator", status: "pending", ready: true, is_next: true }],
      },
    },
  };
};
renderAll = globalThis.__appTest.renderAll;
`,
    context
  );

  await context.__appTest.handleInteractiveClick({
    target: {
      closest(selector) {
        if (selector === "[data-preview-task]") {
          return { dataset: { previewTask: task } };
        }
        return null;
      },
    },
  });

  assert.equal(context.__postJsonCalls.length, 1);
  assert.equal(context.__appTest.state.showWelcome, false);
  assert.equal(context.__appTest.state.agentSessions.length, 1);
  assert.equal(context.__appTest.state.agentSessions[0].title, task);
  assert.equal(context.__appTest.loadPersistedHistorySelection().id, context.__appTest.state.selectedAgentSessionId);
  assert.equal(context.document.getElementById("chatStream").dataset.context, "agent-session");
  const html = context.document.getElementById("chatStream").innerHTML;
  assert.match(html, /assistant-card--run-preview/);
  assert.match(html, /Autonomy: Autonomous/);
  assert.match(html, /Planning: Heuristic/);
  assert.doesNotMatch(html, /chat-welcome/);
});

await runTest("plan preview click waits for the backend preview response", async () => {
  const context = createHarness();
  const task = "Open calculator and type 7+8";
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.uiMode = "agent";
  context.__appTest.state.hydrated = true;
  context.__postJsonCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
  return new Promise((resolve) => {
    globalThis.__resolvePreviewRequest = () => resolve({
      ok: true,
      payload: {
        task: payload.task,
        task_graph_signature: "preview-click-waited",
        task_graph: {
          task: payload.task,
          subgoals: [{ id: "subgoal_01", title: "Open calculator", status: "pending", capability_preference: "desktop_gui" }],
          dependencies: { subgoal_01: [] },
        },
        plan_health: {
          counts: { total: 1, completed: 0, ready: 1, blocked: 0 },
          next_subgoal_id: "subgoal_01",
          autonomy: { status: "ready", can_continue: true, next_action: "execute", blockers: [] },
          items: [{ id: "subgoal_01", title: "Open calculator", status: "pending", ready: true, is_next: true }],
        },
      },
    });
  });
};
renderAll = () => {};
`,
    context
  );

  let handlerSettled = false;
  const previewClick = context.__appTest.handleInteractiveClick({
    target: {
      closest(selector) {
        if (selector === "[data-preview-task]") {
          return { dataset: { previewTask: task } };
        }
        return null;
      },
    },
  });
  previewClick.then(() => {
    handlerSettled = true;
  });
  await Promise.resolve();

  assert.equal(context.__postJsonCalls.length, 1);
  assert.equal(context.__postJsonCalls[0].url, "/api/tasks/preview");
  assert.equal(context.__appTest.state.taskPreviewLoading, true);
  assert.equal(handlerSettled, false);

  context.__resolvePreviewRequest();
  await previewClick;

  assert.equal(handlerSettled, true);
  assert.equal(context.__appTest.state.taskPreviewLoading, false);
  assert.equal(context.__appTest.state.taskPreview.task_graph_signature, "preview-click-waited");
  assert.equal(context.document.getElementById("submitHint").textContent, "Plan preview ready");
});

await runTest("duplicate plan preview clicks are ignored while the first request is in flight", async () => {
  const context = createHarness();
  const task = "Open calculator and type 7+8";
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.uiMode = "agent";
  context.__appTest.state.hydrated = true;
  context.__postJsonCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
  return new Promise((resolve) => {
    globalThis.__resolvePreviewRequest = () => resolve({
      ok: true,
      payload: {
        task: payload.task,
        task_graph_signature: "preview-deduped",
        task_graph: {
          task: payload.task,
          subgoals: [{ id: "subgoal_01", title: "Open calculator", status: "pending", capability_preference: "desktop_gui" }],
          dependencies: { subgoal_01: [] },
        },
      },
    });
  });
};
renderAll = () => {};
`,
    context
  );
  const clickEvent = {
    target: {
      closest(selector) {
        if (selector === "[data-preview-task]") {
          return { dataset: { previewTask: task } };
        }
        return null;
      },
    },
  };

  const firstClick = context.__appTest.handleInteractiveClick(clickEvent);
  await Promise.resolve();
  assert.equal(context.__postJsonCalls.length, 1);
  assert.equal(context.__appTest.state.taskPreviewLoading, true);

  await context.__appTest.handleInteractiveClick(clickEvent);

  assert.equal(context.__postJsonCalls.length, 1);
  assert.equal(context.__appTest.state.taskPreviewLoading, true);
  assert.equal(context.document.getElementById("submitHint").textContent, "Generating plan preview");

  context.__resolvePreviewRequest();
  await firstClick;

  assert.equal(context.__appTest.state.taskPreviewLoading, false);
  assert.equal(context.__appTest.state.taskPreview.task_graph_signature, "preview-deduped");
});

await runTest("agent task submission waits for an in-flight plan preview", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.uiMode = "agent";
  context.__appTest.state.hydrated = true;
  context.__appTest.state.taskPreviewTask = "Open calculator";
  context.__appTest.state.taskPreviewLoading = true;
  context.__postJsonCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload });
  throw new Error("Task submission should wait for the in-flight preview.");
};
renderAll = () => {};
`,
    context
  );

  vm.runInContext("renderComposerState(getAgentConversationContext())", context);
  assert.equal(context.document.getElementById("submitButton").disabled, true);
  assert.equal(context.document.getElementById("previewTaskButton").disabled, true);
  assert.equal(context.document.getElementById("submitHint").textContent, "Generating plan preview");

  await context.__appTest.submitAgentTask("Open calculator");

  assert.equal(context.__postJsonCalls.length, 0);
  assert.equal(context.__appTest.state.pendingTask, null);
  assert.equal(context.__appTest.state.activeJob, null);
  assert.equal(context.document.getElementById("submitHint").textContent, "Generating plan preview");
});

await runTest("task preview start is gated when the preview is not signed", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.uiMode = "agent";
  context.__appTest.state.taskPreviewTask = "Open calculator and type 7+8";
  context.__appTest.state.taskPreview = {
    task: "Open calculator and type 7+8",
    requires_review: false,
    task_graph: {
      task: "Open calculator and type 7+8",
      subgoals: [{ id: "subgoal_01", title: "Open calculator", status: "pending", capability_preference: "desktop_gui" }],
      dependencies: { subgoal_01: [] },
    },
  };
  context.__appTest.state.taskPreviewConfigSignature = context.__appTest.buildConfigSignature(
    context.__appTest.originals.buildRunConfigOverrides()
  );

  const html = context.__appTest.renderTaskPreviewMessage();

  assert.match(html, /Needs refresh/);
  assert.match(html, /Refresh preview/);
  assert.doesNotMatch(html, /data-submit-preview-task=/);

  context.__postJsonCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload });
  throw new Error("Unsigned preview should not submit.");
};
renderAll = () => {};
`,
    context
  );

  await context.__appTest.handleInteractiveClick({
    target: {
      closest(selector) {
        if (selector === "[data-submit-preview-task]") {
          return { dataset: { submitPreviewTask: "Open calculator and type 7+8" } };
        }
        return null;
      },
    },
  });

  assert.equal(context.__postJsonCalls.length, 0);
  assert.equal(context.__appTest.state.taskPreviewError, "");
  assert.equal(context.__appTest.state.taskPreviewStartError, "Refresh the plan preview before starting.");
  assert.equal(context.document.getElementById("submitHint").textContent, "Refresh the plan preview before starting.");
});

await runTest("submitting from preview sends the matching task graph", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.uiMode = "agent";
  context.__appTest.state.taskPreviewTask = "Open calculator and type 7+8";
  context.__appTest.state.taskPreview = {
    task: "Open calculator and type 7+8",
    task_graph_signature: "preview-signature-123",
    task_graph: {
      task: "Open calculator and type 7+8",
      subgoals: [
        { id: "subgoal_01", title: "Open calculator", status: "pending", capability_preference: "desktop_gui" },
        { id: "subgoal_02", title: "Type 7+8", status: "pending", capability_preference: "desktop_gui" },
      ],
      dependencies: { subgoal_01: [], subgoal_02: ["subgoal_01"] },
      intent: { task_type: "desktop_app", risk_level: "low" },
    },
  };
  context.__appTest.state.taskPreviewConfigSignature = context.__appTest.buildConfigSignature(
    context.__appTest.originals.buildConfigOverrides()
  );
  context.__postJsonCalls = [];
  context.__refreshCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
  return {
    ok: true,
    payload: {
      id: "job-preview",
      task: "Open calculator and type 7+8",
      status: "approval",
      result: {
        latest_summary: "Review the generated plan.",
        pending_decision: {
          decision_type: "plan_review",
          summary: "Review the generated plan before continuing.",
        },
        execution_state: {
          plan_health: {
            counts: { total: 2, completed: 0, ready: 1, blocked: 0 },
            autonomy: { status: "review_required", can_continue: false, next_action: "approve_plan" },
          },
        },
      },
    },
  };
};
refreshOverview = async (options) => {
  globalThis.__refreshCalls.push(JSON.parse(JSON.stringify(options || {})));
  globalThis.__activeJobAtRefresh = JSON.parse(JSON.stringify(state.activeJob || null));
};
`,
    context
  );

  await context.__appTest.submitAgentTask("Open calculator and type 7+8");

  assert.equal(context.__postJsonCalls.length, 1);
  assert.equal(context.__postJsonCalls[0].url, "/api/tasks");
  assert.equal(context.__postJsonCalls[0].payload.task_graph.subgoals[0].id, "subgoal_01");
  assert.equal(context.__postJsonCalls[0].payload.task_graph_signature, "preview-signature-123");
  assert.equal("task_graph_review_status" in context.__postJsonCalls[0].payload, false);
  assert.equal(JSON.stringify(context.__postJsonCalls[0].payload.task_graph.dependencies.subgoal_02), '["subgoal_01"]');
  assert.equal(context.__appTest.state.pendingTask, null);
  assert.equal(context.__activeJobAtRefresh.id, "job-preview");
  assert.equal(context.__activeJobAtRefresh.status, "approval");
  assert.equal(context.__activeJobAtRefresh.result.execution_state.plan_health.autonomy.status, "review_required");
  assert.equal(context.document.getElementById("submitHint").textContent, "Awaiting approval");
  assert.equal(JSON.stringify(context.__refreshCalls), '[{"forceLatest":true}]');
  assert.equal(context.__appTest.state.taskPreview, null);
});

await runTest("backend preview rejection keeps the visible preview blocked", async () => {
  const context = createHarness();
  const task = "Open calculator and type 7+8";
  const serverError = "Task graph signature does not match the current task or configuration. Refresh the plan preview.";
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.uiMode = "agent";
  context.__appTest.state.taskPreviewTask = task;
  context.__appTest.state.taskPreview = {
    task,
    task_graph_signature: "preview-signature-rejected",
    task_graph: {
      task,
      subgoals: [
        { id: "subgoal_01", title: "Open calculator", status: "pending", capability_preference: "desktop_gui" },
      ],
      dependencies: { subgoal_01: [] },
      intent: { task_type: "desktop_app", risk_level: "low" },
    },
  };
  context.__appTest.state.taskPreviewConfigSignature = context.__appTest.buildConfigSignature(
    context.__appTest.originals.buildConfigOverrides()
  );
  context.__postJsonCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
  return { ok: false, payload: { error: ${JSON.stringify(serverError)} } };
};
renderAll = () => {};
`,
    context
  );

  await context.__appTest.submitAgentTask(task);

  assert.equal(context.__postJsonCalls.length, 1);
  assert.equal(context.__postJsonCalls[0].payload.task_graph_signature, "preview-signature-rejected");
  assert.equal(context.__appTest.state.pendingTask, null);
  assert.equal(context.__appTest.state.taskPreview.task_graph_signature, "preview-signature-rejected");
  assert.equal(context.__appTest.state.taskPreviewError, "");
  assert.equal(context.__appTest.state.taskPreviewStartError, serverError);
  assert.equal(context.document.getElementById("submitHint").textContent, serverError);
  const html = context.__appTest.renderTaskPreviewMessage();
  assert.match(html, /Needs refresh/);
  assert.match(html, /Task graph signature does not match/);
  assert.doesNotMatch(html, /data-submit-preview-task=/);

  await context.__appTest.submitAgentTask(task);

  assert.equal(context.__postJsonCalls.length, 1);
  assert.equal(context.document.getElementById("submitHint").textContent, serverError);
});


await runTest("starting from preview marks the matching plan as reviewed", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.uiMode = "agent";
  context.__appTest.state.taskPreviewTask = "Open calculator and type 7+8";
  context.__appTest.state.taskPreview = {
    task: "Open calculator and type 7+8",
    task_graph_signature: "preview-signature-approved",
    task_graph: {
      task: "Open calculator and type 7+8",
      subgoals: [
        { id: "subgoal_01", title: "Open calculator", status: "pending", capability_preference: "desktop_gui" },
      ],
      dependencies: { subgoal_01: [] },
      intent: { task_type: "desktop_app", risk_level: "medium" },
    },
  };
  context.__appTest.state.taskPreviewConfigSignature = context.__appTest.buildConfigSignature(
    context.__appTest.originals.buildConfigOverrides()
  );
  context.__postJsonCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
  return { ok: true, payload: { id: "job-preview-reviewed", task: payload.task, status: "running", result: {} } };
};
refreshOverview = async () => {};
`,
    context
  );

  await context.__appTest.submitAgentTask("Open calculator and type 7+8", { previewReviewed: true });

  assert.equal(context.__postJsonCalls.length, 1);
  assert.equal(context.__postJsonCalls[0].url, "/api/tasks");
  assert.equal(context.__postJsonCalls[0].payload.task_graph_signature, "preview-signature-approved");
  assert.equal(context.__postJsonCalls[0].payload.task_graph_review_status, "approved");
  assert.equal(context.__postJsonCalls[0].payload.task_graph_review_signature, "preview-signature-approved");
});

await runTest("preview start click only approves review-required plans", async () => {
  const createPreviewClickEvent = () => ({
    target: {
      closest(selector) {
        if (selector === "[data-submit-preview-task]") {
          return { dataset: { submitPreviewTask: "Open calculator and type 7+8" } };
        }
        return null;
      },
    },
  });

  const readyContext = createHarness();
  readyContext.__appTest.state.locale = "en-US";
  readyContext.__appTest.state.uiMode = "agent";
  readyContext.__appTest.state.taskPreviewTask = "Open calculator and type 7+8";
  readyContext.__appTest.state.taskPreview = {
    task: "Open calculator and type 7+8",
    requires_review: false,
    task_graph_signature: "preview-signature-ready",
    task_graph: {
      task: "Open calculator and type 7+8",
      subgoals: [{ id: "subgoal_01", title: "Open calculator", status: "pending", capability_preference: "desktop_gui" }],
      dependencies: { subgoal_01: [] },
    },
  };
  readyContext.__appTest.state.taskPreviewConfigSignature = readyContext.__appTest.buildConfigSignature(
    readyContext.__appTest.originals.buildConfigOverrides()
  );
  readyContext.__postJsonCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
  return { ok: true, payload: { id: "job-preview-ready", task: payload.task, status: "running", result: {} } };
};
refreshOverview = async () => {};
renderAll = () => {};
`,
    readyContext
  );

  await readyContext.__appTest.handleInteractiveClick(createPreviewClickEvent());
  await Promise.resolve();

  assert.equal(readyContext.__postJsonCalls.length, 1);
  assert.equal(readyContext.__postJsonCalls[0].payload.task_graph_signature, "preview-signature-ready");
  assert.equal("task_graph_review_status" in readyContext.__postJsonCalls[0].payload, false);

  const reviewContext = createHarness();
  reviewContext.__appTest.state.locale = "en-US";
  reviewContext.__appTest.state.uiMode = "agent";
  reviewContext.__appTest.state.taskPreviewTask = "Open calculator and type 7+8";
  reviewContext.__appTest.state.taskPreview = {
    task: "Open calculator and type 7+8",
    requires_review: true,
    task_graph_signature: "preview-signature-review",
    task_graph: {
      task: "Open calculator and type 7+8",
      subgoals: [{ id: "subgoal_01", title: "Open calculator", status: "pending", capability_preference: "desktop_gui" }],
      dependencies: { subgoal_01: [] },
    },
  };
  reviewContext.__appTest.state.taskPreviewConfigSignature = reviewContext.__appTest.buildConfigSignature(
    reviewContext.__appTest.originals.buildConfigOverrides()
  );
  reviewContext.__postJsonCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
  return { ok: true, payload: { id: "job-preview-review", task: payload.task, status: "running", result: {} } };
};
refreshOverview = async () => {};
renderAll = () => {};
`,
    reviewContext
  );

  await reviewContext.__appTest.handleInteractiveClick(createPreviewClickEvent());
  await Promise.resolve();

  assert.equal(reviewContext.__postJsonCalls.length, 1);
  assert.equal(reviewContext.__postJsonCalls[0].payload.task_graph_signature, "preview-signature-review");
  assert.equal(reviewContext.__postJsonCalls[0].payload.task_graph_review_status, "approved");
  assert.equal(reviewContext.__postJsonCalls[0].payload.task_graph_review_signature, "preview-signature-review");

  const autonomyContext = createHarness();
  autonomyContext.__appTest.state.locale = "en-US";
  autonomyContext.__appTest.state.uiMode = "agent";
  autonomyContext.__appTest.state.taskPreviewTask = "Open calculator and type 7+8";
  autonomyContext.__appTest.state.taskPreview = {
    task: "Open calculator and type 7+8",
    requires_review: false,
    task_graph_signature: "preview-signature-autonomy-review",
    task_graph: {
      task: "Open calculator and type 7+8",
      subgoals: [{ id: "subgoal_01", title: "Open calculator", status: "pending", capability_preference: "desktop_gui" }],
      dependencies: { subgoal_01: [] },
    },
    plan_health: {
      autonomy: { status: "review_required", can_continue: false, next_action: "approve_plan" },
    },
  };
  autonomyContext.__appTest.state.taskPreviewConfigSignature = autonomyContext.__appTest.buildConfigSignature(
    autonomyContext.__appTest.originals.buildConfigOverrides()
  );
  autonomyContext.__postJsonCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
  return { ok: true, payload: { id: "job-preview-autonomy-review", task: payload.task, status: "running", result: {} } };
};
refreshOverview = async () => {};
renderAll = () => {};
`,
    autonomyContext
  );

  await autonomyContext.__appTest.handleInteractiveClick(createPreviewClickEvent());
  await Promise.resolve();

  assert.equal(autonomyContext.__postJsonCalls.length, 1);
  assert.equal(autonomyContext.__postJsonCalls[0].payload.task_graph_signature, "preview-signature-autonomy-review");
  assert.equal(autonomyContext.__postJsonCalls[0].payload.task_graph_review_status, "approved");
  assert.equal(autonomyContext.__postJsonCalls[0].payload.task_graph_review_signature, "preview-signature-autonomy-review");
});


await runTest("unsigned preview graph is not submitted", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.uiMode = "agent";
  context.__appTest.state.taskPreviewTask = "Open calculator and type 7+8";
  context.__appTest.state.taskPreview = {
    task: "Open calculator and type 7+8",
    task_graph: {
      task: "Open calculator and type 7+8",
      subgoals: [
        { id: "subgoal_01", title: "Open calculator", status: "pending", capability_preference: "desktop_gui" },
      ],
      dependencies: { subgoal_01: [] },
    },
  };
  context.__appTest.state.taskPreviewConfigSignature = context.__appTest.buildConfigSignature(
    context.__appTest.originals.buildConfigOverrides()
  );
  context.__postJsonCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
  return { ok: true, payload: { id: "job-unsigned-preview", task: payload.task, status: "running" } };
};
refreshOverview = async () => {};
`,
    context
  );

  await context.__appTest.submitAgentTask("Open calculator and type 7+8");

  assert.equal(context.__postJsonCalls.length, 1);
  assert.equal(context.__postJsonCalls[0].url, "/api/tasks");
  assert.equal("task_graph" in context.__postJsonCalls[0].payload, false);
  assert.equal("task_graph_signature" in context.__postJsonCalls[0].payload, false);
  assert.equal(context.__appTest.state.taskPreview, null);
});


await runTest("agent task submission ignores duplicate clicks while the first request is pending", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.uiMode = "agent";
  context.__postJsonCalls = [];
  let resolvePostJson;
  vm.runInContext(
    `
postJson = (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
  return new Promise((resolve) => {
    globalThis.__resolvePostJson = resolve;
  });
};
refreshOverview = async () => {};
renderAll = () => {};
`,
    context
  );

  const firstSubmission = context.__appTest.submitAgentTask("Open calculator");
  await Promise.resolve();
  await context.__appTest.submitAgentTask("Open calculator");
  resolvePostJson = context.__resolvePostJson;

  assert.equal(context.__postJsonCalls.length, 1);
  assert.equal(context.__appTest.state.pendingTask, "Open calculator");
  assert.equal(context.document.getElementById("submitHint").textContent, "A task is already running");
  context.__appTest.state.hydrated = true;
  vm.runInContext("renderComposerState({ type: 'pending' })", context);
  assert.equal(context.document.getElementById("taskInput").disabled, true);
  assert.equal(context.document.getElementById("submitButton").disabled, true);
  assert.equal(context.document.getElementById("previewTaskButton").disabled, true);

  resolvePostJson({
    ok: true,
    payload: {
      id: "job-single-submit",
      task: "Open calculator",
      status: "running",
      result: { latest_summary: "Starting calculator." },
    },
  });
  await firstSubmission;

  assert.equal(context.__postJsonCalls.length, 1);
  assert.equal(context.__appTest.state.activeJob.id, "job-single-submit");
  assert.equal(context.__appTest.state.pendingTask, null);
});

await runTest("stale overview refresh does not clear a newly submitted active job", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.uiMode = "agent";
  context.__appTest.state.hydrated = true;
  context.__staleOverviewPayload = buildOverviewPayload();
  context.__postJsonCalls = [];
  vm.runInContext(
    `
fetchJson = async (url) => {
  if (url === "/api/overview") {
    return new Promise((resolve) => {
      globalThis.__resolveStaleOverview = () => resolve(globalThis.__staleOverviewPayload);
    });
  }
  throw new Error("Unexpected fetchJson URL: " + url);
};
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
  return {
    ok: true,
    payload: {
      id: "job-race-submit",
      task: payload.task,
      status: "running",
      result: { latest_summary: "Starting after submit." },
    },
  };
};
renderAll = () => {};
`,
    context
  );

  const staleRefresh = context.__appTest.refreshOverview({ background: true });
  await Promise.resolve();
  assert.equal(context.__appTest.state.overviewFetchInFlight, true);

  await context.__appTest.submitAgentTask("Open calculator");

  assert.equal(context.__postJsonCalls.length, 1);
  assert.equal(context.__appTest.state.activeJob.id, "job-race-submit");
  assert.equal(context.__appTest.state.pendingTask, null);

  context.__resolveStaleOverview();
  await staleRefresh;

  assert.equal(context.__appTest.state.activeJob.id, "job-race-submit");
  assert.equal(context.__appTest.state.jobs[0].id, "job-race-submit");
  assert.equal(context.__appTest.state.pendingTask, null);
  assert.equal(context.__appTest.state.selectedAgentSessionId !== null, true);
  const session = context.__appTest.state.agentSessions.find((item) => item.id === context.__appTest.state.selectedAgentSessionId);
  assert.ok(session);
  assert.equal(session.pending_job_id, "job-race-submit");
  vm.runInContext("renderComposerState(getAgentConversationContext())", context);
  assert.equal(context.document.getElementById("taskInput").disabled, true);
  assert.equal(context.document.getElementById("submitButton").hidden, true);
});

await runTest("failed agent submission clears empty pending session selection", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.uiMode = "agent";
  context.__appTest.state.hydrated = true;
  context.__postJsonCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
  return { ok: false, payload: { error: "Planner service unavailable." } };
};
renderAll = () => {};
`,
    context
  );

  await context.__appTest.submitAgentTask("Open calculator");

  assert.equal(context.__postJsonCalls.length, 1);
  assert.equal(context.__postJsonCalls[0].url, "/api/tasks");
  assert.equal(context.__appTest.state.pendingTask, null);
  assert.equal(context.__appTest.state.selectedAgentSessionId, null);
  assert.equal(context.__appTest.state.showWelcome, true);
  assert.deepEqual(snapshot(context.__appTest.state.agentSessions), []);
  assert.equal(context.__appTest.loadPersistedHistorySelection(), null);
  assert.equal(context.document.getElementById("submitHint").textContent, "Planner service unavailable.");
  vm.runInContext("renderComposerState(getAgentConversationContext())", context);
  assert.equal(context.document.getElementById("taskInput").disabled, false);
  assert.equal(context.document.getElementById("submitButton").disabled, false);
  assert.equal(context.document.getElementById("previewTaskButton").disabled, false);
});

await runTest("agent submission without a job id clears pending state", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.uiMode = "agent";
  context.__appTest.state.hydrated = true;
  context.__postJsonCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
  return { ok: true, payload: { task: payload.task, status: "queued" } };
};
refreshOverview = async () => {
  throw new Error("Malformed task submissions should not refresh overview.");
};
renderAll = () => {};
`,
    context
  );

  await context.__appTest.submitAgentTask("Open calculator");

  assert.equal(context.__postJsonCalls.length, 1);
  assert.equal(context.__postJsonCalls[0].url, "/api/tasks");
  assert.equal(context.__appTest.state.activeJob, null);
  assert.equal(context.__appTest.state.pendingTask, null);
  assert.equal(context.__appTest.state.selectedAgentSessionId, null);
  assert.equal(context.__appTest.state.showWelcome, true);
  assert.deepEqual(snapshot(context.__appTest.state.agentSessions), []);
  assert.equal(context.__appTest.loadPersistedHistorySelection(), null);
  assert.equal(context.document.getElementById("submitHint").textContent, "Task submission did not return a trackable job id.");
  vm.runInContext("renderComposerState(getAgentConversationContext())", context);
  assert.equal(context.document.getElementById("taskInput").disabled, false);
  assert.equal(context.document.getElementById("submitButton").disabled, false);
  assert.equal(context.document.getElementById("previewTaskButton").disabled, false);
});

await runTest("plan preview shortcut is ignored while a resume request is pending", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.uiMode = "agent";
  context.__appTest.state.hydrated = true;
  context.__appTest.state.resumePendingRunId = "run-human";
  context.document.getElementById("taskInput").value = "Open calculator";
  context.__postJsonCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
  return { ok: true, payload: { task: payload.task, task_graph_signature: "should-not-preview" } };
};
renderAll = () => {};
`,
    context
  );

  const event = {
    target: {
      closest(selector) {
        if (selector === "[data-preview-task]") {
          return { dataset: { previewTask: "Open calculator" } };
        }
        return null;
      },
    },
  };

  await context.__appTest.handleInteractiveClick(event);

  assert.equal(context.__postJsonCalls.length, 0);
  assert.equal(context.__appTest.state.taskPreviewLoading, false);
  assert.equal(context.__appTest.state.taskPreviewTask, "");
  assert.equal(context.document.getElementById("submitHint").textContent, "A task is already running");
});

await runTest("new task keeps pending resume state until the request settles", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.uiMode = "agent";
  context.__appTest.state.pendingTask = "Resume the checkout";
  context.__appTest.state.resumePendingRunId = "run-checkout";
  context.__appTest.state.selectedAgentSessionId = "agent-session-checkout";
  context.__appTest.state.taskPreviewTask = "Open calculator";
  context.__appTest.state.taskPreviewConfigSignature = "stale-preview-signature";
  context.__appTest.state.taskPreview = {
    task: "Open calculator",
    task_graph_signature: "stale-preview-signature",
    task_graph: { task: "Open calculator", subgoals: [{ id: "subgoal_01", title: "Open calculator" }] },
  };
  vm.runInContext("startNewTask()", context);

  assert.equal(context.__appTest.state.pendingTask, "Resume the checkout");
  assert.equal(context.__appTest.state.resumePendingRunId, "run-checkout");
  assert.equal(context.__appTest.state.selectedAgentSessionId, "agent-session-checkout");
  assert.equal(context.__appTest.state.taskPreviewTask, "Open calculator");
  assert.equal(context.document.getElementById("submitHint").textContent, "A task is already running");
});

await runTest("history clear is blocked while a task request is pending", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.uiMode = "agent";
  context.__appTest.state.pendingTask = "Open calculator";
  context.__alerts = [];
  context.__postJsonCalls = [];
  vm.runInContext(
    `
window.alert = (message) => {
  globalThis.__alerts.push(message);
};
window.confirm = () => {
  throw new Error("confirm should not be called while a task is pending");
};
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload: JSON.parse(JSON.stringify(payload || {})) });
  return { ok: true, payload: { cleared: true } };
};
`,
    context
  );

  await vm.runInContext("clearHistoryRecords()", context);

  assert.deepEqual(context.__alerts, ["A task is still running, so history cannot be cleared yet."]);
  assert.equal(context.__postJsonCalls.length, 0);
  assert.equal(context.__appTest.state.pendingTask, "Open calculator");
});

await runTest("history navigation keeps pending task state until submission resolves", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.uiMode = "agent";
  context.__appTest.state.pendingTask = "Open calculator";
  context.__appTest.state.selectedRunId = "run-current";
  context.__appTest.state.selectedAgentSessionId = "agent-current";
  context.__appTest.state.runs = [
    { id: "run-current", task: "Open calculator", started_at: 100 },
    { id: "run-old", task: "Open notes", started_at: 50 },
  ];
  context.__appTest.state.agentSessions = [
    { id: "agent-current", title: "Open calculator", run_ids: ["run-current"], pending_task: "Open calculator" },
    { id: "agent-old", title: "Open notes", run_ids: ["run-old"], pending_task: "" },
  ];
  context.__appTest.state.agentRunSessionMap = { "run-current": "agent-current", "run-old": "agent-old" };
  context.__appTest.state.taskPreviewTask = "Open calculator";
  context.__appTest.state.taskPreviewConfigSignature = "preview-signature";
  context.__appTest.state.taskPreview = {
    task: "Open calculator",
    task_graph_signature: "preview-signature",
    task_graph: { task: "Open calculator", subgoals: [{ id: "subgoal_01", title: "Open calculator" }] },
  };

  vm.runInContext("selectRun('run-old', { manualSelection: true })", context);

  assert.equal(context.__appTest.state.pendingTask, "Open calculator");
  assert.equal(context.__appTest.state.selectedRunId, "run-current");
  assert.equal(context.__appTest.state.selectedAgentSessionId, "agent-current");
  assert.equal(context.__appTest.state.taskPreviewTask, "Open calculator");
  assert.deepEqual(context.__loadRunDetailsCalls, []);
  assert.equal(context.document.getElementById("submitHint").textContent, "A task is already running");

  vm.runInContext("selectAgentSession('agent-old')", context);

  assert.equal(context.__appTest.state.pendingTask, "Open calculator");
  assert.equal(context.__appTest.state.selectedRunId, "run-current");
  assert.equal(context.__appTest.state.selectedAgentSessionId, "agent-current");
  assert.deepEqual(context.__loadRunDetailsCalls, []);
});

await runTest("pending task is not satisfied by an older same-task run", async () => {
  const context = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.mode": "agent",
      "desktop-agent-workspace.agent-sessions": JSON.stringify([
        {
          id: "agent-new-submit",
          title: "Open calculator",
          created_at: 200,
          updated_at: 220,
          run_ids: [],
          pending_task: "Open calculator",
          pending_job_id: "",
        },
      ]),
      "desktop-agent-workspace.history-selection": JSON.stringify({ kind: "agent", id: "agent-new-submit" }),
    },
  });
  context.__appTest.state.locale = "en-US";

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  assert.equal(context.__appTest.state.pendingTask, "Open calculator");
  context.__overviewPayload = buildOverviewPayload({
    runs: [
      {
        id: "run-old-calc",
        task: "Open calculator",
        started_at: 100,
        finished_at: 120,
        completed: true,
      },
    ],
  });
  await context.__appTest.refreshOverview({ background: true });

  const pendingSession = context.__appTest.state.agentSessions.find((session) => session.id === "agent-new-submit");
  assert.equal(context.__appTest.state.pendingTask, "Open calculator");
  assert.equal(context.__appTest.state.selectedRunId, null);
  assert.ok(pendingSession);
  assert.deepEqual(snapshot(pendingSession.run_ids), []);
  assert.equal(pendingSession.pending_task, "Open calculator");
  assert.notEqual(context.__appTest.state.agentRunSessionMap["run-old-calc"], "agent-new-submit");
  assert.deepEqual(context.__loadRunDetailsCalls, []);
});

await runTest("pending task attaches to a fresh same-task run", async () => {
  const context = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.mode": "agent",
      "desktop-agent-workspace.agent-sessions": JSON.stringify([
        {
          id: "agent-fresh-submit",
          title: "Open calculator",
          created_at: 100,
          updated_at: 120,
          run_ids: [],
          pending_task: "Open calculator",
          pending_job_id: "",
        },
      ]),
      "desktop-agent-workspace.history-selection": JSON.stringify({ kind: "agent", id: "agent-fresh-submit" }),
    },
  });
  context.__appTest.state.locale = "en-US";

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  assert.equal(context.__appTest.state.pendingTask, "Open calculator");
  context.__overviewPayload = buildOverviewPayload({
    runs: [
      {
        id: "run-fresh-calc",
        task: "Open calculator",
        started_at: 121,
        finished_at: 140,
        completed: true,
      },
    ],
  });
  await context.__appTest.refreshOverview({ background: true });

  const pendingSession = context.__appTest.state.agentSessions.find((session) => session.id === "agent-fresh-submit");
  assert.equal(context.__appTest.state.pendingTask, null);
  assert.equal(context.__appTest.state.selectedRunId, "run-fresh-calc");
  assert.ok(pendingSession);
  assert.deepEqual(snapshot(pendingSession.run_ids), ["run-fresh-calc"]);
  assert.equal(pendingSession.pending_task, "");
  assert.equal(pendingSession.pending_job_id, "");
  assert.equal(context.__appTest.state.agentRunSessionMap["run-fresh-calc"], "agent-fresh-submit");
  assert.deepEqual(context.__loadRunDetailsCalls, ["run-fresh-calc"]);
});


await runTest("stale preview graph is not submitted after planning config changes", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.uiMode = "agent";
  context.__appTest.state.taskPreviewTask = "Open calculator and type 7+8";
  context.__appTest.state.taskPreviewConfigSignature = context.__appTest.buildConfigSignature({ max_task_subgoals: 2 });
  context.__appTest.state.taskPreview = {
    task: "Open calculator and type 7+8",
    task_graph: {
      task: "Open calculator and type 7+8",
      subgoals: [
        { id: "subgoal_01", title: "Open calculator", status: "pending", capability_preference: "desktop_gui" },
      ],
      dependencies: { subgoal_01: [] },
    },
  };
  context.__postJsonCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
  return { ok: true, payload: { id: "job-no-stale-preview" } };
};
`,
    context
  );

  await context.__appTest.submitAgentTask("Open calculator and type 7+8");

  assert.equal(context.__postJsonCalls.length, 1);
  assert.equal(context.__postJsonCalls[0].url, "/api/tasks");
  assert.equal("task_graph" in context.__postJsonCalls[0].payload, false);
  assert.equal(context.__appTest.state.taskPreview, null);
});

await runTest("preview graph submission keeps max run seconds in signature scope", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.uiMode = "agent";
  context.document.getElementById("maxRunSecondsInput").value = "42";
  const task = "Open calculator and type 7+8";
  const runConfig = {
    ...context.__appTest.originals.buildConfigOverrides(),
    max_run_seconds: 42,
  };
  context.__appTest.state.taskPreviewTask = task;
  context.__appTest.state.taskPreviewConfigSignature = context.__appTest.buildConfigSignature(runConfig);
  context.__appTest.state.taskPreview = {
    task,
    task_graph: {
      task,
      subgoals: [
        { id: "subgoal_01", title: "Open calculator", status: "pending", capability_preference: "desktop_gui" },
      ],
      dependencies: { subgoal_01: [] },
    },
    task_graph_signature: "preview-with-run-limit",
  };
  context.__postJsonCalls = [];
  vm.runInContext(
    `
postJson = async (url, payload) => {
  globalThis.__postJsonCalls.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
  return { ok: true, payload: { id: "job-preview-run-limit", task: payload.task, status: "running" } };
};
refreshOverview = async () => {};
`,
    context
  );

  await context.__appTest.submitAgentTask(task);

  assert.equal(context.__postJsonCalls.length, 1);
  assert.equal(context.__postJsonCalls[0].payload.config_overrides.max_run_seconds, 42);
  assert.equal(context.__postJsonCalls[0].payload.task_graph.subgoals[0].id, "subgoal_01");
  assert.equal(context.__postJsonCalls[0].payload.task_graph_signature, "preview-with-run-limit");
});


await runTest("planning config edits clear the visible task preview", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.hydrated = true;
  context.__appTest.state.taskPreviewTask = "Open calculator";
  context.__appTest.state.taskPreviewConfigSignature = context.__appTest.buildConfigSignature({ max_task_subgoals: 2 });
  context.__appTest.state.taskPreview = {
    task: "Open calculator",
    task_graph: { task: "Open calculator", subgoals: [{ id: "subgoal_01", title: "Open calculator" }] },
  };

  context.__appTest.scheduleRuntimePreferencesSync();

  assert.equal(context.__appTest.state.taskPreview, null);
  assert.equal(context.__appTest.state.taskPreviewTask, "");
  assert.equal(context.__appTest.state.taskPreviewConfigSignature, "");
  assert.equal(context.document.getElementById("submitHint").textContent, "Settings changed; refresh the plan preview.");
});

await runTest("run limit edits clear the visible task preview", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.hydrated = true;
  context.__appTest.state.taskPreviewTask = "Open calculator";
  context.__appTest.state.taskPreviewConfigSignature = context.__appTest.buildConfigSignature({ max_run_seconds: 30 });
  context.__appTest.state.taskPreview = {
    task: "Open calculator",
    task_graph: { task: "Open calculator", subgoals: [{ id: "subgoal_01", title: "Open calculator" }] },
  };

  context.document.getElementById("maxRunSecondsInput").value = "45";
  context.__appTest.handleRunLimitChange();

  assert.equal(context.__appTest.state.taskPreview, null);
  assert.equal(context.__appTest.state.taskPreviewTask, "");
  assert.equal(context.__appTest.state.taskPreviewConfigSignature, "");
  assert.equal(context.document.getElementById("submitHint").textContent, "Settings changed; refresh the plan preview.");
});

await runTest("run limit edits clear a stale preview start blocker", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.hydrated = true;
  context.__appTest.state.taskPreviewStartError = "The preview is not ready to start.";

  context.document.getElementById("maxRunSecondsInput").value = "45";
  context.__appTest.handleRunLimitChange();

  assert.equal(context.__appTest.state.taskPreviewStartError, "");
});


await runTest("dashboard brand assets and layout tokens use the Claude design shell", async () => {
  const indexSource = fs.readFileSync(path.resolve(import.meta.dirname, "../index.html"), "utf8");
  const stylesSource = fs.readFileSync(path.resolve(import.meta.dirname, "../styles.css"), "utf8");
  const dashboardLogoSvg = path.resolve(import.meta.dirname, "../icons/logo-mark.svg");
  const webLogoSvg = path.resolve(import.meta.dirname, "../../../web/public/logo-mark.svg");
  const finalRootBlock = getLastCssBlock(stylesSource, ":root");
  const finalSurfaceBlock = getLastCssBlock(stylesSource, ".surface", /min-width:\s*0;/);
  const finalChatSurfaceSizingBlock = getLastCssBlock(stylesSource, ".chat-surface,\n.developer-surface", /flex:\s*1 1 auto;/);
  const finalChatSurfaceBlock = getLastCssBlock(stylesSource, ".chat-surface", /display:\s*flex;/);
  const finalChatScrollBlock = getLastCssBlock(stylesSource, ".chat-scroll", /justify-content:\s*center;/);
  const finalWelcomeChatSurfaceBlock = getLastCssBlock(
    stylesSource,
    '.chat-surface[data-context="agent-welcome"],\n.chat-surface[data-context="chat-welcome"]',
    /justify-content:\s*center;/
  );
  const finalWelcomeChatScrollBlock = getLastCssBlock(
    stylesSource,
    '.chat-scroll[data-context="agent-welcome"],\n.chat-scroll[data-context="chat-welcome"]',
    /display:\s*none;/
  );
  const finalChatStreamBlock = getLastCssBlock(stylesSource, ".chat-stream");
  const finalMessageRowBlock = getLastCssBlock(stylesSource, ".chat-stream > .message");
  const finalChatWelcomeBlock = getLastCssBlock(stylesSource, ".chat-welcome", /width:\s*min\(100%, var\(--content-max\)\);/);
  const finalWelcomeMinimalBlock = getLastCssBlock(stylesSource, ".chat-welcome--minimal", /display:\s*none;/);
  const finalAgentWelcomeBlock = getLastCssBlock(
    stylesSource,
    '.chat-stream[data-context="agent-welcome"]',
    /justify-content:\s*flex-end;/
  );
  const finalAssistantShellBlock = getLastCssBlock(stylesSource, ".assistant-shell");
  const finalComposerWrapBlock = getLastCssBlock(stylesSource, ".composer-wrap", /align-items:\s*center;/);
  const finalWelcomeComposerWrapBlock = getLastCssBlock(
    stylesSource,
    '.composer-wrap[data-context="agent-welcome"],\n.composer-wrap[data-context="chat-welcome"]',
    /flex-direction:\s*column-reverse;/
  );
  const finalWelcomeComposerWordmarkBlock = getLastCssBlock(
    stylesSource,
    '.composer-wrap[data-context="agent-welcome"]::before,\n.composer-wrap[data-context="chat-welcome"]::before',
    /content:\s*"Aoryn";/
  );
  const finalWelcomeComposerSizingBlock = getLastCssBlock(
    stylesSource,
    '.composer-wrap[data-context="agent-welcome"] .composer,\n.composer-wrap[data-context="agent-welcome"] .composer-suggestions,\n.composer-wrap[data-context="chat-welcome"] .composer,\n.composer-wrap[data-context="chat-welcome"] .composer-suggestions',
    /width:\s*min\(100%, 960px\);/
  );
  const finalWelcomeComposerSuggestionsBlock = getLastCssBlock(
    stylesSource,
    '.composer-wrap[data-context="agent-welcome"] .composer-suggestions,\n.composer-wrap[data-context="chat-welcome"] .composer-suggestions',
    /justify-content:\s*flex-start;/
  );
  const finalComposerSuggestionsBlock = getLastCssBlock(
    stylesSource,
    ".composer-suggestions",
    /width:\s*min\(100%, var\(--composer-max\)\);/
  );
  const finalComposerBlock = getLastCssBlock(
    stylesSource,
    ".composer",
    /width:\s*min\(100%, var\(--composer-max\)\);/
  );

  assert.match(indexSource, /brand-mark__image" src="\/assets\/icons\/aoryn-mark\.png\?v=__APP_ASSET_VERSION__/);
  assert.match(indexSource, /id="previewTaskButton"/);
  assert.match(indexSource, /id="autonomyModeSelect"/);
  assert.match(indexSource, /id="planningModeSelect"/);
  assert.match(indexSource, /id="taskGraphRequestTimeoutInput"/);
  assert.match(indexSource, /id="planReviewPolicySelect"/);
  assert.match(indexSource, /id="approvalPolicySelect"/);
  assert.match(indexSource, /id="stageReviewPolicySelect"/);
  assert.match(indexSource, /id="maxTaskSubgoalsInput"/);
  assert.match(indexSource, /id="recoverableRetryLimitInput"/);
  assert.match(indexSource, /id="replanOnRecoverableError"/);
  assert.match(indexSource, /id="taskWorkspaceEnabled"/);
  assert.equal(indexSource.includes("logo-mark.svg"), false);
  assert.match(finalRootBlock, /--sidebar-open:\s*260px;/);
  assert.match(finalRootBlock, /--sidebar-collapsed:\s*84px;/);
  assert.match(finalRootBlock, /--content-max:\s*1400px;/);
  assert.match(finalRootBlock, /--composer-max:\s*1240px;/);
  assert.match(finalRootBlock, /--reading-max:\s*860px;/);
  assert.match(finalSurfaceBlock, /min-width:\s*0;/);
  assert.match(finalChatSurfaceSizingBlock, /flex:\s*1 1 auto;/);
  assert.match(finalChatSurfaceSizingBlock, /width:\s*100%;/);
  assert.match(finalChatSurfaceBlock, /display:\s*flex;/);
  assert.equal(stylesSource.includes("--content-max: 760px;"), false);
  assert.equal(stylesSource.includes("--content-max: 968px;"), false);
  assert.match(finalChatScrollBlock, /display:\s*flex;/);
  assert.match(finalChatScrollBlock, /justify-content:\s*center;/);
  assert.match(finalWelcomeChatSurfaceBlock, /justify-content:\s*center;/);
  assert.match(finalWelcomeChatScrollBlock, /display:\s*none;/);
  assert.match(finalChatStreamBlock, /align-items:\s*stretch;/);
  assert.match(finalChatStreamBlock, /width:\s*min\(100%, var\(--content-max\)\);/);
  assert.match(finalMessageRowBlock, /width:\s*100%;/);
  assert.match(finalChatWelcomeBlock, /width:\s*min\(100%, var\(--content-max\)\);/);
  assert.match(finalChatWelcomeBlock, /text-align:\s*center;/);
  assert.match(finalWelcomeMinimalBlock, /display:\s*none;/);
  assert.match(finalAgentWelcomeBlock, /justify-content:\s*flex-end;/);
  assert.match(finalAgentWelcomeBlock, /min-height:\s*0;/);
  assert.match(finalAssistantShellBlock, /width:\s*100%;/);
  assert.match(finalComposerWrapBlock, /width:\s*100%;/);
  assert.match(finalComposerWrapBlock, /align-items:\s*center;/);
  assert.match(finalWelcomeComposerWrapBlock, /flex:\s*0 0 auto;/);
  assert.match(finalWelcomeComposerWrapBlock, /position:\s*relative;/);
  assert.match(finalWelcomeComposerWrapBlock, /overflow:\s*visible;/);
  assert.match(finalWelcomeComposerWrapBlock, /flex-direction:\s*column-reverse;/);
  assert.match(finalWelcomeComposerWrapBlock, /gap:\s*14px;/);
  assert.match(finalWelcomeComposerWrapBlock, /transform:\s*translateY\(clamp\(44px, 6vh, 88px\)\);/);
  assert.match(finalWelcomeComposerWordmarkBlock, /content:\s*"Aoryn";/);
  assert.match(finalWelcomeComposerWordmarkBlock, /position:\s*absolute;/);
  assert.match(finalWelcomeComposerWordmarkBlock, /padding-inline:\s*0\.08em;/);
  assert.match(finalWelcomeComposerWordmarkBlock, /font-style:\s*normal;/);
  assert.match(finalWelcomeComposerWordmarkBlock, /font-weight:\s*720;/);
  assert.match(finalWelcomeComposerWordmarkBlock, /color:\s*rgba\(15,\s*23,\s*42,\s*0\.94\);/);
  assert.match(finalWelcomeComposerSizingBlock, /width:\s*min\(100%, 960px\);/);
  assert.match(finalWelcomeComposerSizingBlock, /max-width:\s*960px;/);
  assert.match(finalWelcomeComposerSuggestionsBlock, /justify-content:\s*flex-start;/);
  assert.match(finalWelcomeComposerSuggestionsBlock, /margin:\s*0 auto;/);
  assert.match(finalComposerSuggestionsBlock, /width:\s*min\(100%, 1180px\);|width:\s*min\(100%, var\(--composer-max\)\);/);
  assert.match(finalComposerBlock, /width:\s*min\(100%, 1180px\);|width:\s*min\(100%, var\(--composer-max\)\);/);
  assert.equal(fs.existsSync(dashboardLogoSvg), false);
  assert.equal(fs.existsSync(webLogoSvg), false);
});


await runTest("mode switch is rebuilt as a single segmented control", async () => {
  const context = createHarness();
  context.__appTest.initializeState();

  const modeTabs = context.document.getElementById("uiModeTabs");
  assert.match(modeTabs.innerHTML, /mode-switch__button-label">Chat</);
  assert.match(modeTabs.innerHTML, /mode-switch__button-label">Agent</);
  assert.match(modeTabs.innerHTML, /role="tab"/);

  const indexSource = fs.readFileSync(path.resolve(import.meta.dirname, "../index.html"), "utf8");
  assert.match(indexSource, /<div class="mode-switch" id="uiModeTabs" role="tablist" aria-label="Mode switch">/);
  assert.match(indexSource, /<\/div>\s*<button class="settings-button" id="settingsButton"/);
});


await runTest("developer surface empty states use the refreshed panel shell", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.jobs = [];
  context.__appTest.state.activeJob = null;
  context.__appTest.state.selectedRunDetails = null;

  context.__appTest.renderDeveloper();

  assert.match(context.document.getElementById("jobList").innerHTML, /panel-empty-state/);
  assert.match(context.document.getElementById("developerTimeline").innerHTML, /panel-empty-state/);
});

await runTest("developer timeline renders active and historical plan health", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  const executionState = {
    orchestration_phase: "stage_ready",
    active_specialist: "desktop_operator",
    plan_health: {
      counts: { total: 2, completed: 0, blocked: 1, ready: 1, exhausted: 1 },
      next_subgoal_id: "subgoal_02",
      items: [
        {
          id: "subgoal_01",
          title: "Recover blocked page",
          status: "blocked",
          capability_preference: "browser_dom",
          retry_remaining: 0,
          exhausted: true,
        },
        {
          id: "subgoal_02",
          title: "Continue local notes",
          status: "pending",
          capability_preference: "desktop_gui",
          retry_remaining: 2,
          is_next: true,
        },
      ],
    },
  };
  const activeJob = {
    id: "job-plan",
    task: "Recover page and continue",
    status: "running",
    started_at: 1711000000,
    result: {
      run_id: "run-plan",
      latest_summary: "Recovering after a stale target.",
      steps: 3,
      execution_state: executionState,
    },
  };

  context.__appTest.state.activeJob = activeJob;
  context.__appTest.state.jobs = [activeJob];
  context.__appTest.state.selectedRunDetails = null;
  context.__appTest.renderDeveloper();

  let timelineHtml = context.document.getElementById("developerTimeline").innerHTML;
  assert.match(timelineHtml, /timeline-item--plan/);
  assert.match(timelineHtml, /timeline-item--live/);
  assert.match(timelineHtml, /data-next-subgoal="subgoal_02"/);
  assert.match(timelineHtml, /Continue local notes/);
  assert.match(context.document.getElementById("activePayloadView").textContent, /plan_health/);

  const stateOnlyActiveJob = snapshot(activeJob);
  delete stateOnlyActiveJob.result.execution_state;
  stateOnlyActiveJob.result.state = {
    ...snapshot(executionState),
    current_goal: "Continue local notes from summary state",
  };
  stateOnlyActiveJob.result.state.plan_health.items[1].title = "Continue local notes from summary state";
  context.__appTest.state.activeJob = stateOnlyActiveJob;
  context.__appTest.state.jobs = [stateOnlyActiveJob];
  context.__appTest.renderDeveloper();

  timelineHtml = context.document.getElementById("developerTimeline").innerHTML;
  assert.match(timelineHtml, /timeline-item--plan/);
  assert.match(timelineHtml, /data-next-subgoal="subgoal_02"/);
  assert.match(timelineHtml, /Continue local notes from summary state/);

  context.__appTest.state.activeJob = null;
  context.__appTest.state.jobs = [];
  context.__appTest.state.selectedRunDetails = {
    id: "run-historical-plan",
    task: "Recover page and continue",
    execution_state: executionState,
    timeline: [
      {
        step: 1,
        captured_at: 1711000005,
        plan: { status_summary: "Recover blocked page" },
        executed_actions: [{ type: "wait", seconds: 0.1 }],
        verification: {
          status: "partial_progress",
          failure_kind: "needs_more_evidence",
          message: "Page recovered but final form state is not confirmed.",
        },
      },
    ],
  };
  context.__appTest.renderDeveloper();

  timelineHtml = context.document.getElementById("developerTimeline").innerHTML;
  assert.match(timelineHtml, /timeline-item--plan/);
  assert.match(timelineHtml, /data-next-subgoal="subgoal_02"/);
  assert.match(timelineHtml, /Recover blocked page/);
  assert.match(timelineHtml, /data-status="partial_progress"/);
  assert.match(timelineHtml, /Partial progress/);
  assert.match(timelineHtml, /Verification: partial_progress/);
});


await runTest("inspector renders refreshed overview timeline and gallery shells", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.selectedRunDetails = {
    id: "run-inspector",
    task: "Inspect the pricing page",
    started_at: 1711000000,
    finished_at: 1711000060,
    steps: 3,
    completed: true,
    cancelled: false,
    requires_human: false,
    error: null,
    cancel_reason: null,
    interruption_reason: null,
    dry_run: false,
    execution_state: {
      last_step: {
        capability: "browser_dom",
        intent: "Open the pricing page from the current navigation.",
        risk_level: "low",
        surface_kind: "managed_aoryn_browser",
        actions: [{ type: "click", text: "Pricing" }],
      },
      plan_health: {
        counts: { total: 2, completed: 1, blocked: 0, ready: 1 },
        next_subgoal_id: "subgoal_02",
        items: [
          { id: "subgoal_01", title: "Open the homepage", status: "completed", capability_preference: "browser_dom" },
          { id: "subgoal_02", title: "Open pricing", status: "pending", capability_preference: "browser_dom", is_next: true },
        ],
      },
    },
    timeline: [
      {
        step: 1,
        task: "Open the homepage",
        captured_at: 1711000005,
        screenshot: "shot-1.png",
        executed_actions: [{ type: "launch_browser" }],
        plan: { status_summary: "Opened the homepage" },
        verification: {
          status: "failed",
          failure_kind: "blocked_by_ui",
          message: "Popup blocked navigation.",
          evidence: [{ kind: "screenshot", value: "blocked-modal" }],
        },
      },
      {
        step: 2,
        task: "Open pricing",
        captured_at: 1711000040,
        screenshot: "shot-2.png",
        executed_actions: [{ type: "click", text: "Pricing" }],
        plan: { status_summary: "Opened the pricing page" },
        step_proposal: {
          capability: "browser_dom",
          intent: "Click the pricing navigation item.",
          risk_level: "low",
          surface_kind: "managed_aoryn_browser",
          actions: [{ type: "click", text: "Pricing" }],
        },
        verification: {
          status: "partial_progress",
          failure_kind: "needs_more_evidence",
          message: "Pricing page opened; tiers still need inspection.",
          evidence: [{ kind: "url", value: "/pricing" }],
        },
      },
    ],
  };

  context.__appTest.state.detailView = "overview";
  context.__appTest.renderInspector();
  assert.match(context.document.getElementById("runDetail").innerHTML, /inspector-overview/);
  assert.match(context.document.getElementById("runDetail").innerHTML, /inspector-section-card--summary/);
  assert.match(context.document.getElementById("runDetail").innerHTML, /inspector-section-card--plan/);
  assert.match(context.document.getElementById("runDetail").innerHTML, /inspector-section-card--step/);
  assert.match(context.document.getElementById("runDetail").innerHTML, /data-next-subgoal="subgoal_02"/);
  assert.match(context.document.getElementById("runDetail").innerHTML, /Open the pricing page from the current navigation/);

  context.__appTest.state.detailView = "timeline";
  context.__appTest.renderInspector();
  const timelineDetailHtml = context.document.getElementById("runDetail").innerHTML;
  assert.match(timelineDetailHtml, /inspector-timeline-list/);
  assert.match(timelineDetailHtml, /timeline-item--inspector/);
  assert.match(timelineDetailHtml, /data-status="failed"/);
  assert.match(timelineDetailHtml, /Failed/);
  assert.match(timelineDetailHtml, /Failure: blocked_by_ui/);
  assert.match(timelineDetailHtml, /Reason: Popup blocked navigation/);
  assert.match(timelineDetailHtml, /Evidence: screenshot/);
  assert.match(timelineDetailHtml, /Click the pricing navigation item/);
  assert.match(timelineDetailHtml, /data-status="partial_progress"/);
  assert.match(timelineDetailHtml, /Partial progress/);
  assert.match(timelineDetailHtml, /Verification: partial_progress/);
  assert.match(timelineDetailHtml, /Failure: needs_more_evidence/);
  assert.match(timelineDetailHtml, /Evidence: url/);

  context.__appTest.state.detailView = "gallery";
  context.__appTest.renderInspector();
  assert.match(context.document.getElementById("runDetail").innerHTML, /inspector-gallery-grid/);
  assert.match(context.document.getElementById("runDetail").innerHTML, /inspector-gallery-card/);
});


await runTest("help center uses refreshed empty state and markdown shell", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.helpTitle = "Developer Docs";
  context.__appTest.state.helpLoading = true;
  context.__appTest.state.helpError = "";
  context.__appTest.state.helpContent = "";

  context.__appTest.renderHelpCenter();
  assert.match(context.document.getElementById("helpContent").innerHTML, /panel-empty-state/);

  context.__appTest.state.helpLoading = false;
  context.__appTest.state.helpContent = "# Developer Docs\n\nUse the desktop dashboard.";
  context.__appTest.renderHelpCenter();
  assert.match(context.document.getElementById("helpContent").innerHTML, /help-doc-shell/);
});


await runTest("custom select refreshed shell still renders trigger and menu markup", async () => {
  const context = createHarness();
  context.__appTest.state.locale = "en-US";
  context.__appTest.state.openCustomSelectId = "modelProvider";

  const wrapper = {
    innerHTML: "",
    querySelector() {
      return null;
    },
    classList: {
      toggle() {},
      contains(className) {
        return className === "custom-select";
      },
    },
  };
  const select = {
    id: "modelProvider",
    options: [
      { value: "lmstudio_local", textContent: "Local LM Studio" },
      { value: "openai_compatible", textContent: "OpenAI-Compatible API" },
    ],
    selectedIndex: 1,
    value: "openai_compatible",
    disabled: false,
    nextElementSibling: wrapper,
  };

  context.__appTest.originals.syncCustomSelect(select);

  assert.match(wrapper.innerHTML, /custom-select__trigger/);
  assert.match(wrapper.innerHTML, /custom-select__menu/);
  assert.match(wrapper.innerHTML, /custom-select__option is-selected/);
});

await runTest("custom select preserves menu scroll while the shell refreshes", async () => {
  const context = createHarness();
  context.__appTest.state.openCustomSelectId = "availableModels";

  const previousMenu = { scrollTop: 132 };
  const nextMenu = { scrollTop: 0 };
  let queryCount = 0;
  const wrapper = {
    innerHTML: "",
    querySelector(selector) {
      if (selector !== ".custom-select__menu") return null;
      queryCount += 1;
      return queryCount === 1 ? previousMenu : nextMenu;
    },
    classList: {
      toggle() {},
      contains(className) {
        return className === "custom-select";
      },
    },
  };
  const select = {
    id: "availableModels",
    options: [
      { value: "gpt-5-chat", textContent: "gpt-5-chat" },
      { value: "claude-opus-4-6", textContent: "claude-opus-4-6" },
    ],
    selectedIndex: 0,
    value: "gpt-5-chat",
    disabled: false,
    nextElementSibling: wrapper,
  };

  context.__appTest.originals.syncCustomSelect(select);

  assert.equal(context.__appTest.state.customSelectMenuState.availableModels.scrollTop, 132);
  assert.equal(nextMenu.scrollTop, 132);
});

await runTest("background overview refresh skips rerender when the snapshot is unchanged", async () => {
  const overview = buildOverviewPayload({
    runs: [{ id: "run-1", task: "demo", steps: 1, completed: false }],
    runtimePreferences: { updated_at: 12 },
  });
  const context = createHarness({ overviewPayload: snapshot(overview) });

  context.__renderCount = 0;
  context.__persistCount = 0;
  vm.runInContext(
    `
renderAll = () => { globalThis.__renderCount += 1; };
persistOverviewSnapshot = () => { globalThis.__persistCount += 1; };
loadRunDetails = async (runId) => {
  globalThis.__loadRunDetailsCalls.push(runId);
  state.selectedRunDetails = { id: runId, task: runId };
  state.loadingRunDetails = false;
  renderAll();
};
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  const renderCountAfterInitial = context.__renderCount;
  const persistCountAfterInitial = context.__persistCount;
  const detailCallsAfterInitial = context.__loadRunDetailsCalls.length;

  await context.__appTest.refreshOverview({ background: true });

  assert.equal(context.__renderCount, renderCountAfterInitial);
  assert.equal(context.__persistCount, persistCountAfterInitial);
  assert.equal(context.__loadRunDetailsCalls.length, detailCallsAfterInitial);
  assert.equal(typeof context.__appTest.state.lastOverviewSignature, "string");
  assert.notEqual(context.__appTest.state.lastOverviewSignature, "");
});

await runTest("background overview refresh applies changed autonomy preset contract", async () => {
  const overview = buildOverviewPayload({
    runs: [{ id: "run-contract", task: "demo", steps: 1, completed: false }],
    runtimePreferences: { updated_at: 12 },
    autonomyModePresets: {
      autonomous: {
        plan_review_policy: "never",
        approval_policy: "autonomous",
        stage_review_policy: "never",
        replan_on_recoverable_error: true,
        recoverable_error_retry_limit: 4,
        max_replans_per_run: 5,
        max_failures_per_subgoal: 5,
      },
    },
  });
  const context = createHarness({ overviewPayload: snapshot(overview) });
  context.__renderCount = 0;
  context.__persistCount = 0;
  vm.runInContext(
    `
renderAll = () => { globalThis.__renderCount += 1; };
persistOverviewSnapshot = () => { globalThis.__persistCount += 1; };
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  const renderCountAfterInitial = context.__renderCount;
  const persistCountAfterInitial = context.__persistCount;
  const changedOverview = snapshot(overview);
  changedOverview.meta.autonomy_mode_presets.autonomous = {
    plan_review_policy: "low_risk_auto",
    approval_policy: "tiered",
    stage_review_policy: "risk_change",
    replan_on_recoverable_error: false,
    recoverable_error_retry_limit: 8,
    max_replans_per_run: 6,
    max_failures_per_subgoal: 7,
  };
  context.__overviewPayload = changedOverview;

  await context.__appTest.refreshOverview({ background: true });

  assert.ok(context.__renderCount > renderCountAfterInitial);
  assert.ok(context.__persistCount > persistCountAfterInitial);
  assert.equal(context.__appTest.state.meta.autonomy_mode_presets.autonomous.approval_policy, "tiered");

  context.__appTest.applyAutonomyModePreset("autonomous");
  assert.equal(context.document.getElementById("planReviewPolicySelect").value, "low_risk_auto");
  assert.equal(context.document.getElementById("approvalPolicySelect").value, "tiered");
  assert.equal(context.document.getElementById("stageReviewPolicySelect").value, "risk_change");
  assert.equal(context.document.getElementById("replanOnRecoverableError").checked, false);
  assert.equal(context.document.getElementById("recoverableRetryLimitInput").value, 8);
  assert.equal(context.document.getElementById("maxReplansInput").value, 6);
  assert.equal(context.document.getElementById("maxFailuresInput").value, 7);
});

await runTest("run state refresh signature ignores empty summary shells", async () => {
  const context = createHarness();
  const emptySignature = vm.runInContext(
    `buildRunStateRefreshSignature({
      id: "run-empty-summary",
      state: {
        pending_decision: {},
        plan_health: { counts: {}, autonomy: {}, items: [] },
        evidence_ledger: [],
        repair_history: [],
        capability_failures: {},
        workspace_summary: { facts: [], sources: [], evidence: [], notes: [] }
      }
    })`,
    context
  );
  assert.equal(emptySignature, "");

  const nestedDecisionSignature = vm.runInContext(
    `buildRunStateRefreshSignature({
      id: "run-nested-decision",
      execution_state: {
        pending_decision: {
          decision_type: "plan_review",
          summary: "Review the generated task plan."
        }
      },
      state: {
        pending_decision: {}
      }
    })`,
    context
  );
  assert.notEqual(nestedDecisionSignature, "");
  assert.match(nestedDecisionSignature, /Review the generated task plan/);
});

await runTest("background overview refresh reloads selected run details when detail timestamp changes", async () => {
  const overview = buildOverviewPayload({
    runs: [{ id: "run-state", task: "track plan state", steps: 1, completed: false, details_updated_at: 100 }],
  });
  const context = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.history-selection": JSON.stringify({ kind: "run", id: "run-state" }),
    },
    overviewPayload: snapshot(overview),
  });

  context.__loadRunDetailsCalls = [];
  vm.runInContext(
    `
renderAll = () => {};
loadRunDetails = async (runId) => {
  globalThis.__loadRunDetailsCalls.push(runId);
  const summary = state.runs.find((run) => run.id === runId) || { id: runId };
  state.selectedRunDetails = { ...summary };
  state.loadingRunDetails = false;
};
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  assert.equal(context.__loadRunDetailsCalls.length, 1);
  assert.equal(context.__appTest.state.selectedRunDetails.details_updated_at, 100);

  context.__overviewPayload = buildOverviewPayload({
    runs: [{ id: "run-state", task: "track plan state", steps: 1, completed: false, details_updated_at: 200 }],
  });

  await context.__appTest.refreshOverview({ background: true });

  assert.equal(context.__loadRunDetailsCalls.length, 2);
  assert.equal(context.__appTest.state.selectedRunDetails.details_updated_at, 200);
});

await runTest("background overview refresh reloads selected run details when run metadata changes", async () => {
  const overview = buildOverviewPayload({
    runs: [
      {
        id: "run-metadata",
        task: "track run metadata",
        steps: 1,
        dry_run: true,
        max_steps: 4,
        max_run_seconds: 120,
        pause_after_action: 0.25,
        completed: false,
        details_updated_at: 100,
      },
    ],
  });
  const context = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.history-selection": JSON.stringify({ kind: "run", id: "run-metadata" }),
    },
    overviewPayload: snapshot(overview),
  });

  context.__loadRunDetailsCalls = [];
  vm.runInContext(
    `
renderAll = () => {};
loadRunDetails = async (runId) => {
  globalThis.__loadRunDetailsCalls.push(runId);
  const summary = state.runs.find((run) => run.id === runId) || { id: runId };
  state.selectedRunDetails = { ...summary };
  state.loadingRunDetails = false;
};
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  assert.equal(context.__loadRunDetailsCalls.length, 1);
  assert.equal(context.__appTest.state.selectedRunDetails.max_run_seconds, 120);

  const changedOverview = snapshot(overview);
  changedOverview.runs[0].dry_run = false;
  changedOverview.runs[0].max_steps = 6;
  changedOverview.runs[0].max_run_seconds = 240;
  changedOverview.runs[0].pause_after_action = 0.5;
  context.__overviewPayload = changedOverview;

  await context.__appTest.refreshOverview({ background: true });

  assert.equal(context.__loadRunDetailsCalls.length, 2);
  assert.equal(context.__appTest.state.selectedRunDetails.dry_run, false);
  assert.equal(context.__appTest.state.selectedRunDetails.max_steps, 6);
  assert.equal(context.__appTest.state.selectedRunDetails.max_run_seconds, 240);
  assert.equal(context.__appTest.state.selectedRunDetails.pause_after_action, 0.5);
});

await runTest("background overview refresh reloads selected run details when execution budget changes", async () => {
  const overview = buildOverviewPayload({
    runs: [
      {
        id: "run-budget",
        task: "track execution budget",
        steps: 1,
        completed: false,
        execution_budget: {
          max_steps: 4,
          max_run_seconds: 120,
          desktop_autonomy_mode: "conservative",
          replan_on_recoverable_error: "true",
          recoverable_error_retry_limit: 2,
        },
        details_updated_at: 100,
      },
    ],
  });
  const context = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.history-selection": JSON.stringify({ kind: "run", id: "run-budget" }),
    },
    overviewPayload: snapshot(overview),
  });

  context.__loadRunDetailsCalls = [];
  vm.runInContext(
    `
renderAll = () => {};
loadRunDetails = async (runId) => {
  globalThis.__loadRunDetailsCalls.push(runId);
  const summary = state.runs.find((run) => run.id === runId) || { id: runId };
  state.selectedRunDetails = { ...summary, ...summarizeOverviewExecutionBudget(summary) };
  state.loadingRunDetails = false;
};
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  assert.equal(context.__loadRunDetailsCalls.length, 1);
  assert.equal(context.__appTest.state.selectedRunDetails.max_run_seconds, 120);
  assert.equal(context.__appTest.state.selectedRunDetails.desktop_autonomy_mode, "conservative");

  const changedOverview = snapshot(overview);
  changedOverview.runs[0].execution_budget.max_run_seconds = 240;
  changedOverview.runs[0].execution_budget.desktop_autonomy_mode = "autonomous";
  changedOverview.runs[0].execution_budget.recoverable_error_retry_limit = 4;
  context.__overviewPayload = changedOverview;

  await context.__appTest.refreshOverview({ background: true });

  assert.equal(context.__loadRunDetailsCalls.length, 2);
  assert.equal(context.__appTest.state.selectedRunDetails.max_run_seconds, 240);
  assert.equal(context.__appTest.state.selectedRunDetails.desktop_autonomy_mode, "autonomous");
  assert.equal(context.__appTest.state.selectedRunDetails.recoverable_error_retry_limit, 4);
});

await runTest("background overview refresh reloads selected run details when execution environment changes", async () => {
  const overview = buildOverviewPayload({
    runs: [
      {
        id: "run-environment",
        task: "track execution environment",
        steps: 1,
        completed: false,
        browser_control_mode: "hybrid",
        browser_dom_backend: "playwright",
        browser_headless: false,
        cursor_motion_enabled: false,
        generic_app_launch_enabled: true,
        shell_recipe_policy: "approval_required",
        details_updated_at: 100,
      },
    ],
  });
  const context = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.history-selection": JSON.stringify({ kind: "run", id: "run-environment" }),
    },
    overviewPayload: snapshot(overview),
  });

  context.__loadRunDetailsCalls = [];
  vm.runInContext(
    `
renderAll = () => {};
loadRunDetails = async (runId) => {
  globalThis.__loadRunDetailsCalls.push(runId);
  const summary = state.runs.find((run) => run.id === runId) || { id: runId };
  state.selectedRunDetails = { ...summary };
  state.loadingRunDetails = false;
};
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  assert.equal(context.__loadRunDetailsCalls.length, 1);
  assert.equal(context.__appTest.state.selectedRunDetails.browser_control_mode, "hybrid");
  assert.equal(context.__appTest.state.selectedRunDetails.browser_headless, false);

  const changedOverview = snapshot(overview);
  changedOverview.runs[0].browser_control_mode = "dom";
  changedOverview.runs[0].browser_headless = true;
  changedOverview.runs[0].cursor_motion_enabled = true;
  changedOverview.runs[0].generic_app_launch_enabled = false;
  context.__overviewPayload = changedOverview;

  await context.__appTest.refreshOverview({ background: true });

  assert.equal(context.__loadRunDetailsCalls.length, 2);
  assert.equal(context.__appTest.state.selectedRunDetails.browser_control_mode, "dom");
  assert.equal(context.__appTest.state.selectedRunDetails.browser_headless, true);
  assert.equal(context.__appTest.state.selectedRunDetails.cursor_motion_enabled, true);
  assert.equal(context.__appTest.state.selectedRunDetails.generic_app_launch_enabled, false);
});

await runTest("background overview refresh reloads selected run details when error text changes", async () => {
  const overview = buildOverviewPayload({
    runs: [
      {
        id: "run-error-text",
        task: "track changing failure reason",
        steps: 2,
        completed: false,
        error: "Initial planner failure.",
        details_updated_at: 100,
      },
    ],
  });
  const context = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.history-selection": JSON.stringify({ kind: "run", id: "run-error-text" }),
    },
    overviewPayload: snapshot(overview),
  });

  context.__loadRunDetailsCalls = [];
  vm.runInContext(
    `
renderAll = () => {};
loadRunDetails = async (runId) => {
  globalThis.__loadRunDetailsCalls.push(runId);
  const summary = state.runs.find((run) => run.id === runId) || { id: runId };
  state.selectedRunDetails = { ...summary };
  state.loadingRunDetails = false;
};
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  assert.equal(context.__loadRunDetailsCalls.length, 1);
  assert.equal(context.__appTest.state.selectedRunDetails.error, "Initial planner failure.");

  const changedOverview = snapshot(overview);
  changedOverview.runs[0].error = "Planner crashed after approval cleanup.";
  context.__overviewPayload = changedOverview;

  await context.__appTest.refreshOverview({ background: true });

  assert.equal(context.__loadRunDetailsCalls.length, 2);
  assert.equal(context.__appTest.state.selectedRunDetails.error, "Planner crashed after approval cleanup.");
});

await runTest("background overview refresh reloads selected run details when state summary changes", async () => {
  const overview = buildOverviewPayload({
    runs: [
      {
        id: "run-state-summary",
        task: "track changing plan state",
        steps: 1,
        completed: false,
        details_updated_at: 100,
        state: {
          current_goal: "Recover blocked page",
          app_context: {
            human_handoff_kind: "login",
            human_handoff_reason: "Complete sign-in before continuing.",
          },
          last_verification: {
            status: "partial_progress",
            failure_kind: "needs_more_evidence",
            message: "The recovered page needs one more check.",
          },
          evidence_ledger: [{ status: "partial_progress", kind: "selector", selector: "#continue" }],
          plan_health: {
            counts: { total: 2, completed: 0, pending: 2, ready: 1, blocked: 0 },
            next_subgoal_id: "subgoal_01",
            items: [
              { id: "subgoal_01", title: "Recover blocked page", status: "pending", ready: true, is_next: true },
              { id: "subgoal_02", title: "Continue local notes", status: "pending" },
            ],
          },
        },
      },
    ],
  });
  const context = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.history-selection": JSON.stringify({ kind: "run", id: "run-state-summary" }),
    },
    overviewPayload: snapshot(overview),
  });

  context.__loadRunDetailsCalls = [];
  vm.runInContext(
    `
renderAll = () => {};
loadRunDetails = async (runId) => {
  globalThis.__loadRunDetailsCalls.push(runId);
  const summary = state.runs.find((run) => run.id === runId) || { id: runId };
  state.selectedRunDetails = JSON.parse(JSON.stringify(summary));
  state.loadingRunDetails = false;
};
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  assert.equal(context.__loadRunDetailsCalls.length, 1);
  assert.equal(context.__appTest.state.selectedRunDetails.state.current_goal, "Recover blocked page");

  const changedOverview = snapshot(overview);
  changedOverview.runs[0].state.current_goal = "Continue local notes";
  changedOverview.runs[0].state.plan_health.counts.completed = 1;
  changedOverview.runs[0].state.plan_health.next_subgoal_id = "subgoal_02";
  changedOverview.runs[0].state.plan_health.items = [
    { id: "subgoal_01", title: "Recover blocked page", status: "completed" },
    { id: "subgoal_02", title: "Continue local notes", status: "pending", ready: true, is_next: true },
  ];
  context.__overviewPayload = changedOverview;

  await context.__appTest.refreshOverview({ background: true });

  assert.equal(context.__loadRunDetailsCalls.length, 2);
  assert.equal(context.__appTest.state.selectedRunDetails.state.current_goal, "Continue local notes");
  assert.equal(context.__appTest.state.selectedRunDetails.state.plan_health.next_subgoal_id, "subgoal_02");

  const callsAfterPlanRefresh = context.__loadRunDetailsCalls.length;
  const verificationChangedOverview = snapshot(changedOverview);
  verificationChangedOverview.runs[0].state.last_verification.status = "failed";
  verificationChangedOverview.runs[0].state.last_verification.failure_kind = "verification_failed";
  verificationChangedOverview.runs[0].state.evidence_ledger.push({ status: "failed", kind: "screenshot" });
  context.__overviewPayload = verificationChangedOverview;

  await context.__appTest.refreshOverview({ background: true });

  assert.equal(context.__loadRunDetailsCalls.length, callsAfterPlanRefresh + 1);
  assert.equal(context.__appTest.state.selectedRunDetails.state.last_verification.status, "failed");

  const callsAfterVerificationRefresh = context.__loadRunDetailsCalls.length;
  const handoffChangedOverview = snapshot(verificationChangedOverview);
  handoffChangedOverview.runs[0].state.app_context = {
    manual_resume_status: "resumed",
    manual_resume_reason: "Sign-in completed by the user.",
  };
  context.__overviewPayload = handoffChangedOverview;

  await context.__appTest.refreshOverview({ background: true });

  assert.equal(context.__loadRunDetailsCalls.length, callsAfterVerificationRefresh + 1);
  assert.equal(context.__appTest.state.selectedRunDetails.state.app_context.manual_resume_status, "resumed");
});

await runTest("background overview refresh prefers display state over stale full execution summary", async () => {
  const overview = buildOverviewPayload({
    runs: [
      {
        id: "run-display-state-over-full",
        task: "track display state priority",
        steps: 1,
        completed: false,
        execution_state: {
          current_goal: "Full state stale goal",
          plan_health: {
            counts: { total: 2, completed: 0, pending: 2, ready: 1, blocked: 0 },
            next_subgoal_id: "full-stale",
          },
        },
        state: {
          current_goal: "Display state current goal",
          plan_health: {
            counts: { total: 2, completed: 1, pending: 1, ready: 1, blocked: 0 },
            next_subgoal_id: "display-current",
          },
        },
      },
    ],
  });
  const context = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.history-selection": JSON.stringify({ kind: "run", id: "run-display-state-over-full" }),
    },
    overviewPayload: snapshot(overview),
  });

  context.__loadRunDetailsCalls = [];
  vm.runInContext(
    `
renderAll = () => {};
loadRunDetails = async (runId) => {
  globalThis.__loadRunDetailsCalls.push(runId);
  const summary = state.runs.find((run) => run.id === runId) || { id: runId };
  state.selectedRunDetails = JSON.parse(JSON.stringify(summary));
  state.loadingRunDetails = false;
};
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  assert.equal(context.__loadRunDetailsCalls.length, 1);
  assert.equal(context.__appTest.state.selectedRunDetails.state.current_goal, "Display state current goal");

  const changedOverview = snapshot(overview);
  changedOverview.runs[0].state.current_goal = "Display state updated goal";
  changedOverview.runs[0].state.plan_health.next_subgoal_id = "display-updated";
  context.__overviewPayload = changedOverview;

  await context.__appTest.refreshOverview({ background: true });

  assert.equal(context.__loadRunDetailsCalls.length, 2);
  assert.equal(context.__appTest.state.selectedRunDetails.state.current_goal, "Display state updated goal");

  const overviewSignature = vm.runInContext(
    "JSON.parse(buildOverviewSignature(globalThis.__overviewPayload)).runs[0]",
    context
  );
  assert.equal(overviewSignature.current_goal, "Display state updated goal");
  assert.equal(overviewSignature.plan_health.next_subgoal_id, "display-updated");
});

await runTest("background overview refresh reloads selected run details when pending decision action changes", async () => {
  const overview = buildOverviewPayload({
    runs: [
      {
        id: "run-pending-action",
        task: "track pending approval action",
        steps: 1,
        completed: false,
        details_updated_at: 100,
        state: {
          current_goal: "Approve next action",
          pending_decision: {
            id: "approval-1",
            decision_type: "step_approval",
            summary: "Review checkout click.",
            reason: "The action is critical.",
            risk_level: "critical",
            actions: [{ type: "browser_dom_click", selector: "#checkout" }],
          },
        },
      },
    ],
  });
  const context = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.history-selection": JSON.stringify({ kind: "run", id: "run-pending-action" }),
    },
    overviewPayload: snapshot(overview),
  });

  context.__loadRunDetailsCalls = [];
  vm.runInContext(
    `
renderAll = () => {};
loadRunDetails = async (runId) => {
  globalThis.__loadRunDetailsCalls.push(runId);
  const summary = state.runs.find((run) => run.id === runId) || { id: runId };
  state.selectedRunDetails = JSON.parse(JSON.stringify(summary));
  state.loadingRunDetails = false;
};
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  assert.equal(context.__loadRunDetailsCalls.length, 1);
  assert.equal(context.__appTest.state.selectedRunDetails.state.pending_decision.actions[0].selector, "#checkout");

  const changedOverview = snapshot(overview);
  changedOverview.runs[0].state.pending_decision.actions = [
    { type: "browser_dom_click", selector: "#confirm-checkout" },
  ];
  context.__overviewPayload = changedOverview;

  await context.__appTest.refreshOverview({ background: true });

  assert.equal(context.__loadRunDetailsCalls.length, 2);
  assert.equal(
    context.__appTest.state.selectedRunDetails.state.pending_decision.actions[0].selector,
    "#confirm-checkout"
  );
});

await runTest("background overview refresh reloads selected run details when execution state pending decision changes", async () => {
  const overview = buildOverviewPayload({
    runs: [
      {
        id: "run-execution-pending-action",
        task: "track nested approval action",
        steps: 1,
        completed: false,
        details_updated_at: 100,
        execution_state: {
          current_goal: "Approve nested action",
          pending_decision: {
            id: "approval-1",
            decision_type: "step_approval",
            summary: "Review checkout click.",
            reason: "The action is critical.",
            risk_level: "critical",
            actions: [{ type: "browser_dom_click", selector: "#checkout" }],
          },
        },
      },
    ],
  });
  const context = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.history-selection": JSON.stringify({ kind: "run", id: "run-execution-pending-action" }),
    },
    overviewPayload: snapshot(overview),
  });

  context.__loadRunDetailsCalls = [];
  vm.runInContext(
    `
renderAll = () => {};
loadRunDetails = async (runId) => {
  globalThis.__loadRunDetailsCalls.push(runId);
  const summary = state.runs.find((run) => run.id === runId) || { id: runId };
  state.selectedRunDetails = JSON.parse(JSON.stringify(summary));
  state.loadingRunDetails = false;
};
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  assert.equal(context.__loadRunDetailsCalls.length, 1);
  assert.equal(
    context.__appTest.state.selectedRunDetails.execution_state.pending_decision.actions[0].selector,
    "#checkout"
  );

  const changedOverview = snapshot(overview);
  changedOverview.runs[0].execution_state.pending_decision.actions = [
    { type: "browser_dom_click", selector: "#confirm-checkout" },
  ];
  context.__overviewPayload = changedOverview;
  const overviewSignatures = vm.runInContext(
    `[
      state.lastOverviewSignature,
      buildOverviewSignature(globalThis.__overviewPayload),
      buildRunStateRefreshSignature(state.selectedRunDetails),
      buildRunStateRefreshSignature(globalThis.__overviewPayload.runs[0]),
    ]`,
    context
  );
  assert.notEqual(overviewSignatures[0], overviewSignatures[1]);
  assert.notEqual(overviewSignatures[2], overviewSignatures[3]);

  await context.__appTest.refreshOverview({ background: true });

  assert.equal(context.__loadRunDetailsCalls.length, 2);
  assert.equal(
    context.__appTest.state.selectedRunDetails.execution_state.pending_decision.actions[0].selector,
    "#confirm-checkout"
  );
});

await runTest("background overview refresh reloads selected run details when workspace summary changes", async () => {
  const overview = buildOverviewPayload({
    runs: [
      {
        id: "run-workspace-summary",
        task: "track changing workspace state",
        steps: 1,
        completed: false,
        details_updated_at: 100,
        state: {
          current_goal: "Collect local evidence",
          active_specialist: "desktop_operator",
          current_surface_kind: "current_user_desktop",
          last_progress_at: 1711000001,
          workspace_summary: {
            facts: [{ key: "evidence-status", value: "Searching for evidence." }],
            sources: [{ title: "Local draft", url: "file:///draft.md" }],
          },
        },
      },
    ],
  });
  const context = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.history-selection": JSON.stringify({ kind: "run", id: "run-workspace-summary" }),
    },
    overviewPayload: snapshot(overview),
  });

  context.__loadRunDetailsCalls = [];
  vm.runInContext(
    `
renderAll = () => {};
loadRunDetails = async (runId) => {
  globalThis.__loadRunDetailsCalls.push(runId);
  const summary = state.runs.find((run) => run.id === runId) || { id: runId };
  state.selectedRunDetails = JSON.parse(JSON.stringify(summary));
  state.loadingRunDetails = false;
};
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  assert.equal(context.__loadRunDetailsCalls.length, 1);
  assert.equal(context.__appTest.state.selectedRunDetails.state.workspace_summary.facts[0].value, "Searching for evidence.");
  assert.equal(context.__appTest.state.selectedRunDetails.state.current_surface_kind, "current_user_desktop");

  const changedOverview = snapshot(overview);
  changedOverview.runs[0].state.current_surface_kind = "managed_aoryn_browser";
  changedOverview.runs[0].state.last_progress_at = 1711000002;
  changedOverview.runs[0].state.workspace_summary.facts[0].value = "Evidence collected.";
  changedOverview.runs[0].state.workspace_summary.sources[0].title = "Verified local draft";
  context.__overviewPayload = changedOverview;

  await context.__appTest.refreshOverview({ background: true });

  assert.equal(context.__loadRunDetailsCalls.length, 2);
  assert.equal(context.__appTest.state.selectedRunDetails.state.workspace_summary.facts[0].value, "Evidence collected.");
  assert.equal(context.__appTest.state.selectedRunDetails.state.workspace_summary.sources[0].title, "Verified local draft");
  assert.equal(context.__appTest.state.selectedRunDetails.state.current_surface_kind, "managed_aoryn_browser");
});

await runTest("background overview refresh reloads selected run details when recovery trace changes", async () => {
  const overview = buildOverviewPayload({
    runs: [
      {
        id: "run-recovery-trace",
        task: "track changing recovery trace",
        steps: 2,
        completed: false,
        details_updated_at: 100,
        state: {
          current_goal: "Repair the desktop action",
          recovery_reason: "Click target was stale.",
          repair_history: [{ mode: "repair", subgoal_id: "subgoal_01", failure_kind: "stale_target", step: 1 }],
          capability_failures: { "subgoal_01:desktop_gui": ["stale_target"] },
        },
      },
    ],
  });
  const context = createHarness({
    localStorageSeed: {
      "desktop-agent-workspace.history-selection": JSON.stringify({ kind: "run", id: "run-recovery-trace" }),
    },
    overviewPayload: snapshot(overview),
  });

  context.__loadRunDetailsCalls = [];
  vm.runInContext(
    `
renderAll = () => {};
loadRunDetails = async (runId) => {
  globalThis.__loadRunDetailsCalls.push(runId);
  const summary = state.runs.find((run) => run.id === runId) || { id: runId };
  state.selectedRunDetails = JSON.parse(JSON.stringify(summary));
  state.loadingRunDetails = false;
};
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  assert.equal(context.__loadRunDetailsCalls.length, 1);
  assert.equal(context.__appTest.state.selectedRunDetails.state.repair_history.length, 1);

  const changedOverview = snapshot(overview);
  changedOverview.runs[0].state.repair_history.push({
    mode: "replan",
    subgoal_id: "subgoal_01",
    failure_kind: "stale_target",
    message: "Switched to a browser DOM route.",
    step: 2,
  });
  changedOverview.runs[0].state.capability_failures["subgoal_01:desktop_gui"].push("partial_progress");
  context.__overviewPayload = changedOverview;

  await context.__appTest.refreshOverview({ background: true });

  assert.equal(context.__loadRunDetailsCalls.length, 2);
  assert.equal(context.__appTest.state.selectedRunDetails.state.repair_history[1].mode, "replan");
  assert.equal(context.__appTest.state.selectedRunDetails.state.capability_failures["subgoal_01:desktop_gui"][1], "partial_progress");
});

await runTest("background overview refresh rerenders when plan health changes", async () => {
  const activeJob = {
    id: "job-plan-health",
    status: "running",
    task: "Recover and continue",
    updated_at: 1711000000,
    result: {
      run_id: "run-plan-health",
      latest_summary: "Working on the plan.",
      execution_state: {
        current_goal: "Recover blocked page",
        plan_health: {
          counts: { total: 2, completed: 0, pending: 2, ready: 1, blocked: 0 },
          next_subgoal_id: "subgoal_01",
          autonomy: { status: "ready", next_action: "execute" },
          items: [
            { id: "subgoal_01", title: "Recover blocked page", status: "pending", ready: true, is_next: true },
            { id: "subgoal_02", title: "Continue local notes", status: "pending", ready: false },
          ],
        },
      },
    },
  };
  const context = createHarness({
    overviewPayload: buildOverviewPayload({ activeJob: snapshot(activeJob) }),
  });

  context.__renderCount = 0;
  context.__persistCount = 0;
  vm.runInContext(
    `
renderAll = () => { globalThis.__renderCount += 1; };
persistOverviewSnapshot = () => { globalThis.__persistCount += 1; };
loadRunDetails = async (runId) => {
  globalThis.__loadRunDetailsCalls.push(runId);
  state.selectedRunDetails = { id: runId, task: runId };
  state.loadingRunDetails = false;
  renderAll();
};
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  const renderCountAfterInitial = context.__renderCount;
  const persistCountAfterInitial = context.__persistCount;
  const changedActiveJob = snapshot(activeJob);
  changedActiveJob.result.execution_state.plan_health = {
    counts: { total: 2, completed: 1, pending: 1, ready: 1, blocked: 0 },
    next_subgoal_id: "subgoal_02",
    autonomy: { status: "ready", next_action: "execute" },
    items: [
      { id: "subgoal_01", title: "Recover blocked page", status: "completed", ready: false },
      { id: "subgoal_02", title: "Continue local notes", status: "pending", ready: true, is_next: true },
    ],
  };
  context.__overviewPayload = buildOverviewPayload({ activeJob: changedActiveJob });

  await context.__appTest.refreshOverview({ background: true });

  assert.ok(context.__renderCount > renderCountAfterInitial);
  assert.ok(context.__persistCount > persistCountAfterInitial);
  assert.equal(
    context.__appTest.summarizeOverviewPlanHealth(changedActiveJob.result.execution_state.plan_health).autonomy.can_continue,
    null
  );
  assert.equal(context.__appTest.state.activeJob.result.execution_state.plan_health.next_subgoal_id, "subgoal_02");
  assert.notEqual(context.__appTest.state.activeJob.result.execution_state.plan_health.autonomy.can_continue, false);
});

await runTest("background overview refresh rerenders when workspace summary changes", async () => {
  const activeJob = {
    id: "job-workspace-summary",
    status: "running",
    task: "Collect source notes",
    updated_at: 1711000000,
    result: {
      run_id: "run-workspace-summary",
      latest_summary: "Collecting source notes.",
      workspace_summary: {
        facts: [{ key: "source-status", value: "Searching for source candidates." }],
        sources: [{ title: "Local notes", url: "file:///notes.md" }],
      },
      execution_state: {
        current_goal: "Collect source notes",
      },
    },
  };
  const context = createHarness({
    overviewPayload: buildOverviewPayload({ activeJob: snapshot(activeJob) }),
  });

  context.__renderCount = 0;
  context.__persistCount = 0;
  vm.runInContext(
    `
renderAll = () => { globalThis.__renderCount += 1; };
persistOverviewSnapshot = () => { globalThis.__persistCount += 1; };
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  const renderCountAfterInitial = context.__renderCount;
  const persistCountAfterInitial = context.__persistCount;
  const changedActiveJob = snapshot(activeJob);
  changedActiveJob.result.workspace_summary.facts[0].value = "Source candidates collected.";
  context.__overviewPayload = buildOverviewPayload({ activeJob: changedActiveJob });

  await context.__appTest.refreshOverview({ background: true });

  assert.ok(context.__renderCount > renderCountAfterInitial);
  assert.ok(context.__persistCount > persistCountAfterInitial);
  assert.equal(context.__appTest.state.activeJob.result.workspace_summary.facts[0].value, "Source candidates collected.");
});

await runTest("background overview refresh rerenders when active state summary changes", async () => {
  const activeJob = {
    id: "job-state-summary-refresh",
    status: "approval",
    task: "Review state-only progress",
    updated_at: 1711000000,
    result: {
      run_id: "run-state-summary-refresh",
      latest_summary: "Waiting for state-only approval.",
      state: {
        current_goal: "Review generated summary state",
        orchestration_phase: "stage_review",
        stage_review_status: "pending",
        pending_decision: {
          decision_type: "stage_review",
          summary: "Review the summarized stage.",
          risk_level: "high",
        },
        plan_health: {
          counts: { total: 1, completed: 0, ready: 1 },
          next_subgoal_id: "subgoal_01",
          autonomy: { status: "review_required", can_continue: false, requires_review: true },
          items: [{ id: "subgoal_01", title: "Review generated summary state", status: "pending", is_next: true }],
        },
      },
    },
  };
  const context = createHarness({
    overviewPayload: buildOverviewPayload({ activeJob: snapshot(activeJob) }),
  });

  context.__renderCount = 0;
  context.__persistCount = 0;
  vm.runInContext(
    `
renderAll = () => { globalThis.__renderCount += 1; };
persistOverviewSnapshot = () => { globalThis.__persistCount += 1; };
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  const renderCountAfterInitial = context.__renderCount;
  const persistCountAfterInitial = context.__persistCount;
  const changedActiveJob = snapshot(activeJob);
  changedActiveJob.result.state.pending_decision.summary = "Review the updated summarized stage.";
  changedActiveJob.result.state.plan_health.autonomy.status = "ready";
  changedActiveJob.result.state.plan_health.autonomy.can_continue = true;
  changedActiveJob.result.state.stage_review_status = "approved";
  context.__overviewPayload = buildOverviewPayload({ activeJob: changedActiveJob });

  await context.__appTest.refreshOverview({ background: true });

  assert.ok(context.__renderCount > renderCountAfterInitial);
  assert.ok(context.__persistCount > persistCountAfterInitial);
  assert.equal(
    context.__appTest.state.activeJob.result.state.pending_decision.summary,
    "Review the updated summarized stage."
  );
  assert.equal(context.__appTest.state.activeJob.result.state.stage_review_status, "approved");
  assert.equal(context.__appTest.state.activeJob.result.state.plan_health.autonomy.status, "ready");
});

await runTest("background overview refresh rerenders when live telemetry changes", async () => {
  const activeJob = {
    id: "job-live-telemetry",
    status: "running",
    task: "Move through the live desktop",
    updated_at: 1711000000,
    result: {
      run_id: "run-live-telemetry",
      latest_summary: "Moving toward the target.",
      latest_screenshot: "live-shot.png",
      latest_timings: { total: 1.2, capture_initial: 0.2, plan: 0.4, execute: 0.6 },
      live_pointer: { norm_x: 0.25, norm_y: 0.3, phase: "moving", updated_at: 1711000001 },
      live_pointer_trail: [{ norm_x: 0.2, norm_y: 0.25, updated_at: 1711000000 }],
      execution_state: {
        current_goal: "Move through the live desktop",
      },
    },
  };
  const context = createHarness({
    overviewPayload: buildOverviewPayload({ activeJob: snapshot(activeJob) }),
  });

  context.__renderCount = 0;
  context.__persistCount = 0;
  vm.runInContext(
    `
renderAll = () => { globalThis.__renderCount += 1; };
persistOverviewSnapshot = () => { globalThis.__persistCount += 1; };
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  const renderCountAfterInitial = context.__renderCount;
  const persistCountAfterInitial = context.__persistCount;
  const timingChangedJob = snapshot(activeJob);
  timingChangedJob.result.latest_timings = { total: 1.8, capture_initial: 0.2, plan: 0.5, execute: 1.1 };
  context.__overviewPayload = buildOverviewPayload({ activeJob: timingChangedJob });

  await context.__appTest.refreshOverview({ background: true });

  assert.ok(context.__renderCount > renderCountAfterInitial);
  assert.ok(context.__persistCount > persistCountAfterInitial);
  assert.equal(context.__appTest.state.activeJob.result.latest_timings.total, 1.8);

  const renderCountAfterTiming = context.__renderCount;
  const pointerChangedJob = snapshot(timingChangedJob);
  pointerChangedJob.result.live_pointer = { norm_x: 0.62, norm_y: 0.56, phase: "arrived", updated_at: 1711000002 };
  pointerChangedJob.result.live_pointer_trail.push({ norm_x: 0.62, norm_y: 0.56, updated_at: 1711000002 });
  context.__overviewPayload = buildOverviewPayload({ activeJob: pointerChangedJob });

  await context.__appTest.refreshOverview({ background: true });

  assert.ok(context.__renderCount > renderCountAfterTiming);
  assert.equal(context.__appTest.state.activeJob.result.live_pointer.norm_x, 0.62);
  assert.equal(context.__appTest.state.activeJob.result.live_pointer_trail.length, 2);
});

await runTest("background overview refresh rerenders when active progress counters change", async () => {
  const activeJob = {
    id: "job-progress-counters",
    status: "running",
    task: "Track execution progress",
    started_at: 1711000000,
    updated_at: 1711000001,
    result: {
      run_id: "run-progress-counters",
      started_at: 1711000000,
      latest_summary: "Executing the current plan.",
      steps: 1,
      dry_run: true,
      execution_state: {
        current_goal: "Track execution progress",
      },
    },
  };
  const context = createHarness({
    overviewPayload: buildOverviewPayload({ activeJob: snapshot(activeJob) }),
  });

  context.__renderCount = 0;
  context.__persistCount = 0;
  vm.runInContext(
    `
renderAll = () => { globalThis.__renderCount += 1; };
persistOverviewSnapshot = () => { globalThis.__persistCount += 1; };
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  const renderCountAfterInitial = context.__renderCount;
  const persistCountAfterInitial = context.__persistCount;
  const changedCounterJob = snapshot(activeJob);
  changedCounterJob.result.steps = 2;
  changedCounterJob.result.dry_run = false;
  context.__overviewPayload = buildOverviewPayload({ activeJob: changedCounterJob });

  await context.__appTest.refreshOverview({ background: true });

  assert.ok(context.__renderCount > renderCountAfterInitial);
  assert.ok(context.__persistCount > persistCountAfterInitial);
  assert.equal(context.__appTest.state.activeJob.result.steps, 2);
  assert.equal(context.__appTest.state.activeJob.result.dry_run, false);
});

await runTest("background overview refresh rerenders when active run limit changes", async () => {
  const activeJob = {
    id: "job-run-limit",
    status: "running",
    task: "Respect the active execution limit",
    started_at: 1711000000,
    updated_at: 1711000001,
    max_run_seconds: 120,
    config_overrides: {
      max_run_seconds: 30,
    },
    result: {
      run_id: "run-run-limit",
      latest_summary: "Executing within the configured limit.",
      steps: 1,
      execution_state: {
        current_goal: "Respect the active execution limit",
      },
    },
  };
  const context = createHarness({
    overviewPayload: buildOverviewPayload({ activeJob: snapshot(activeJob) }),
  });

  context.__renderCount = 0;
  context.__persistCount = 0;
  vm.runInContext(
    `
renderAll = () => { globalThis.__renderCount += 1; };
persistOverviewSnapshot = () => { globalThis.__persistCount += 1; };
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  const renderCountAfterInitial = context.__renderCount;
  const persistCountAfterInitial = context.__persistCount;
  const changedLimitJob = snapshot(activeJob);
  changedLimitJob.max_run_seconds = 240;
  context.__overviewPayload = buildOverviewPayload({ activeJob: changedLimitJob });

  await context.__appTest.refreshOverview({ background: true });

  assert.ok(context.__renderCount > renderCountAfterInitial);
  assert.ok(context.__persistCount > persistCountAfterInitial);
  assert.equal(context.__appTest.state.activeJob.max_run_seconds, 240);
});

await runTest("background overview refresh rerenders when action trace details change", async () => {
  const activeJob = {
    id: "job-action-trace",
    status: "running",
    task: "Launch the requested desktop app",
    updated_at: 1711000000,
    result: {
      run_id: "run-action-trace",
      latest_summary: "Launching the app.",
      latest_actions: [{ type: "launch_app", app: "calculator" }],
      live_action: { type: "click", x: 320, y: 240, button: "left", clicks: 1, status: "running" },
      execution_state: {
        current_goal: "Launch the requested desktop app",
      },
    },
  };
  const context = createHarness({
    overviewPayload: buildOverviewPayload({ activeJob: snapshot(activeJob) }),
  });

  context.__renderCount = 0;
  context.__persistCount = 0;
  vm.runInContext(
    `
renderAll = () => { globalThis.__renderCount += 1; };
persistOverviewSnapshot = () => { globalThis.__persistCount += 1; };
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  const renderCountAfterInitial = context.__renderCount;
  const persistCountAfterInitial = context.__persistCount;
  const changedActionJob = snapshot(activeJob);
  changedActionJob.result.latest_actions = [{ type: "launch_app", app: "notepad" }];
  context.__overviewPayload = buildOverviewPayload({ activeJob: changedActionJob });

  await context.__appTest.refreshOverview({ background: true });

  assert.ok(context.__renderCount > renderCountAfterInitial);
  assert.ok(context.__persistCount > persistCountAfterInitial);
  assert.equal(context.__appTest.state.activeJob.result.latest_actions[0].app, "notepad");

  const renderCountAfterAction = context.__renderCount;
  const changedLiveActionJob = snapshot(changedActionJob);
  changedLiveActionJob.result.live_action = { type: "click", x: 640, y: 360, button: "left", clicks: 1, status: "running" };
  context.__overviewPayload = buildOverviewPayload({ activeJob: changedLiveActionJob });

  await context.__appTest.refreshOverview({ background: true });

  assert.ok(context.__renderCount > renderCountAfterAction);
  assert.equal(context.__appTest.state.activeJob.result.live_action.x, 640);
});

await runTest("background overview refresh rerenders when step proposal changes", async () => {
  const activeJob = {
    id: "job-step-proposal",
    status: "running",
    task: "Continue the autonomous desktop run",
    updated_at: 1711000000,
    result: {
      run_id: "run-step-proposal",
      latest_summary: "Choosing the next action.",
      step_proposal: {
        capability: "desktop_gui",
        intent: "Click the stale desktop target.",
        risk_level: "low",
        target_scope: "subgoal",
        surface_kind: "current_user_desktop",
        requires_approval: false,
        completes_subgoal: false,
        actions: [{ type: "click", x: 320, y: 240, button: "left" }],
      },
      execution_state: {
        current_goal: "Continue the autonomous desktop run",
      },
    },
  };
  const context = createHarness({
    overviewPayload: buildOverviewPayload({ activeJob: snapshot(activeJob) }),
  });

  context.__renderCount = 0;
  context.__persistCount = 0;
  vm.runInContext(
    `
renderAll = () => { globalThis.__renderCount += 1; };
persistOverviewSnapshot = () => { globalThis.__persistCount += 1; };
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  const renderCountAfterInitial = context.__renderCount;
  const persistCountAfterInitial = context.__persistCount;
  const changedProposalJob = snapshot(activeJob);
  changedProposalJob.result.step_proposal = {
    capability: "browser_dom",
    intent: "Use DOM automation after the desktop target became stale.",
    risk_level: "medium",
    target_scope: "subgoal",
    surface_kind: "managed_aoryn_browser",
    requires_approval: false,
    completes_subgoal: false,
    actions: [{ type: "click", selector: "#continue", button: "left" }],
  };
  context.__overviewPayload = buildOverviewPayload({ activeJob: changedProposalJob });

  await context.__appTest.refreshOverview({ background: true });

  assert.ok(context.__renderCount > renderCountAfterInitial);
  assert.ok(context.__persistCount > persistCountAfterInitial);
  assert.equal(context.__appTest.state.activeJob.result.step_proposal.capability, "browser_dom");
  assert.equal(context.__appTest.state.activeJob.result.step_proposal.actions[0].selector, "#continue");
});

await runTest("background overview refresh rerenders when execution last step changes", async () => {
  const activeJob = {
    id: "job-last-step-proposal",
    status: "running",
    task: "Continue from the latest saved step",
    updated_at: 1711000000,
    result: {
      run_id: "run-last-step-proposal",
      latest_summary: "Continuing from saved state.",
      execution_state: {
        current_goal: "Continue from the latest saved step",
        last_step: {
          capability: "desktop_gui",
          intent: "Click the saved desktop target.",
          risk_level: "low",
          surface_kind: "current_user_desktop",
          actions: [{ type: "click", x: 320, y: 240, button: "left" }],
        },
      },
    },
  };
  const context = createHarness({
    overviewPayload: buildOverviewPayload({ activeJob: snapshot(activeJob) }),
  });

  context.__renderCount = 0;
  context.__persistCount = 0;
  vm.runInContext(
    `
renderAll = () => { globalThis.__renderCount += 1; };
persistOverviewSnapshot = () => { globalThis.__persistCount += 1; };
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  const renderCountAfterInitial = context.__renderCount;
  const persistCountAfterInitial = context.__persistCount;
  const changedLastStepJob = snapshot(activeJob);
  changedLastStepJob.result.execution_state.last_step = {
    capability: "browser_dom",
    intent: "Use DOM automation for the saved step.",
    risk_level: "medium",
    surface_kind: "managed_aoryn_browser",
    actions: [{ type: "click", selector: "#continue", button: "left" }],
  };
  context.__overviewPayload = buildOverviewPayload({ activeJob: changedLastStepJob });

  await context.__appTest.refreshOverview({ background: true });

  assert.ok(context.__renderCount > renderCountAfterInitial);
  assert.ok(context.__persistCount > persistCountAfterInitial);
  assert.equal(context.__appTest.state.activeJob.result.execution_state.last_step.capability, "browser_dom");
});

await runTest("background overview refresh rerenders when active recovery trace changes", async () => {
  const activeJob = {
    id: "job-recovery-trace",
    status: "running",
    task: "Recover the current route",
    updated_at: 1711000000,
    result: {
      latest_summary: "Repairing the current route.",
      execution_state: {
        current_goal: "Repair stale target",
        recovery_reason: "The click target became stale.",
        repair_history: [{ mode: "repair", subgoal_id: "subgoal_01", failure_kind: "stale_target", step: 1 }],
        capability_failures: { "subgoal_01:desktop_gui": ["stale_target"] },
      },
    },
  };
  const context = createHarness({
    overviewPayload: buildOverviewPayload({ activeJob: snapshot(activeJob) }),
  });

  context.__renderCount = 0;
  context.__persistCount = 0;
  vm.runInContext(
    `
renderAll = () => { globalThis.__renderCount += 1; };
persistOverviewSnapshot = () => { globalThis.__persistCount += 1; };
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  const renderCountAfterInitial = context.__renderCount;
  const persistCountAfterInitial = context.__persistCount;
  const changedActiveJob = snapshot(activeJob);
  changedActiveJob.result.execution_state.repair_history.push({
    mode: "replan",
    subgoal_id: "subgoal_01",
    failure_kind: "stale_target",
    message: "Switched to a DOM route.",
    step: 2,
  });
  changedActiveJob.result.execution_state.capability_failures["subgoal_01:desktop_gui"].push("partial_progress");
  context.__overviewPayload = buildOverviewPayload({ activeJob: changedActiveJob });

  await context.__appTest.refreshOverview({ background: true });

  assert.ok(context.__renderCount > renderCountAfterInitial);
  assert.ok(context.__persistCount > persistCountAfterInitial);
  assert.equal(context.__appTest.state.activeJob.result.execution_state.repair_history[1].mode, "replan");
  assert.equal(context.__appTest.state.activeJob.result.execution_state.capability_failures["subgoal_01:desktop_gui"][1], "partial_progress");
});

await runTest("background overview refresh rerenders when active handoff state changes", async () => {
  const activeJob = {
    id: "job-handoff-state",
    status: "running",
    task: "Wait for sign-in and continue",
    updated_at: 1711000000,
    result: {
      latest_summary: "Waiting for the user to finish sign-in.",
      execution_state: {
        current_goal: "Resume after sign-in",
        app_context: {
          human_handoff_kind: "login",
          human_handoff_reason: "Complete sign-in before continuing.",
        },
      },
    },
  };
  const context = createHarness({
    overviewPayload: buildOverviewPayload({ activeJob: snapshot(activeJob) }),
  });

  context.__renderCount = 0;
  context.__persistCount = 0;
  vm.runInContext(
    `
renderAll = () => { globalThis.__renderCount += 1; };
persistOverviewSnapshot = () => { globalThis.__persistCount += 1; };
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  const renderCountAfterInitial = context.__renderCount;
  const persistCountAfterInitial = context.__persistCount;
  const changedActiveJob = snapshot(activeJob);
  changedActiveJob.result.execution_state.app_context = {
    manual_resume_status: "resumed",
    manual_resume_reason: "Sign-in completed by the user.",
  };
  context.__overviewPayload = buildOverviewPayload({ activeJob: changedActiveJob });

  await context.__appTest.refreshOverview({ background: true });

  assert.ok(context.__renderCount > renderCountAfterInitial);
  assert.ok(context.__persistCount > persistCountAfterInitial);
  assert.equal(context.__appTest.state.activeJob.result.execution_state.app_context.manual_resume_status, "resumed");
});

await runTest("background overview refresh notices historical run task graph changes", async () => {
  const run = {
    id: "run-graph-summary",
    task: "Recover from saved graph",
    started_at: 1711000000,
    finished_at: 1711000060,
    steps: 1,
    completed: false,
    can_resume: true,
    state: {
      current_goal: "Recover blocked page",
      task_graph: {
        task: "Recover from saved graph",
        subgoals: [
          { id: "subgoal_01", title: "Recover blocked page", status: "pending", capability_preference: "desktop_gui" },
        ],
      },
    },
  };
  const context = createHarness({
    overviewPayload: buildOverviewPayload({ runs: [snapshot(run)] }),
  });

  context.__renderCount = 0;
  context.__persistCount = 0;
  vm.runInContext(
    `
renderAll = () => { globalThis.__renderCount += 1; };
persistOverviewSnapshot = () => { globalThis.__persistCount += 1; };
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  const renderCountAfterInitial = context.__renderCount;
  const persistCountAfterInitial = context.__persistCount;
  const changedRun = snapshot(run);
  changedRun.state.current_goal = "Continue local notes";
  changedRun.state.task_graph.subgoals = [
    { id: "subgoal_01", title: "Recover blocked page", status: "completed", capability_preference: "desktop_gui" },
    { id: "subgoal_02", title: "Continue local notes", status: "pending", capability_preference: "desktop_gui" },
  ];
  context.__overviewPayload = buildOverviewPayload({ runs: [changedRun] });

  await context.__appTest.refreshOverview({ background: true });

  assert.ok(context.__renderCount > renderCountAfterInitial);
  assert.ok(context.__persistCount > persistCountAfterInitial);
  assert.equal(context.__appTest.state.runs[0].state.current_goal, "Continue local notes");
  assert.equal(context.__appTest.state.runs[0].state.task_graph.subgoals[1].title, "Continue local notes");
});

await runTest("background overview refresh notices replan status changes", async () => {
  const activeJob = {
    id: "job-replan-status",
    status: "running",
    task: "Recover and replan",
    updated_at: 1711000000,
    result: {
      latest_summary: "Recovering from a failed step.",
      execution_state: {
        current_goal: "Recover blocked page",
        stage_review_status: "pending",
        last_replan_reason: "The original route failed.",
      },
    },
  };
  const context = createHarness({
    overviewPayload: buildOverviewPayload({ activeJob: snapshot(activeJob) }),
  });

  context.__renderCount = 0;
  context.__persistCount = 0;
  vm.runInContext(
    `
renderAll = () => { globalThis.__renderCount += 1; };
persistOverviewSnapshot = () => { globalThis.__persistCount += 1; };
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  const renderCountAfterInitial = context.__renderCount;
  const persistCountAfterInitial = context.__persistCount;
  const changedActiveJob = snapshot(activeJob);
  changedActiveJob.result.execution_state.stage_review_status = "approved";
  changedActiveJob.result.execution_state.last_replan_reason = "The replanned route is ready.";
  context.__overviewPayload = buildOverviewPayload({ activeJob: changedActiveJob });

  await context.__appTest.refreshOverview({ background: true });

  assert.ok(context.__renderCount > renderCountAfterInitial);
  assert.ok(context.__persistCount > persistCountAfterInitial);
  assert.equal(context.__appTest.state.activeJob.result.execution_state.stage_review_status, "approved");
  assert.equal(
    context.__appTest.state.activeJob.result.execution_state.last_replan_reason,
    "The replanned route is ready."
  );
});

await runTest("background overview refresh notices plan review status changes", async () => {
  const activeJob = {
    id: "job-plan-review-status",
    status: "running",
    task: "Review generated task plan",
    updated_at: 1711000000,
    result: {
      latest_summary: "Waiting for plan review.",
      plan_review_status: "pending",
      execution_state: {
        current_goal: "Review generated task plan",
        orchestration_phase: "plan_review",
        plan_review_status: "pending",
      },
    },
  };
  const context = createHarness({
    overviewPayload: buildOverviewPayload({ activeJob: snapshot(activeJob) }),
  });

  context.__renderCount = 0;
  context.__persistCount = 0;
  vm.runInContext(
    `
renderAll = () => { globalThis.__renderCount += 1; };
persistOverviewSnapshot = () => { globalThis.__persistCount += 1; };
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  const renderCountAfterInitial = context.__renderCount;
  const persistCountAfterInitial = context.__persistCount;
  const changedActiveJob = snapshot(activeJob);
  changedActiveJob.result.plan_review_status = "approved";
  changedActiveJob.result.execution_state.plan_review_status = "approved";
  context.__overviewPayload = buildOverviewPayload({ activeJob: changedActiveJob });

  await context.__appTest.refreshOverview({ background: true });

  assert.ok(context.__renderCount > renderCountAfterInitial);
  assert.ok(context.__persistCount > persistCountAfterInitial);
  assert.equal(context.__appTest.state.activeJob.result.plan_review_status, "approved");
  assert.equal(context.__appTest.state.activeJob.result.execution_state.plan_review_status, "approved");
});

await runTest("background overview refresh notices terminal job error changes", async () => {
  const job = {
    id: "job-terminal-error",
    status: "failed",
    task: "Diagnose a failed autonomous run",
    updated_at: 1711000000,
    error: "Initial planner failure.",
    result: {
      run_id: "run-terminal-error",
      error: "Initial planner failure.",
      latest_summary: "The run failed during planning.",
    },
  };
  const context = createHarness({
    overviewPayload: buildOverviewPayload({ jobs: [snapshot(job)] }),
  });
  context.__appTest.state.locale = "en-US";

  context.__renderCount = 0;
  context.__persistCount = 0;
  vm.runInContext(
    `
renderAll = () => { globalThis.__renderCount += 1; };
persistOverviewSnapshot = () => { globalThis.__persistCount += 1; };
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  const renderCountAfterInitial = context.__renderCount;
  const persistCountAfterInitial = context.__persistCount;
  const changedJob = snapshot(job);
  changedJob.status = "running";
  changedJob.error = null;
  changedJob.result.error = "Planner crashed after approval cleanup.";
  changedJob.result.pending_decision = {
    summary: "Stale approval should not override the terminal result.",
  };
  context.__overviewPayload = buildOverviewPayload({ jobs: [changedJob] });

  await context.__appTest.refreshOverview({ background: true });

  assert.ok(context.__renderCount > renderCountAfterInitial);
  assert.ok(context.__persistCount > persistCountAfterInitial);
  assert.equal(context.__appTest.state.jobs[0].result.error, "Planner crashed after approval cleanup.");

  context.__jobCardPayload = changedJob;
  const stateInfo = vm.runInContext("buildRecordState(globalThis.__jobCardPayload)", context);
  assert.ok(["Failed", "失败"].includes(stateInfo.label));
  assert.equal(stateInfo.tone, "bad");
  const jobCardHtml = vm.runInContext("renderJobCard(globalThis.__jobCardPayload)", context);
  assert.match(jobCardHtml, /job-card__summary/);
  assert.match(jobCardHtml, /Failed|失败/);
  assert.match(jobCardHtml, /Planner crashed after approval cleanup\./);
  assert.doesNotMatch(jobCardHtml, /Awaiting approval/);
});

await runTest("background overview refresh notices result-only human handoff changes", async () => {
  const job = {
    id: "job-result-handoff",
    status: "running",
    task: "Resume after sign-in",
    updated_at: 1711000000,
    requires_human: false,
    result: {
      run_id: "run-result-handoff",
      requires_human: false,
      latest_summary: "Checking whether sign-in is needed.",
    },
  };
  const context = createHarness({
    overviewPayload: buildOverviewPayload({ jobs: [snapshot(job)] }),
  });

  context.__renderCount = 0;
  context.__persistCount = 0;
  vm.runInContext(
    `
renderAll = () => { globalThis.__renderCount += 1; };
persistOverviewSnapshot = () => { globalThis.__persistCount += 1; };
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  const renderCountAfterInitial = context.__renderCount;
  const persistCountAfterInitial = context.__persistCount;
  const changedJob = snapshot(job);
  changedJob.result.requires_human = true;
  changedJob.result.interruption_kind = "requires_auth";
  changedJob.result.interruption_reason = "Complete sign-in before continuing.";
  context.__overviewPayload = buildOverviewPayload({ jobs: [changedJob] });

  await context.__appTest.refreshOverview({ background: true });

  assert.ok(context.__renderCount > renderCountAfterInitial);
  assert.ok(context.__persistCount > persistCountAfterInitial);
  assert.equal(context.__appTest.state.jobs[0].result.requires_human, true);

  context.__handoffJob = changedJob;
  const stateInfo = vm.runInContext("buildRecordState(globalThis.__handoffJob)", context);
  assert.equal(stateInfo.tone, "warn");
  const handoffChipHtml = vm.runInContext("renderHumanVerificationChip(globalThis.__handoffJob)", context);
  assert.match(handoffChipHtml, /metric-pill warn/);
});

await runTest("background overview refresh notices nested pending decision changes", async () => {
  const activeJob = {
    id: "job-nested-approval",
    status: "approval",
    task: "Review nested plan state",
    updated_at: 1711000000,
    result: {
      latest_summary: "Waiting for nested approval.",
      execution_state: {
        pending_decision: {
          decision_type: "plan_review",
          summary: "Review the nested task plan.",
          reason: "The plan is high risk.",
          risk_level: "high",
        },
      },
    },
  };
  const context = createHarness({
    overviewPayload: buildOverviewPayload({ activeJob: snapshot(activeJob) }),
  });

  context.__renderCount = 0;
  context.__persistCount = 0;
  vm.runInContext(
    `
renderAll = () => { globalThis.__renderCount += 1; };
persistOverviewSnapshot = () => { globalThis.__persistCount += 1; };
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  const renderCountAfterInitial = context.__renderCount;
  const changedActiveJob = snapshot(activeJob);
  changedActiveJob.result.execution_state.pending_decision.summary = "Review the updated nested task plan.";
  context.__overviewPayload = buildOverviewPayload({ activeJob: changedActiveJob });

  await context.__appTest.refreshOverview({ background: true });

  assert.ok(context.__renderCount > renderCountAfterInitial);
  assert.equal(
    context.__appTest.state.activeJob.result.execution_state.pending_decision.summary,
    "Review the updated nested task plan."
  );
});

await runTest("background overview refresh notices pending decision action changes", async () => {
  const activeJob = {
    id: "job-approval-action",
    status: "approval",
    task: "Review a critical step",
    updated_at: 1711000000,
    result: {
      latest_summary: "Waiting for step approval.",
      execution_state: {
        pending_decision: {
          decision_type: "step_approval",
          summary: "Review the next action.",
          reason: "The action is critical.",
          risk_level: "critical",
          actions: [{ type: "browser_dom_click", selector: "#checkout" }],
        },
      },
    },
  };
  const context = createHarness({
    overviewPayload: buildOverviewPayload({ activeJob: snapshot(activeJob) }),
  });

  context.__renderCount = 0;
  context.__persistCount = 0;
  vm.runInContext(
    `
renderAll = () => { globalThis.__renderCount += 1; };
persistOverviewSnapshot = () => { globalThis.__persistCount += 1; };
`,
    context
  );

  context.__appTest.initializeState();
  await context.__appTest.refreshOverview({ initial: true });

  const renderCountAfterInitial = context.__renderCount;
  const persistCountAfterInitial = context.__persistCount;
  const changedActiveJob = snapshot(activeJob);
  changedActiveJob.result.execution_state.pending_decision.actions = [
    { type: "browser_dom_click", selector: "#confirm-checkout" },
  ];
  context.__overviewPayload = buildOverviewPayload({ activeJob: changedActiveJob });

  await context.__appTest.refreshOverview({ background: true });

  assert.ok(context.__renderCount > renderCountAfterInitial);
  assert.ok(context.__persistCount > persistCountAfterInitial);
  assert.equal(
    context.__appTest.state.activeJob.result.execution_state.pending_decision.actions[0].selector,
    "#confirm-checkout"
  );
});
