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
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(`${escapedSelector}\\s*\\{([\\s\\S]*?)\\}`, "g");
  const matches = [...source.matchAll(pattern)].map((match) => match[1]);

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
  runs = [],
  chatLaunchId = "boot-1",
  defaults = {},
  runtimePreferences = {},
  modelProviders = [],
  structuredOutputModes = [],
  browserDomBackends = [],
  browserChannels = [],
} = {}) {
  return {
    meta: {
      chat_launch_id: chatLaunchId,
      defaults,
      model_providers: modelProviders,
      structured_output_modes: structuredOutputModes,
      browser_dom_backends: browserDomBackends,
      browser_channels: browserChannels,
    },
    runtime_preferences: runtimePreferences,
    active_job: null,
    jobs: [],
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
  renderRunningMessage,
  renderPendingMessage,
  renderUserMessage,
  renderNormalAssistantMessage,
  refreshOverview,
  buildSidebarHistoryItems,
  syncChatLaunchState,
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

  context.__appTest.state.uiMode = "chat";
  context.__appTest.state.selectedChatSessionId = "chat-1";
  let items = context.__appTest.buildSidebarHistoryItems();
  assert.deepEqual(snapshot(items.map((item) => item.id)), ["chat-1", "run-1", "run-2"]);
  assert.equal(items[0].active, true);
  assert.equal(items[1].active, false);

  context.__appTest.state.uiMode = "agent";
  context.__appTest.state.showWelcome = false;
  context.__appTest.state.selectedRunId = "run-1";
  items = context.__appTest.buildSidebarHistoryItems();
  assert.deepEqual(snapshot(items.map((item) => item.id)), ["chat-1", "run-1", "run-2"]);
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
    },
    runtimePreferences: {
      config_overrides: {
        model_provider: "openai_compatible",
        model_base_url: "https://api.runtime.example/v1",
        model_name: "gpt-runtime",
        model_auto_discover: false,
        model_structured_output: "json_object",
        browser_dom_backend: "playwright",
        browser_channel: "chrome",
        browser_headless: true,
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
  assert.equal(context.document.getElementById("browserChannel").value, "chrome");
  assert.equal(context.document.getElementById("browserHeadless").checked, true);

  const overrides = snapshot(context.__appTest.originals.buildConfigOverrides());
  assert.equal(overrides.model_provider, "openai_compatible");
  assert.equal(overrides.model_base_url, "https://api.runtime.example/v1");
  assert.equal(overrides.model_name, "gpt-runtime");
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
      steps: 2,
      dry_run: false,
    },
  });

  assert.match(chatHtml, /assistant-shell/);
  assert.match(chatHtml, /assistant-card--chat/);
  assert.match(chatHtml, /logo-mark\.png/);
  assert.match(agentHtml, /assistant-shell/);
  assert.match(agentHtml, /assistant-card--run/);
  assert.match(agentHtml, /assistant-run__hero/);
  assert.match(agentHtml, /logo-mark\.png/);
});


await runTest("dashboard brand assets and layout tokens stay on the fallback white shell", async () => {
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

  assert.match(indexSource, /brand-mark__image" src="\/assets\/icons\/logo-mark\.png\?v=__APP_ASSET_VERSION__/);
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
    timeline: [
      {
        step: 1,
        task: "Open the homepage",
        captured_at: 1711000005,
        screenshot: "shot-1.png",
        executed_actions: [{ type: "launch_browser" }],
        plan: { status_summary: "Opened the homepage" },
      },
      {
        step: 2,
        task: "Open pricing",
        captured_at: 1711000040,
        screenshot: "shot-2.png",
        executed_actions: [{ type: "click", text: "Pricing" }],
        plan: { status_summary: "Opened the pricing page" },
      },
    ],
  };

  context.__appTest.state.detailView = "overview";
  context.__appTest.renderInspector();
  assert.match(context.document.getElementById("runDetail").innerHTML, /inspector-overview/);
  assert.match(context.document.getElementById("runDetail").innerHTML, /inspector-section-card--summary/);

  context.__appTest.state.detailView = "timeline";
  context.__appTest.renderInspector();
  assert.match(context.document.getElementById("runDetail").innerHTML, /inspector-timeline-list/);
  assert.match(context.document.getElementById("runDetail").innerHTML, /timeline-item--inspector/);

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
