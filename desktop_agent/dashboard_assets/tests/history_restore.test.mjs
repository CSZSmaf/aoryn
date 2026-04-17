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
  refreshOverview,
  buildSidebarHistoryItems,
  syncChatLaunchState,
  loadPersistedHistorySelection,
  originals: {
    hydrateDefaults,
    restoreOverviewSnapshot,
    renderAvailableModels,
    updateProviderActionButtons,
    updateProviderStatusHints,
    scheduleProviderInspection,
    buildConfigOverrides,
    fillSelect,
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
  assert.match(chatHtml, /chat-welcome/);
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
