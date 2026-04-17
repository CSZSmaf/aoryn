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


function buildOverviewPayload({ runs = [], chatLaunchId = "boot-1" } = {}) {
  return {
    meta: {
      chat_launch_id: chatLaunchId,
      defaults: {},
      model_providers: [],
      structured_output_modes: [],
      browser_dom_backends: [],
      browser_channels: [],
    },
    runtime_preferences: {},
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
