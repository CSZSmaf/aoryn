const DEFAULT_LOCALE = "zh-CN";
const APP_VERSION = "__APP_VERSION__";
const APP_ASSET_VERSION = "__APP_ASSET_VERSION__";
const LOCALE_STORAGE_KEY = "desktop-agent-workspace.locale";
const UI_MODE_STORAGE_KEY = "desktop-agent-workspace.mode";
const SIDEBAR_COLLAPSED_STORAGE_KEY = "desktop-agent-workspace.sidebar-collapsed";
const OVERVIEW_CACHE_KEY = "desktop-agent-workspace.overview-cache";
const SEND_SHORTCUT_STORAGE_KEY = "desktop-agent-workspace.send-shortcut";
const CHAT_SESSIONS_STORAGE_KEY = "desktop-agent-workspace.chat-sessions";
const HISTORY_SELECTION_STORAGE_KEY = "desktop-agent-workspace.history-selection";
const ACTIVE_CHAT_SESSION_STORAGE_KEY = "desktop-agent-workspace.active-chat-session";
const ACTIVE_CHAT_SESSION_SESSION_KEY = "desktop-agent-workspace.session-active-chat-session";
const CHAT_LAUNCH_SESSION_KEY = "desktop-agent-workspace.session-chat-launch-id";
const CUSTOM_SELECT_IDS = ["languageSelect", "sendShortcutSelect", "modelProvider", "structuredOutput", "availableModels", "browserDomBackend", "browserChannel"];
const DISPLAY_DEVICE_NAME_PATTERN = /DISPLAY(\d+)/i;

const COPY = {
  "zh-CN": {
    document: { title: "Aoryn" },
    sidebar: {
      appTitle: "Aoryn",
      appSubtitle: "任务",
      newTask: "新建",
      history: "历史",
    },
    topbar: {
      menu: "菜单",
      chatMode: "聊天",
      devMode: "开发",
      settings: "设置",
    },
    chat: {
      emptyEyebrow: "Aoryn",
      emptyTitle: "你想让它做什么？",
      emptyBody: "输入目标，执行过程和截图会出现在对话里。",
      inputLabel: "任务",
      inputPlaceholder: "例如：访问 openai.com，点击 login，然后输入邮箱",
      inputHint: "Enter 发送",
      stop: "停止",
      send: "发送",
    },
    settings: {
      eyebrow: "设置",
      title: "设置",
      subtitle: "应用到下一次任务。",
      profileTitle: "本地工作台",
      generalEyebrow: "通用",
      generalTitle: "通用",
      language: "语言",
      inputTitle: "输入",
      sendShortcut: "发送快捷键",
      runtimeEyebrow: "运行",
      runtimeTitle: "执行",
      runtimeHint: "控制下一次任务的步数和暂停。",
      maxSteps: "步数",
      pausePerAction: "暂停",
      providerEyebrow: "模型",
      providerTitle: "连接",
      providerProfile: "提供方",
      baseUrl: "Base URL",
      modelName: "模型",
      apiKey: "API Key",
      structuredOutput: "结构化输出",
      autoDiscover: "自动发现",
      autoDiscoverHint: "优先使用 /v1/models 返回的第一个模型。",
      discoveredModels: "可用模型",
      useSelected: "使用",
      portal: "控制台",
      docs: "文档",
      browserEyebrow: "浏览器",
      browserTitle: "浏览器",
      domBackend: "DOM",
      domBackendHint: "当前仅内置 Playwright。",
      domTimeout: "超时",
      browserChannel: "通道",
      browserPath: "路径",
      headless: "无头模式",
      headlessHint: "适合不需要可视窗口的检查流程。",
    },
    inspector: {
      eyebrow: "详情",
      title: "运行详情",
      open: "详情",
      empty: "选择一条记录后在这里查看。",
      overview: "概览",
      timeline: "时间线",
      gallery: "截图",
    },
    developer: {
      eyebrow: "开发",
      title: "开发台",
      subtitle: "队列、模型和原始运行细节。",
      providerEyebrow: "模型",
      providerTitle: "检查",
      testProvider: "测试",
      refreshModels: "刷新",
      loadModel: "加载",
      providerStatus: "这里显示模型连接状态。",
      queueEyebrow: "队列",
      queueTitle: "最近任务",
      payloadEyebrow: "Payload",
      payloadTitle: "实时快照",
      runEyebrow: "运行",
      runTitle: "时间线",
    },
    common: { refresh: "刷新", close: "×", closeLabel: "关闭" },
  },
  "en-US": {
    document: { title: "Aoryn" },
    sidebar: {
      appTitle: "Aoryn",
      appSubtitle: "Tasks",
      newTask: "New",
      history: "History",
    },
    topbar: {
      menu: "Menu",
      chatMode: "Chat",
      devMode: "Developer",
      settings: "Settings",
    },
    chat: {
      emptyEyebrow: "Aoryn",
      emptyTitle: "What should it do?",
      emptyBody: "Enter a goal and keep the run plus screenshots in the chat.",
      inputLabel: "Task",
      inputPlaceholder: "Example: visit openai.com, click login, then type your email",
      inputHint: "Press Enter to send",
      stop: "Stop",
      send: "Send",
    },
    settings: {
      eyebrow: "Settings",
      title: "Settings",
      subtitle: "Applied to the next task.",
      profileTitle: "Local workspace",
      generalEyebrow: "General",
      generalTitle: "General",
      language: "Language",
      inputTitle: "Input",
      sendShortcut: "Send shortcut",
      runtimeEyebrow: "Runtime",
      runtimeTitle: "Run",
      runtimeHint: "Control step count and pause for the next task.",
      maxSteps: "Steps",
      pausePerAction: "Pause",
      providerEyebrow: "Model",
      providerTitle: "Connection",
      providerProfile: "Provider",
      baseUrl: "Base URL",
      modelName: "Model",
      apiKey: "API Key",
      structuredOutput: "Structured output",
      autoDiscover: "Auto discover",
      autoDiscoverHint: "Prefer the first model returned by /v1/models.",
      discoveredModels: "Available models",
      useSelected: "Use",
      portal: "Portal",
      docs: "Docs",
      browserEyebrow: "Browser",
      browserTitle: "Browser",
      domBackend: "DOM",
      domBackendHint: "Only Playwright is built in right now.",
      domTimeout: "Timeout",
      browserChannel: "Channel",
      browserPath: "Path",
      headless: "Headless",
      headlessHint: "Useful when a visible window is not required.",
    },
    inspector: {
      eyebrow: "Details",
      title: "Run details",
      open: "Details",
      empty: "Select a run to inspect it here.",
      overview: "Overview",
      timeline: "Timeline",
      gallery: "Gallery",
    },
    developer: {
      eyebrow: "Developer",
      title: "Developer console",
      subtitle: "Queue, models, and raw run details.",
      providerEyebrow: "Model",
      providerTitle: "Checks",
      testProvider: "Test",
      refreshModels: "Refresh",
      loadModel: "Load",
      providerStatus: "Provider status appears here.",
      queueEyebrow: "Queue",
      queueTitle: "Recent jobs",
      payloadEyebrow: "Payload",
      payloadTitle: "Live snapshot",
      runEyebrow: "Run",
      runTitle: "Timeline",
    },
    common: { refresh: "Refresh", close: "×", closeLabel: "Close" },
  },
};

const state = {
  meta: null,
  runtimePreferences: null,
  activeJob: null,
  runs: [],
  jobs: [],
  chatSessions: [],
  selectedRunId: null,
  selectedRunDetails: null,
  selectedChatSessionId: null,
  locale: DEFAULT_LOCALE,
  uiMode: "agent",
  detailView: "overview",
  drawerOpen: false,
  settingsOpen: false,
  helpOpen: false,
  sidebarCollapsed: false,
  mobileSidebarOpen: false,
  pollingHandle: null,
  providerSnapshot: null,
  providerStatusMessage: "",
  connected: false,
  usingCachedSnapshot: false,
  hydrated: false,
  autoFollowLatest: true,
  showWelcome: true,
  loadingRunDetails: false,
  pendingTask: null,
  chatPending: false,
  chatStopRequested: false,
  chatAbortController: null,
  chatPendingBadgeTimer: 0,
  chatMessageActionFeedback: null,
  chatMessageActionFeedbackTimer: 0,
  runtimePreferencesSyncTimer: 0,
  sendShortcut: "enter",
  openCustomSelectId: null,
  providerInspectionBusy: false,
  providerInspectionSignature: "",
  providerInspectionToken: 0,
  providerRefreshTimer: null,
  environmentCheck: null,
  environmentCheckLoading: false,
  environmentCheckTimer: 0,
  environmentCheckToken: 0,
  displayDetection: null,
  displayDetectionLoading: false,
  displayDetectionTimer: 0,
  displayDetectionToken: 0,
  settingsRestoreFocus: null,
  helpRestoreFocus: null,
  helpContent: null,
  helpLoading: false,
  helpError: "",
  aboutOpen: false,
  aboutRestoreFocus: null,
  onboardingPrompted: false,
  chatLaunchId: null,
  historySelection: null,
  historySelectionRestored: false,
};

const elements = {
  appShell: document.getElementById("appShell"),
  mobileMenuButton: document.getElementById("mobileSidebarButton"),
  sidebarBrandButton: document.getElementById("sidebarBrandButton"),
  sidebarBackdrop: document.getElementById("sidebarBackdrop"),
  newTaskButton: document.getElementById("newTaskButton"),
  sidebarRunList: document.getElementById("sidebarRunList"),
  refreshRunsButton: document.getElementById("refreshRunsButton"),
  connectionBadge: document.getElementById("connectionBadge"),
  uiModeTabs: document.getElementById("uiModeTabs"),
  settingsButton: document.getElementById("settingsButton"),
  topbarTitle: document.getElementById("topbarTitle"),
  topbarSubtitle: document.getElementById("topbarSubtitle"),
  chatStream: document.getElementById("chatStream"),
  chatScroll: document.getElementById("chatScroll"),
  composerSuggestions: document.getElementById("composerSuggestions"),
  taskForm: document.getElementById("taskForm"),
  taskInput: document.getElementById("taskInput"),
  submitButton: document.getElementById("submitButton"),
  stopButton: document.getElementById("stopButton"),
  submitHint: document.getElementById("submitHint"),
  openInspectorButton: document.getElementById("openInspectorButton"),
  developerTimeline: document.getElementById("developerTimeline"),
  jobList: document.getElementById("jobList"),
  activePayloadView: document.getElementById("activePayloadView"),
  displayDetectionBadge: document.getElementById("displayDetectionBadge"),
  displayDetectionCompare: document.getElementById("displayDetectionCompare"),
  displayDetectionJsonView: document.getElementById("displayDetectionJsonView"),
  testProviderButton: document.getElementById("testProviderButton"),
  refreshModelsButton: document.getElementById("refreshModelsButton"),
  loadLmStudioModelButton: document.getElementById("loadLmStudioModelButton"),
  providerStatusNote: document.getElementById("providerStatusNote"),
  domStatusBadge: document.getElementById("domStatusBadge"),
  openSettingsFromDeveloper: document.getElementById("openSettingsFromDeveloper"),
  settingsOverlay: document.getElementById("settingsOverlay"),
  settingsBackdrop: document.getElementById("settingsBackdrop"),
  settingsModal: document.getElementById("settingsModal"),
  onboardingSection: document.getElementById("onboardingSection"),
  closeSettingsButton: document.getElementById("closeSettingsButton"),
  configBadge: document.getElementById("configBadge"),
  languageSelect: document.getElementById("languageSelect"),
  sendShortcutSelect: document.getElementById("sendShortcutSelect"),
  maxStepsInput: document.getElementById("maxStepsInput"),
  pauseInput: document.getElementById("pauseInput"),
  displaySettingsTitle: document.getElementById("displaySettingsTitle"),
  displaySettingsHint: document.getElementById("displaySettingsHint"),
  displayDetectionSummaryGrid: document.getElementById("displayDetectionSummaryGrid"),
  displayOverrideEnabled: document.getElementById("displayOverrideEnabled"),
  displayOverrideLabel: document.getElementById("displayOverrideLabel"),
  displayOverrideHelp: document.getElementById("displayOverrideHelp"),
  displayOverrideFields: document.getElementById("displayOverrideFields"),
  displayWorkAreaFields: document.getElementById("displayWorkAreaFields"),
  displayMonitorSelect: document.getElementById("displayMonitorSelect"),
  displayDpiScaleInput: document.getElementById("displayDpiScaleInput"),
  displayWorkAreaLeftInput: document.getElementById("displayWorkAreaLeftInput"),
  displayWorkAreaTopInput: document.getElementById("displayWorkAreaTopInput"),
  displayWorkAreaWidthInput: document.getElementById("displayWorkAreaWidthInput"),
  displayWorkAreaHeightInput: document.getElementById("displayWorkAreaHeightInput"),
  displayMonitorLabel: document.getElementById("displayMonitorLabel"),
  displayDpiLabel: document.getElementById("displayDpiLabel"),
  displayWorkAreaLeftLabel: document.getElementById("displayWorkAreaLeftLabel"),
  displayWorkAreaTopLabel: document.getElementById("displayWorkAreaTopLabel"),
  displayWorkAreaWidthLabel: document.getElementById("displayWorkAreaWidthLabel"),
  displayWorkAreaHeightLabel: document.getElementById("displayWorkAreaHeightLabel"),
  displayOverrideStatusNote: document.getElementById("displayOverrideStatusNote"),
  displayResetButton: document.getElementById("displayResetButton"),
  modelProvider: document.getElementById("modelProvider"),
  modelBaseUrl: document.getElementById("modelBaseUrl"),
  modelName: document.getElementById("modelName"),
  modelApiKey: document.getElementById("modelApiKey"),
  structuredOutput: document.getElementById("structuredOutput"),
  modelAutoDiscover: document.getElementById("modelAutoDiscover"),
  availableModels: document.getElementById("availableModels"),
  refreshCatalogButton: document.getElementById("refreshCatalogButton"),
  providerCatalogNote: document.getElementById("providerCatalogNote"),
  applyModelButton: document.getElementById("applyModelButton"),
  openProviderPortalButton: document.getElementById("openProviderPortalButton"),
  openProviderDocsButton: document.getElementById("openProviderDocsButton"),
  browserDomBackend: document.getElementById("browserDomBackend"),
  browserDomTimeout: document.getElementById("browserDomTimeout"),
  browserChannel: document.getElementById("browserChannel"),
  browserExecutablePath: document.getElementById("browserExecutablePath"),
  browserHeadless: document.getElementById("browserHeadless"),
  openHelpCenterButton: document.getElementById("openHelpCenterButton"),
  openDeveloperConsoleButton: document.getElementById("openDeveloperConsoleButton"),
  openAboutButton: document.getElementById("openAboutButton"),
  aboutTitle: document.getElementById("aboutTitle"),
  aboutSubtitle: document.getElementById("aboutSubtitle"),
  aboutAndLogsHint: document.getElementById("aboutAndLogsHint"),
  aboutOverlay: document.getElementById("aboutOverlay"),
  aboutBackdrop: document.getElementById("aboutBackdrop"),
  aboutModal: document.getElementById("aboutModal"),
  closeAboutButton: document.getElementById("closeAboutButton"),
  aboutContent: document.getElementById("aboutContent"),
  helpOverlay: document.getElementById("helpOverlay"),
  helpBackdrop: document.getElementById("helpBackdrop"),
  helpModal: document.getElementById("helpModal"),
  closeHelpButton: document.getElementById("closeHelpButton"),
  helpContent: document.getElementById("helpContent"),
  inspectorOverlay: document.getElementById("inspectorOverlay"),
  inspectorBackdrop: document.getElementById("inspectorBackdrop"),
  closeDrawerButton: document.getElementById("closeDrawerButton"),
  detailTabs: document.getElementById("detailTabs"),
  inspectorSubtitle: document.getElementById("inspectorSubtitle"),
  runDetail: document.getElementById("runDetail"),
  imageLightbox: document.getElementById("imageLightbox"),
  lightboxImage: document.getElementById("lightboxImage"),
  lightboxCaption: document.getElementById("lightboxCaption"),
  lightboxCloseButton: document.getElementById("lightboxCloseButton"),
};

async function initializeApp() {
  initializeState();
  initializeEnhancedControls();
  bindEvents();
  renderAll();
  await refreshOverview({ initial: true });
  if (state.pollingHandle) {
    window.clearInterval(state.pollingHandle);
  }
  state.pollingHandle = window.setInterval(() => {
    void refreshOverview({ background: true });
  }, 2500);
}

document.addEventListener("DOMContentLoaded", () => {
  void initializeApp();
});

function initializeState() {
  state.locale = detectInitialLocale();
  state.uiMode = detectInitialUiMode();
  state.sidebarCollapsed = detectSidebarCollapsed();
  state.sendShortcut = detectSendShortcutMode();
  clearLegacyActiveChatSessionStorage();
  state.chatLaunchId = readSessionStorage(CHAT_LAUNCH_SESSION_KEY) || null;
  state.chatSessions = loadChatSessions();
  state.historySelection = loadPersistedHistorySelection();
  state.selectedChatSessionId = detectInitialChatSessionId(state.chatSessions);
  ensureRuntimePreferencesState();
  fillLanguageOptions();
  fillSendShortcutOptions();
  renderAvailableModels(null);
  updateProviderStatusHints();
  updateProviderActionButtons();
}

function initializeEnhancedControls() {
  CUSTOM_SELECT_IDS.forEach((selectId) => mountCustomSelect(selectId));
  syncCustomSelects();
}

function bindEvents() {
  elements.sidebarBrandButton?.addEventListener("click", toggleSidebar);
  elements.mobileMenuButton?.addEventListener("click", openSidebar);
  elements.sidebarBackdrop?.addEventListener("click", closeSidebar);
  elements.newTaskButton?.addEventListener("click", startNewTask);
  elements.refreshRunsButton?.addEventListener("click", () => refreshOverview({ forceDetailRefresh: true }));
  elements.uiModeTabs?.addEventListener("click", handleModeClick);
  elements.settingsButton?.addEventListener("click", openSettings);
  elements.openSettingsFromDeveloper?.addEventListener("click", openSettings);
  elements.settingsBackdrop?.addEventListener("click", closeSettings);
  elements.closeSettingsButton?.addEventListener("click", closeSettings);
  elements.openHelpCenterButton?.addEventListener("click", openHelpCenter);
  elements.openDeveloperConsoleButton?.addEventListener("click", openDeveloperConsole);
  elements.openAboutButton?.addEventListener("click", openAboutPanel);
  elements.aboutBackdrop?.addEventListener("click", closeAboutPanel);
  elements.closeAboutButton?.addEventListener("click", closeAboutPanel);
  elements.onboardingSection?.addEventListener("click", handleAboutPanelClick);
  elements.aboutContent?.addEventListener("click", handleAboutPanelClick);
  elements.helpBackdrop?.addEventListener("click", closeHelpCenter);
  elements.closeHelpButton?.addEventListener("click", closeHelpCenter);
  elements.languageSelect?.addEventListener("change", (event) => setLocale(event.target.value));
  elements.sendShortcutSelect?.addEventListener("change", (event) => setSendShortcutMode(event.target.value));
  elements.displayOverrideEnabled?.addEventListener("change", handleDisplayOverrideToggle);
  elements.displayResetButton?.addEventListener("click", resetDisplayOverrides);
  elements.taskForm?.addEventListener("submit", handleSubmit);
  elements.taskInput?.addEventListener("keydown", handleTaskInputKeydown);
  elements.stopButton?.addEventListener("click", handleStopTask);
  elements.sidebarRunList?.addEventListener("click", handleHistoryClick);
  elements.chatStream?.addEventListener("click", handleInteractiveClick);
  elements.composerSuggestions?.addEventListener("click", handleInteractiveClick);
  elements.openInspectorButton?.addEventListener("click", openInspectorForCurrent);
  elements.inspectorBackdrop?.addEventListener("click", closeDrawer);
  elements.closeDrawerButton?.addEventListener("click", closeDrawer);
  elements.detailTabs?.addEventListener("click", handleDetailTabClick);
  elements.runDetail?.addEventListener("click", handleInteractiveClick);
  elements.modelProvider?.addEventListener("change", () => handleProviderChange({ force: false }));
  elements.modelBaseUrl?.addEventListener("input", handleModelBaseUrlInput);
  elements.modelBaseUrl?.addEventListener("blur", handleProviderFieldBlur);
  elements.modelApiKey?.addEventListener("blur", handleProviderFieldBlur);
  elements.modelAutoDiscover?.addEventListener("change", updateProviderStatusHints);
  elements.availableModels?.addEventListener("change", updateProviderActionButtons);
  elements.refreshCatalogButton?.addEventListener("click", handleRefreshCatalog);
  elements.applyModelButton?.addEventListener("click", applyDiscoveredModel);
  elements.openProviderPortalButton?.addEventListener("click", () => openProviderLink("portal_url"));
  elements.openProviderDocsButton?.addEventListener("click", () => openProviderLink("docs_url"));
  elements.testProviderButton?.addEventListener("click", () => inspectProvider(tr("正在测试模型连接...", "Testing provider...")));
  elements.refreshModelsButton?.addEventListener("click", () => inspectProvider(tr("正在刷新模型目录...", "Refreshing model catalog...")));
  elements.loadLmStudioModelButton?.addEventListener("click", loadSelectedModelIntoLmStudio);
  elements.imageLightbox?.addEventListener("click", handleLightboxClick);
  elements.lightboxCloseButton?.addEventListener("click", closeLightbox);
  document.addEventListener("keydown", handleGlobalKeydown);
  document.addEventListener("pointerdown", handleGlobalPointerDown);
  window.addEventListener("resize", handleViewportChange);

  [
    elements.modelProvider,
    elements.modelBaseUrl,
    elements.modelName,
    elements.modelApiKey,
    elements.modelAutoDiscover,
    elements.structuredOutput,
    elements.browserDomBackend,
    elements.browserDomTimeout,
    elements.browserChannel,
    elements.browserExecutablePath,
    elements.browserHeadless,
  ]
    .filter(Boolean)
    .forEach((element) => {
      element.addEventListener("change", scheduleRuntimePreferencesSync);
      if (["INPUT", "TEXTAREA"].includes(element.tagName)) {
        element.addEventListener("input", scheduleRuntimePreferencesSync);
      }
    });

  [
    elements.displayMonitorSelect,
    elements.displayDpiScaleInput,
    elements.displayWorkAreaLeftInput,
    elements.displayWorkAreaTopInput,
    elements.displayWorkAreaWidthInput,
    elements.displayWorkAreaHeightInput,
  ]
    .filter(Boolean)
    .forEach((element) => {
      element.addEventListener("change", handleDisplayOverrideDraftChange);
      if (["INPUT", "TEXTAREA"].includes(element.tagName)) {
        element.addEventListener("input", handleDisplayOverrideDraftChange);
      }
    });
}

async function refreshOverview(options = {}) {
  const payload = await fetchJson("/api/overview");
  if (!payload) {
    state.connected = false;
    if (!state.meta) {
      restoreOverviewSnapshot();
    }
    renderAll();
    return;
  }

  state.connected = true;
  state.usingCachedSnapshot = false;
  state.meta = payload.meta || null;
  state.runtimePreferences = payload.runtime_preferences || state.runtimePreferences;
  ensureRuntimePreferencesState();
  syncChatLaunchState(state.meta);
  state.activeJob = payload.active_job || null;
  state.jobs = payload.jobs || [];
  state.runs = payload.runs || [];
  persistOverviewSnapshot(payload);
  clearPendingTaskIfObserved();

  hydrateDefaults();
  restoreInitialHistorySelection(options);
  ensureSelectedRun(options);
  renderAll();

  if (state.selectedRunId && shouldRefreshSelectedRunDetails(options)) {
    await loadRunDetails(state.selectedRunId, { background: Boolean(options.background) });
  } else {
    renderAll();
  }
  maybeAutoOpenOnboarding();
  if (!state.environmentCheck && !state.environmentCheckLoading) {
    scheduleEnvironmentCheck({ immediate: true });
  }
  if (!state.displayDetection && !state.displayDetectionLoading) {
    scheduleDisplayDetection({ immediate: true });
  }
}

function updateJobSnapshot(jobId, patch) {
  if (!jobId || !patch) return;
  state.jobs = (state.jobs || []).map((job) => {
    if (!job || job.id !== jobId) return job;
    return { ...job, ...patch };
  });
}

function markActiveJobStopping() {
  if (!state.activeJob) return null;
  const nextActiveJob = {
    ...state.activeJob,
    cancel_requested: true,
    status: "stopping",
  };
  state.activeJob = nextActiveJob;
  updateJobSnapshot(nextActiveJob.id, {
    cancel_requested: true,
    status: "stopping",
  });
  return nextActiveJob;
}

function hydrateDefaults() {
  if (!state.meta) return;
  const firstHydration = !state.hydrated;
  const defaults = getEffectiveConfigDefaults();

  fillLanguageOptions();
  fillSendShortcutOptions();
  fillSelect(
    elements.modelProvider,
    state.meta.model_providers || [],
    (firstHydration ? defaults.model_provider : elements.modelProvider.value) || defaults.model_provider
  );
  fillSelect(
    elements.structuredOutput,
    state.meta.structured_output_modes || [],
    (firstHydration ? defaults.model_structured_output : elements.structuredOutput.value) || defaults.model_structured_output
  );
  fillSelect(
    elements.browserDomBackend,
    state.meta.browser_dom_backends || [],
    (firstHydration ? defaults.browser_dom_backend : elements.browserDomBackend.value) || defaults.browser_dom_backend
  );
  fillSelect(
    elements.browserChannel,
    localizeBrowserChannels(state.meta.browser_channels || []),
    (firstHydration ? defaults.browser_channel : elements.browserChannel.value) || defaults.browser_channel || ""
  );

  if (firstHydration) {
    elements.maxStepsInput.value = defaults.max_steps ?? "";
    elements.pauseInput.value = defaults.pause_after_action ?? "";
    elements.modelBaseUrl.value = defaults.model_base_url ?? "";
    elements.modelName.value = defaults.model_name ?? "";
    elements.modelApiKey.value = defaults.model_api_key ?? "";
    elements.modelAutoDiscover.checked = Boolean(defaults.model_auto_discover);
    elements.browserDomTimeout.value = defaults.browser_dom_timeout ?? "";
    elements.browserChannel.value = defaults.browser_channel ?? "";
    elements.browserExecutablePath.value = defaults.browser_executable_path ?? "";
    elements.browserHeadless.checked = Boolean(defaults.browser_headless);
    elements.modelProvider.dataset.previousProfile = elements.modelProvider.value || "";
    updateModelBaseUrlAutofillState();
    state.hydrated = true;
  }

  handleProviderChange({ force: firstHydration });
  updateProviderStatusHints();
  updateProviderActionButtons();
  scheduleRuntimePreferencesSync();
}

function ensureSelectedRun(options = {}) {
  const latestRunId = state.runs[0]?.id || null;
  const activeRunId = state.activeJob?.result?.run_id || null;
  const selectedExists = state.runs.some((run) => run.id === state.selectedRunId);

  if (activeRunId && (state.autoFollowLatest || options.forceLatest)) {
    state.selectedRunId = activeRunId;
    state.showWelcome = false;
    if (state.uiMode !== "chat") {
      persistHistorySelection({ kind: "run", id: activeRunId });
    }
    return;
  }

  if (state.pendingTask) return;

  if (state.showWelcome) {
    if (!selectedExists) {
      state.selectedRunId = null;
      state.selectedRunDetails = null;
    }
    return;
  }

  if (!state.selectedRunId || !selectedExists) {
    state.selectedRunId = latestRunId;
    if (latestRunId) {
      state.showWelcome = false;
      if (state.uiMode !== "chat") {
        persistHistorySelection({ kind: "run", id: latestRunId });
      }
    }
  }
}

function shouldRefreshSelectedRunDetails(options = {}) {
  if (!state.selectedRunId || state.showWelcome) return false;
  if (options.forceDetailRefresh || options.forceLatest) return true;
  if (!state.selectedRunDetails || state.selectedRunDetails.id !== state.selectedRunId) return true;

  const summary = state.runs.find((run) => run.id === state.selectedRunId);
  if (!summary) return false;

  return (
    (summary.steps ?? 0) !== (state.selectedRunDetails.steps ?? 0) ||
    Boolean(summary.error) !== Boolean(state.selectedRunDetails.error) ||
    Boolean(summary.completed) !== Boolean(state.selectedRunDetails.completed) ||
    Boolean(summary.cancelled) !== Boolean(state.selectedRunDetails.cancelled) ||
    (summary.cancel_reason || null) !== (state.selectedRunDetails.cancel_reason || null) ||
    Boolean(summary.requires_human) !== Boolean(state.selectedRunDetails.requires_human) ||
    (summary.interruption_kind || null) !== (state.selectedRunDetails.interruption_kind || null) ||
    (summary.interruption_reason || null) !== (state.selectedRunDetails.interruption_reason || null)
  );
}

async function loadRunDetails(runId, options = {}) {
  if (!runId) {
    state.loadingRunDetails = false;
    state.selectedRunDetails = null;
    renderAll();
    return;
  }

  const requestedRunId = runId;
  if (!options.background) {
    state.loadingRunDetails = true;
    renderAll();
  }

  const details = await fetchJson(`/api/runs/${encodeURIComponent(runId)}`);
  if (state.selectedRunId !== requestedRunId) return;

  state.loadingRunDetails = false;
  state.selectedRunDetails = details || null;
  renderAll();
}

function renderAll() {
  applyShellState();
  applyStaticCopy();
  applySupplementalStaticCopy();
  renderTopbar();
  renderSettingsProfile();
  renderDisplayDetection();
  renderOnboardingGuide();
  renderAboutPanel();
  renderSidebarRuns();
  renderChat();
  renderDeveloper();
  renderHelpCenter();
  renderInspector();
  renderProviderCatalogNote();
  updateProviderActionButtons();
  syncCustomSelects();
}

function applyShellState() {
  document.body.dataset.uiMode = state.uiMode;
  document.body.dataset.sidebarCollapsed = String(state.sidebarCollapsed);
  document.body.dataset.sidebarOpen = String(state.mobileSidebarOpen);
  document.body.dataset.authLocked = "false";
  elements.settingsOverlay.hidden = !state.settingsOpen;
  elements.aboutOverlay.hidden = !state.aboutOpen;
  elements.helpOverlay.hidden = !state.helpOpen;
  elements.inspectorOverlay.hidden = !state.drawerOpen;
  elements.sidebarBackdrop.hidden = !state.mobileSidebarOpen;
}


function renderTopbar() {
  const context = getConversationContext();
  const connection = elements.connectionBadge;
  connection.className = "connection-chip connection-chip--status";
  let connectionLabel = tr("离线", "Offline");

  if (state.connected) {
    connection.classList.add("connection-chip--ok");
    connectionLabel = tr("在线", "Online");
  } else if (state.usingCachedSnapshot) {
    connection.classList.add("connection-chip--warn");
    connectionLabel = tr("缓存", "Cached");
  } else {
    connection.classList.add("connection-chip--bad");
    connectionLabel = tr("离线", "Offline");
  }
  connection.setAttribute("title", connectionLabel);
  connection.setAttribute("aria-label", connectionLabel);

  if (state.uiMode === "developer") {
    elements.topbarTitle.textContent = tr("开发台", "Developer");
    elements.topbarSubtitle.textContent = "";
    return;
  }

  if (context.type === "active") {
    elements.topbarTitle.textContent = cleanRunTitle(context.active.task);
    elements.topbarSubtitle.textContent = "";
    return;
  }

  if (context.type === "run") {
    elements.topbarTitle.textContent = cleanRunTitle(context.details.task);
    elements.topbarSubtitle.textContent = "";
    return;
  }

  if (context.type === "pending") {
    elements.topbarTitle.textContent = cleanRunTitle(context.task);
    elements.topbarSubtitle.textContent = "";
    return;
  }

  elements.topbarTitle.textContent = "Aoryn";
  elements.topbarSubtitle.textContent = "";
}

function classifyHistoryTask(task) {
  const source = normalizeText(task).toLowerCase();

  if (!source) return "general";
  if (
    /calculator|calculate|math|equation|sum|total|number|count|\d+\s*[\+\-\*\/=]\s*\d+/.test(source) ||
    /计算|数字|加减乘除/.test(source)
  ) {
    return "calc";
  }
  if (/amazon|shop|shopping|price|buy|product|pants|cart/.test(source) || /购物|商品|价格|购买/.test(source)) {
    return "shop";
  }
  if (/search|find|lookup|research|docs|document|paper|read/.test(source) || /搜索|查找|文档|论文|资料/.test(source)) {
    return "search";
  }
  if (/notepad|note|edit|write|type|draft|file/.test(source) || /记事|编辑|输入|文件|写/.test(source)) {
    return "edit";
  }
  if (/visit|open|login|click|website|browser|site|openai|web/.test(source) || /访问|打开|登录|点击|网页|网站/.test(source)) {
    return "web";
  }
  return "general";
}

function renderHistoryBadge(task) {
  const category = classifyHistoryTask(task);
  const iconMap = {
    calc: `
      <svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true">
        <rect x="6.5" y="4.5" width="11" height="15" rx="3" fill="none" stroke="currentColor" stroke-width="1.7" />
        <path d="M9 9.5h6M9 13h2.5m3.5 0H15m-6 3h2.5m3.5 0H15" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="1.7" />
      </svg>
    `,
    web: `
      <svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="7" fill="none" stroke="currentColor" stroke-width="1.7" />
        <path d="M5.5 12h13M12 5.2c1.9 2 3 4.4 3 6.8s-1.1 4.8-3 6.8c-1.9-2-3-4.4-3-6.8s1.1-4.8 3-6.8Z" fill="none" stroke="currentColor" stroke-width="1.5" />
      </svg>
    `,
    search: `
      <svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="10.5" cy="10.5" r="4.5" fill="none" stroke="currentColor" stroke-width="1.7" />
        <path d="m14 14 4.2 4.2" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="1.7" />
      </svg>
    `,
    shop: `
      <svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M7.5 8.5h9l-.8 9H8.3l-.8-9Z" fill="none" stroke="currentColor" stroke-linejoin="round" stroke-width="1.7" />
        <path d="M9.5 9V8a2.5 2.5 0 0 1 5 0v1" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="1.7" />
      </svg>
    `,
    edit: `
      <svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M8 6.5h8M8 10.5h5.5M8 14.5h4" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="1.7" />
        <path d="m14.7 15.8 3.5-3.5 1.3 1.3-3.5 3.5-2.4.9Z" fill="none" stroke="currentColor" stroke-linejoin="round" stroke-width="1.5" />
        <rect x="6" y="4.5" width="10" height="13" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.5" />
      </svg>
    `,
    general: `
      <svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true">
        <path d="m12 4.8 4.8 7.2L12 19.2 7.2 12 12 4.8Z" fill="none" stroke="currentColor" stroke-linejoin="round" stroke-width="1.7" />
      </svg>
    `,
  };

  return `<span class="history-item__badge history-item__badge--${category}" aria-hidden="true">${iconMap[category] || iconMap.general}</span>`;
}

function renderChat() {
  const context = getConversationContext();
  const messages = [];

  if (context.type === "welcome") {
    messages.push(renderWelcomeMessage());
  } else if (context.type === "pending") {
    messages.push(renderUserMessage(context.task));
    messages.push(renderPendingMessage(context.task));
  } else if (context.type === "loading") {
    messages.push(renderLoadingMessage());
  } else if (context.type === "active") {
    messages.push(renderUserMessage(context.active.task || ""));
    messages.push(renderRunningMessage(context.active));
  } else if (context.type === "run") {
    messages.push(renderUserMessage(context.details.task || ""));
    messages.push(...renderCompletedConversation(context.details));
  }

  elements.chatStream.innerHTML = messages.join("");
  renderComposerSuggestions(context);
  renderComposerState(context);

  if (context.type === "active" || context.type === "pending") {
    window.requestAnimationFrame(() => {
      elements.chatScroll.scrollTop = elements.chatScroll.scrollHeight;
    });
  }
}

function renderWelcomeMessage() {
  return `
    <div class="chat-welcome">
      <p>${escapeHtml(t("chat.emptyEyebrow"))}</p>
      <h2>${escapeHtml(t("chat.emptyTitle"))}</h2>
      <p>${escapeHtml(t("chat.emptyBody"))}</p>
    </div>
  `;
}

function renderPendingMessage(task) {
  return `
    <div class="message message--assistant">
      <article class="assistant-card">
        <div class="assistant-card__head">
          <div>
            <h3>${escapeHtml(tr("已发送", "Queued"))}</h3>
            <p>${escapeHtml(tr("等待第一条进度。", "Waiting for the first update."))}</p>
          </div>
          <span class="status-pill warn">${escapeHtml(tr("等待", "Waiting"))}</span>
        </div>
        <div class="message-actions">
          <span class="metric-pill">${escapeHtml(truncate(task, 42))}</span>
        </div>
      </article>
    </div>
  `;
}

function renderLoadingMessage() {
  return `
    <div class="message message--assistant">
      <article class="assistant-card">
        <div class="assistant-card__head">
          <div>
            <h3>${escapeHtml(tr("加载中", "Loading"))}</h3>
          </div>
          <span class="status-pill">${escapeHtml(tr("加载", "Loading"))}</span>
        </div>
      </article>
    </div>
  `;
}

function renderRunningMessage(active) {
  const progress = active.result || {};
  const previewUrl =
    progress.run_id && progress.latest_screenshot
      ? buildArtifactUrl(progress.run_id, progress.latest_screenshot)
      : null;
  const latestSummary = normalizeText(progress.latest_summary) || tr("等待下一步。", "Waiting for the next step.");
  const latestActions = (progress.latest_actions || []).slice(0, 4);
  const jobState = active.cancel_requested
    ? { label: tr("停止中", "Stopping"), tone: "warn" }
    : { label: tr("执行中", "Running"), tone: "ok" };

  return `
    <div class="message message--assistant">
      <article class="assistant-card">
        <div class="assistant-card__head">
          <div>
            <h3>${escapeHtml(latestSummary)}</h3>
            <p>${escapeHtml(tr("实时执行中。", "The run is still active."))}</p>
          </div>
          <span class="status-pill ${jobState.tone}">${escapeHtml(jobState.label)}</span>
        </div>

        <div class="metric-row">
          ${renderMetricCard(tr("用时", "Time"), formatDuration(active.started_at || progress.started_at))}
          ${renderMetricCard(tr("步骤", "Steps"), String(progress.steps ?? 0))}
        </div>

        ${
          previewUrl
            ? `
              <div class="message-group">
                <img class="message-image" src="${escapeHtml(previewUrl)}" alt="${escapeHtml(tr("最新截图", "Latest screenshot"))}" />
                <div class="message-actions">
                  <button class="secondary-button" type="button" data-lightbox-src="${escapeHtml(previewUrl)}" data-lightbox-caption="${escapeHtml(active.task || "")}">
                    ${escapeHtml(tr("放大", "Zoom"))}
                  </button>
                  ${
                    progress.run_id
                      ? `<button class="secondary-button" type="button" data-open-inspector="${escapeHtml(progress.run_id)}">${escapeHtml(
                          tr("详情", "Details")
                        )}</button>`
                      : ""
                  }
                </div>
              </div>
            `
            : ""
        }

        ${latestActions.length ? `<div class="action-row">${latestActions.map(renderActionPill).join("")}</div>` : ""}

        <div class="message-actions">
          <button class="primary-button" type="button" data-stop-active-task="true">
            ${escapeHtml(active.cancel_requested ? tr("停止中", "Stopping") : tr("停止", "Stop"))}
          </button>
        </div>
      </article>
    </div>
  `;
}

function renderCompletedConversation(details) {
  const messages = [renderResultSummaryMessage(details)];
  const screenshots = collectRunScreenshots(details);
  const steps = (details.timeline || []).slice(-4).reverse();
  const followUps = buildFollowUpSuggestions(details);

  if (screenshots.length) {
    messages.push(renderScreenshotMessage(details, screenshots.slice(0, 4)));
  }
  if (steps.length) {
    messages.push(renderStepMessage(details, steps));
  }
  if (followUps.length) {
    messages.push(renderFollowUpMessage(followUps));
  }

  return messages;
}

function renderResultSummaryMessage(details) {
  const stateInfo = buildRecordState(details);
  const actions = collectLatestActions(details).slice(0, 4);

  return `
    <div class="message message--assistant">
      <article class="assistant-card">
        <div class="assistant-card__head">
          <div>
            <h3>${escapeHtml(stateInfo.label)}</h3>
            <p>${escapeHtml(runSummary(details))}</p>
          </div>
          <span class="status-pill ${stateInfo.tone}">${escapeHtml(stateInfo.label)}</span>
        </div>

        <div class="metric-row">
          ${renderMetricCard(tr("开始", "Start"), formatShortTime(details.started_at))}
          ${renderMetricCard(tr("结束", "End"), formatShortTime(details.finished_at))}
          ${renderMetricCard(tr("步骤", "Steps"), String(details.steps ?? 0))}
        </div>

        <div class="message-actions">
          ${renderExecutionModeChip(details.dry_run)}
          ${renderHumanVerificationChip(details)}
        </div>

        ${actions.length ? `<div class="action-row">${actions.map(renderActionPill).join("")}</div>` : ""}

        <div class="message-actions">
          <button class="secondary-button" type="button" data-open-inspector="${escapeHtml(details.id)}">
            ${escapeHtml(tr("详情", "Details"))}
          </button>
          <button class="secondary-button" type="button" data-prefill-task="${escapeHtml(details.task || "")}">
            ${escapeHtml(tr("继续", "Continue"))}
          </button>
        </div>
      </article>
    </div>
  `;
}

function renderScreenshotMessage(details, screenshots) {
  return `
    <div class="message message--assistant">
      <article class="assistant-card">
        <div class="assistant-card__head">
          <div>
            <h3>${escapeHtml(tr("截图", "Screenshots"))}</h3>
          </div>
          <button class="secondary-button" type="button" data-open-inspector="${escapeHtml(details.id)}">
            ${escapeHtml(tr("更多", "More"))}
          </button>
        </div>

        <div class="message-gallery">
          ${screenshots
            .map(
              (shot) => `
                <figure>
                  <img src="${escapeHtml(shot.src)}" alt="${escapeHtml(shot.alt)}" />
                  <button class="secondary-button" type="button" data-lightbox-src="${escapeHtml(shot.src)}" data-lightbox-caption="${escapeHtml(shot.caption)}">
                    ${escapeHtml(tr("放大", "Zoom"))}
                  </button>
                </figure>
              `
            )
            .join("")}
        </div>
      </article>
    </div>
  `;
}

function renderStepMessage(details, steps) {
  return `
    <div class="message message--assistant">
      <article class="assistant-card">
        <div class="assistant-card__head">
          <div>
            <h3>${escapeHtml(tr("步骤", "Steps"))}</h3>
          </div>
          <button class="secondary-button" type="button" data-open-inspector="${escapeHtml(details.id)}">
            ${escapeHtml(tr("时间线", "Timeline"))}
          </button>
        </div>

        <ol class="step-list">
          ${steps
            .map(
              (step) => `
                <li>
                  <strong>${escapeHtml(step.plan?.status_summary || step.task || tr("无摘要", "No summary"))}</strong>
                  <div class="message-meta">${escapeHtml(formatShortTime(step.captured_at))}</div>
                </li>
              `
            )
            .join("")}
        </ol>
      </article>
    </div>
  `;
}

function renderFollowUpMessage(items) {
  return `
    <div class="message message--assistant">
      <article class="assistant-card">
        <div class="assistant-card__head">
          <div>
            <h3>${escapeHtml(tr("继续", "Continue"))}</h3>
          </div>
        </div>

        <div class="message-group">
          ${items
            .map(
              (item) => `
                <article class="detail-card">
                  <span class="detail-card__label">${escapeHtml(item.title)}</span>
                  <div class="detail-card__value">${escapeHtml(item.description)}</div>
                  <div class="message-actions">
                    <button class="secondary-button" type="button" data-prefill-task="${escapeHtml(item.task)}">
                      ${escapeHtml(item.actionLabel)}
                    </button>
                  </div>
                </article>
              `
            )
            .join("")}
        </div>
      </article>
    </div>
  `;
}

function renderUserMessage(task) {
  return `
    <div class="message message--user">
      <div class="message-bubble">${escapeHtml(cleanRunTitle(task))}</div>
    </div>
  `;
}

function renderComposerSuggestions(context) {
  if (state.activeJob || state.uiMode === "developer" || context.type !== "welcome") {
    elements.composerSuggestions.innerHTML = "";
    return;
  }

  const items = buildStarterSuggestions();
  if (!items.length) {
    elements.composerSuggestions.innerHTML = "";
    return;
  }

  elements.composerSuggestions.innerHTML = items
    .map(
      (item) => `
        <button class="suggestion-chip" type="button" data-prefill-task="${escapeHtml(item.task)}" title="${escapeHtml(item.description || "")}">
          ${escapeHtml(item.label)}
        </button>
      `
    )
    .join("");
}

function renderDeveloper() {
  updateDomStatus();
  elements.openInspectorButton.disabled = !Boolean(state.selectedRunDetails || state.activeJob?.result?.run_id);
  elements.providerStatusNote.textContent = state.providerStatusMessage || t("developer.providerStatus");
  renderDisplayDetectionDeveloperPanel();

  if (!state.jobs.length) {
    elements.jobList.innerHTML = `<div class="empty-state">${escapeHtml(tr("暂无任务", "No recent jobs"))}</div>`;
  } else {
    elements.jobList.innerHTML = state.jobs.map(renderJobCard).join("");
  }

  elements.activePayloadView.textContent = JSON.stringify(state.activeJob?.result || state.activeJob || {}, null, 2);

  if (state.selectedRunDetails?.timeline?.length) {
    elements.developerTimeline.innerHTML = state.selectedRunDetails.timeline
      .slice()
      .reverse()
      .slice(0, 6)
      .map(renderDeveloperTimelineItem)
      .join("");
  } else if (state.activeJob) {
    elements.developerTimeline.innerHTML = renderLiveDeveloperTimeline();
  } else {
    elements.developerTimeline.innerHTML = `<div class="empty-state">${escapeHtml(tr("选择一条记录", "Select a run"))}</div>`;
  }
}

function renderJobCard(job) {
  return `
    <article class="job-card">
      <div class="panel-head">
        <div>
          <p>${escapeHtml(job.id)}</p>
          <h3>${escapeHtml(cleanRunTitle(job.task))}</h3>
        </div>
        <span class="status-pill ${statusTone(job.status)}">${escapeHtml(translateJobStatus(job.status))}</span>
      </div>
    </article>
  `;
}

function renderDeveloperTimelineItem(step) {
  const screenshotUrl =
    state.selectedRunDetails?.id && step.screenshot
      ? buildArtifactUrl(state.selectedRunDetails.id, step.screenshot)
      : null;

  return `
    <article class="timeline-item">
      <div class="timeline-item__head">
        <div>
          <p>${escapeHtml(tr("步骤", "Step"))} ${escapeHtml(String(step.step))}</p>
          <h3>${escapeHtml(step.plan?.status_summary || step.task || tr("无摘要", "No summary"))}</h3>
        </div>
        <span class="status-pill ${step.error ? "bad" : "ok"}">${escapeHtml(step.error ? tr("错误", "Error") : tr("完成", "OK"))}</span>
      </div>
      ${screenshotUrl ? `<img class="timeline-shot" src="${escapeHtml(screenshotUrl)}" alt="${escapeHtml(tr("步骤截图", "Step screenshot"))}" />` : ""}
    </article>
  `;
}

function renderLiveDeveloperTimeline() {
  const progress = state.activeJob?.result || {};
  const previewUrl =
    progress.run_id && progress.latest_screenshot
      ? buildArtifactUrl(progress.run_id, progress.latest_screenshot)
      : null;

  return `
    <article class="timeline-item">
      <div class="timeline-item__head">
        <div>
          <p>${escapeHtml(tr("实时", "Live"))}</p>
          <h3>${escapeHtml(normalizeText(progress.latest_summary) || tr("等待进度", "Waiting for progress"))}</h3>
        </div>
        <span class="status-pill ok">${escapeHtml(tr("执行中", "Running"))}</span>
      </div>
      ${previewUrl ? `<img class="timeline-shot" src="${escapeHtml(previewUrl)}" alt="${escapeHtml(tr("最新截图", "Latest screenshot"))}" />` : ""}
    </article>
  `;
}


function renderDisplayDetection() {
  renderDisplayDetectionSettings();
  renderDisplayDetectionDeveloperPanel();
}

function renderDisplayDetectionSettings() {
  if (!elements.displayDetectionSummaryGrid) return;

  const isEnglish = state.locale === "en-US";
  const snapshot = state.displayDetection;
  const override = snapshot?.override || {};
  const editable = override.editable !== false;

  if (elements.displaySettingsTitle) {
    elements.displaySettingsTitle.textContent = isEnglish ? "Display & Positioning" : "显示与定位";
  }
  if (elements.displaySettingsHint) {
    elements.displaySettingsHint.textContent = isEnglish
      ? "Review what Aoryn detected from Windows. Manual correction only changes runtime planning and window positioning."
      : "这里会显示 Aoryn 从 Windows 识别到的显示环境。手动纠正只会影响运行时规划和窗口定位，不会修改系统显示设置。";
  }
  if (elements.displayOverrideLabel) {
    elements.displayOverrideLabel.textContent = isEnglish ? "Enable manual correction" : "启用手动纠正";
  }
  if (elements.displayOverrideHelp) {
    elements.displayOverrideHelp.textContent = isEnglish
      ? "Manual correction only changes Aoryn's runtime positioning, not the Windows display settings."
      : "手动纠正只会修改 Aoryn 的运行时定位，不会修改 Windows 的显示设置。";
  }
  if (elements.displayMonitorLabel) {
    elements.displayMonitorLabel.textContent = isEnglish ? "Target monitor" : "目标显示器";
  }
  if (elements.displayDpiLabel) {
    elements.displayDpiLabel.textContent = isEnglish ? "DPI / Scale" : "DPI / 缩放";
  }
  if (elements.displayWorkAreaLeftLabel) {
    elements.displayWorkAreaLeftLabel.textContent = isEnglish ? "Work area left" : "工作区左边界";
  }
  if (elements.displayWorkAreaTopLabel) {
    elements.displayWorkAreaTopLabel.textContent = isEnglish ? "Work area top" : "工作区上边界";
  }
  if (elements.displayWorkAreaWidthLabel) {
    elements.displayWorkAreaWidthLabel.textContent = isEnglish ? "Work area width" : "工作区宽度";
  }
  if (elements.displayWorkAreaHeightLabel) {
    elements.displayWorkAreaHeightLabel.textContent = isEnglish ? "Work area height" : "工作区高度";
  }
  if (elements.displayResetButton) {
    elements.displayResetButton.textContent = isEnglish ? "Reset to auto" : "恢复自动识别";
  }

  syncDisplayOverrideInputs();
  updateDisplayOverrideVisibility();

  elements.displayOverrideEnabled.disabled = !editable;
  elements.displayMonitorSelect.disabled = !editable;
  elements.displayDpiScaleInput.disabled = !editable;
  elements.displayWorkAreaLeftInput.disabled = !editable;
  elements.displayWorkAreaTopInput.disabled = !editable;
  elements.displayWorkAreaWidthInput.disabled = !editable;
  elements.displayWorkAreaHeightInput.disabled = !editable;
  elements.displayResetButton.disabled = !editable;

  if (state.displayDetectionLoading && !snapshot) {
    elements.displayDetectionSummaryGrid.innerHTML = `<div class="empty-state">${escapeHtml(isEnglish ? "Reading display detection..." : "正在读取显示识别结果…")}</div>`;
  } else if (!snapshot) {
    elements.displayDetectionSummaryGrid.innerHTML = `<div class="empty-state">${escapeHtml(isEnglish ? "Display detection will appear here after the first refresh." : "首次刷新后会在这里显示识别结果。")}</div>`;
  } else {
    elements.displayDetectionSummaryGrid.innerHTML = buildDisplaySummaryCards(snapshot);
  }

  const tone = override.status === "invalid_override" ? "bad" : override.status === "override" ? "ok" : "";
  if (elements.displayOverrideStatusNote) {
    elements.displayOverrideStatusNote.textContent = buildDisplayOverrideStatusNote(snapshot);
    if (tone) {
      elements.displayOverrideStatusNote.dataset.tone = tone;
    } else {
      delete elements.displayOverrideStatusNote.dataset.tone;
    }
  }
}

function renderDisplayDetectionDeveloperPanel() {
  if (!elements.displayDetectionJsonView || !elements.displayDetectionCompare || !elements.displayDetectionBadge) return;

  const isEnglish = state.locale === "en-US";
  const eyebrow = document.getElementById("displayDetectionPanelEyebrow");
  const title = document.getElementById("displayDetectionPanelTitle");
  if (eyebrow) eyebrow.textContent = isEnglish ? "Display" : "显示";
  if (title) title.textContent = isEnglish ? "Display detection" : "显示识别";

  const snapshot = state.displayDetection;
  const status = snapshot?.override?.status || "auto";
  elements.displayDetectionBadge.className = `connection-chip ${getDisplayDetectionBadgeTone(status)}`;
  elements.displayDetectionBadge.textContent = getDisplayDetectionBadgeLabel(status);

  if (state.displayDetectionLoading && !snapshot) {
    elements.displayDetectionCompare.innerHTML = `<div class="empty-state">${escapeHtml(isEnglish ? "Reading display detection..." : "正在读取显示识别结果…")}</div>`;
    elements.displayDetectionJsonView.textContent = "{}";
    return;
  }

  if (!snapshot) {
    elements.displayDetectionCompare.innerHTML = `<div class="empty-state">${escapeHtml(isEnglish ? "Display detection data will appear here." : "这里会显示显示识别详情。")}</div>`;
    elements.displayDetectionJsonView.textContent = "{}";
    return;
  }

  elements.displayDetectionCompare.innerHTML = `
    <div class="display-compare-grid">
      ${renderDisplayCompareCard(isEnglish ? "Detected" : "系统识别", snapshot.detected)}
      ${renderDisplayCompareCard(isEnglish ? "Effective" : "当前生效", snapshot.effective)}
    </div>
    <p>${escapeHtml(buildDisplayOverrideStatusNote(snapshot))}</p>
  `;
  elements.displayDetectionJsonView.textContent = JSON.stringify(snapshot, null, 2);
}

function syncDisplayOverrideInputs() {
  const configOverrides = state.runtimePreferences?.config_overrides || {};
  fillSelect(elements.displayMonitorSelect, buildDisplayMonitorOptions(), configOverrides.display_override_monitor_device_name || "");
  elements.displayOverrideEnabled.checked = Boolean(configOverrides.display_override_enabled);
  elements.displayDpiScaleInput.value = configOverrides.display_override_dpi_scale ?? "";
  elements.displayWorkAreaLeftInput.value = configOverrides.display_override_work_area_left ?? "";
  elements.displayWorkAreaTopInput.value = configOverrides.display_override_work_area_top ?? "";
  elements.displayWorkAreaWidthInput.value = configOverrides.display_override_work_area_width ?? "";
  elements.displayWorkAreaHeightInput.value = configOverrides.display_override_work_area_height ?? "";
}

function updateDisplayOverrideVisibility() {
  const enabled = Boolean(elements.displayOverrideEnabled?.checked);
  if (elements.displayOverrideFields) {
    elements.displayOverrideFields.hidden = !enabled;
  }
  if (elements.displayWorkAreaFields) {
    elements.displayWorkAreaFields.hidden = !enabled;
  }
}

function ensureRuntimePreferencesState() {
  if (!state.runtimePreferences || typeof state.runtimePreferences !== "object") {
    state.runtimePreferences = {
      config_overrides: {},
      ui_preferences: {},
      updated_at: null,
    };
  }
  if (!state.runtimePreferences.config_overrides || typeof state.runtimePreferences.config_overrides !== "object") {
    state.runtimePreferences.config_overrides = {};
  }
  if (!state.runtimePreferences.ui_preferences || typeof state.runtimePreferences.ui_preferences !== "object") {
    state.runtimePreferences.ui_preferences = {};
  }
  return state.runtimePreferences;
}

function getRuntimeConfigOverrides() {
  return ensureRuntimePreferencesState().config_overrides || {};
}

function getEffectiveConfigDefaults() {
  return {
    ...(state.meta?.defaults || {}),
    ...getRuntimeConfigOverrides(),
  };
}

function isConfigHydrated() {
  return Boolean(state.hydrated);
}

function getConfigLoadingMessage() {
  return tr("正在加载配置...", "Loading configuration...");
}

function persistRuntimePreferencesLocally() {
  const snapshot = ensureRuntimePreferencesState();
  snapshot.config_overrides = buildConfigOverrides();
  snapshot.updated_at = Date.now() / 1000;
  state.runtimePreferences = snapshot;
}

function seedDisplayOverrideDraftFromSnapshot(snapshot = state.displayDetection?.effective) {
  if (!elements.displayOverrideEnabled?.checked || !snapshot) return;

  const currentMonitor = snapshot.current_monitor;
  const workArea = currentMonitor?.work_area;
  const currentDpiScale = Number(snapshot.dpi_scale || 0);

  if (elements.displayMonitorSelect && !elements.displayMonitorSelect.value && currentMonitor?.device_name) {
    elements.displayMonitorSelect.value = currentMonitor.device_name;
  }
  if (
    elements.displayDpiScaleInput &&
    !String(elements.displayDpiScaleInput.value || "").trim() &&
    Number.isFinite(currentDpiScale) &&
    currentDpiScale > 0
  ) {
    elements.displayDpiScaleInput.value = currentDpiScale.toFixed(2).replace(/\.00$/, "");
  }

  const workAreaInputs = [
    elements.displayWorkAreaLeftInput,
    elements.displayWorkAreaTopInput,
    elements.displayWorkAreaWidthInput,
    elements.displayWorkAreaHeightInput,
  ];
  const hasAnyWorkAreaValue = workAreaInputs.some((element) => String(element?.value || "").trim());
  if (!hasAnyWorkAreaValue && workArea) {
    if (elements.displayWorkAreaLeftInput) elements.displayWorkAreaLeftInput.value = String(workArea.left ?? 0);
    if (elements.displayWorkAreaTopInput) elements.displayWorkAreaTopInput.value = String(workArea.top ?? 0);
    if (elements.displayWorkAreaWidthInput) {
      elements.displayWorkAreaWidthInput.value = String(Math.max(0, Number(workArea.right || 0) - Number(workArea.left || 0)));
    }
    if (elements.displayWorkAreaHeightInput) {
      elements.displayWorkAreaHeightInput.value = String(Math.max(0, Number(workArea.bottom || 0) - Number(workArea.top || 0)));
    }
  }
}

function normalizeMonitorDeviceName(deviceName) {
  const normalized = normalizeText(deviceName || "");
  return normalized.replace(/^\\\\\.\\/, "");
}

function handleDisplayOverrideDraftChange() {
  persistRuntimePreferencesLocally();
  scheduleRuntimePreferencesSync();
  scheduleDisplayDetection();
}

function buildDisplayMonitorOptions() {
  const monitors = Array.isArray(state.displayDetection?.detected?.monitors) ? state.displayDetection.detected.monitors : [];
  return [
    { value: "", label: tr("自动", "Auto") },
    ...monitors.map((monitor) => ({
      value: monitor.device_name || "",
      label: `${monitor.device_name || tr("未知显示器", "Unknown monitor")} (${formatWorkArea(monitor.work_area)})`,
    })),
  ];
}

function buildDisplaySummaryCards(snapshot) {
  const effective = snapshot?.effective || {};
  const currentMonitor = effective.current_monitor;
  const taskbar = effective.taskbar;
  const checkedAt = snapshot?.checked_at ? formatTime(snapshot.checked_at) : tr("刚刚", "Just now");
  const cards = [
    { label: tr("当前显示器", "Current monitor"), value: currentMonitor?.device_name || tr("未检测到", "Unavailable") },
    { label: tr("工作区", "Work area"), value: formatWorkArea(currentMonitor?.work_area) },
    { label: tr("虚拟桌面", "Virtual bounds"), value: formatWorkArea(effective.virtual_bounds) },
    { label: tr("DPI / 缩放", "DPI / Scale"), value: formatScale(effective.dpi_scale) },
    { label: tr("任务栏", "Taskbar"), value: formatTaskbar(taskbar) },
    { label: tr("检测时间", "Checked"), value: checkedAt },
  ];

  return cards
    .map(
      (item) => `
        <article class="display-detection-card">
          <strong>${escapeHtml(item.label)}</strong>
          <span>${escapeHtml(item.value)}</span>
        </article>
      `
    )
    .join("");
}

function renderDisplayCompareCard(label, environment) {
  const monitor = environment?.current_monitor;
  return `
    <article class="display-compare-card">
      <strong>${escapeHtml(label)}</strong>
      <span>${escapeHtml((monitor?.device_name || tr("未检测到", "Unavailable")) + " · " + formatWorkArea(monitor?.work_area))}</span>
      <span>${escapeHtml(tr("虚拟桌面", "Virtual bounds") + ": " + formatWorkArea(environment?.virtual_bounds))}</span>
      <span>${escapeHtml(tr("DPI / 缩放", "DPI / Scale") + ": " + formatScale(environment?.dpi_scale))}</span>
      <span>${escapeHtml(tr("任务栏", "Taskbar") + ": " + formatTaskbar(environment?.taskbar))}</span>
    </article>
  `;
}

function buildDisplayOverrideStatusNote(snapshot) {
  if (!snapshot?.override) {
    return tr("显示识别结果会在这里更新。", "Display detection details will appear here.");
  }
  const override = snapshot.override;
  if (override.status === "override") {
    return tr(
      "手动纠正已生效，后续任务会按当前生效值规划和定位。",
      "Manual display correction is active. Future tasks will use the effective values for planning and positioning."
    );
  }
  if (override.status === "invalid_override") {
    return (
      override.warnings?.[0] ||
      tr("已回退到自动识别，请重新确认显示器和工作区设置。", "Aoryn fell back to automatic detection. Review the saved monitor and work-area values.")
    );
  }
  if (override.status === "readonly") {
    return tr("当前平台仅支持只读显示识别。", "Display detection is read-only on this platform.");
  }
  return tr("当前使用自动识别结果。", "Automatic display detection is currently active.");
}

function formatWorkArea(rect) {
  if (!rect) return tr("未检测到", "Unavailable");
  const width = Math.max(0, Number(rect.right || 0) - Number(rect.left || 0));
  const height = Math.max(0, Number(rect.bottom || 0) - Number(rect.top || 0));
  return `${rect.left},${rect.top} ${width}x${height}`;
}

function formatScale(scale) {
  const value = Number(scale || 0);
  if (!Number.isFinite(value) || value <= 0) {
    return tr("未检测到", "Unavailable");
  }
  return `${Math.round(value * 100)}% (${value.toFixed(2)}x)`;
}

function formatTaskbar(taskbar) {
  if (!taskbar) return tr("未检测到", "Unavailable");
  const position = taskbar.position || tr("未知", "unknown");
  const autoHide = taskbar.auto_hide ? tr("自动隐藏", "auto-hide") : tr("固定显示", "visible");
  return `${position} · ${autoHide}`;
}

function getDisplayDetectionBadgeTone(status) {
  if (status === "override") return "connection-chip--ok";
  if (status === "invalid_override") return "connection-chip--warn";
  return "connection-chip--muted";
}

function getDisplayDetectionBadgeLabel(status) {
  if (status === "override") return tr("手动覆盖", "Override");
  if (status === "invalid_override") return tr("覆盖失效", "Invalid");
  if (status === "readonly") return tr("只读", "Read-only");
  return tr("自动识别", "Auto");
}

function handleDisplayOverrideToggle() {
  updateDisplayOverrideVisibility();
  scheduleRuntimePreferencesSync();
  renderAll();
}

function resetDisplayOverrides() {
  if (elements.displayOverrideEnabled) elements.displayOverrideEnabled.checked = false;
  if (elements.displayMonitorSelect) elements.displayMonitorSelect.value = "";
  if (elements.displayDpiScaleInput) elements.displayDpiScaleInput.value = "";
  if (elements.displayWorkAreaLeftInput) elements.displayWorkAreaLeftInput.value = "";
  if (elements.displayWorkAreaTopInput) elements.displayWorkAreaTopInput.value = "";
  if (elements.displayWorkAreaWidthInput) elements.displayWorkAreaWidthInput.value = "";
  if (elements.displayWorkAreaHeightInput) elements.displayWorkAreaHeightInput.value = "";
  updateDisplayOverrideVisibility();
  scheduleRuntimePreferencesSync();
  scheduleDisplayDetection();
  renderAll();
}

function formatMonitorLabel(monitor, { includePrimary = false } = {}) {
  const rawDeviceName = typeof monitor === "string" ? monitor : monitor?.device_name;
  const normalizedDeviceName = normalizeMonitorDeviceName(rawDeviceName);
  const match = normalizedDeviceName.match(DISPLAY_DEVICE_NAME_PATTERN);
  let label = normalizedDeviceName || tr("\u672a\u77e5\u663e\u793a\u5668", "Unknown monitor");

  if (match) {
    label = tr(`\u663e\u793a\u5668 ${match[1]}`, `Display ${match[1]}`);
  }
  if (includePrimary && typeof monitor === "object" && monitor?.is_primary) {
    label += tr(" \u00b7 \u4e3b\u663e\u793a\u5668", " \u00b7 Primary");
  }
  return label;
}

function formatMonitorSummary(monitor) {
  if (!monitor) return tr("\u672a\u68c0\u6d4b\u5230", "Unavailable");
  return `${formatMonitorLabel(monitor, { includePrimary: true })} \u00b7 ${formatWorkArea(monitor.work_area)}`;
}

function buildDisplayMonitorOptions() {
  const monitors = Array.isArray(state.displayDetection?.detected?.monitors) ? state.displayDetection.detected.monitors : [];
  return [
    { value: "", label: tr("\u81ea\u52a8", "Auto") },
    ...monitors.map((monitor) => ({
      value: monitor.device_name || "",
      label: `${formatMonitorLabel(monitor, { includePrimary: true })} \u00b7 ${formatWorkArea(monitor.work_area)}`,
    })),
  ];
}

function buildDisplaySummaryCards(snapshot) {
  const effective = snapshot?.effective || {};
  const currentMonitor = effective.current_monitor;
  const taskbar = effective.taskbar;
  const checkedAt = snapshot?.checked_at ? formatTime(snapshot.checked_at) : tr("\u521a\u521a", "Just now");
  const cards = [
    { label: tr("\u5f53\u524d\u663e\u793a\u5668", "Current monitor"), value: formatMonitorSummary(currentMonitor) },
    { label: tr("\u5de5\u4f5c\u533a", "Work area"), value: formatWorkArea(currentMonitor?.work_area) },
    { label: tr("\u865a\u62df\u684c\u9762", "Virtual bounds"), value: formatWorkArea(effective.virtual_bounds) },
    { label: "DPI / Scale", value: formatScale(effective.dpi_scale) },
    { label: tr("\u4efb\u52a1\u680f", "Taskbar"), value: formatTaskbar(taskbar) },
    { label: tr("\u68c0\u6d4b\u65f6\u95f4", "Checked"), value: checkedAt },
  ];

  return cards
    .map(
      (item) => `
        <article class="display-detection-card">
          <strong>${escapeHtml(item.label)}</strong>
          <span>${escapeHtml(item.value)}</span>
        </article>
      `
    )
    .join("");
}

function renderDisplayCompareCard(label, environment) {
  const monitor = environment?.current_monitor;
  return `
    <article class="display-compare-card">
      <strong>${escapeHtml(label)}</strong>
      <span>${escapeHtml(formatMonitorSummary(monitor))}</span>
      <span>${escapeHtml(`${tr("\u865a\u62df\u684c\u9762", "Virtual bounds")}: ${formatWorkArea(environment?.virtual_bounds)}`)}</span>
      <span>${escapeHtml(`DPI / Scale: ${formatScale(environment?.dpi_scale)}`)}</span>
      <span>${escapeHtml(`${tr("\u4efb\u52a1\u680f", "Taskbar")}: ${formatTaskbar(environment?.taskbar)}`)}</span>
    </article>
  `;
}

function handleDisplayOverrideToggle() {
  if (elements.displayOverrideEnabled?.checked) {
    seedDisplayOverrideDraftFromSnapshot();
  }
  updateDisplayOverrideVisibility();
  persistRuntimePreferencesLocally();
  scheduleRuntimePreferencesSync();
  scheduleDisplayDetection();
  renderAll();
}

function resetDisplayOverrides() {
  if (elements.displayOverrideEnabled) elements.displayOverrideEnabled.checked = false;
  if (elements.displayMonitorSelect) elements.displayMonitorSelect.value = "";
  if (elements.displayDpiScaleInput) elements.displayDpiScaleInput.value = "";
  if (elements.displayWorkAreaLeftInput) elements.displayWorkAreaLeftInput.value = "";
  if (elements.displayWorkAreaTopInput) elements.displayWorkAreaTopInput.value = "";
  if (elements.displayWorkAreaWidthInput) elements.displayWorkAreaWidthInput.value = "";
  if (elements.displayWorkAreaHeightInput) elements.displayWorkAreaHeightInput.value = "";
  updateDisplayOverrideVisibility();
  persistRuntimePreferencesLocally();
  scheduleRuntimePreferencesSync();
  scheduleDisplayDetection();
  renderAll();
}

function renderProviderCatalogNote() {
  if (!elements.providerCatalogNote) return;
  const profile = findProviderProfile(elements.modelProvider.value);
  let note = "";
  let tone = "";

  if (!isConfigHydrated()) {
    note = getConfigLoadingMessage();
  } else if (!profile?.supports_model_refresh) {
    note = "";
  } else if (state.providerInspectionBusy) {
    note = tr("正在读取模型目录...", "Loading available models...");
  } else if (state.providerSnapshot && state.providerSnapshot.provider === profile.value) {
    if (state.providerSnapshot.ok) {
      const count =
        (state.providerSnapshot.catalog_models || []).length || (state.providerSnapshot.loaded_models || []).length || 0;
      note = tr(`已发现 ${count} 个模型。`, `${count} model(s) available.`);
      tone = count ? "ok" : "";
    } else {
      note = state.providerSnapshot.error || tr("无法读取模型目录。", "Could not read the model catalog.");
      tone = "bad";
    }
  }

  elements.providerCatalogNote.textContent = note;
  if (tone) {
    elements.providerCatalogNote.dataset.tone = tone;
  } else {
    delete elements.providerCatalogNote.dataset.tone;
  }
}

function renderInspector() {
  const details = state.selectedRunDetails;
  elements.inspectorSubtitle.textContent = details ? cleanRunTitle(details.task) : t("inspector.empty");

  elements.detailTabs?.querySelectorAll("[data-detail-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.detailView === state.detailView);
  });

  if (!details) {
    elements.runDetail.innerHTML = `<div class="empty-state">${escapeHtml(t("inspector.empty"))}</div>`;
    return;
  }

  if (state.detailView === "timeline") {
    elements.runDetail.innerHTML = renderRunTimeline(details);
    return;
  }

  if (state.detailView === "gallery") {
    elements.runDetail.innerHTML = renderRunGallery(details);
    return;
  }

  elements.runDetail.innerHTML = renderRunOverview(details);
}

function renderRunOverview(details) {
  const stateInfo = buildRecordState(details);
  const screenshots = collectRunScreenshots(details);
  const latestActions = collectLatestActions(details).slice(0, 4);

  return `
    <article class="detail-card">
      <span class="detail-card__label">${escapeHtml(tr("状态", "Status"))}</span>
      <div class="detail-card__value">${escapeHtml(stateInfo.label)}</div>
      <div class="message-actions">
        <span class="status-pill ${stateInfo.tone}">${escapeHtml(stateInfo.label)}</span>
        ${renderExecutionModeChip(details.dry_run)}
        ${renderHumanVerificationChip(details)}
      </div>
    </article>

    <div class="summary-grid">
      ${renderDetailMetricCard(tr("开始", "Start"), formatShortTime(details.started_at))}
      ${renderDetailMetricCard(tr("结束", "End"), formatShortTime(details.finished_at))}
      ${renderDetailMetricCard(tr("截图", "Shots"), String(screenshots.length))}
    </div>

    ${latestActions.length ? `<article class="detail-card"><div class="action-row">${latestActions.map(renderActionPill).join("")}</div></article>` : ""}

    ${
      screenshots[0]
        ? `
          <article class="detail-card">
            <img class="message-image" src="${escapeHtml(screenshots[0].src)}" alt="${escapeHtml(screenshots[0].alt)}" />
            <div class="message-actions">
              <button class="secondary-button" type="button" data-lightbox-src="${escapeHtml(screenshots[0].src)}" data-lightbox-caption="${escapeHtml(screenshots[0].caption)}">
                ${escapeHtml(tr("放大", "Zoom"))}
              </button>
            </div>
          </article>
        `
        : ""
    }
  `;
}

function renderRunTimeline(details) {
  if (!(details.timeline || []).length) {
    return `<div class="empty-state">${escapeHtml(tr("暂无时间线", "No timeline yet"))}</div>`;
  }

  return (details.timeline || [])
    .map((step) => {
      const screenshotUrl = details.id && step.screenshot ? buildArtifactUrl(details.id, step.screenshot) : null;
      return `
        <article class="timeline-item">
          <div class="timeline-item__head">
            <div>
              <p>${escapeHtml(tr("步骤", "Step"))} ${escapeHtml(String(step.step))}</p>
              <h3>${escapeHtml(step.plan?.status_summary || step.task || tr("无摘要", "No summary"))}</h3>
            </div>
            <span class="status-pill ${step.error ? "bad" : "ok"}">${escapeHtml(step.error ? tr("错误", "Error") : tr("完成", "OK"))}</span>
          </div>
          ${(step.executed_actions || []).length ? `<div class="action-row">${(step.executed_actions || []).map(renderActionPill).join("")}</div>` : ""}
          ${
            screenshotUrl
              ? `
                <img class="timeline-shot" src="${escapeHtml(screenshotUrl)}" alt="${escapeHtml(tr("步骤截图", "Step screenshot"))}" />
                <div class="message-actions">
                  <button class="secondary-button" type="button" data-lightbox-src="${escapeHtml(screenshotUrl)}" data-lightbox-caption="${escapeHtml(step.plan?.status_summary || step.task || "")}">
                    ${escapeHtml(tr("放大", "Zoom"))}
                  </button>
                </div>
              `
              : ""
          }
        </article>
      `;
    })
    .join("");
}

function renderRunGallery(details) {
  const screenshots = collectRunScreenshots(details);
  if (!screenshots.length) {
    return `<div class="empty-state">${escapeHtml(tr("暂无截图", "No screenshots"))}</div>`;
  }

  return `
    <div class="detail-gallery">
      ${screenshots
        .map(
          (shot) => `
            <figure>
              <img src="${escapeHtml(shot.src)}" alt="${escapeHtml(shot.alt)}" />
              <button class="secondary-button" type="button" data-lightbox-src="${escapeHtml(shot.src)}" data-lightbox-caption="${escapeHtml(shot.caption)}">
                ${escapeHtml(tr("放大", "Zoom"))}
              </button>
            </figure>
          `
        )
        .join("")}
    </div>
  `;
}

function handleModeClick(event) {
  const button = event.target.closest("[data-ui-mode]");
  if (!button) return;
  setUiMode(button.dataset.uiMode);
}

function handleInteractiveClick(event) {
  const lightboxTrigger = event.target.closest("[data-lightbox-src]");
  if (lightboxTrigger) {
    openLightbox(lightboxTrigger.dataset.lightboxSrc, lightboxTrigger.dataset.lightboxCaption);
    return;
  }

  const prefillTrigger = event.target.closest("[data-prefill-task]");
  if (prefillTrigger) {
    prefillTask(prefillTrigger.dataset.prefillTask || "");
    return;
  }

  const inspectorTrigger = event.target.closest("[data-open-inspector]");
  if (inspectorTrigger) {
    openInspectorForRun(inspectorTrigger.dataset.openInspector);
    return;
  }

  const stopTrigger = event.target.closest("[data-stop-active-task]");
  if (stopTrigger) {
    handleStopTask();
  }
}

function handleDetailTabClick(event) {
  const button = event.target.closest("[data-detail-view]");
  if (!button) return;
  setDetailView(button.dataset.detailView);
}

function handleTaskInputKeydown(event) {
  if (event.key !== "Enter" || event.isComposing) return;

  if (state.sendShortcut === "ctrl-enter") {
    if (!event.ctrlKey) return;
    event.preventDefault();
    if (elements.submitButton.disabled) return;
    elements.taskForm.requestSubmit();
    return;
  }

  if (event.shiftKey) return;
  event.preventDefault();
  if (elements.submitButton.disabled) return;
  elements.taskForm.requestSubmit();
}

async function handleStopTask() {
  if (state.uiMode === "chat" && state.chatPending) {
    if (state.chatStopRequested) {
      renderAll();
      return;
    }
    if (state.chatStreamDraft?.completed || !state.chatAbortController) {
      state.chatStopRequested = true;
      finalizeStoppedChatDraft();
      renderAll();
      return;
    }
    state.chatStopRequested = true;
    if (state.chatAbortController) {
      try {
        state.chatAbortController.abort();
      } catch {
        // Ignore abort failures.
      }
    }
    renderAll();
    scheduleEnvironmentCheck({ immediate: true });
    return;
  }

  if (!state.activeJob || state.activeJob.cancel_requested) {
    renderAll();
    return;
  }

  const previousActiveJob = state.activeJob ? { ...state.activeJob } : null;
  const previousJobs = Array.isArray(state.jobs) ? state.jobs.map((job) => (job ? { ...job } : job)) : [];
  markActiveJobStopping();
  renderAll();
  const response = await postJson("/api/tasks/stop", {});

  if (!response.ok) {
    state.activeJob = previousActiveJob;
    state.jobs = previousJobs;
    elements.submitHint.textContent = response.payload?.error || tr("停止失败", "Failed to stop the task");
    renderAll();
    return;
  }

  state.activeJob = {
    ...state.activeJob,
    ...(response.payload || {}),
    cancel_requested: true,
    status: "stopping",
  };
  updateJobSnapshot(state.activeJob.id, {
    ...(response.payload || {}),
    cancel_requested: true,
    status: "stopping",
  });
  renderAll();
  await refreshOverview({ forceDetailRefresh: true });
}

function handleGlobalKeydown(event) {
  if (state.openCustomSelectId && event.key === "Escape") {
    event.preventDefault();
    closeCustomSelect({ restoreFocus: true });
    return;
  }

  if (event.key === "Escape") {
    if (!elements.imageLightbox.hidden) {
      closeLightbox();
      return;
    }
    if (state.drawerOpen) {
      closeDrawer();
      return;
    }
    if (state.aboutOpen) {
      closeAboutPanel();
      return;
    }
    if (state.settingsOpen) {
      closeSettings();
      return;
    }
    if (state.mobileSidebarOpen) {
      closeSidebar();
    }
    return;
  }

  if (state.settingsOpen && event.key === "Tab") {
    trapFocusWithin(event, elements.settingsModal);
  }
  if (state.aboutOpen && event.key === "Tab") {
    trapFocusWithin(event, elements.aboutModal);
  }

  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "b" && !isTypingTarget(event.target)) {
    event.preventDefault();
    toggleSidebar();
  }
}

function handleGlobalPointerDown(event) {
  if (!state.openCustomSelectId) return;
  if (event.target.closest(".custom-select")) return;
  closeCustomSelect({ restoreFocus: false });
}

function openSettings() {
  state.settingsRestoreFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  state.settingsOpen = true;
  renderAll();
  scheduleProviderInspection({ immediate: true, force: true, message: tr("正在读取模型目录...", "Loading available models...") });
  window.requestAnimationFrame(() => {
    getFocusableNodes(elements.settingsModal)[0]?.focus();
  });
}

function closeSettings() {
  window.clearTimeout(state.providerRefreshTimer);
  closeCustomSelect({ restoreFocus: false });
  state.settingsOpen = false;
  renderAll();
  if (state.settingsRestoreFocus?.focus) {
    window.requestAnimationFrame(() => {
      state.settingsRestoreFocus.focus();
      state.settingsRestoreFocus = null;
    });
  }
}

function openAboutPanel() {
  state.aboutRestoreFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  closeCustomSelect({ restoreFocus: false });
  state.settingsOpen = false;
  state.helpOpen = false;
  state.aboutOpen = true;
  renderAll();
  window.requestAnimationFrame(() => {
    getFocusableNodes(elements.aboutModal)[0]?.focus();
  });
}

function closeAboutPanel() {
  state.aboutOpen = false;
  renderAll();
  if (state.aboutRestoreFocus?.focus) {
    window.requestAnimationFrame(() => {
      state.aboutRestoreFocus.focus();
      state.aboutRestoreFocus = null;
    });
  }
}

function getUiPreferences() {
  return state.runtimePreferences?.ui_preferences || { onboarding_completed: false };
}

function isOnboardingComplete() {
  return Boolean(getUiPreferences().onboarding_completed);
}

function maybeAutoOpenOnboarding() {
  if (state.onboardingPrompted || isOnboardingComplete()) return;
  if (state.settingsOpen || state.helpOpen || state.aboutOpen || state.drawerOpen) return;
  state.onboardingPrompted = true;
  openSettings();
}

async function updateUiPreferences(patch) {
  const nextPreferences = { ...getUiPreferences(), ...(patch || {}) };
  try {
    const snapshot = await postJson("/api/runtime-preferences", { ui_preferences: nextPreferences });
    if (snapshot.ok && snapshot.payload) {
      state.runtimePreferences = snapshot.payload;
    }
  } catch {
    state.runtimePreferences = {
      ...(state.runtimePreferences || {}),
      ui_preferences: nextPreferences,
    };
  }
  renderAll();
  scheduleEnvironmentCheck({ immediate: true });
}

function applyOnboardingProvider(providerValue) {
  if (!elements.modelProvider) return;
  elements.modelProvider.value = providerValue;
  syncCustomSelect(elements.modelProvider);
  handleProviderChange({ force: true });
  updateProviderStatusHints();
  scheduleRuntimePreferencesSync();
  renderAll();
}

function openInspectorForCurrent() {
  const activeRunId = state.activeJob?.result?.run_id;
  if (activeRunId) {
    openInspectorForRun(activeRunId);
    return;
  }
  if (state.selectedRunId) {
    openInspectorForRun(state.selectedRunId);
  }
}

function openInspectorForRun(runId) {
  if (!runId) return;
  if (runId !== state.selectedRunId || !state.selectedRunDetails) {
    selectRun(runId, { openDrawer: true, manualSelection: true });
    return;
  }
  openDrawer();
}

function openDrawer() {
  if (!state.selectedRunDetails && !state.selectedRunId) return;
  state.drawerOpen = true;
  renderAll();
}

function closeDrawer() {
  state.drawerOpen = false;
  renderAll();
}

function toggleSidebar() {
  if (window.innerWidth <= 960) {
    if (state.mobileSidebarOpen) {
      closeSidebar();
    } else {
      openSidebar();
    }
    return;
  }

  state.sidebarCollapsed = !state.sidebarCollapsed;
  safeStorageSet(SIDEBAR_COLLAPSED_STORAGE_KEY, String(state.sidebarCollapsed));
  renderAll();
}

function openSidebar() {
  state.mobileSidebarOpen = true;
  renderAll();
}

function closeSidebar() {
  state.mobileSidebarOpen = false;
  renderAll();
}

function handleViewportChange() {
  if (window.innerWidth > 960 && state.mobileSidebarOpen) {
    state.mobileSidebarOpen = false;
    renderAll();
  }
}

function getFocusableNodes(container) {
  if (!container) return [];
  return Array.from(
    container.querySelectorAll(
      'button:not([disabled]):not([hidden]), [href], input:not([disabled]):not([type="hidden"]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )
  ).filter((node) => !node.hidden && node.offsetParent !== null);
}

function trapFocusWithin(event, container) {
  const focusable = getFocusableNodes(container);
  if (!focusable.length) return;

  const first = focusable[0];
  const last = focusable[focusable.length - 1];

  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function setDetailView(view) {
  state.detailView = ["overview", "timeline", "gallery"].includes(view) ? view : "overview";
  renderAll();
  return;
  if (elements.openAboutButton) {
    elements.openAboutButton.textContent = tr("鍏充簬涓庢棩蹇?", "About & Logs");
  }
  if (elements.aboutAndLogsHint) {
    elements.aboutAndLogsHint.textContent = tr(
      "鏌ョ湅鐗堟湰淇℃伅銆佹墦寮€閰嶇疆涓庢棩蹇楃洰褰曪紝浠ュ強蹇€熷洖鐪嬫渶杩戣繍琛岃褰曘€?",
      "Check the app version, open config and log folders, and jump back to recent runs."
    );
  }
  const aboutAndLogsTitle = document.getElementById("aboutAndLogsTitle");
  if (aboutAndLogsTitle) {
    aboutAndLogsTitle.textContent = tr("鍏充簬涓庢棩蹇?", "About & Logs");
  }
  if (elements.aboutTitle) {
    elements.aboutTitle.textContent = tr("鍏充簬 Aoryn", "About Aoryn");
  }
  if (elements.aboutSubtitle) {
    elements.aboutSubtitle.textContent = tr("鐗堟湰銆佽瘖鏂笌杩愯璁板綍", "Version, diagnostics, and logs");
  }
  elements.aboutBackdrop?.setAttribute("aria-label", tr("鍏抽棴鍏充簬闈㈡澘", "Close about panel"));
  elements.closeAboutButton?.setAttribute("aria-label", closeLabel);
}


function prefillTask(task) {
  const nextTask = String(task || "").trim();
  if (nextTask) {
    elements.taskInput.value = nextTask;
  }
  state.showWelcome = false;
  if (state.uiMode !== "user") {
    state.uiMode = "user";
    safeStorageSet(UI_MODE_STORAGE_KEY, state.uiMode);
  }
  closeSettings();
  closeDrawer();
  closeSidebar();
  renderAll();
  window.requestAnimationFrame(() => {
    elements.taskInput.focus();
    const end = elements.taskInput.value.length;
    if (typeof elements.taskInput.setSelectionRange === "function") {
      elements.taskInput.setSelectionRange(end, end);
    }
  });
}

function fillLanguageOptions() {
  const items =
    state.meta?.ui_languages?.length
      ? state.meta.ui_languages.map((item) => ({
          value: item.value,
          label: item.value === "zh-CN" ? "简体中文" : item.value === "en-US" ? "English" : item.label || item.value,
        }))
      : [
          { value: "zh-CN", label: "简体中文" },
          { value: "en-US", label: "English" },
        ];

  fillSelect(elements.languageSelect, items, state.locale);
}

function fillSendShortcutOptions() {
  fillSelect(
    elements.sendShortcutSelect,
    [
      { value: "enter", label: tr("Enter 发送", "Enter to send") },
      { value: "ctrl-enter", label: tr("Ctrl+Enter 发送", "Ctrl+Enter to send") },
    ],
    state.sendShortcut
  );
}

function setSendShortcutMode(mode) {
  state.sendShortcut = mode === "ctrl-enter" ? "ctrl-enter" : "enter";
  safeStorageSet(SEND_SHORTCUT_STORAGE_KEY, state.sendShortcut);
  if (elements.sendShortcutSelect) {
    elements.sendShortcutSelect.value = state.sendShortcut;
    syncCustomSelect(elements.sendShortcutSelect);
  }
}

function localizeBrowserChannels(items) {
  const source =
    items?.length
      ? items
      : [
          { value: "", label: "System default" },
          { value: "msedge", label: "Microsoft Edge" },
          { value: "chrome", label: "Google Chrome" },
          { value: "firefox", label: "Mozilla Firefox" },
        ];

  return source.map((item) => {
    const value = item.value ?? "";
    if (value === "") {
      return { value, label: tr("系统默认", "System default") };
    }
    return { value, label: item.label || value };
  });
}

function mountCustomSelect(selectId) {
  const select = document.getElementById(selectId);
  if (!select || select.dataset.customSelectMounted === "true") return;

  const wrapper = document.createElement("div");
  wrapper.className = "custom-select";
  wrapper.dataset.selectId = selectId;
  wrapper.addEventListener("click", handleCustomSelectClick);
  wrapper.addEventListener("keydown", handleCustomSelectKeydown);

  select.classList.add("native-select");
  select.insertAdjacentElement("afterend", wrapper);
  select.dataset.customSelectMounted = "true";
  select.addEventListener("change", () => syncCustomSelect(select));

  syncCustomSelect(select);
}

function syncCustomSelects() {
  CUSTOM_SELECT_IDS.forEach((selectId) => syncCustomSelect(document.getElementById(selectId)));
}

function syncCustomSelect(select) {
  if (!select) return;
  const wrapper = select.nextElementSibling;
  if (!wrapper || !wrapper.classList.contains("custom-select")) return;

  const selectedOption = select.options[select.selectedIndex] || select.options[0] || null;
  const selectedLabel = selectedOption ? selectedOption.textContent.trim() : tr("未选择", "Not selected");
  const isOpen = state.openCustomSelectId === select.id;
  const options = Array.from(select.options || []);

  wrapper.classList.toggle("is-open", isOpen);
  wrapper.classList.toggle("is-disabled", Boolean(select.disabled));
  wrapper.innerHTML = `
    <button
      class="custom-select__trigger"
      type="button"
      aria-haspopup="listbox"
      aria-expanded="${isOpen ? "true" : "false"}"
      aria-controls="custom-select-menu-${escapeHtml(select.id)}"
      ${select.disabled ? "disabled" : ""}
    >
      <span class="custom-select__value">${escapeHtml(selectedLabel)}</span>
      <span class="custom-select__chevron" aria-hidden="true">
        <svg class="icon-svg" viewBox="0 0 24 24">
          <path d="m7 10 5 5 5-5" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" />
        </svg>
      </span>
    </button>
    <div class="custom-select__menu" id="custom-select-menu-${escapeHtml(select.id)}" role="listbox" ${isOpen ? "" : "hidden"}>
      ${options
        .map((option, index) => {
          const label = option.textContent.trim();
          const selected = option.value === select.value;
          return `
            <button
              class="custom-select__option${selected ? " is-selected" : ""}"
              type="button"
              role="option"
              aria-selected="${selected ? "true" : "false"}"
              data-index="${index}"
              data-value="${escapeHtml(option.value)}"
            >
              ${escapeHtml(label)}
            </button>
          `;
        })
        .join("")}
    </div>
  `;
}

function fillSelect(select, items, selectedValue) {
  if (!select) return;
  const normalizedItems = (items || []).map((item) => (typeof item === "string" ? { value: item, label: item } : item));
  select.innerHTML = normalizedItems
    .map((item) => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label || item.value)}</option>`)
    .join("");

  const values = new Set(normalizedItems.map((item) => item.value));
  if (selectedValue && values.has(selectedValue)) {
    select.value = selectedValue;
  } else if (normalizedItems[0]) {
    select.value = normalizedItems[0].value;
  }

  syncCustomSelect(select);
}

function handleCustomSelectClick(event) {
  const wrapper = event.currentTarget;
  const select = document.getElementById(wrapper.dataset.selectId);
  if (!select || select.disabled) return;

  const option = event.target.closest(".custom-select__option");
  if (option) {
    setCustomSelectValue(select, option.dataset.value || "");
    closeCustomSelect({ restoreFocus: true });
    return;
  }

  const trigger = event.target.closest(".custom-select__trigger");
  if (!trigger) return;

  if (state.openCustomSelectId === select.id) {
    closeCustomSelect({ restoreFocus: false });
  } else {
    openCustomSelect(select.id, { focusSelected: true });
  }
}

function handleCustomSelectKeydown(event) {
  const wrapper = event.currentTarget;
  const select = document.getElementById(wrapper.dataset.selectId);
  if (!select || select.disabled) return;

  const options = Array.from(wrapper.querySelectorAll(".custom-select__option"));
  const currentIndex = options.findIndex((node) => node === document.activeElement);

  if (event.target.closest(".custom-select__trigger")) {
    if (["Enter", " ", "ArrowDown"].includes(event.key)) {
      event.preventDefault();
      openCustomSelect(select.id, { focusSelected: true });
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      openCustomSelect(select.id, { focusLast: true });
    }
    return;
  }

  if (!event.target.closest(".custom-select__option")) return;

  if (event.key === "ArrowDown") {
    event.preventDefault();
    options[Math.min(currentIndex + 1, options.length - 1)]?.focus();
    return;
  }

  if (event.key === "ArrowUp") {
    event.preventDefault();
    options[Math.max(currentIndex - 1, 0)]?.focus();
    return;
  }

  if (event.key === "Home") {
    event.preventDefault();
    options[0]?.focus();
    return;
  }

  if (event.key === "End") {
    event.preventDefault();
    options[options.length - 1]?.focus();
    return;
  }

  if (["Enter", " "].includes(event.key)) {
    event.preventDefault();
    setCustomSelectValue(select, event.target.dataset.value || "");
    closeCustomSelect({ restoreFocus: true });
    return;
  }

  if (event.key === "Escape") {
    event.preventDefault();
    closeCustomSelect({ restoreFocus: true });
    return;
  }

  if (event.key === "Tab") {
    closeCustomSelect({ restoreFocus: false });
  }
}

function openCustomSelect(selectId, options = {}) {
  state.openCustomSelectId = selectId;
  syncCustomSelects();
  window.requestAnimationFrame(() => {
    focusCustomSelectOption(selectId, options);
  });
}

function closeCustomSelect({ restoreFocus = false } = {}) {
  const targetId = state.openCustomSelectId;
  if (!targetId) return;
  state.openCustomSelectId = null;
  syncCustomSelects();
  if (restoreFocus) {
    window.requestAnimationFrame(() => {
      getCustomSelectTrigger(targetId)?.focus();
    });
  }
}

function focusCustomSelectOption(selectId, options = {}) {
  const select = document.getElementById(selectId);
  const wrapper = select?.nextElementSibling;
  if (!wrapper) return;
  const items = Array.from(wrapper.querySelectorAll(".custom-select__option"));
  if (!items.length) return;
  const selectedIndex = items.findIndex((node) => node.dataset.value === select.value);
  if (options.focusLast) {
    items[items.length - 1]?.focus();
    return;
  }
  if (options.focusSelected && selectedIndex >= 0) {
    items[selectedIndex].focus();
    return;
  }
  items[0]?.focus();
}

function getCustomSelectTrigger(selectId) {
  const select = document.getElementById(selectId);
  const wrapper = select?.nextElementSibling;
  return wrapper?.querySelector(".custom-select__trigger") || null;
}

function setCustomSelectValue(select, value) {
  if (!select) return;
  select.value = value;
  select.dispatchEvent(new Event("change", { bubbles: true }));
  syncCustomSelect(select);
}

function updateModelBaseUrlAutofillState() {
  const profile = findProviderProfile(elements.modelProvider.value);
  const currentBaseUrl = elements.modelBaseUrl.value.trim();
  elements.modelBaseUrl.dataset.autofilled =
    profile?.base_url && currentBaseUrl === profile.base_url ? "true" : "false";
}

function handleModelBaseUrlInput() {
  updateModelBaseUrlAutofillState();
}

function localizeProviderProfile(profile) {
  if (!profile) return { label: "", description: "" };
  if (state.locale === "en-US") {
    return { label: profile.label || profile.value, description: profile.description || "" };
  }

  const localized = {
    lmstudio_local: { label: "本地 LM Studio", description: "使用本地 LM Studio 兼容接口。" },
    openai_api: { label: "OpenAI API", description: "使用 OpenAI 官方接口。" },
    openai_compatible: { label: "兼容接口", description: "使用第三方 OpenAI 兼容接口。" },
    custom: { label: "自定义", description: "手动填写端点和参数。" },
  }[profile.value];

  return {
    label: localized?.label || profile.label || profile.value,
    description: localized?.description || profile.description || "",
  };
}

function handleProviderChange(options = {}) {
  const profile = findProviderProfile(elements.modelProvider.value);
  const previousProfile = elements.modelProvider.dataset.previousProfile || "";
  const changed = previousProfile !== (profile?.value || "");
  elements.modelProvider.dataset.previousProfile = profile?.value || "";

  if (profile) {
    const currentBaseUrl = elements.modelBaseUrl.value.trim();
    const isAutofilledBaseUrl = elements.modelBaseUrl.dataset.autofilled === "true";
    const shouldFillBaseUrl =
      changed ||
      !currentBaseUrl ||
      isAutofilledBaseUrl ||
      (options.force && (!currentBaseUrl || isAutofilledBaseUrl));
    if (shouldFillBaseUrl && profile.base_url) {
      elements.modelBaseUrl.value = profile.base_url;
      elements.modelBaseUrl.dataset.autofilled = "true";
    } else {
      updateModelBaseUrlAutofillState();
    }
    if ((options.force || changed) && typeof profile.auto_discover === "boolean") {
      elements.modelAutoDiscover.checked = Boolean(profile.auto_discover);
    }
    elements.modelApiKey.placeholder = profile.api_key_required ? tr("必填", "Required") : tr("可选", "Optional");
  }

  if (changed) {
    state.providerSnapshot = null;
    state.providerInspectionSignature = "";
    renderAvailableModels(null);
  }

  updateProviderStatusHints();
  updateProviderActionButtons();

  if (state.settingsOpen && profile?.supports_model_refresh && (changed || options.force)) {
    scheduleProviderInspection({
      immediate: true,
      force: true,
      message: tr("正在刷新模型目录...", "Refreshing model catalog..."),
    });
  }
}

function updateProviderStatusHints() {
  if (!isConfigHydrated()) {
    state.providerStatusMessage = getConfigLoadingMessage();
    return;
  }
  const profile = findProviderProfile(elements.modelProvider.value);
  const localized = localizeProviderProfile(profile);

  if (state.providerSnapshot && state.providerSnapshot.provider === profile?.value) {
    if (state.providerSnapshot.ok) {
      const count =
        (state.providerSnapshot.catalog_models || []).length || (state.providerSnapshot.loaded_models || []).length || 0;
      const preferredChatModel = String(state.providerSnapshot.preferred_chat_model || "").trim();
      const baseMessage = tr(`已连接，发现 ${count} 个模型。`, `Connected. ${count} model(s) available.`);
      state.providerStatusMessage = preferredChatModel
        ? `${baseMessage} ${tr(`当前对话模型：${preferredChatModel}。`, `Current chat model: ${preferredChatModel}.`)}`
        : baseMessage;
    } else {
      state.providerStatusMessage = state.providerSnapshot.error || tr("无法读取模型目录。", "Could not read the model catalog.");
    }
  } else {
    const notes = [];
    if (localized.description) notes.push(localized.description);
    if (profile?.api_key_required) notes.push(tr("需要 API Key。", "API key required."));
    if (elements.modelAutoDiscover.checked) notes.push(tr("已开启自动发现。", "Auto discovery is enabled."));
    state.providerStatusMessage = notes.join(" ") || t("developer.providerStatus");
  }
}

function updateProviderActionButtons() {
  const configReady = isConfigHydrated();
  const profile = findProviderProfile(elements.modelProvider.value);
  const hasSelection = configReady && Boolean(elements.availableModels.value);
  const canRefresh = configReady && Boolean(profile?.supports_model_refresh);
  elements.testProviderButton.disabled = !canRefresh || state.providerInspectionBusy;
  elements.refreshModelsButton.disabled = !canRefresh || state.providerInspectionBusy;
  if (elements.refreshCatalogButton) {
    elements.refreshCatalogButton.disabled = !canRefresh || state.providerInspectionBusy;
  }
  elements.applyModelButton.disabled = !hasSelection;
  elements.loadLmStudioModelButton.disabled = !Boolean(profile?.supports_model_load && hasSelection);
  elements.openProviderPortalButton.disabled = !configReady || !Boolean(profile?.portal_url);
  elements.openProviderDocsButton.disabled = !configReady || !Boolean(profile?.docs_url);
}

async function inspectProvider(message, options = {}) {
  if (!isConfigHydrated()) {
    state.providerInspectionBusy = false;
    state.providerSnapshot = null;
    state.providerInspectionSignature = "";
    renderAvailableModels(null);
    updateProviderStatusHints();
    renderAll();
    return;
  }
  const signature = options.signature || getProviderInspectionSignature();
  const token = ++state.providerInspectionToken;
  state.providerInspectionBusy = true;
  setProviderStatus(message);
  renderAll();

  const response = await postJson("/api/provider/models", { config_overrides: buildConfigOverrides() });
  if (token !== state.providerInspectionToken) {
    return;
  }

  state.providerInspectionBusy = false;
  state.providerInspectionSignature = signature;
  if (!response.ok) {
    const errorMessage = response.payload?.error || tr("模型检查失败。", "Provider inspection failed.");
    state.providerSnapshot = buildProviderErrorSnapshot(errorMessage);
    renderAvailableModels(state.providerSnapshot);
    setProviderStatus(errorMessage);
    renderAll();
    return;
  }

  state.providerSnapshot = response.payload;
  renderAvailableModels(response.payload);
  updateProviderStatusHints();
  renderAll();
}

function renderAvailableModels(snapshot) {
  const items = Array.isArray(snapshot?.catalog_models) ? snapshot.catalog_models : [];
  if (!items.length) {
    let emptyLabel = state.providerInspectionBusy
      ? tr("正在读取模型...", "Loading models...")
      : tr("暂无可用模型", "No models available");
    if (!isConfigHydrated()) {
      emptyLabel = getConfigLoadingMessage();
    } else if (snapshot && snapshot.ok === false && snapshot.error && !state.providerInspectionBusy) {
      emptyLabel = snapshot.error;
    }
    elements.availableModels.innerHTML = `<option value="">${escapeHtml(emptyLabel)}</option>`;
    elements.availableModels.value = "";
    elements.availableModels.disabled = true;
    syncCustomSelect(elements.availableModels);
    updateProviderActionButtons();
    return;
  }

  const currentModel = elements.modelName.value.trim();
  const preferredChatModel = String(snapshot?.preferred_chat_model || "").trim();
  const autoSelection = !currentModel || ["auto", "first"].includes(currentModel.toLowerCase());
  const rankedItems = items
    .map((item, index) => ({ item, index }))
    .sort((left, right) => {
      const leftRank =
        left.item.id === preferredChatModel ? 0 : left.item.loaded ? 1 : 2;
      const rightRank =
        right.item.id === preferredChatModel ? 0 : right.item.loaded ? 1 : 2;
      if (leftRank !== rightRank) {
        return leftRank - rightRank;
      }
      return left.index - right.index;
    })
    .map(({ item }) => item);
  elements.availableModels.innerHTML = rankedItems
    .map((item) => {
      const badges = [];
      if (item.id === preferredChatModel) {
        badges.push(tr("(当前对话)", "(Active chat)"));
      }
      if (item.loaded) {
        badges.push(tr("(已加载)", "(Loaded)"));
      }
      const badgeText = badges.length ? ` ${badges.join(" ")}` : "";
      const label = `${item.label || item.id}${badgeText}`;
      return `<option value="${escapeHtml(item.id)}">${escapeHtml(label)}</option>`;
    })
    .join("");

  const matchedConfigured = rankedItems.find((item) => item.id === currentModel);
  const matchedPreferred = rankedItems.find((item) => item.id === preferredChatModel);
  const matchedLoaded = rankedItems.find((item) => item.loaded);
  elements.availableModels.value =
    (autoSelection ? matchedPreferred?.id : matchedConfigured?.id) ||
    matchedConfigured?.id ||
    matchedPreferred?.id ||
    matchedLoaded?.id ||
    rankedItems[0].id;
  elements.availableModels.disabled = false;
  syncCustomSelect(elements.availableModels);
  updateProviderActionButtons();
}

function applyDiscoveredModel() {
  const modelId = elements.availableModels.value;
  if (!modelId) return;
  elements.modelName.value = modelId;
  elements.modelAutoDiscover.checked = false;
  setProviderStatus(tr(`已切换到 ${modelId}。`, `Switched to ${modelId}.`));
  renderAll();
}

async function loadSelectedModelIntoLmStudio() {
  const modelId = elements.availableModels.value;
  if (!modelId) {
    setProviderStatus(tr("请先选择模型。", "Select a model first."));
    renderAll();
    return;
  }

  setProviderStatus(tr("正在卸载当前模型并加载新模型...", "Unloading the current model and loading the new model..."));
  renderAll();

  const response = await postJson("/api/provider/load-model", {
    model_id: modelId,
    unload_first: true,
    config_overrides: buildConfigOverrides(),
  });

  if (!response.ok) {
    setProviderStatus(response.payload?.error || tr("模型加载失败。", "Model load failed."));
    renderAll();
    return;
  }

  const unloadedCount = Array.isArray(response.payload?.unloaded_instance_ids)
    ? response.payload.unloaded_instance_ids.length
    : 0;
  if (response.payload?.already_loaded) {
    setProviderStatus(
      unloadedCount
        ? tr(`已卸载 ${unloadedCount} 个旧实例，并保留 ${modelId} 继续使用。`, `Unloaded ${unloadedCount} previous instance(s) and kept ${modelId} active.`)
        : tr(`${modelId} 已经处于加载状态。`, `${modelId} is already loaded.`)
    );
  } else {
    setProviderStatus(
      unloadedCount
        ? tr(`已先卸载 ${unloadedCount} 个旧实例，再加载 ${modelId}。`, `Unloaded ${unloadedCount} previous instance(s) before loading ${modelId}.`)
        : tr(`已发送 ${modelId}。`, `Sent ${modelId}.`)
    );
  }
  await inspectProvider(tr("正在刷新模型目录...", "Refreshing model catalog..."));
}

function handleProviderFieldBlur() {
  if (!state.settingsOpen) return;
  elements.modelBaseUrl.value = elements.modelBaseUrl.value.trim();
  elements.modelApiKey.value = elements.modelApiKey.value.trim();
  updateModelBaseUrlAutofillState();
  scheduleProviderInspection({
    immediate: true,
    force: true,
    message: tr("正在重新读取模型...", "Refreshing available models..."),
  });
}

function handleRefreshCatalog() {
  scheduleProviderInspection({
    immediate: true,
    force: true,
    message: tr("正在刷新模型目录...", "Refreshing model catalog..."),
  });
}

function getProviderInspectionSignature() {
  return JSON.stringify({
    provider: elements.modelProvider.value || "",
    baseUrl: elements.modelBaseUrl.value.trim(),
    apiKey: elements.modelApiKey.value.trim(),
  });
}

function scheduleProviderInspection({ immediate = false, force = false, message } = {}) {
  if (!isConfigHydrated() || !state.meta) {
    state.providerSnapshot = null;
    state.providerInspectionBusy = false;
    state.providerInspectionSignature = "";
    renderAvailableModels(null);
    updateProviderStatusHints();
    updateProviderActionButtons();
    renderAll();
    return;
  }
  const profile = findProviderProfile(elements.modelProvider.value);
  if (!profile?.supports_model_refresh) {
    state.providerSnapshot = null;
    state.providerInspectionBusy = false;
    state.providerInspectionSignature = "";
    renderAvailableModels(null);
    renderAll();
    return;
  }

  const signature = getProviderInspectionSignature();
  if (!force && state.providerSnapshot && state.providerInspectionSignature === signature) {
    renderAll();
    return;
  }

  window.clearTimeout(state.providerRefreshTimer);
  const run = () => {
    inspectProvider(message || tr("正在读取模型目录...", "Loading available models..."), { signature });
  };

  if (immediate) {
    run();
    return;
  }

  state.providerRefreshTimer = window.setTimeout(run, 120);
}

function buildProviderErrorSnapshot(errorMessage) {
  return {
    ok: false,
    provider: elements.modelProvider.value || "",
    api_base: elements.modelBaseUrl.value.trim() || "",
    root_base: "",
    loaded_models: [],
    catalog_models: [],
    error: errorMessage,
  };
}

function openProviderLink(key) {
  const profile = findProviderProfile(elements.modelProvider.value);
  const url = profile?.[key];
  if (!url) return;
  window.open(url, "_blank", "noopener,noreferrer");
}

function updateDomStatus() {
  const domStatus = state.meta?.dom_status;
  if (!domStatus) {
    elements.domStatusBadge.className = "connection-chip connection-chip--muted";
    elements.domStatusBadge.textContent = "DOM";
    elements.domStatusBadge.title = "";
    return;
  }

  if (domStatus.available) {
    elements.domStatusBadge.className = "connection-chip connection-chip--ok";
    elements.domStatusBadge.textContent = tr("DOM 就绪", "DOM Ready");
  } else {
    elements.domStatusBadge.className = "connection-chip connection-chip--warn";
    elements.domStatusBadge.textContent = tr("DOM 不可用", "DOM Unavailable");
  }
  elements.domStatusBadge.title = normalizeText(domStatus.detail || "");
}

function setProviderStatus(message) {
  state.providerStatusMessage = message;
  elements.providerStatusNote.textContent = message;
}

function buildConfigOverrides() {
  const normalizedApiKey = elements.modelApiKey.value.trim();
  const displayOverrideEnabled = Boolean(elements.displayOverrideEnabled?.checked);
  const displayMonitorValue = (elements.displayMonitorSelect?.value || "").trim();
  const displayDpiValue = (elements.displayDpiScaleInput?.value || "").trim();
  const workAreaLeft = (elements.displayWorkAreaLeftInput?.value || "").trim();
  const workAreaTop = (elements.displayWorkAreaTopInput?.value || "").trim();
  const workAreaWidth = (elements.displayWorkAreaWidthInput?.value || "").trim();
  const workAreaHeight = (elements.displayWorkAreaHeightInput?.value || "").trim();
  const hasCompleteWorkArea = [workAreaLeft, workAreaTop, workAreaWidth, workAreaHeight].every(Boolean);
  const overrides = {
    model_provider: elements.modelProvider.value || undefined,
    model_base_url: elements.modelBaseUrl.value.trim() || undefined,
    model_name: elements.modelName.value.trim() || undefined,
    model_api_key: normalizedApiKey || undefined,
    model_auto_discover: Boolean(elements.modelAutoDiscover.checked),
    model_structured_output: elements.structuredOutput.value || undefined,
    browser_control_mode: "hybrid",
    browser_dom_backend: elements.browserDomBackend.value || undefined,
    browser_dom_timeout: elements.browserDomTimeout.value ? Number(elements.browserDomTimeout.value) : undefined,
    browser_channel: elements.browserChannel.value.trim() || undefined,
    browser_executable_path: elements.browserExecutablePath.value.trim() || undefined,
    browser_headless: Boolean(elements.browserHeadless.checked),
    display_override_enabled: displayOverrideEnabled || undefined,
    display_override_monitor_device_name: displayOverrideEnabled && displayMonitorValue ? displayMonitorValue : undefined,
    display_override_dpi_scale: displayOverrideEnabled && displayDpiValue ? Number(displayDpiValue) : undefined,
    display_override_work_area_left: displayOverrideEnabled && hasCompleteWorkArea ? Number(workAreaLeft) : undefined,
    display_override_work_area_top: displayOverrideEnabled && hasCompleteWorkArea ? Number(workAreaTop) : undefined,
    display_override_work_area_width: displayOverrideEnabled && hasCompleteWorkArea ? Number(workAreaWidth) : undefined,
    display_override_work_area_height: displayOverrideEnabled && hasCompleteWorkArea ? Number(workAreaHeight) : undefined,
  };

  return Object.fromEntries(Object.entries(overrides).filter(([, value]) => value !== undefined && value !== ""));
}

function scheduleRuntimePreferencesSync() {
  if (!state.hydrated) return;
  if (state.runtimePreferencesSyncTimer) {
    window.clearTimeout(state.runtimePreferencesSyncTimer);
  }
  state.runtimePreferencesSyncTimer = window.setTimeout(() => {
    state.runtimePreferencesSyncTimer = 0;
    syncRuntimePreferences();
  }, 180);
}

async function syncRuntimePreferences() {
  if (!state.hydrated) return;
  try {
    const response = await postJson("/api/runtime-preferences", { config_overrides: buildConfigOverrides() });
    if (response.ok && response.payload) {
      state.runtimePreferences = response.payload;
    }
  } catch {
    // Ignore local runtime preference sync failures.
  }
  scheduleEnvironmentCheck();
  scheduleDisplayDetection();
}

function findProviderProfile(value = elements.modelProvider.value) {
  const profile = (state.meta?.model_providers || []).find((item) => item.value === value) || null;
  if (!profile) return null;
  const defaults = getEffectiveConfigDefaults();
  if (defaults.model_provider !== profile.value) {
    return profile;
  }
  return {
    ...profile,
    base_url: defaults.model_base_url || profile.base_url,
    auto_discover:
      typeof defaults.model_auto_discover === "boolean" ? defaults.model_auto_discover : profile.auto_discover,
  };
}

function buildStarterSuggestions() {
  const recipes = (state.meta?.workflow_recipes || []).map(localizeWorkflowRecipe);
  const presets = (state.meta?.presets || []).map(localizePreset);
  const merged = [...recipes, ...presets];
  const seen = new Set();

  return merged
    .filter((item) => {
      const key = `${item.label}:${item.task}`;
      if (!item.task || seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 4);
}

function buildFollowUpSuggestions(details) {
  const baseTask = normalizeText(details.task || tr("这个任务", "this task"));
  const items = [
    {
      title: tr("继续这个任务", "Continue this task"),
      description: tr("从当前状态继续。", "Resume from the current state."),
      task: tr(`继续刚才的任务：${baseTask}。请从当前状态继续。`, `Continue the previous task: ${baseTask}. Resume from the current state.`),
      actionLabel: tr("继续", "Continue"),
    },
  ];

  if (needsHumanVerification(details) || details.error || details.cancelled) {
    items.unshift({
      title: tr("恢复并继续", "Recover and continue"),
      description: tr("先处理当前中断，再继续。", "Handle the interruption, then resume."),
      task: tr(
        `继续刚才的任务：${baseTask}。请先处理当前中断，再从当前状态继续。`,
        `Continue the previous task: ${baseTask}. Resolve the interruption and resume from the current state.`
      ),
      actionLabel: tr("继续", "Continue"),
    });
  }

  return items.slice(0, 2);
}

function localizePreset(item) {
  const localized = {
    visit_docs: { label: "浏览文档", description: "打开文档页面。" },
    dom_follow_up: { label: "登录流程", description: "验证点击和后续输入。" },
    shopping_search: { label: "购物搜索", description: "测试搜索、筛选和排序。" },
  }[item.id];

  return {
    label: state.locale === "zh-CN" && localized ? localized.label : item.label,
    task: item.task,
    description: state.locale === "zh-CN" && localized ? localized.description : item.label || item.task,
  };
}

function localizeWorkflowRecipe(item) {
  const localized = {
    ordered_browser_task: { label: "顺序浏览器任务", description: "先给目标，再给后续动作。" },
    shopping_refine: { label: "风格与颜色筛选", description: "测试风格、颜色和排序。" },
    shopping_compare: { label: "高评分对比", description: "先缩小范围，再比较。" },
    login_flow: { label: "登录流程", description: "两步式页面跳转和交互。" },
    provider_check: { label: "提供方检查", description: "检查文档链接和模型入口。" },
  }[item.id];

  return {
    label: state.locale === "zh-CN" && localized ? localized.label : item.label,
    task: item.task,
    description: state.locale === "zh-CN" && localized ? localized.description : item.hint || item.label,
  };
}

function collectRunScreenshots(details) {
  return (details.timeline || [])
    .filter((step) => step.screenshot)
    .map((step) => ({
      src: buildArtifactUrl(details.id, step.screenshot),
      alt: tr(`步骤 ${step.step} 截图`, `Step ${step.step} screenshot`),
      caption: step.plan?.status_summary || step.task || tr("步骤截图", "Step screenshot"),
      summary: step.plan?.status_summary || step.task || tr("无摘要", "No summary"),
      step: step.step,
    }))
    .reverse();
}

function collectLatestActions(details) {
  const flattened = (details.timeline || [])
    .slice()
    .reverse()
    .flatMap((step) => step.executed_actions || []);

  const seen = new Set();
  const unique = [];
  for (const action of flattened) {
    const signature = JSON.stringify(action);
    if (seen.has(signature)) continue;
    seen.add(signature);
    unique.push(action);
    if (unique.length >= 8) break;
  }
  return unique;
}

function renderMetricCard(label, value) {
  return `<article class="metric-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value ?? "--"))}</strong></article>`;
}

function renderDetailMetricCard(label, value) {
  return `<article class="detail-card"><span class="detail-card__label">${escapeHtml(label)}</span><div class="detail-card__value">${escapeHtml(String(value ?? "--"))}</div></article>`;
}

function renderActionPill(action) {
  if (!action) return "";
  const type = normalizeText(action.type || action.action || tr("动作", "Action"));
  const detail =
    action.text
      ? `text=${truncate(normalizeText(action.text), 18)}`
      : action.key
        ? `key=${action.key}`
        : Array.isArray(action.keys) && action.keys.length
          ? `keys=${action.keys.join("+")}`
          : action.app
            ? `app=${action.app}`
            : typeof action.seconds === "number"
              ? `sec=${action.seconds}`
              : "";

  return `<span class="action-pill">${escapeHtml(type)}${detail ? `<code>${escapeHtml(detail)}</code>` : ""}</span>`;
}

function renderExecutionModeChip(dryRun) {
  return dryRun
    ? `<span class="metric-pill warn">${escapeHtml(tr("演练", "Dry Run"))}</span>`
    : `<span class="metric-pill ok">${escapeHtml(tr("实时", "Live"))}</span>`;
}

function renderHumanVerificationChip(record) {
  if (!needsHumanVerification(record)) return "";
  const label = record?.interruption_kind ? translateInterruptionKind(record.interruption_kind) : tr("需处理", "Attention");
  return `<span class="metric-pill warn">${escapeHtml(label)}</span>`;
}

function buildRecordState(record) {
  if (!record) return { label: tr("未知", "Unknown"), tone: "" };
  if (record.cancel_requested && !record.cancelled && !record.completed && !record.error) return { label: tr("停止中", "Stopping"), tone: "warn" };
  if (record.cancelled || record.status === "cancelled") return { label: tr("已取消", "Cancelled"), tone: "warn" };
  if (needsHumanVerification(record) || record.status === "attention") return { label: tr("需处理", "Attention"), tone: "warn" };
  if (record.error || record.status === "failed") return { label: tr("失败", "Failed"), tone: "bad" };
  if (record.completed || record.status === "completed") return { label: tr("已完成", "Done"), tone: "ok" };
  if (record.status === "queued") return { label: tr("等待", "Queued"), tone: "" };
  return { label: tr("执行中", "Running"), tone: "ok" };
}

function renderRunState(record) {
  return buildRecordState(record).label;
}

function needsHumanVerification(record) {
  return Boolean(record?.requires_human || record?.interruption_kind || record?.interruption_reason);
}

function translateInterruptionKind(kind) {
  const mapping = {
    recaptcha: tr("验证", "reCAPTCHA"),
    captcha: tr("验证", "CAPTCHA"),
    login: tr("登录", "Login"),
    permission: tr("权限", "Permission"),
    modal: tr("确认", "Confirm"),
  };
  return mapping[kind] || tr("处理", "Attention");
}

function translateJobStatus(status) {
  const mapping = {
    queued: tr("等待", "Queued"),
    running: tr("执行中", "Running"),
    attention: tr("需处理", "Attention"),
    cancelled: tr("已取消", "Cancelled"),
    completed: tr("完成", "Done"),
    failed: tr("失败", "Failed"),
    stopping: tr("停止中", "Stopping"),
  };
  return mapping[status] || tr("未知", "Unknown");
}

function statusTone(status) {
  if (status === "running" || status === "completed") return "ok";
  if (status === "attention" || status === "stopping" || status === "cancelled") return "warn";
  if (status === "failed") return "bad";
  return "";
}

function getConversationContext() {
  if (state.activeJob) return { type: "active", active: state.activeJob };
  if (state.pendingTask) return { type: "pending", task: state.pendingTask };
  if (state.loadingRunDetails && state.selectedRunId && !state.selectedRunDetails) return { type: "loading" };
  if (!state.showWelcome && state.selectedRunDetails) return { type: "run", details: state.selectedRunDetails };
  return { type: "welcome" };
}

function clearPendingTaskIfObserved() {
  if (!state.pendingTask) return;
  if (state.activeJob) {
    state.pendingTask = null;
    return;
  }

  const pending = normalizeText(state.pendingTask);
  const matchedRun = state.runs.find((run) => normalizeText(run.task) === pending);
  if (matchedRun) {
    state.pendingTask = null;
    state.selectedRunId = matchedRun.id;
    state.showWelcome = false;
    persistHistorySelection({ kind: "run", id: matchedRun.id });
  }
}

function openLightbox(src, caption) {
  if (!src) return;
  elements.lightboxImage.src = src;
  elements.lightboxCaption.textContent = caption || tr("截图", "Screenshot");
  elements.imageLightbox.hidden = false;
}

function closeLightbox() {
  elements.imageLightbox.hidden = true;
  elements.lightboxImage.removeAttribute("src");
}

function handleLightboxClick(event) {
  if (event.target.dataset.lightboxClose === "true" || event.target === elements.imageLightbox) {
    closeLightbox();
  }
}

function isTypingTarget(target) {
  const node = target || document.activeElement;
  if (!node || !(node instanceof HTMLElement)) return false;
  return node.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(node.tagName);
}

function buildArtifactUrl(runId, artifactName) {
  if (!runId || !artifactName) return "";
  return `/artifacts/${encodeURIComponent(runId)}/${encodeURIComponent(artifactName)}`;
}

function normalizeText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function buildSidebarHistoryTitle(value) {
  const text = normalizeText(value);
  if (!text) return "未命名任务";

  const lower = text.toLowerCase();
  const mathSnippet = extractMathSnippet(text);
  const typedSnippet = extractTypedSnippet(text);
  const searchKeyword = extractSearchKeyword(text);
  const siteLabel = extractSiteLabel(text);

  if ((/calculator|calculate|math/.test(lower) || /计算器|计算|算/.test(text)) && mathSnippet) {
    return `计算器 ${mathSnippet}`;
  }
  if (/calculator|calculate|math/.test(lower) || /计算器|计算|算/.test(text)) {
    return "计算器任务";
  }

  if ((/openai/.test(lower) || /openai\.com/.test(lower)) && /login|log in|sign in|登录/.test(lower + text)) {
    return "OpenAI 登录";
  }

  if (searchKeyword) {
    return `搜索 ${searchKeyword}`;
  }

  if (/amazon|shop|shopping|buy/.test(lower) || /亚马逊|购物|购买/.test(text)) {
    if (/men'?s pants|mens pants|pants|trousers/.test(lower) || /男裤|裤子/.test(text)) {
      return "亚马逊买男裤";
    }
    if (/amazon/.test(lower) || /亚马逊/.test(text)) {
      return "亚马逊购物";
    }
    return "购物任务";
  }

  if ((/notepad/.test(lower) || /记事本/.test(text)) && typedSnippet) {
    return `记事本输入 ${typedSnippet}`;
  }
  if (/notepad/.test(lower) || /记事本/.test(text)) {
    return "记事本输入";
  }

  if (siteLabel && (/visit|open|click|browser|website|site/.test(lower) || /访问|打开|点击|网页|网站/.test(text))) {
    return `访问 ${siteLabel}`;
  }
  if (/openai/.test(lower)) {
    return "访问 OpenAI";
  }

  const category = classifyHistoryTask(text);
  if (category === "web") return "网页操作";
  if (category === "search") return "搜索任务";
  if (category === "shop") return "购物任务";
  if (category === "edit") return typedSnippet ? `输入 ${typedSnippet}` : "编辑任务";
  if (category === "calc") return mathSnippet ? `计算 ${mathSnippet}` : "计算任务";

  return clipText(localizeGenericHistoryTitle(text), 14) || "普通任务";
}

function extractMathSnippet(text) {
  const directMatch =
    text.match(/(?:calculate|计算|算)\s+([0-9+\-*/xX=.()\s]+)/i) ||
    text.match(/([0-9]+(?:\s*[+\-*/xX=]\s*[0-9.]+)+)/);
  const snippet = normalizeText(directMatch?.[1] || "").replace(/\s+/g, "");
  return clipText(snippet, 12);
}

function extractSearchKeyword(text) {
  const englishMatch = text.match(/\bsearch for\s+(.+)$/i);
  const chineseMatch = text.match(/搜索\s+(.+)$/);
  const raw = englishMatch?.[1] || chineseMatch?.[1] || "";
  if (!raw) return "";
  const keyword = raw
    .split(/\b(?:and|then|after|before|click|open|visit|with)\b/i)[0]
    .split(/[，,。;；]/)[0]
    .trim()
    .replace(/^["'`]+|["'`]+$/g, "");
  if (!keyword) return "";
  if (/openai/i.test(keyword)) return "OpenAI";
  if (/amazon/i.test(keyword)) return "亚马逊";
  return clipText(keyword, 12);
}

function extractTypedSnippet(text) {
  const englishMatch = text.match(/\b(?:type|write|input)\s+(.+)$/i);
  const chineseMatch = text.match(/(?:输入|写入)\s+(.+)$/);
  const raw = englishMatch?.[1] || chineseMatch?.[1] || "";
  if (!raw) return "";
  const snippet = raw
    .split(/\b(?:and|then|after|before|click|open|visit)\b/i)[0]
    .split(/[，,。;；]/)[0]
    .trim()
    .replace(/^["'`]+|["'`]+$/g, "");
  return clipText(snippet, 10);
}

function extractSiteLabel(text) {
  const lower = text.toLowerCase();
  if (/openai/.test(lower)) return "OpenAI";
  if (/amazon/.test(lower)) return "亚马逊";

  const domainMatch = text.match(/\b([a-z0-9.-]+\.[a-z]{2,})(?:\/[^\s]*)?/i);
  if (!domainMatch) return "";

  const root = domainMatch[1].replace(/^www\./i, "").split(".")[0] || "";
  if (!root) return "";
  if (/openai/i.test(root)) return "OpenAI";
  if (/amazon/i.test(root)) return "亚马逊";
  return clipText(root.charAt(0).toUpperCase() + root.slice(1), 10);
}

function localizeGenericHistoryTitle(text) {
  const localized = normalizeText(
    text
      .replace(/openai\.com/gi, "OpenAI")
      .replace(/\bopenai\b/gi, "OpenAI")
      .replace(/\bamazon\b/gi, "亚马逊")
      .replace(/\bnotepad\b/gi, "记事本")
      .replace(/\bcalculator\b/gi, "计算器")
      .replace(/\bsearch for\b/gi, "搜索")
      .replace(/\bvisit\b/gi, "访问")
      .replace(/\bopen\b/gi, "打开")
      .replace(/\bclick\b/gi, "点击")
      .replace(/\blog in\b/gi, "登录")
      .replace(/\blogin\b/gi, "登录")
      .replace(/\btype\b/gi, "输入")
      .replace(/\bwrite\b/gi, "写入")
      .replace(/\bshop for\b/gi, "购买")
      .replace(/\band then\b/gi, " ")
      .replace(/\bthen\b/gi, " ")
      .replace(/\band\b/gi, " ")
  );

  if (!localized) return "普通任务";
  if (!/[\u4e00-\u9fff]/.test(localized) && !/OpenAI|亚马逊/i.test(localized)) {
    return "普通任务";
  }
  return localized;
}

function clipText(value, max = 80) {
  const text = String(value || "");
  return text.length <= max ? text : text.slice(0, Math.max(0, max));
}

function cleanRunTitle(value) {
  const text = normalizeText(value || "");
  return truncate(text || tr("未命名任务", "Untitled task"), 60);
}

function runSummary(details) {
  if (details.error) return normalizeText(details.error);
  if (details.cancel_reason) return normalizeText(details.cancel_reason);
  if (details.interruption_reason) return normalizeText(details.interruption_reason);
  if (details.cancelled) return tr("任务在完成前被停止。", "The run was stopped before completion.");
  if (needsHumanVerification(details)) return tr("当前需要人工处理。", "This run currently needs attention.");
  if (details.completed) return tr("任务已完成。", "The run has finished.");
  return tr("任务尚未结束。", "The run is still open.");
}

function formatDuration(startedAt) {
  if (!Number.isFinite(Number(startedAt))) return "--";
  const elapsedSeconds = Math.max(0, Math.round(Date.now() / 1000 - Number(startedAt)));
  const hours = Math.floor(elapsedSeconds / 3600);
  const minutes = Math.floor((elapsedSeconds % 3600) / 60);
  const seconds = elapsedSeconds % 60;

  if (hours > 0) return state.locale === "zh-CN" ? `${hours}小时 ${minutes}分` : `${hours}h ${minutes}m`;
  if (minutes > 0) return state.locale === "zh-CN" ? `${minutes}分 ${seconds}秒` : `${minutes}m ${seconds}s`;
  return state.locale === "zh-CN" ? `${seconds}秒` : `${seconds}s`;
}

function formatShortTime(value) {
  if (!Number.isFinite(Number(value))) return "--";
  return new Intl.DateTimeFormat(state.locale, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(Number(value) * 1000));
}

function formatTime(value) {
  if (!Number.isFinite(Number(value))) return "--";
  return new Intl.DateTimeFormat(state.locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(Number(value) * 1000));
}

function formatTimestamp(value) {
  if (!Number.isFinite(Number(value))) return "--";
  return formatShortTime(value);
}

function truncate(value, max = 80) {
  const text = String(value || "");
  return text.length <= max ? text : `${text.slice(0, Math.max(0, max - 1))}…`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function fetchJson(url) {
  try {
    const response = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) return null;
    return await safeJson(response);
  } catch {
    return null;
  }
}

async function postJson(url, payload) {
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      cache: "no-store",
      body: JSON.stringify(payload || {}),
    });
    return { ok: response.ok, payload: await safeJson(response) };
  } catch {
    return { ok: false, payload: { error: tr("无法连接本地服务。", "Could not reach the local service.") } };
  }
}

async function safeJson(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function restoreOverviewSnapshot() {
  try {
    const raw = window.localStorage.getItem(OVERVIEW_CACHE_KEY);
    if (!raw) return false;
    const snapshot = JSON.parse(raw);
    state.meta = snapshot.meta || null;
    state.runtimePreferences = snapshot.runtime_preferences || state.runtimePreferences;
    ensureRuntimePreferencesState();
    state.activeJob = snapshot.active_job || null;
    state.jobs = snapshot.jobs || [];
    state.runs = snapshot.runs || [];
    state.usingCachedSnapshot = true;
    hydrateDefaults();
    return true;
  } catch {
    return false;
  }
}

function persistOverviewSnapshot(payload) {
  safeStorageSet(OVERVIEW_CACHE_KEY, JSON.stringify(payload));
}

function normalizeLocale(locale) {
  return locale === "en-US" ? "en-US" : "zh-CN";
}

function detectInitialLocale() {
  const saved = window.localStorage.getItem(LOCALE_STORAGE_KEY);
  if (saved) return normalizeLocale(saved);
  const browserLocale = window.navigator.language || DEFAULT_LOCALE;
  return browserLocale.toLowerCase().startsWith("en") ? "en-US" : "zh-CN";
}

function detectInitialUiMode() {
  const saved = window.localStorage.getItem(UI_MODE_STORAGE_KEY);
  return saved === "developer" ? "developer" : "user";
}

function detectSidebarCollapsed() {
  const saved = window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY);
  return saved === "true";
}

function detectSendShortcutMode() {
  const saved = window.localStorage.getItem(SEND_SHORTCUT_STORAGE_KEY);
  return saved === "ctrl-enter" ? "ctrl-enter" : "enter";
}

function t(path) {
  const localized = resolvePath(COPY[state.locale], path);
  if (localized !== undefined) return localized;
  return resolvePath(COPY["en-US"], path) || path;
}

function resolvePath(source, path) {
  return path.split(".").reduce((current, key) => current?.[key], source);
}

function tr(zh, en) {
  return state.locale === "zh-CN" ? zh : en;
}

function safeStorageSet(key, value) {
  try {
    if (value == null || value === "") {
      window.localStorage.removeItem(key);
    } else {
      window.localStorage.setItem(key, value);
    }
  } catch {
    // Ignore storage failures.
  }
}


function buildAboutDiagnosticsSummary() {
  const diagnostics = state.meta?.diagnostics || {};
  return [
    `App: ${state.meta?.title || "Aoryn"}`,
    `Version: ${state.meta?.version || APP_VERSION}`,
    `Runtime: ${state.meta?.runtime_mode || "source"}`,
    `Config: ${diagnostics.config_file || "-"}`,
    `Runs: ${diagnostics.run_root || "-"}`,
    `Data: ${diagnostics.data_dir || "-"}`,
    `Cache: ${diagnostics.cache_dir || "-"}`,
    `Executable: ${diagnostics.executable_path || "-"}`,
  ].join("\n");
}


function setInputValue(element, value) {
  if (!element) return;
  element.value = String(value || "");
}

/*
function renderAuthGate() {
  const locked = isAuthLocked();
  if (elements.authGateOverlay) {
    elements.authGateOverlay.hidden = !locked;
  }
  if (!locked) return;

  const isRegister = state.authGateMode === "register";
  const busy = state.authBusy;

  if (elements.authGateBrandHint) {
    elements.authGateBrandHint.textContent = "Sign in to unlock the workspace.";
  }
  if (elements.authGateEyebrow) {
    elements.authGateEyebrow.textContent = "Account";
  }
  if (elements.authGateTitle) {
    elements.authGateTitle.textContent = isRegister ? "Create your Aoryn account" : "Sign in to unlock Aoryn";
  }
  if (elements.authGateBody) {
    elements.authGateBody.textContent =
      "Only identity and the basic profile are stored in the cloud. Runs, history, screenshots, and settings stay on this device.";
  }
  if (elements.authGateLoginTab) {
    elements.authGateLoginTab.textContent = "Login";
    elements.authGateLoginTab.classList.toggle("is-active", !isRegister);
    elements.authGateLoginTab.disabled = busy;
  }
  if (elements.authGateRegisterTab) {
    elements.authGateRegisterTab.textContent = "Register";
    elements.authGateRegisterTab.classList.toggle("is-active", isRegister);
    elements.authGateRegisterTab.disabled = busy;
  }
  if (elements.authGateApiBaseUrlLabel) {
    elements.authGateApiBaseUrlLabel.textContent = "Auth API";
  }
  if (elements.authGateEmailLabel) {
    elements.authGateEmailLabel.textContent = "Email";
  }
  if (elements.authGateDisplayNameLabel) {
    elements.authGateDisplayNameLabel.textContent = "Display name";
  }
  if (elements.authGatePasswordLabel) {
    elements.authGatePasswordLabel.textContent = "Password";
  }
  if (elements.authGateApiBaseUrlInput) {
    elements.authGateApiBaseUrlInput.placeholder = "https://aoryn.org/api/auth";
    elements.authGateApiBaseUrlInput.disabled = busy;
  }
  if (elements.authGateEmailInput) {
    elements.authGateEmailInput.placeholder = "you@example.com";
    elements.authGateEmailInput.disabled = busy;
  }
  if (elements.authGateDisplayNameInput) {
    elements.authGateDisplayNameInput.placeholder = "Aoryn user";
    elements.authGateDisplayNameInput.disabled = busy;
  }
  if (elements.authGatePasswordInput) {
    elements.authGatePasswordInput.placeholder = "At least 8 characters";
    elements.authGatePasswordInput.disabled = busy;
  }
  if (elements.authGateDisplayNameField) {
    elements.authGateDisplayNameField.hidden = !isRegister;
  }
  if (elements.authGateFeedbackNote) {
    elements.authGateFeedbackNote.textContent = state.authFeedbackMessage;
    if (state.authFeedbackTone) {
      elements.authGateFeedbackNote.dataset.tone = state.authFeedbackTone;
    } else {
      delete elements.authGateFeedbackNote.dataset.tone;
    }
  }
  if (elements.authGateModeSwitchButton) {
    elements.authGateModeSwitchButton.textContent = isRegister
      ? "Already have an account? Login"
      : "Need an account? Register";
    elements.authGateModeSwitchButton.disabled = busy;
  }
  if (elements.authGateSubmitButton) {
    elements.authGateSubmitButton.textContent = busy ? "Working..." : isRegister ? "Create account" : "Login";
    elements.authGateSubmitButton.disabled = busy;
  }
  if (elements.authGateCard && document.activeElement === document.body) {
    window.requestAnimationFrame(() => {
      (isRegister ? elements.authGateDisplayNameInput : elements.authGateEmailInput)?.focus?.();
    });
  }
}

function renderAccountSettings() {
  const isEnglish = state.locale === "en-US";
  const session = state.authSession || {};
  const authenticated = Boolean(session.authenticated);
  const profile = session.profile || {};
  const email = String(session.email || profile.email || "").trim();
  const displayName = String(session.display_name || profile.display_name || "").trim();

  if (elements.accountSettingsTitle) {
    elements.accountSettingsTitle.textContent = isEnglish ? "Account" : "账号";
  }
  if (elements.accountSettingsHint) {
    elements.accountSettingsHint.textContent = isEnglish
      ? "Only identity and the basic profile are stored in the cloud. Tasks, history, screenshots, and config stay on this device."
      : "云端只保存身份与基础资料。任务、历史、截图和配置继续留在这台设备。";
  }
  if (elements.authApiBaseUrlLabel) {
    elements.authApiBaseUrlLabel.textContent = isEnglish ? "Auth API" : "认证接口";
  }
  if (elements.authEmailLabel) {
    elements.authEmailLabel.textContent = isEnglish ? "Email" : "邮箱";
  }
  if (elements.authDisplayNameLabel) {
    elements.authDisplayNameLabel.textContent = isEnglish ? "Display name" : "显示名称";
  }
  if (elements.authPasswordLabel) {
    elements.authPasswordLabel.textContent = isEnglish ? "Password" : "密码";
  }
  if (elements.authRegisterButton) {
    elements.authRegisterButton.textContent = isEnglish ? "Register" : "注册";
    elements.authRegisterButton.disabled = state.authBusy;
  }
  if (elements.authLoginButton) {
    elements.authLoginButton.textContent = isEnglish ? "Login" : "登录";
    elements.authLoginButton.disabled = state.authBusy;
  }
  if (elements.authLogoutButton) {
    elements.authLogoutButton.textContent = isEnglish ? "Logout" : "退出登录";
    elements.authLogoutButton.disabled = state.authBusy || !authenticated;
  }
  if (elements.accountStatusTitle) {
    elements.accountStatusTitle.textContent = state.authBusy
      ? isEnglish
        ? "Syncing account..."
        : "正在处理账号…"
      : authenticated
      ? displayName || email || (isEnglish ? "Signed in" : "已登录")
      : isEnglish
      ? "Signed out"
      : "未登录";
  }
  if (elements.accountStatusDetail) {
    elements.accountStatusDetail.textContent = authenticated
      ? email || (isEnglish ? "Session stored locally on this device." : "会话已安全保存在本机。")
      : isEnglish
      ? "Register or sign in with the same account used by the website."
      : "使用与官网相同的账号注册或登录。";
  }
  if (elements.accountStatusBadge) {
    elements.accountStatusBadge.className = `status-pill ${state.authBusy ? "warn" : authenticated ? "ok" : ""}`.trim();
    elements.accountStatusBadge.textContent = state.authBusy
      ? isEnglish
        ? "Working"
        : "处理中"
      : authenticated
      ? isEnglish
        ? "Signed in"
        : "已登录"
      : isEnglish
      ? "Signed out"
      : "未登录";
  }
  if (elements.authFeedbackNote) {
    elements.authFeedbackNote.textContent = state.authFeedbackMessage;
    if (state.authFeedbackTone) {
      elements.authFeedbackNote.dataset.tone = state.authFeedbackTone;
    } else {
      delete elements.authFeedbackNote.dataset.tone;
    }
  }
}

async function handleAuthRegister() {
  const { apiBaseUrl, email, displayName, password } = readAuthFormValues();
  if (!email) {
    setAuthFeedback("bad", tr("请输入邮箱。", "Please enter an email address."));
    renderAll();
    return;
  }
  if (password.length < 8) {
    setAuthFeedback("bad", tr("密码至少需要 8 个字符。", "Password must be at least 8 characters long."));
    renderAll();
    return;
  }

  state.authBusy = true;
  setAuthFeedback("", "");
  renderAll();
  try {
    const response = await postJson("/api/auth/register", {
      apiBaseUrl,
      email,
      password,
      displayName,
    });
    if (!response.ok) {
      throw new Error(response.payload?.error || response.payload?.message || tr("注册失败。", "Registration failed."));
    }
    await persistAuthPreferences();
    clearAuthPasswords();
    setAuthGateMode("login");
    setAuthFeedback(
      "ok",
      response.payload?.message || tr("请检查邮箱并完成验证。", "Please check your email and complete the verification.")
    );
    await loadAuthSession({ silent: true });
  } catch (error) {
    setAuthFeedback("bad", error instanceof Error ? error.message : tr("注册失败。", "Registration failed."));
  } finally {
    state.authBusy = false;
    renderAll();
  }
}

async function handleAuthLogin() {
  const { apiBaseUrl, email, displayName, password } = readAuthFormValues();
  if (!email) {
    setAuthFeedback("bad", tr("请输入邮箱。", "Please enter an email address."));
    renderAll();
    return;
  }
  if (!password) {
    setAuthFeedback("bad", tr("请输入密码。", "Please enter your password."));
    renderAll();
    return;
  }

  state.authBusy = true;
  setAuthFeedback("", "");
  renderAll();
  try {
    const response = await postJson("/api/auth/login", {
      apiBaseUrl,
      email,
      password,
    });
    if (!response.ok) {
      throw new Error(response.payload?.error || response.payload?.message || tr("登录失败。", "Login failed."));
    }
    state.authSession = response.payload?.session || state.authSession;
    clearAuthPasswords();
    const profile = state.authSession?.profile || {};
    if (elements.authDisplayNameInput && !elements.authDisplayNameInput.value.trim()) {
      elements.authDisplayNameInput.value = String(profile.display_name || displayName || "").trim();
    }
    if (elements.authGateDisplayNameInput && !elements.authGateDisplayNameInput.value.trim()) {
      elements.authGateDisplayNameInput.value = String(profile.display_name || displayName || "").trim();
    }
    await persistAuthPreferences();
    setAuthFeedback("ok", response.payload?.message || tr("登录成功。", "Signed in successfully."));
  } catch (error) {
    setAuthFeedback("bad", error instanceof Error ? error.message : tr("登录失败。", "Login failed."));
  } finally {
    state.authBusy = false;
    renderAll();
  }
}

async function handleAuthLogout() {
  const { apiBaseUrl } = readAuthFormValues();
  state.authBusy = true;
  setAuthFeedback("", "");
  renderAll();
  try {
    const response = await postJson("/api/auth/logout", { apiBaseUrl });
    if (!response.ok) {
      throw new Error(response.payload?.error || response.payload?.message || tr("退出失败。", "Sign out failed."));
    }
    state.authSession = response.payload?.session || null;
    state.settingsOpen = false;
    state.helpOpen = false;
    state.aboutOpen = false;
    state.drawerOpen = false;
    setAuthGateMode("login");
    clearAuthPasswords();
    setAuthFeedback("ok", response.payload?.message || tr("已退出登录。", "Signed out successfully."));
  } catch (error) {
    setAuthFeedback("bad", error instanceof Error ? error.message : tr("退出失败。", "Sign out failed."));
  } finally {
    state.authBusy = false;
    renderAll();
  }
}
*/

state.chatStreamDraft = state.chatStreamDraft || null;
state.chatStreamRenderTimer = state.chatStreamRenderTimer || 0;
state.chatAbortController = state.chatAbortController || null;
state.chatStopRequested = Boolean(state.chatStopRequested);

function clearChatStreamRenderTimer() {
  if (!state.chatStreamRenderTimer) return;
  window.clearTimeout(state.chatStreamRenderTimer);
  state.chatStreamRenderTimer = 0;
}

function scheduleChatStreamRender() {
  if (state.chatStreamRenderTimer) return;
  state.chatStreamRenderTimer = window.setTimeout(() => {
    state.chatStreamRenderTimer = 0;
    renderAll();
  }, 32);
}

async function streamChatReply(body, handlers = {}, options = {}) {
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: options.signal,
  });

  const contentType = response.headers.get("content-type") || "";
  if (!response.ok && !contentType.includes("text/event-stream")) {
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    throw new Error(
      payload?.error || tr("普通对话请求被模型拒绝或执行失败，请检查模型配置和 provider 返回。", "The chat request was rejected or failed. Check the model and provider response.")
    );
  }

  if (!response.body) {
    const fallback = await postJson("/api/chat", body);
    if (!fallback.ok) {
      throw new Error(
        fallback.payload?.error || tr("普通对话请求被模型拒绝或执行失败，请检查模型配置和 provider 返回。", "The chat request was rejected or failed. Check the model and provider response.")
      );
    }
    handlers.onStart?.({ session_meta: body.session_meta || null });
    if (fallback.payload?.assistant_message) {
      handlers.onDelta?.({ content_delta: fallback.payload.assistant_message });
    }
    handlers.onDone?.({
      assistant_message: fallback.payload?.assistant_message || "",
      agent_handoff: fallback.payload?.agent_handoff || null,
      session_meta: fallback.payload?.session_meta || body.session_meta || null,
    });
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let streamClosed = false;

  const processEventBlock = (block) => {
    const lines = block
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    if (!lines.length) return;

    let eventName = "message";
    const dataLines = [];
    for (const line of lines) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trim());
      }
    }

    let payload = {};
    const raw = dataLines.join("\n");
    if (raw) {
      try {
        payload = JSON.parse(raw);
      } catch {
        payload = {};
      }
    }

    if (eventName === "start") {
      handlers.onStart?.(payload);
      return;
    }
    if (eventName === "delta") {
      handlers.onDelta?.(payload);
      return;
    }
    if (eventName === "done") {
      handlers.onDone?.(payload);
      streamClosed = true;
      return;
    }
    if (eventName === "error") {
      handlers.onError?.(payload);
      streamClosed = true;
    }
  };

  const flushBuffer = (finalChunk = false) => {
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      processEventBlock(block);
      boundary = buffer.indexOf("\n\n");
    }
    if (finalChunk && buffer.trim()) {
      processEventBlock(buffer);
      buffer = "";
    }
  };

  while (!streamClosed) {
    const { value, done } = await reader.read();
    if (done) {
      buffer += decoder.decode();
      flushBuffer(true);
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    flushBuffer(false);
  }

  if (!streamClosed) {
    handlers.onError?.({
      error: tr("回复流意外中断，请重试。", "The reply stream ended unexpectedly. Please try again."),
    });
  }
}


function renderNormalAssistantPendingMessage(draft = state.chatStreamDraft) {
  const content = String(draft?.content || "");
  const waitingMarkup = `
    <div class="assistant-copy assistant-copy--stream assistant-copy--waiting">
      <span class="stream-wait-indicator" aria-hidden="true"></span>
    </div>
  `;
  const streamingMarkup = `
    <div class="assistant-copy assistant-copy--stream">
      ${renderChatRichText(`${content} ▍`)}
    </div>
  `;

  return `
    <div class="message message--assistant">
      <article class="assistant-card assistant-card--chat assistant-card--pending">
        ${content ? streamingMarkup : waitingMarkup}
      </article>
    </div>
  `;
}


function normalizeChatMessageContent(value) {
  return String(value || "").replace(/\r\n/g, "\n").trim();
}

function normalizeChatRetryContext(value) {
  if (!value || typeof value !== "object") return null;
  const messages = Array.isArray(value.messages)
    ? value.messages
        .map((item) => ({
          role: item?.role === "assistant" ? "assistant" : "user",
          content: normalizeChatMessageContent(item?.content || ""),
        }))
        .filter((item) => item.content)
    : [];
  const suggestedTextModel = normalizeText(value.suggested_text_model || "");
  const previousModel = normalizeText(value.previous_model || "");
  const restoreToModel = normalizeText(value.restore_to_model || "") || previousModel;
  if (!messages.length || !suggestedTextModel || !previousModel) {
    return null;
  }
  return {
    messages,
    suggested_text_model: suggestedTextModel,
    previous_model: previousModel,
    restore_to_model: restoreToModel,
  };
}

function readSessionStorage(key) {
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeSessionStorage(key, value) {
  try {
    if (value == null || value === "") {
      window.sessionStorage.removeItem(key);
    } else {
      window.sessionStorage.setItem(key, value);
    }
  } catch {
    // Ignore storage failures.
  }
}

function clearLegacyActiveChatSessionStorage() {
  try {
    window.localStorage.removeItem(ACTIVE_CHAT_SESSION_STORAGE_KEY);
  } catch {
    // Ignore storage failures.
  }
}

function loadChatSessions() {
  try {
    const raw = window.localStorage.getItem(CHAT_SESSIONS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((item) => ({
        id: String(item?.id || "").trim(),
        title: normalizeText(item?.title || ""),
        created_at: Number(item?.created_at || 0) || Math.floor(Date.now() / 1000),
        updated_at: Number(item?.updated_at || 0) || Math.floor(Date.now() / 1000),
        messages: Array.isArray(item?.messages)
          ? item.messages
              .map((message, messageIndex) => ({
                id: String(message?.id || "").trim() || `legacy-${item?.id || "chat"}-${messageIndex}`,
                role: message?.role === "assistant" ? "assistant" : "user",
                content: normalizeChatMessageContent(message?.content || ""),
                created_at: Number(message?.created_at || 0) || Math.floor(Date.now() / 1000),
                status:
                  message?.role === "assistant" && message?.status === "stopped"
                    ? "stopped"
                    : "complete",
                handoff:
                  message?.handoff && typeof message.handoff === "object"
                    ? {
                        suggested_task: normalizeText(message.handoff.suggested_task || ""),
                        reason: normalizeText(message.handoff.reason || ""),
                      }
                    : null,
                error_code: normalizeText(message?.error_code || ""),
                recovery_action: normalizeText(message?.recovery_action || ""),
                recovery_label: normalizeText(message?.recovery_label || ""),
                retry_context: normalizeChatRetryContext(message?.retry_context),
              }))
              .filter((message) => message.content)
          : [],
        }))
      .filter((item) => item.id)
      .sort((left, right) => Number(right.updated_at || 0) - Number(left.updated_at || 0));
  } catch {
    return [];
  }
}

function persistChatSessions() {
  safeStorageSet(CHAT_SESSIONS_STORAGE_KEY, JSON.stringify(state.chatSessions.slice(0, 24)));
  writeSessionStorage(ACTIVE_CHAT_SESSION_SESSION_KEY, state.selectedChatSessionId || null);
  writeSessionStorage(CHAT_LAUNCH_SESSION_KEY, state.chatLaunchId || null);
  clearLegacyActiveChatSessionStorage();
}

function normalizeHistorySelection(raw) {
  if (!raw || typeof raw !== "object") return null;
  const kind = raw.kind === "chat" || raw.kind === "run" ? raw.kind : null;
  const id = normalizeText(raw.id || "");
  if (!kind || !id) return null;
  return { kind, id };
}

function loadPersistedHistorySelection() {
  try {
    const raw = window.localStorage.getItem(HISTORY_SELECTION_STORAGE_KEY);
    if (!raw) return null;
    return normalizeHistorySelection(JSON.parse(raw));
  } catch {
    return null;
  }
}

function persistHistorySelection(selection) {
  const normalized = normalizeHistorySelection(selection);
  state.historySelection = normalized;
  if (!normalized) {
    safeStorageSet(HISTORY_SELECTION_STORAGE_KEY, null);
    return;
  }
  safeStorageSet(HISTORY_SELECTION_STORAGE_KEY, JSON.stringify(normalized));
}

function clearHistorySelection(kind = null) {
  if (!kind) {
    persistHistorySelection(null);
    return;
  }
  if (state.historySelection?.kind === kind) {
    persistHistorySelection(null);
  }
}

function findLatestNonEmptyChatSessionId() {
  return (
    state.chatSessions.find((session) => Array.isArray(session.messages) && session.messages.length)?.id || null
  );
}

function restoreInitialHistorySelection(options = {}) {
  if (state.historySelectionRestored) return;

  state.historySelectionRestored = true;
  const savedSelection = normalizeHistorySelection(state.historySelection);
  if (!savedSelection) {
    if (state.uiMode === "chat" && !getSelectedChatSession()) {
      state.selectedChatSessionId = findLatestNonEmptyChatSessionId();
    }
    return;
  }

  if (savedSelection.kind === "chat") {
    const hasSavedChat = state.chatSessions.some(
      (session) => session.id === savedSelection.id && Array.isArray(session.messages) && session.messages.length
    );
    if (hasSavedChat) {
      state.selectedChatSessionId = savedSelection.id;
      state.uiMode = "chat";
      safeStorageSet(UI_MODE_STORAGE_KEY, state.uiMode);
      return;
    }

    if (state.uiMode === "chat") {
      const fallbackChatId = findLatestNonEmptyChatSessionId();
      state.selectedChatSessionId = fallbackChatId;
      if (fallbackChatId) {
        persistHistorySelection({ kind: "chat", id: fallbackChatId });
      } else {
        persistHistorySelection(null);
      }
      return;
    }

    persistHistorySelection(null);
    return;
  }

  const hasSavedRun = state.runs.some((run) => run.id === savedSelection.id);
  state.uiMode = "agent";
  safeStorageSet(UI_MODE_STORAGE_KEY, state.uiMode);

  if (hasSavedRun) {
    state.selectedRunId = savedSelection.id;
    state.showWelcome = false;
    state.loadingRunDetails = true;
    return;
  }

  persistHistorySelection(null);
  state.selectedRunId = null;
  state.selectedRunDetails = null;
  state.loadingRunDetails = false;
  state.showWelcome = true;
  if (options.forceLatest) {
    state.autoFollowLatest = true;
  }
}

function detectInitialChatSessionId(sessions) {
  const saved = readSessionStorage(ACTIVE_CHAT_SESSION_SESSION_KEY);
  if (saved && sessions.some((item) => item.id === saved && Array.isArray(item.messages) && item.messages.length)) {
    return saved;
  }
  clearLegacyActiveChatSessionStorage();
  return null;
}

function syncChatLaunchState(meta) {
  const nextLaunchId = String(meta?.chat_launch_id || "").trim();
  if (!nextLaunchId) return;

  const previousLaunchId = readSessionStorage(CHAT_LAUNCH_SESSION_KEY);
  state.chatLaunchId = nextLaunchId;

  if (previousLaunchId && previousLaunchId !== nextLaunchId) {
    if (state.chatPending) {
      stopActiveChatReply();
    }
  }

  writeSessionStorage(CHAT_LAUNCH_SESSION_KEY, nextLaunchId);
  writeSessionStorage(
    ACTIVE_CHAT_SESSION_SESSION_KEY,
    state.selectedChatSessionId || null
  );
  clearLegacyActiveChatSessionStorage();
}

function detectInitialUiMode() {
  const saved = window.localStorage.getItem(UI_MODE_STORAGE_KEY);
  if (saved === "chat" || saved === "agent" || saved === "developer") return saved;
  if (saved === "user") return "agent";
  return "agent";
}

function generateChatSessionId() {
  if (window.crypto?.randomUUID) {
    return `chat-${window.crypto.randomUUID().slice(0, 12)}`;
  }
  return `chat-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function generateChatMessageId() {
  if (window.crypto?.randomUUID) {
    return `msg-${window.crypto.randomUUID().slice(0, 12)}`;
  }
  return `msg-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function getSelectedChatSession() {
  return state.chatSessions.find((item) => item.id === state.selectedChatSessionId) || null;
}

function ensureChatSession(seedText = "") {
  let session = getSelectedChatSession();
  if (session) {
    persistHistorySelection({ kind: "chat", id: session.id });
    return session;
  }

  const now = Math.floor(Date.now() / 1000);
  session = {
    id: generateChatSessionId(),
    title: normalizeText(seedText),
    created_at: now,
    updated_at: now,
    messages: [],
  };
  state.chatSessions = [session, ...state.chatSessions];
  state.selectedChatSessionId = session.id;
  persistHistorySelection({ kind: "chat", id: session.id });
  persistChatSessions();
  return session;
}

function appendChatMessage(sessionId, message) {
  const session = state.chatSessions.find((item) => item.id === sessionId);
  if (!session) return;

  const payload = {
    id: String(message.id || "").trim() || generateChatMessageId(),
    role: message.role === "assistant" ? "assistant" : "user",
    content: normalizeChatMessageContent(message.content),
    created_at: Math.floor(Date.now() / 1000),
    status:
      message.role === "assistant" && message.status === "stopped"
        ? "stopped"
        : "complete",
    handoff:
      message.handoff && typeof message.handoff === "object"
        ? {
            suggested_task: normalizeText(message.handoff.suggested_task || ""),
            reason: normalizeText(message.handoff.reason || ""),
          }
        : null,
    error_code: normalizeText(message.error_code || ""),
    recovery_action: normalizeText(message.recovery_action || ""),
    recovery_label: normalizeText(message.recovery_label || ""),
    retry_context: normalizeChatRetryContext(message.retry_context),
  };
  if (!payload.content) return;

  session.messages.push(payload);
  if (payload.role === "user" && !session.title) {
    session.title = payload.content;
  }
  session.updated_at = payload.created_at;
  state.chatSessions = state.chatSessions
    .slice()
    .sort((left, right) => Number(right.updated_at || 0) - Number(left.updated_at || 0));
  persistChatSessions();
}

function buildChatSessionTitle(session) {
  const firstUserMessage = session?.messages?.find((item) => item.role === "user")?.content || session?.title || "";
  const source = normalizeText(firstUserMessage);
  const lower = source.toLowerCase();

  if (!source) return tr("普通对话", "Chat");
  if (/lm studio|lmstudio|本地模型|模型/.test(lower + source)) return tr("模型配置", "Model setup");
  if (/agent|模式|difference|区别|thinking|普通对话/.test(lower + source)) return tr("模式说明", "Mode guide");
  if (/browser|playwright|通道|浏览器/.test(lower + source)) return tr("浏览器设置", "Browser setup");
  if (/help|readme|文档|帮助/.test(lower + source)) return tr("帮助文档", "Help docs");
  if (/task|prompt|任务|提示词|改写/.test(lower + source)) return tr("任务整理", "Task drafting");
  if (looksLikeAgentTaskForUi(source)) return buildSidebarHistoryTitle(source);
  return clipText(source.replace(/\?+$/, "").replace(/？+$/, ""), 14) || tr("普通对话", "Chat");
}

function looksLikeAgentTaskForUi(text) {
  const source = normalizeText(text).toLowerCase();
  return /open|launch|visit|search|click|type|press|shop|buy|login|登录|访问|搜索|点击|输入|打开|购买/.test(source);
}

function buildSidebarHistoryItems() {
  const runItems = state.runs.map((run) => ({
    kind: "run",
    id: run.id,
    updatedAt: Number(run.finished_at || run.started_at || run.created_at || 0),
    title: normalizeText(run.task || ""),
    label: buildSidebarHistoryTitle(run.task),
    active: state.uiMode !== "chat" && !state.showWelcome && state.selectedRunId === run.id,
    task: run.task,
  }));
  const chatItems = state.chatSessions
    .filter((session) => (session.messages || []).length)
    .map((session) => ({
      kind: "chat",
      id: session.id,
      updatedAt: Number(session.updated_at || session.created_at || 0),
      title: normalizeText(session.messages?.find((item) => item.role === "user")?.content || session.title || ""),
      label: buildChatSessionTitle(session),
      active: state.uiMode === "chat" && state.selectedChatSessionId === session.id,
      task: session.title,
    }));

  return [...chatItems, ...runItems].sort((left, right) => right.updatedAt - left.updatedAt);
}

function renderTopbar() {
  const context = getAgentConversationContext();
  const chatSession = getSelectedChatSession();
  const connection = elements.connectionBadge;
  connection.className = "connection-chip connection-chip--status";
  let connectionLabel = tr("在线", "Online");

  if (state.connected) {
    connection.classList.add("connection-chip--ok");
    connectionLabel = tr("在线", "Online");
  } else if (state.usingCachedSnapshot) {
    connection.classList.add("connection-chip--warn");
    connectionLabel = tr("缓存", "Cached");
  } else {
    connection.classList.add("connection-chip--bad");
    connectionLabel = tr("离线", "Offline");
  }
  connection.setAttribute("title", connectionLabel);
  connection.setAttribute("aria-label", connectionLabel);

  if (state.uiMode === "chat") {
    elements.topbarTitle.textContent = chatSession ? buildChatSessionTitle(chatSession) : tr("普通对话", "Chat");
    elements.topbarSubtitle.textContent = "";
    return;
  }

  if (state.uiMode === "developer") {
    elements.topbarTitle.textContent = tr("开发控制台", "Developer");
    elements.topbarSubtitle.textContent = "";
    return;
  }

  if (context.type === "active") {
    elements.topbarTitle.textContent = cleanRunTitle(context.active.task);
    elements.topbarSubtitle.textContent = "";
    return;
  }

  if (context.type === "run") {
    elements.topbarTitle.textContent = cleanRunTitle(context.details.task);
    elements.topbarSubtitle.textContent = "";
    return;
  }

  if (context.type === "pending") {
    elements.topbarTitle.textContent = cleanRunTitle(context.task);
    elements.topbarSubtitle.textContent = "";
    return;
  }

  elements.topbarTitle.textContent = "Agent";
  elements.topbarSubtitle.textContent = "";
}

function renderSidebarRuns() {
  const items = buildSidebarHistoryItems();
  if (!items.length) {
    elements.sidebarRunList.innerHTML = `<div class="empty-state">${escapeHtml(tr("还没有历史记录。", "No history yet."))}</div>`;
    return;
  }

  elements.sidebarRunList.innerHTML = items
    .map((item) => {
      const targetAttr =
        item.kind === "chat"
          ? `data-chat-session-id="${escapeHtml(item.id)}"`
          : `data-run-id="${escapeHtml(item.id)}"`;
      return `
        <button
          class="history-item history-item--${item.kind}${item.active ? " active" : ""}"
          type="button"
          ${targetAttr}
          title="${escapeHtml(item.title || item.label)}"
        >
          <span class="history-item__inner">
            ${renderMixedHistoryBadge(item)}
            <span class="history-item__title">${escapeHtml(item.label)}</span>
          </span>
        </button>
      `;
    })
    .join("");
}

function renderMixedHistoryBadge(item) {
  if (item.kind !== "chat") {
    return renderHistoryBadge(item.task);
  }
  return `
    <span class="history-item__badge history-item__badge--chat" aria-hidden="true">
      <svg class="icon-svg" viewBox="0 0 24 24">
        <path
          d="M5.5 6.5A3.5 3.5 0 0 1 9 3h6a3.5 3.5 0 0 1 3.5 3.5v4A3.5 3.5 0 0 1 15 14h-2.4l-3.3 2.7c-.55.45-1.3.06-1.3-.64V14H9a3.5 3.5 0 0 1-3.5-3.5z"
          fill="none"
          stroke="currentColor"
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="1.8"
        />
      </svg>
    </span>
  `;
}

function getAgentConversationContext() {
  if (state.activeJob) return { type: "active", active: state.activeJob };
  if (state.pendingTask) return { type: "pending", task: state.pendingTask };
  if (state.loadingRunDetails && state.selectedRunId && !state.selectedRunDetails) return { type: "loading" };
  if (!state.showWelcome && state.selectedRunDetails) return { type: "run", details: state.selectedRunDetails };
  return { type: "welcome" };
}

function renderChat() {
  if (state.uiMode === "chat") {
    renderNormalChat();
    return;
  }
  renderAgentChat();
}

function renderAgentChat() {
  const context = getAgentConversationContext();
  const messages = [];

  if (context.type === "welcome") {
    messages.push(renderWelcomeMessage());
  } else if (context.type === "pending") {
    messages.push(renderUserMessage(context.task));
    messages.push(renderPendingMessage(context.task));
  } else if (context.type === "loading") {
    messages.push(renderLoadingMessage());
  } else if (context.type === "active") {
    messages.push(renderUserMessage(context.active.task || ""));
    messages.push(renderRunningMessage(context.active));
  } else if (context.type === "run") {
    messages.push(renderUserMessage(context.details.task || ""));
    messages.push(...renderCompletedConversation(context.details));
  }

  elements.chatStream.innerHTML = messages.join("");
  renderComposerSuggestions(context);
  renderComposerState(context);

  if (context.type === "active" || context.type === "pending") {
    window.requestAnimationFrame(() => {
      elements.chatScroll.scrollTop = elements.chatScroll.scrollHeight;
    });
  }
}

function renderNormalChat() {
  const session = getSelectedChatSession();
  const messages = [];

  if (!session || !(session.messages || []).length) {
    messages.push(`
      <div class="chat-welcome">
        <p>${escapeHtml(tr("普通对话", "Chat"))}</p>
        <h2>${escapeHtml(tr("你想先了解什么？", "What do you want to ask first?"))}</h2>
        <p>${escapeHtml(
          tr(
            "可以直接问产品能力、LM Studio 配置、浏览器设置或排障。如果你想让系统真正执行任务，我会给你转到 Agent 的入口。",
            "Ask about product features, LM Studio setup, browser settings, or troubleshooting. If you want real execution, I will offer an Agent handoff."
          )
        )}</p>
      </div>
    `);
  } else {
    for (const message of session.messages) {
      if (message.role === "user") {
        messages.push(renderUserMessage(message.content));
      } else {
        messages.push(renderNormalAssistantMessage(message));
      }
    }
    if (state.chatPending) {
      messages.push(renderNormalAssistantPendingMessage());
    }
  }

  elements.chatStream.innerHTML = messages.join("");
  renderComposerSuggestions({ type: "chat" });
  renderComposerState({ type: "chat" });

  window.requestAnimationFrame(() => {
    elements.chatScroll.scrollTop = elements.chatScroll.scrollHeight;
  });
}

function renderNormalAssistantMessage(message) {
  const handoff = message.handoff?.suggested_task
    ? `
      <div class="message-actions">
        <button class="secondary-button" type="button" data-start-agent-task="${escapeHtml(message.handoff.suggested_task)}">
          ${escapeHtml(tr("转到 Agent 执行", "Send to Agent"))}
        </button>
        ${
          message.handoff.reason
            ? `<span class="message-meta">${escapeHtml(
                state.locale === "zh-CN" ? "适合真实执行的桌面或浏览器动作。" : message.handoff.reason
              )}</span>`
            : ""
        }
      </div>
    `
    : "";

  return `
    <div class="message message--assistant">
      <article class="assistant-card assistant-card--chat">
        <div class="assistant-copy">${renderChatRichText(message.content)}</div>
        ${handoff}
      </article>
    </div>
  `;
}

function renderNormalAssistantPendingMessage() {
  return `
    <div class="message message--assistant">
      <article class="assistant-card assistant-card--chat">
        <div class="assistant-copy">
          <p>${escapeHtml(tr("正在思考当前问题。", "Thinking about your request."))}</p>
        </div>
      </article>
    </div>
  `;
}

function renderChatRichText(text) {
  const blocks = String(text || "")
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean);

  if (!blocks.length) {
    return `<p>${escapeHtml(text || "")}</p>`;
  }

  return blocks
    .map((block) => {
      const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
      if (lines.every((line) => line.startsWith("- "))) {
        return `<ul>${lines.map((line) => `<li>${escapeHtml(line.slice(2))}</li>`).join("")}</ul>`;
      }
      return `<p>${lines.map((line) => escapeHtml(line)).join("<br />")}</p>`;
    })
    .join("");
}

function renderComposerSuggestions(context) {
  if (state.uiMode === "chat") {
    const session = getSelectedChatSession();
    if (state.chatPending || session?.messages?.length) {
      elements.composerSuggestions.innerHTML = "";
      return;
    }
    const items = [
      { label: tr("模式区别", "Modes"), task: tr("普通对话和 Agent 有什么区别？", "What is the difference between chat mode and Agent mode?") },
      { label: "LM Studio", task: tr("怎么配置 LM Studio 并自动发现模型？", "How do I configure LM Studio and auto-discover models?") },
      { label: tr("浏览器设置", "Browser"), task: tr("浏览器通道、Playwright 和路径分别怎么设置？", "How should I configure browser channel, Playwright, and executable path?") },
      { label: tr("任务改写", "Rewrite"), task: tr("帮我把需求改写成适合 Agent 执行的任务。", "Help me rewrite my request into an Agent-ready task.") },
    ];
    elements.composerSuggestions.innerHTML = items
      .map(
        (item) => `
          <button class="suggestion-chip" type="button" data-prefill-chat="${escapeHtml(item.task)}">
            ${escapeHtml(item.label)}
          </button>
        `
      )
      .join("");
    return;
  }

  if (state.activeJob || state.uiMode === "developer" || context.type !== "welcome") {
    elements.composerSuggestions.innerHTML = "";
    return;
  }

  const items = buildStarterSuggestions();
  if (!items.length) {
    elements.composerSuggestions.innerHTML = "";
    return;
  }

  elements.composerSuggestions.innerHTML = items
    .map(
      (item) => `
        <button class="suggestion-chip" type="button" data-prefill-task="${escapeHtml(item.task)}" title="${escapeHtml(item.description || "")}">
          ${escapeHtml(item.label)}
        </button>
      `
    )
    .join("");
}

function handleHistoryClick(event) {
  const chatButton = event.target.closest("[data-chat-session-id]");
  if (chatButton) {
    selectChatSession(chatButton.dataset.chatSessionId);
    return;
  }

  const runButton = event.target.closest("[data-run-id]");
  if (!runButton) return;
  selectRun(runButton.dataset.runId, { manualSelection: true });
}

function handleInteractiveClick(event) {
  const lightboxTrigger = event.target.closest("[data-lightbox-src]");
  if (lightboxTrigger) {
    openLightbox(lightboxTrigger.dataset.lightboxSrc, lightboxTrigger.dataset.lightboxCaption);
    return;
  }

  const chatPrefillTrigger = event.target.closest("[data-prefill-chat]");
  if (chatPrefillTrigger) {
    prefillChatMessage(chatPrefillTrigger.dataset.prefillChat || "");
    return;
  }

  const startAgentTrigger = event.target.closest("[data-start-agent-task]");
  if (startAgentTrigger) {
    prefillTask(startAgentTrigger.dataset.startAgentTask || "");
    return;
  }

  const copyChatTrigger = event.target.closest("[data-copy-chat-message]");
  if (copyChatTrigger) {
    handleCopyChatMessage(copyChatTrigger.dataset.copyChatMessage || "");
    return;
  }

  const retryChatTrigger = event.target.closest("[data-retry-chat-message]");
  if (retryChatTrigger) {
    handleRetryChatMessage(retryChatTrigger.dataset.retryChatMessage || "");
    return;
  }

  const recoverChatTrigger = event.target.closest("[data-recover-chat-message]");
  if (recoverChatTrigger) {
    handleRecoverChatMessage(recoverChatTrigger.dataset.recoverChatMessage || "");
    return;
  }

  const prefillTrigger = event.target.closest("[data-prefill-task]");
  if (prefillTrigger) {
    prefillTask(prefillTrigger.dataset.prefillTask || "");
    return;
  }

  const inspectorTrigger = event.target.closest("[data-open-inspector]");
  if (inspectorTrigger) {
    openInspectorForRun(inspectorTrigger.dataset.openInspector);
    return;
  }

  const stopTrigger = event.target.closest("[data-stop-active-task]");
  if (stopTrigger) {
    handleStopTask();
  }
}

async function handleSubmit(event) {
  event.preventDefault();
  const text = elements.taskInput.value.trim();

  if (!isConfigHydrated()) {
    elements.submitHint.textContent = getConfigLoadingMessage();
    return;
  }

  if (!text) {
    elements.submitHint.textContent = tr("先输入内容", "Enter something first");
    return;
  }

  if (state.uiMode === "chat") {
    await submitChatMessage(text);
    return;
  }

  await submitAgentTask(text);
}

async function submitChatMessage(text) {
  const session = ensureChatSession(text);
  appendChatMessage(session.id, { role: "user", content: text });
  state.chatPending = true;
  elements.taskInput.value = "";
  renderAll();

  const activeSession = getSelectedChatSession() || session;
  const response = await postJson("/api/chat", {
    messages: (activeSession.messages || []).slice(-12).map((item) => ({ role: item.role, content: item.content })),
    config_overrides: buildConfigOverrides(),
    session_meta: { session_id: activeSession.id, locale: state.locale },
  });

  state.chatPending = false;
  if (!response.ok) {
    appendChatMessage(activeSession.id, {
      role: "assistant",
      content: response.payload?.error || tr("普通对话请求被模型拒绝或执行失败，请检查模型配置和 provider 返回。", "The chat request was rejected or failed. Check the model and provider response."),
    });
    renderAll();
    return;
  }

  appendChatMessage(activeSession.id, {
    role: "assistant",
    content: response.payload?.assistant_message || tr("我暂时没有收到可用回复。", "I did not receive a usable reply."),
    handoff: response.payload?.agent_handoff || null,
  });
  renderAll();
}

async function submitAgentTask(taskText) {
  const payload = {
    task: taskText.trim(),
    planner_mode: "auto",
    dry_run: false,
    max_steps: elements.maxStepsInput.value ? Number(elements.maxStepsInput.value) : null,
    pause_after_action: elements.pauseInput.value ? Number(elements.pauseInput.value) : null,
    config_overrides: buildConfigOverrides(),
  };

  if (!payload.task) {
    elements.submitHint.textContent = tr("先输入任务", "Enter a task");
    return;
  }

  state.pendingTask = payload.task;
  state.showWelcome = false;
  state.autoFollowLatest = true;
  state.selectedRunId = null;
  state.selectedRunDetails = null;
  clearHistorySelection("run");
  if (state.uiMode !== "agent") {
    setUiMode("agent");
  }
  renderAll();

  const response = await postJson("/api/tasks", payload);
  if (!response.ok) {
    state.pendingTask = null;
    elements.submitHint.textContent = response.payload?.error || tr("任务提交失败", "Task submission failed");
    renderAll();
    return;
  }

  elements.taskInput.value = "";
  elements.submitHint.textContent = tr("任务已发送", "Queued");
  await refreshOverview({ forceLatest: true });
}

function handleGlobalKeydown(event) {
  if (state.openCustomSelectId && event.key === "Escape") {
    event.preventDefault();
    closeCustomSelect({ restoreFocus: true });
    return;
  }

  if (event.key === "Escape") {
    if (!elements.imageLightbox.hidden) {
      closeLightbox();
      return;
    }
    if (state.drawerOpen) {
      closeDrawer();
      return;
    }
    if (state.helpOpen) {
      closeHelpCenter();
      return;
    }
    if (state.settingsOpen) {
      closeSettings();
      return;
    }
    if (state.mobileSidebarOpen) {
      closeSidebar();
    }
    return;
  }

  if (state.helpOpen && event.key === "Tab") {
    trapFocusWithin(event, elements.helpModal);
  }

  if (state.settingsOpen && event.key === "Tab") {
    trapFocusWithin(event, elements.settingsModal);
  }

  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "b" && !isTypingTarget(event.target)) {
    event.preventDefault();
    toggleSidebar();
  }
}

function setUiMode(mode) {
  state.uiMode = ["chat", "agent", "developer"].includes(mode) ? mode : "agent";
  safeStorageSet(UI_MODE_STORAGE_KEY, state.uiMode);
  renderAll();
}

function startNewTask() {
  closeSidebar();
  closeDrawer();

  if (state.uiMode === "chat") {
    if (state.chatPending) {
      stopActiveChatReply();
    }
    state.selectedChatSessionId = null;
    state.chatPending = false;
    clearHistorySelection("chat");
    renderAll();
    window.requestAnimationFrame(() => {
      elements.taskInput.focus();
    });
    persistChatSessions();
    return;
  }

  state.showWelcome = true;
  state.selectedRunId = null;
  state.selectedRunDetails = null;
  state.loadingRunDetails = false;
  state.pendingTask = null;
  state.autoFollowLatest = false;
  clearHistorySelection("run");
  if (state.uiMode !== "agent") {
    state.uiMode = "agent";
    safeStorageSet(UI_MODE_STORAGE_KEY, state.uiMode);
  }
  renderAll();
  window.requestAnimationFrame(() => {
    elements.taskInput.focus();
  });
}

function prefillChatMessage(text) {
  elements.taskInput.value = String(text || "");
  if (state.uiMode !== "chat") {
    setUiMode("chat");
  }
  closeSettings();
  closeHelpCenter();
  closeSidebar();
  renderAll();
  window.requestAnimationFrame(() => {
    elements.taskInput.focus();
    const end = elements.taskInput.value.length;
    elements.taskInput.setSelectionRange?.(end, end);
  });
}

function prefillTask(task) {
  const nextTask = String(task || "").trim();
  if (nextTask) {
    elements.taskInput.value = nextTask;
  }
  state.showWelcome = false;
  if (state.uiMode !== "agent") {
    state.uiMode = "agent";
    safeStorageSet(UI_MODE_STORAGE_KEY, state.uiMode);
  }
  closeSettings();
  closeHelpCenter();
  closeDrawer();
  closeSidebar();
  renderAll();
  window.requestAnimationFrame(() => {
    elements.taskInput.focus();
    const end = elements.taskInput.value.length;
    if (typeof elements.taskInput.setSelectionRange === "function") {
      elements.taskInput.setSelectionRange(end, end);
    }
  });
}

function selectRun(runId, options = {}) {
  state.showWelcome = false;
  state.selectedRunId = runId;
  state.selectedRunDetails = null;
  state.loadingRunDetails = true;
  state.autoFollowLatest = !options.manualSelection || runId === state.runs[0]?.id;
  state.pendingTask = null;
  state.uiMode = options.keepMode === "developer" ? "developer" : "agent";
  safeStorageSet(UI_MODE_STORAGE_KEY, state.uiMode);
  persistHistorySelection({ kind: "run", id: runId });
  if (options.openDrawer) {
    state.drawerOpen = true;
  }
  closeSidebar();
  renderAll();
  loadRunDetails(runId, { background: false });
}

function selectChatSession(sessionId) {
  if (state.chatPending && state.selectedChatSessionId !== sessionId) {
    stopActiveChatReply();
  }
  state.selectedChatSessionId = sessionId;
  state.uiMode = "chat";
  safeStorageSet(UI_MODE_STORAGE_KEY, state.uiMode);
  persistHistorySelection({ kind: "chat", id: sessionId });
  persistChatSessions();
  closeSidebar();
  renderAll();
}

function openDeveloperConsole() {
  closeCustomSelect({ restoreFocus: false });
  closeSettings();
  setUiMode("developer");
}

function openHelpCenter() {
  state.helpRestoreFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  closeCustomSelect({ restoreFocus: false });
  state.settingsOpen = false;
  state.helpOpen = true;
  renderAll();
  if (!state.helpContent && !state.helpLoading) {
    loadHelpContent();
  }
  window.requestAnimationFrame(() => {
    getFocusableNodes(elements.helpModal)[0]?.focus();
  });
}

function closeHelpCenter() {
  state.helpOpen = false;
  renderAll();
  if (state.helpRestoreFocus?.focus) {
    window.requestAnimationFrame(() => {
      state.helpRestoreFocus.focus();
      state.helpRestoreFocus = null;
    });
  }
}


function renderSimpleMarkdown(markdown) {
  const engine = getChatMarkdownEngine();
  if (engine && typeof engine.render === "function") {
    return `<article class="help-doc help-doc--markdown assistant-markdown">${engine.render(markdown)}</article>`;
  }

  const lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    if (line.startsWith("```")) {
      const codeLines = [];
      index += 1;
      while (index < lines.length && !lines[index].startsWith("```")) {
        codeLines.push(lines[index]);
        index += 1;
      }
      html.push(`<pre class="help-code"><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
      index += 1;
      continue;
    }

    if (line.startsWith("### ")) {
      html.push(`<h3>${escapeHtml(line.slice(4).trim())}</h3>`);
      index += 1;
      continue;
    }
    if (line.startsWith("## ")) {
      html.push(`<h2>${escapeHtml(line.slice(3).trim())}</h2>`);
      index += 1;
      continue;
    }
    if (line.startsWith("# ")) {
      html.push(`<h1>${escapeHtml(line.slice(2).trim())}</h1>`);
      index += 1;
      continue;
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
        items.push(`<li>${escapeHtml(lines[index].replace(/^\s*[-*]\s+/, ""))}</li>`);
        index += 1;
      }
      html.push(`<ul>${items.join("")}</ul>`);
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^\s*\d+\.\s+/.test(lines[index])) {
        items.push(`<li>${escapeHtml(lines[index].replace(/^\s*\d+\.\s+/, ""))}</li>`);
        index += 1;
      }
      html.push(`<ol>${items.join("")}</ol>`);
      continue;
    }

    const paragraph = [];
    while (index < lines.length && lines[index].trim() && !/^(#|##|###|```|\s*[-*]\s+|\s*\d+\.\s+)/.test(lines[index])) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    html.push(`<p>${escapeHtml(paragraph.join(" ")).replace(/\`([^`]+)\`/g, "<code>$1</code>")}</p>`);
  }

  return `<article class="help-doc">${html.join("")}</article>`;
}


function applyStaticCopy() {
  document.documentElement.lang = state.locale;
  document.title = t("document.title");

  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });

  document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    node.setAttribute("placeholder", t(node.dataset.i18nPlaceholder));
  });

  const closeLabel = t("common.closeLabel");
  const sidebarToggleLabel = state.sidebarCollapsed ? tr("展开侧栏", "Expand sidebar") : tr("收起侧栏", "Collapse sidebar");
  elements.newTaskButton?.setAttribute("aria-label", t("sidebar.newTask"));
  elements.sidebarBrandButton?.setAttribute("aria-label", sidebarToggleLabel);
  elements.sidebarBrandButton?.setAttribute("title", sidebarToggleLabel);
  elements.closeSettingsButton?.setAttribute("aria-label", closeLabel);
  elements.closeDrawerButton?.setAttribute("aria-label", closeLabel);
  elements.settingsButton?.setAttribute("aria-label", t("topbar.settings"));
  elements.settingsButton?.setAttribute("title", t("topbar.settings"));
  elements.refreshRunsButton?.setAttribute("aria-label", t("common.refresh"));
  elements.refreshRunsButton?.setAttribute("title", t("common.refresh"));
  elements.submitButton?.setAttribute("aria-label", t("chat.send"));
  elements.submitButton?.setAttribute("title", t("chat.send"));
  elements.stopButton?.setAttribute("aria-label", t("chat.stop"));
  elements.stopButton?.setAttribute("title", t("chat.stop"));
  elements.refreshCatalogButton?.setAttribute("aria-label", t("developer.refreshModels"));
  elements.refreshCatalogButton?.setAttribute("title", t("developer.refreshModels"));

  elements.uiModeTabs?.querySelectorAll("[data-ui-mode]").forEach((button) => {
    const label = button.dataset.uiMode === "agent" ? "Agent" : tr("普通对话", "Chat");
    button.setAttribute("aria-label", label);
    button.setAttribute("title", label);
    button.classList.toggle("active", button.dataset.uiMode === state.uiMode);
  });

  if (elements.openHelpCenterButton) {
    elements.openHelpCenterButton.textContent = tr("开发者文档", "Developer Docs");
  }
  if (elements.openDeveloperConsoleButton) {
    elements.openDeveloperConsoleButton.textContent = tr("开发控制台", "Developer Console");
  }
  const helpTitle = document.getElementById("helpAndAdvancedTitle");
  if (helpTitle) {
    helpTitle.textContent = tr("文档与高级", "Docs & Advanced");
  }
  const helpCenterTitle = document.getElementById("helpCenterTitle");
  if (helpCenterTitle && !state.helpContent) {
    helpCenterTitle.textContent = tr("开发者文档", "Developer Docs");
  }
  elements.helpBackdrop?.setAttribute("aria-label", tr("关闭开发者文档", "Close developer docs"));
  elements.closeHelpButton?.setAttribute("aria-label", closeLabel);
}

function setLocale(locale) {
  state.locale = normalizeLocale(locale);
  state.helpContent = "";
  state.helpError = "";
  state.helpLoading = false;
  state.helpLocale = "";
  state.helpTitle = state.locale === "en-US" ? "Developer Docs" : "开发者文档";
  safeStorageSet(LOCALE_STORAGE_KEY, state.locale);
  fillLanguageOptions();
  fillSendShortcutOptions();
  fillSelect(
    elements.browserChannel,
    localizeBrowserChannels(state.meta?.browser_channels || []),
    elements.browserChannel?.value || state.meta?.defaults?.browser_channel || ""
  );
  renderAll();
  if (state.helpOpen) {
    loadHelpContent();
  }
}

function renderSettingsProfile() {
  const profileTitle = document.querySelector(".settings-profile strong");
  if (profileTitle) {
    profileTitle.textContent = tr("本地工作台", "Local Workspace");
  }
  if (elements.configBadge) {
    elements.configBadge.textContent = "";
  }
}


async function loadHelpContent() {
  state.helpLoading = true;
  state.helpError = "";
  state.helpTitle = state.locale === "en-US" ? "Developer Docs" : "开发者文档";
  renderAll();

  const locale = normalizeLocale(state.locale);
  const payload = await fetchJson(`/api/help?locale=${encodeURIComponent(locale)}`);
  state.helpLoading = false;
  if (!payload) {
    state.helpError = tr("无法加载开发者文档。", "Could not load developer docs.");
    renderAll();
    return;
  }

  state.helpLocale = payload.locale || locale;
  state.helpTitle = payload.title || (locale === "en-US" ? "Developer Docs" : "开发者文档");
  state.helpContent = payload.markdown || "";
  state.helpError = "";
  renderAll();
}

function renderHelpCenter() {
  if (elements.helpCenterTitle) {
    elements.helpCenterTitle.textContent = state.helpTitle || tr("开发者文档", "Developer Docs");
  }
  if (!elements.helpContent) return;

  if (state.helpLoading) {
    elements.helpContent.innerHTML = `<div class="empty-state">${escapeHtml(tr("正在加载开发者文档…", "Loading developer docs..."))}</div>`;
    return;
  }

  if (state.helpError) {
    elements.helpContent.innerHTML = `<div class="empty-state">${escapeHtml(state.helpError)}</div>`;
    return;
  }

  if (!state.helpContent) {
    elements.helpContent.innerHTML = `<div class="empty-state">${escapeHtml(tr("暂无文档内容。", "No documentation available."))}</div>`;
    return;
  }

  elements.helpContent.innerHTML = renderSimpleMarkdown(state.helpContent);
}
state.chatStreamDraft = state.chatStreamDraft || null;
state.chatStreamRenderTimer = state.chatStreamRenderTimer || 0;
state.chatStreamRevealTimer = state.chatStreamRevealTimer || 0;
state.chatPendingBadgeTimer = state.chatPendingBadgeTimer || 0;

function getChatMarkdownEngine() {
  return globalThis.DesktopAgentMarkdown || null;
}

function fallbackRenderChatMarkdown(text) {
  const blocks = String(text || "")
    .replace(/\r\n/g, "\n")
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean);

  if (!blocks.length) {
    return `<p>${escapeHtml(text || "")}</p>`;
  }

  return blocks
    .map((block) => {
      const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
      if (lines.every((line) => line.startsWith("- "))) {
        return `<ul>${lines.map((line) => `<li>${escapeHtml(line.slice(2))}</li>`).join("")}</ul>`;
      }
      return `<p>${lines.map((line) => escapeHtml(line)).join("<br />")}</p>`;
    })
    .join("");
}

function renderChatMarkdown(text) {
  const engine = getChatMarkdownEngine();
  if (engine && typeof engine.render === "function") {
    return engine.render(text);
  }
  return fallbackRenderChatMarkdown(text);
}

function renderStreamingChatMarkdown(text, options = {}) {
  const engine = getChatMarkdownEngine();
  if (engine && typeof engine.renderStreaming === "function") {
    return engine.renderStreaming(text, options);
  }
  return fallbackRenderChatMarkdown(text);
}

function renderChatRichText(text) {
  return renderChatMarkdown(text);
}

function clearChatStreamRenderTimer() {
  if (!state.chatStreamRenderTimer) return;
  window.clearTimeout(state.chatStreamRenderTimer);
  state.chatStreamRenderTimer = 0;
}

function scheduleChatStreamRender() {
  if (state.chatStreamRenderTimer) return;
  state.chatStreamRenderTimer = window.setTimeout(() => {
    state.chatStreamRenderTimer = 0;
    renderAll();
  }, 32);
}

function clearChatStreamRevealTimer() {
  if (!state.chatStreamRevealTimer) return;
  window.clearTimeout(state.chatStreamRevealTimer);
  state.chatStreamRevealTimer = 0;
}

function clearChatPendingBadgeTimer() {
  if (!state.chatPendingBadgeTimer) return;
  window.clearTimeout(state.chatPendingBadgeTimer);
  state.chatPendingBadgeTimer = 0;
}

function scheduleChatPendingBadgeTick() {
  const draft = state.chatStreamDraft;
  if (!draft || !draft.waiting || draft.content || !draft.startedAt) return;
  if (state.chatPendingBadgeTimer) return;

  const elapsed = Math.max(0, Date.now() - draft.startedAt);
  const remainder = elapsed % 1000;
  const delay = remainder === 0 ? 1000 : 1000 - remainder;

  state.chatPendingBadgeTimer = window.setTimeout(() => {
    state.chatPendingBadgeTimer = 0;
    if (!state.chatPending || !state.chatStreamDraft?.waiting || state.chatStreamDraft?.content) {
      return;
    }
    renderAll();
    scheduleChatPendingBadgeTick();
  }, delay);
}

function clearChatMessageActionFeedbackTimer() {
  if (!state.chatMessageActionFeedbackTimer) return;
  window.clearTimeout(state.chatMessageActionFeedbackTimer);
  state.chatMessageActionFeedbackTimer = 0;
}

function clearActiveChatRequest() {
  state.chatAbortController = null;
  state.chatStopRequested = false;
}

function isAbortError(error) {
  return Boolean(error) && (error.name === "AbortError" || /aborted|abort/i.test(String(error.message || "")));
}

function stopActiveChatReply() {
  if (state.chatAbortController) {
    try {
      state.chatAbortController.abort();
    } catch {
      // Ignore abort failures.
    }
  }
  clearChatStreamRevealTimer();
  clearChatStreamRenderTimer();
  clearChatPendingBadgeTimer();
  state.chatPending = false;
  state.chatStreamDraft = null;
  clearActiveChatRequest();
}

function createChatStreamDraft(sessionId) {
  return {
    sessionId,
    content: "",
    targetContent: "",
    waiting: true,
    completed: false,
    finalPayload: null,
    status: "streaming",
    startedAt: Date.now(),
  };
}

function ensureChatStreamDraft(sessionId) {
  if (!state.chatStreamDraft || state.chatStreamDraft.sessionId !== sessionId) {
    state.chatStreamDraft = createChatStreamDraft(sessionId);
  }
  return state.chatStreamDraft;
}

function buildChatRequestMessages(messages) {
  const normalized = [];
  for (const item of Array.isArray(messages) ? messages : []) {
    const role = item?.role === "assistant" ? "assistant" : "user";
    const content = normalizeChatMessageContent(item?.content || "");
    if (!content) continue;
    if (normalized.length && normalized[normalized.length - 1].role === role) {
      normalized[normalized.length - 1] = { role, content };
    } else {
      normalized.push({ role, content });
    }
  }
  return normalized.slice(-12);
}

function getLatestCompletedAssistantMessage(sessionMessages = []) {
  for (let index = sessionMessages.length - 1; index >= 0; index -= 1) {
    const message = sessionMessages[index];
    if (message?.role === "assistant") {
      return message;
    }
  }
  return null;
}

function findRetryRequestMessages(session, assistantMessageId) {
  if (!session?.messages?.length || !assistantMessageId) return null;

  const assistantIndex = session.messages.findIndex(
    (message) => message?.role === "assistant" && message.id === assistantMessageId
  );
  if (assistantIndex < 0) return null;

  const latestAssistant = getLatestCompletedAssistantMessage(session.messages);
  if (!latestAssistant || latestAssistant.id !== assistantMessageId) {
    return null;
  }

  const requestMessages = buildChatRequestMessages(session.messages.slice(0, assistantIndex));
  if (!requestMessages.length || requestMessages[requestMessages.length - 1].role !== "user") {
    return null;
  }
  return requestMessages;
}

function setChatMessageActionFeedback(messageId, action, status) {
  clearChatMessageActionFeedbackTimer();
  state.chatMessageActionFeedback = messageId
    ? { messageId, action, status }
    : null;
  if (!messageId) {
    renderAll();
    return;
  }
  state.chatMessageActionFeedbackTimer = window.setTimeout(() => {
    state.chatMessageActionFeedback = null;
    state.chatMessageActionFeedbackTimer = 0;
    renderAll();
  }, 1600);
  renderAll();
}

async function copyTextToClipboard(text) {
  const value = String(text || "");
  if (!value) return false;

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    // Fall through to the textarea fallback.
  }

  const probe = document.createElement("textarea");
  probe.value = value;
  probe.setAttribute("readonly", "readonly");
  probe.style.position = "fixed";
  probe.style.opacity = "0";
  probe.style.pointerEvents = "none";
  document.body.appendChild(probe);
  probe.select();
  probe.setSelectionRange(0, probe.value.length);

  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch {
    copied = false;
  } finally {
    probe.remove();
  }
  return copied;
}

function finalizeChatStreamDraft() {
  const draft = state.chatStreamDraft;
  if (!draft || !draft.completed || draft.content.length < draft.targetContent.length) return;

  const payload = draft.finalPayload || {};
  const finalContent = normalizeChatMessageContent(payload.assistant_message || draft.targetContent || "");
  const handoff = payload.agent_handoff || null;
  const sessionId = draft.sessionId;

  clearChatStreamRevealTimer();
  clearChatStreamRenderTimer();
  clearChatPendingBadgeTimer();
  state.chatPending = false;
  state.chatStreamDraft = null;
  clearActiveChatRequest();

  appendChatMessage(sessionId, {
    role: "assistant",
    content: finalContent || tr("\u6211\u6682\u65f6\u6ca1\u6709\u6536\u5230\u53ef\u7528\u56de\u590d\u3002", "I did not receive a usable reply."),
    status: draft.status === "stopped" ? "stopped" : "complete",
    handoff,
  });
  renderAll();
}

function finalizeStoppedChatDraft() {
  const draft = state.chatStreamDraft;
  if (!draft) return;

  const stoppedContent = normalizeChatMessageContent(
    draft.content || draft.targetContent || tr("已停止，本次回复未完成。", "Stopped before the reply was completed.")
  );
  draft.content = stoppedContent;
  draft.targetContent = stoppedContent;
  draft.waiting = false;
  draft.completed = true;
  draft.status = "stopped";
  finalizeChatStreamDraft();
}

function advanceChatStreamReveal() {
  state.chatStreamRevealTimer = 0;
  const draft = state.chatStreamDraft;
  if (!draft) return;

  if (draft.content.length < draft.targetContent.length) {
    const engine = getChatMarkdownEngine();
    const step =
      engine && typeof engine.advanceRevealContent === "function"
        ? engine.advanceRevealContent(draft.content, draft.targetContent)
        : {
            content: draft.targetContent.slice(0, draft.content.length + 8),
            done: draft.content.length + 8 >= draft.targetContent.length,
          };
    draft.content = step.content;
    scheduleChatStreamRender();
  }

  if (draft.content.length < draft.targetContent.length) {
    ensureChatStreamReveal();
    return;
  }

  if (draft.completed) {
    finalizeChatStreamDraft();
  }
}

function ensureChatStreamReveal() {
  const draft = state.chatStreamDraft;
  if (!draft) return;
  if (draft.content.length >= draft.targetContent.length) {
    if (draft.completed) {
      finalizeChatStreamDraft();
    }
    return;
  }
  if (state.chatStreamRevealTimer) return;
  state.chatStreamRevealTimer = window.setTimeout(() => {
    advanceChatStreamReveal();
  }, 24);
}

function formatChatPendingElapsed(startedAt) {
  if (!startedAt) return "0s";
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
  if (elapsedSeconds < 60) {
    return `${elapsedSeconds}s`;
  }
  const minutes = Math.floor(elapsedSeconds / 60);
  const seconds = String(elapsedSeconds % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function renderAssistantAvatar() {
  return `
    <div class="assistant-avatar" aria-hidden="true">
      <img class="assistant-avatar__image" src="/assets/icons/logo-mark.svg?v=${APP_ASSET_VERSION}" alt="" />
    </div>
  `;
}

function renderAssistantMessageShell(content, options = {}) {
  const timerLabel = normalizeText(options.timerLabel || "");
  return `
    <div class="message message--assistant">
      <div class="assistant-shell${timerLabel ? " assistant-shell--timed" : ""}">
        <div class="assistant-shell__avatar">
          ${renderAssistantAvatar()}
        </div>
        <div class="assistant-shell__body">
          ${
            timerLabel
              ? `
                  <div class="assistant-shell__meta">
                    <span class="assistant-pending-badge" aria-live="polite">
                      <span class="assistant-pending-badge__dot" aria-hidden="true"></span>
                      ${escapeHtml(timerLabel)}
                    </span>
                  </div>
                `
              : ""
          }
          ${content}
        </div>
      </div>
    </div>
  `;
}


function renderNormalAssistantMessage(message, options = {}) {
  const showActions = Boolean(options.showActions);
  const feedback = state.chatMessageActionFeedback;
  const copyLabel =
    feedback?.messageId === message.id && feedback?.action === "copy"
      ? feedback.status === "success"
        ? tr("已复制", "Copied")
        : tr("复制失败", "Copy failed")
      : tr("复制", "Copy");
  const retryLabel = tr("重试", "Retry");
  const handoffButton = message.handoff?.suggested_task
    ? `
        <button class="secondary-button" type="button" data-start-agent-task="${escapeHtml(message.handoff.suggested_task)}">
          ${escapeHtml(tr("\u8f6c\u5230 Agent \u6267\u884c", "Send to Agent"))}
        </button>
    `
    : "";
  const handoffReason = message.handoff?.reason
    ? `<span class="message-meta">${escapeHtml(
        state.locale === "zh-CN" ? "\u9002\u5408\u771f\u5b9e\u6267\u884c\u7684\u684c\u9762\u6216\u6d4f\u89c8\u5668\u52a8\u4f5c\u3002" : message.handoff.reason
      )}</span>`
    : "";
  const stoppedNote =
    message.status === "stopped"
      ? `<p class="assistant-status">${escapeHtml(tr("已停止，回答未完成", "Stopped before completion"))}</p>`
      : "";
  const actions = showActions
    ? `
      <div class="message-actions message-actions--assistant">
        <div class="message-actions__buttons">
          ${handoffButton}
          <button class="secondary-button" type="button" data-copy-chat-message="${escapeHtml(message.id)}">
            ${escapeHtml(copyLabel)}
          </button>
          <button class="secondary-button" type="button" data-retry-chat-message="${escapeHtml(message.id)}">
            ${escapeHtml(retryLabel)}
          </button>
        </div>
        ${handoffReason ? `<div class="message-actions__meta">${handoffReason}</div>` : ""}
      </div>
    `
    : "";

  return renderAssistantMessageShell(`
    <article class="assistant-card assistant-card--chat">
      <div class="assistant-copy assistant-markdown">${renderChatMarkdown(message.content)}</div>
      ${stoppedNote}
      ${actions}
    </article>
  `);
}

function renderNormalAssistantPendingMessage(draft = state.chatStreamDraft) {
  const content = String(draft?.content || "");
  const showCursor = Boolean(draft) && (draft.waiting || draft.content.length < draft.targetContent.length || !draft.completed);
  const timerLabel = draft?.waiting && !content ? formatChatPendingElapsed(draft.startedAt) : "";
  const waitingMarkup = `
    <article class="assistant-card assistant-card--chat assistant-card--pending">
      <div class="assistant-pending-state" role="status" aria-live="polite">
        <p class="assistant-pending-state__title">${escapeHtml(
          tr("正在等待模型开始回复…", "Waiting for the model to start responding...")
        )}</p>
        <p class="assistant-pending-state__hint">${escapeHtml(
          tr("收到首个内容后会直接显示在这里。", "The reply will appear here as soon as the first content arrives.")
        )}</p>
      </div>
    </article>
  `;
  const streamingMarkup = `
    <article class="assistant-card assistant-card--chat assistant-card--pending">
      <div class="assistant-copy assistant-markdown assistant-copy--stream">
        ${renderStreamingChatMarkdown(content, { cursor: showCursor })}
      </div>
    </article>
  `;

  return renderAssistantMessageShell(content ? streamingMarkup : waitingMarkup, { timerLabel });
}

function formatRunDurationWindow(startedAt, finishedAt) {
  const start = Number(startedAt);
  const end = Number.isFinite(Number(finishedAt)) ? Number(finishedAt) : Date.now() / 1000;
  if (!Number.isFinite(start)) return "--";
  const elapsedSeconds = Math.max(0, Math.round(end - start));
  const hours = Math.floor(elapsedSeconds / 3600);
  const minutes = Math.floor((elapsedSeconds % 3600) / 60);
  const seconds = elapsedSeconds % 60;

  if (hours > 0) return state.locale === "zh-CN" ? `${hours}小时 ${minutes}分` : `${hours}h ${minutes}m`;
  if (minutes > 0) return state.locale === "zh-CN" ? `${minutes}分 ${seconds}秒` : `${minutes}m ${seconds}s`;
  return state.locale === "zh-CN" ? `${seconds}秒` : `${seconds}s`;
}

function renderAgentRunSection({
  label = "",
  title = "",
  description = "",
  action = "",
  body = "",
  modifier = "",
} = {}) {
  if (!title && !description && !body) return "";
  const modifierClass = modifier ? ` assistant-run__section--${modifier}` : "";
  return `
    <section class="assistant-run__section${modifierClass}">
      <div class="assistant-run__section-head">
        <div>
          ${label ? `<span class="assistant-run__section-label">${escapeHtml(label)}</span>` : ""}
          ${title ? `<h4>${escapeHtml(title)}</h4>` : ""}
          ${description ? `<p>${escapeHtml(description)}</p>` : ""}
        </div>
        ${action}
      </div>
      ${body}
    </section>
  `;
}

function renderAgentRunHero({ src = "", alt = "", caption = "", supporting = "", runId = "", task = "" } = {}) {
  if (!src) return "";
  const zoomButton = `
    <button class="secondary-button" type="button" data-lightbox-src="${escapeHtml(src)}" data-lightbox-caption="${escapeHtml(
      caption || task || tr("最新截图", "Latest screenshot")
    )}">
      ${escapeHtml(tr("放大", "Zoom"))}
    </button>
  `;
  const detailButton = runId
    ? `
        <button class="secondary-button" type="button" data-open-inspector="${escapeHtml(runId)}">
          ${escapeHtml(tr("详情", "Details"))}
        </button>
      `
    : "";
  return `
    <figure class="assistant-run__hero">
      <div class="assistant-run__hero-media">
        <img src="${escapeHtml(src)}" alt="${escapeHtml(alt || caption || task || tr("运行截图", "Run screenshot"))}" />
      </div>
      <figcaption class="assistant-run__hero-caption">
        <div class="assistant-run__hero-copy">
          <span class="assistant-run__section-label">${escapeHtml(tr("最新画面", "Latest view"))}</span>
          <strong>${escapeHtml(caption || tr("捕获状态", "Captured state"))}</strong>
          ${supporting ? `<p>${escapeHtml(supporting)}</p>` : ""}
        </div>
        <div class="assistant-run__hero-actions">
          ${zoomButton}
          ${detailButton}
        </div>
      </figcaption>
    </figure>
  `;
}

function renderAgentRunActionPreview(actions = []) {
  if (!actions.length) return "";
  return renderAgentRunSection({
    label: tr("轨迹", "Trace"),
    title: tr("最近动作", "Recent actions"),
    description: tr("这里会显示本轮执行里最新的一小段动作轨迹。", "A short preview of the latest executed steps."),
    modifier: "actions",
    body: `<div class="assistant-run__action-row">${actions.map(renderActionPill).join("")}</div>`,
  });
}

function renderAgentRunStepPreview(details, steps = []) {
  if (!steps.length) return "";
  const timelineButton = details?.id
    ? `
        <button class="secondary-button" type="button" data-open-inspector="${escapeHtml(details.id)}">
          ${escapeHtml(tr("时间线", "Timeline"))}
        </button>
      `
    : "";
  return renderAgentRunSection({
    label: tr("流程", "Flow"),
    title: tr("步骤预览", "Step preview"),
    description: tr("保留最近的重要里程碑，剩余内容可在详情里继续查看。", "The freshest milestones from this run."),
    action: timelineButton,
    modifier: "timeline",
    body: `
      <ol class="assistant-run__step-list">
        ${steps
          .map(
            (step, index) => `
              <li class="assistant-run__step-item">
                <span class="assistant-run__step-index">${escapeHtml(String(index + 1))}</span>
                <div class="assistant-run__step-copy">
                  <strong>${escapeHtml(step.plan?.status_summary || step.task || tr("无摘要", "No summary"))}</strong>
                  <span>${escapeHtml(formatShortTime(step.captured_at))}</span>
                </div>
              </li>
            `
          )
          .join("")}
      </ol>
    `,
  });
}

function renderAgentRunFollowUps(items = []) {
  if (!items.length) return "";
  return renderAgentRunSection({
    label: tr("下一步", "Next"),
    title: tr("继续推进", "Continue from here"),
    description: tr("给你一组更顺手的后续操作入口。", "Suggested follow-up prompts to keep momentum."),
    modifier: "followups",
    body: `
      <div class="assistant-run__followups">
        ${items
          .map(
            (item) => `
              <article class="assistant-run__followup-card">
                <span class="assistant-run__followup-label">${escapeHtml(item.title)}</span>
                <p>${escapeHtml(item.description)}</p>
                <button class="secondary-button" type="button" data-prefill-task="${escapeHtml(item.task)}">
                  ${escapeHtml(item.actionLabel)}
                </button>
              </article>
            `
          )
          .join("")}
      </div>
    `,
  });
}

function renderAgentRunDock(buttons = []) {
  const content = buttons.filter(Boolean).join("");
  if (!content) return "";
  return `<div class="assistant-run__dock">${content}</div>`;
}

function renderAgentRunCard({
  eyebrow = "",
  title = "",
  summary = "",
  stateLabel = "",
  stateTone = "",
  metrics = [],
  chips = [],
  hero = "",
  trace = "",
  timeline = "",
  followUps = "",
  dock = "",
  variant = "",
} = {}) {
  const metricsMarkup = metrics.filter(Boolean).join("");
  const chipsMarkup = chips.filter(Boolean).join("");
  const variantClass = variant ? ` assistant-card--run-${variant}` : "";
  return renderAssistantMessageShell(`
    <article class="assistant-card assistant-card--run${variantClass}">
      <div class="assistant-run__header">
        <div class="assistant-run__eyebrow">
          ${eyebrow ? `<span class="assistant-run__eyebrow-label">${escapeHtml(eyebrow)}</span>` : ""}
          ${stateLabel ? `<span class="status-pill ${stateTone}">${escapeHtml(stateLabel)}</span>` : ""}
        </div>
        <div class="assistant-run__headline">
          <h3>${escapeHtml(title || tr("未命名任务", "Untitled task"))}</h3>
          ${summary ? `<p>${escapeHtml(summary)}</p>` : ""}
        </div>
      </div>
      ${metricsMarkup ? `<div class="assistant-run__metrics">${metricsMarkup}</div>` : ""}
      ${chipsMarkup ? `<div class="assistant-run__chips">${chipsMarkup}</div>` : ""}
      ${hero}
      ${trace}
      ${timeline}
      ${followUps}
      ${dock}
    </article>
  `);
}

function renderPendingMessage(task) {
  const statusCard = renderAgentRunSection({
    label: tr("状态", "Status"),
    title: tr("已排队，随时准备开始", "Queued and ready"),
    description: tr("Aoryn 已经收下这个任务，正在等待第一条实时进度。", "Aoryn has accepted this task and is waiting for the first live execution update."),
    modifier: "status",
    body: `
      <div class="assistant-run__callout">
        <span class="assistant-run__live-dot" aria-hidden="true"></span>
        <div>
          <strong>${escapeHtml(tr("任务已进入队列", "Task in queue"))}</strong>
          <p>${escapeHtml(tr("一旦真正开始点击或输入，这里会切换成实时执行卡片。", "The card will switch into live execution as soon as the run starts."))}</p>
        </div>
      </div>
    `,
  });

  return renderAgentRunCard({
    eyebrow: tr("Agent 任务", "Agent task"),
    title: cleanRunTitle(task),
    summary: tr("我们已经准备好上下文，马上就会开始第一步。", "We are staging the run and waiting for the first action."),
    stateLabel: tr("排队中", "Queued"),
    stateTone: "warn",
    metrics: [
      renderMetricCard(tr("模式", "Mode"), tr("桌面 Agent", "Desktop agent")),
      renderMetricCard(tr("下一项", "Next"), tr("第一步动作", "First step")),
    ],
    chips: [`<span class="metric-pill">${escapeHtml(truncate(task, 56))}</span>`],
    timeline: statusCard,
    variant: "queued",
  });
}

function renderLoadingMessage() {
  const loadingSection = renderAgentRunSection({
    label: tr("工作区", "Workspace"),
    title: tr("正在恢复当前线程", "Rebuilding the current thread"),
    description: tr("Aoryn 正在把时间线、截图和继续操作合并回同一个界面。", "Aoryn is restoring the selected run so the latest media, steps, and controls can appear together."),
    modifier: "status",
    body: `
      <div class="assistant-run__callout">
        <span class="assistant-run__live-dot assistant-run__live-dot--soft" aria-hidden="true"></span>
        <div>
          <strong>${escapeHtml(tr("正在准备新界面", "Preparing the premium view"))}</strong>
          <p>${escapeHtml(tr("通常只需要一小会儿。", "This usually only takes a moment."))}</p>
        </div>
      </div>
    `,
  });

  return renderAgentRunCard({
    eyebrow: tr("工作区", "Workspace"),
    title: tr("正在载入运行详情", "Loading run details"),
    summary: tr("我们会把最新时间线、截图和操作入口收拢到一张主卡里。", "Pulling the latest timeline, screenshots, and follow-up actions into one surface."),
    stateLabel: tr("加载中", "Loading"),
    metrics: [renderMetricCard(tr("视图", "View"), tr("统一结果卡", "Unified card"))],
    timeline: loadingSection,
    variant: "loading",
  });
}

function renderRunningMessage(active) {
  const progress = active.result || {};
  const previewUrl =
    progress.run_id && progress.latest_screenshot
      ? buildArtifactUrl(progress.run_id, progress.latest_screenshot)
      : null;
  const latestSummary = normalizeText(progress.latest_summary) || tr("等待下一步。", "Waiting for the next step.");
  const latestActions = (progress.latest_actions || []).slice(0, 4);
  const jobState = active.cancel_requested
    ? { label: tr("停止中", "Stopping"), tone: "warn" }
    : { label: tr("执行中", "Running"), tone: "ok" };

  const liveStateSection = renderAgentRunSection({
    label: tr("实时", "Live"),
    title: tr("任务仍在推进", "Run is actively progressing"),
    description: tr("卡片会持续刷新最新截图和最近动作，让状态更集中。", "The card refreshes with the latest captured view and recent execution trace."),
    modifier: "status",
    body: `
      <div class="assistant-run__callout">
        <span class="assistant-run__live-dot" aria-hidden="true"></span>
        <div>
          <strong>${escapeHtml(tr("正在实时执行", "Streaming execution"))}</strong>
          <p>${escapeHtml(tr("Aoryn 仍在替你点击、输入并观察桌面。", "Aoryn is still clicking, typing, and observing the desktop for you."))}</p>
        </div>
      </div>
    `,
  });

  return renderAgentRunCard({
    eyebrow: tr("Agent 运行", "Agent run"),
    title: cleanRunTitle(active.task || latestSummary),
    summary: latestSummary,
    stateLabel: jobState.label,
    stateTone: jobState.tone,
    metrics: [
      renderMetricCard(tr("开始", "Started"), formatShortTime(active.started_at || progress.started_at)),
      renderMetricCard(tr("时长", "Duration"), formatRunDurationWindow(active.started_at || progress.started_at)),
      renderMetricCard(tr("步骤", "Steps"), String(progress.steps ?? 0)),
    ],
    chips: [
      renderExecutionModeChip(progress.dry_run ?? active.dry_run),
      renderHumanVerificationChip(progress),
    ],
    hero: renderAgentRunHero({
      src: previewUrl,
      alt: tr("最新截图", "Latest screenshot"),
      caption: latestSummary,
      supporting: tr("这是当前运行捕获到的最新画面。", "Latest captured frame from the active run."),
      runId: progress.run_id,
      task: active.task || "",
    }),
    trace: renderAgentRunActionPreview(latestActions),
    timeline: liveStateSection,
    dock: renderAgentRunDock([
      progress.run_id
        ? `<button class="secondary-button" type="button" data-open-inspector="${escapeHtml(progress.run_id)}">${escapeHtml(
            tr("详情", "Details")
          )}</button>`
        : "",
      `<button class="primary-button" type="button" data-stop-active-task="true">${escapeHtml(
        active.cancel_requested ? tr("停止中", "Stopping") : tr("停止", "Stop")
      )}</button>`,
    ]),
    variant: active.cancel_requested ? "stopping" : "live",
  });
}

function renderCompletedConversation(details) {
  const screenshots = collectRunScreenshots(details);
  const steps = (details.timeline || []).slice(-4).reverse();
  const followUps = buildFollowUpSuggestions(details);
  const heroShot = screenshots[0] || null;
  const actions = collectLatestActions(details).slice(0, 4);
  const stateInfo = buildRecordState(details);

  return [
    renderAgentRunCard({
      eyebrow: tr("运行结果", "Run result"),
      title: cleanRunTitle(details.task),
      summary: runSummary(details),
      stateLabel: stateInfo.label,
      stateTone: stateInfo.tone,
      metrics: [
        renderMetricCard(tr("开始", "Started"), formatShortTime(details.started_at)),
        renderMetricCard(tr("结束", "Finished"), formatShortTime(details.finished_at)),
        renderMetricCard(tr("时长", "Duration"), formatRunDurationWindow(details.started_at, details.finished_at)),
        renderMetricCard(tr("步骤", "Steps"), String(details.steps ?? 0)),
      ],
      chips: [renderExecutionModeChip(details.dry_run), renderHumanVerificationChip(details)],
      hero: heroShot
        ? renderAgentRunHero({
            src: heroShot.src,
            alt: heroShot.alt,
            caption: heroShot.summary || heroShot.caption,
            supporting: tr("这是这次任务里最近一次抓到的画面。", "Most recent screenshot captured during this run."),
            runId: details.id,
            task: details.task || "",
          })
        : "",
      trace: renderAgentRunActionPreview(actions),
      timeline: renderAgentRunStepPreview(details, steps),
      followUps: renderAgentRunFollowUps(followUps),
      dock: renderAgentRunDock([
        `<button class="secondary-button" type="button" data-open-inspector="${escapeHtml(details.id)}">${escapeHtml(
          tr("详情", "Details")
        )}</button>`,
        `<button class="secondary-button" type="button" data-prefill-task="${escapeHtml(details.task || "")}">${escapeHtml(
          tr("继续", "Continue")
        )}</button>`,
      ]),
      variant: "complete",
    }),
  ];
}

function renderUserMessage(task) {
  return `
    <div class="message message--user">
      <article class="message-bubble message-bubble--user">
        <span class="message-bubble__label">${escapeHtml(tr("任务", "Task"))}</span>
        <p>${escapeHtml(cleanRunTitle(task))}</p>
      </article>
    </div>
  `;
}

function renderPanelEmptyState({
  eyebrow = "",
  title = "",
  description = "",
  tone = "",
} = {}) {
  const toneClass = tone ? ` panel-empty-state--${tone}` : "";
  return `
    <article class="panel-empty-state${toneClass}">
      ${eyebrow ? `<span class="panel-empty-state__eyebrow">${escapeHtml(eyebrow)}</span>` : ""}
      ${title ? `<h3>${escapeHtml(title)}</h3>` : ""}
      ${description ? `<p>${escapeHtml(description)}</p>` : ""}
    </article>
  `;
}

function renderSectionLead({
  eyebrow = "",
  title = "",
  description = "",
  badge = "",
} = {}) {
  return `
    <div class="section-lead">
      <div class="section-lead__copy">
        ${eyebrow ? `<span class="section-lead__eyebrow">${escapeHtml(eyebrow)}</span>` : ""}
        ${title ? `<h3>${escapeHtml(title)}</h3>` : ""}
        ${description ? `<p>${escapeHtml(description)}</p>` : ""}
      </div>
      ${badge}
    </div>
  `;
}

function renderDeveloper() {
  updateDomStatus();
  elements.openInspectorButton.disabled = !Boolean(state.selectedRunDetails || state.activeJob?.result?.run_id);
  elements.providerStatusNote.textContent = state.providerStatusMessage || t("developer.providerStatus");
  renderDisplayDetectionDeveloperPanel();

  if (!state.jobs.length) {
    elements.jobList.innerHTML = renderPanelEmptyState({
      eyebrow: tr("Queue", "Queue"),
      title: tr("暂无任务", "No recent jobs"),
      description: tr("新的任务提交后，这里会显示最近的执行队列。", "Recent queued and finished jobs will appear here."),
    });
  } else {
    elements.jobList.innerHTML = state.jobs.map(renderJobCard).join("");
  }

  elements.activePayloadView.textContent = JSON.stringify(state.activeJob?.result || state.activeJob || {}, null, 2);

  if (state.selectedRunDetails?.timeline?.length) {
    elements.developerTimeline.innerHTML = state.selectedRunDetails.timeline
      .slice()
      .reverse()
      .slice(0, 6)
      .map(renderDeveloperTimelineItem)
      .join("");
  } else if (state.activeJob) {
    elements.developerTimeline.innerHTML = renderLiveDeveloperTimeline();
  } else {
    elements.developerTimeline.innerHTML = renderPanelEmptyState({
      eyebrow: tr("Timeline", "Timeline"),
      title: tr("选择一条记录", "Select a run"),
      description: tr("打开一条历史运行后，这里会显示最近的时间线和关键画面。", "Open a run to review its recent steps and captured screens."),
    });
  }
}

function renderJobCard(job) {
  const startedAt = formatShortTime(job.started_at || job.created_at);
  const finishedAt = Number.isFinite(Number(job.finished_at)) ? formatShortTime(job.finished_at) : "";
  const timelineMeta = [startedAt !== "--" ? startedAt : "", finishedAt ? `→ ${finishedAt}` : ""].filter(Boolean).join(" ");

  return `
    <article class="job-card">
      <div class="job-card__head">
        <div>
          <p>${escapeHtml(job.id)}</p>
          <h3>${escapeHtml(cleanRunTitle(job.task))}</h3>
        </div>
        <span class="status-pill ${statusTone(job.status)}">${escapeHtml(translateJobStatus(job.status))}</span>
      </div>
      <div class="job-card__meta">
        <span>${escapeHtml(timelineMeta || tr("等待时间轴", "Waiting for timeline"))}</span>
      </div>
    </article>
  `;
}

function renderDeveloperTimelineItem(step) {
  const screenshotUrl =
    state.selectedRunDetails?.id && step.screenshot
      ? buildArtifactUrl(state.selectedRunDetails.id, step.screenshot)
      : null;
  const actions = (step.executed_actions || []).slice(0, 4);

  return `
    <article class="timeline-item timeline-item--developer">
      <div class="timeline-item__head">
        <div>
          <p>${escapeHtml(tr("步骤", "Step"))} ${escapeHtml(String(step.step))}</p>
          <h3>${escapeHtml(step.plan?.status_summary || step.task || tr("无摘要", "No summary"))}</h3>
        </div>
        <span class="status-pill ${step.error ? "bad" : "ok"}">${escapeHtml(step.error ? tr("错误", "Error") : tr("完成", "OK"))}</span>
      </div>
      ${actions.length ? `<div class="action-row">${actions.map(renderActionPill).join("")}</div>` : ""}
      ${screenshotUrl ? `<img class="timeline-shot" src="${escapeHtml(screenshotUrl)}" alt="${escapeHtml(tr("步骤截图", "Step screenshot"))}" />` : ""}
      <div class="timeline-item__meta">${escapeHtml(formatShortTime(step.captured_at))}</div>
    </article>
  `;
}

function renderLiveDeveloperTimeline() {
  const progress = state.activeJob?.result || {};
  const previewUrl =
    progress.run_id && progress.latest_screenshot
      ? buildArtifactUrl(progress.run_id, progress.latest_screenshot)
      : null;
  const actions = (progress.latest_actions || []).slice(0, 4);

  return `
    <article class="timeline-item timeline-item--developer timeline-item--live">
      <div class="timeline-item__head">
        <div>
          <p>${escapeHtml(tr("实时", "Live"))}</p>
          <h3>${escapeHtml(normalizeText(progress.latest_summary) || tr("等待进度", "Waiting for progress"))}</h3>
        </div>
        <span class="status-pill ok">${escapeHtml(tr("执行中", "Running"))}</span>
      </div>
      ${actions.length ? `<div class="action-row">${actions.map(renderActionPill).join("")}</div>` : ""}
      ${previewUrl ? `<img class="timeline-shot" src="${escapeHtml(previewUrl)}" alt="${escapeHtml(tr("最新截图", "Latest screenshot"))}" />` : ""}
      <div class="timeline-item__meta">${escapeHtml(tr("实时执行中", "Live run in progress"))}</div>
    </article>
  `;
}

function renderInspector() {
  const details = state.selectedRunDetails;
  elements.inspectorSubtitle.textContent = details ? cleanRunTitle(details.task) : t("inspector.empty");

  elements.detailTabs?.querySelectorAll("[data-detail-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.detailView === state.detailView);
  });

  if (!details) {
    elements.runDetail.innerHTML = renderPanelEmptyState({
      eyebrow: tr("Inspector", "Inspector"),
      title: tr("选择一条记录", "Select a run"),
      description: t("inspector.empty"),
    });
    return;
  }

  if (state.detailView === "timeline") {
    elements.runDetail.innerHTML = renderRunTimeline(details);
    return;
  }

  if (state.detailView === "gallery") {
    elements.runDetail.innerHTML = renderRunGallery(details);
    return;
  }

  elements.runDetail.innerHTML = renderRunOverview(details);
}

function renderRunOverview(details) {
  const stateInfo = buildRecordState(details);
  const screenshots = collectRunScreenshots(details);
  const latestActions = collectLatestActions(details).slice(0, 4);
  const latestShot = screenshots[0] || null;

  return `
    <div class="inspector-overview">
      <article class="inspector-section-card inspector-section-card--summary">
        ${renderSectionLead({
          eyebrow: tr("Run overview", "Run overview"),
          title: cleanRunTitle(details.task),
          description: runSummary(details),
          badge: `<span class="status-pill ${stateInfo.tone}">${escapeHtml(stateInfo.label)}</span>`,
        })}
        <div class="summary-grid">
          ${renderDetailMetricCard(tr("开始", "Start"), formatShortTime(details.started_at))}
          ${renderDetailMetricCard(tr("结束", "End"), formatShortTime(details.finished_at))}
          ${renderDetailMetricCard(tr("时长", "Duration"), formatRunDurationWindow(details.started_at, details.finished_at))}
          ${renderDetailMetricCard(tr("步骤", "Steps"), String(details.steps ?? 0))}
        </div>
        <div class="inspector-section-card__chips">
          ${renderExecutionModeChip(details.dry_run)}
          ${renderHumanVerificationChip(details)}
        </div>
      </article>

      ${
        latestShot
          ? `
            <article class="inspector-section-card inspector-section-card--media">
              ${renderAgentRunHero({
                src: latestShot.src,
                alt: latestShot.alt,
                caption: latestShot.summary || latestShot.caption,
                supporting: tr("这是这次运行最近一次捕获到的画面。", "Most recent captured view from this run."),
                runId: details.id,
                task: details.task || "",
              })}
            </article>
          `
          : ""
      }

      ${
        latestActions.length
          ? `
            <article class="inspector-section-card inspector-section-card--actions">
              ${renderSectionLead({
                eyebrow: tr("Trace", "Trace"),
                title: tr("最近动作", "Recent actions"),
                description: tr("详情页里先给你一小段动作轨迹。", "A quick glance at the latest executed actions."),
              })}
              <div class="action-row">${latestActions.map(renderActionPill).join("")}</div>
            </article>
          `
          : ""
      }
    </div>
  `;
}

function renderRunTimeline(details) {
  if (!(details.timeline || []).length) {
    return renderPanelEmptyState({
      eyebrow: tr("Timeline", "Timeline"),
      title: tr("暂无时间线", "No timeline yet"),
      description: tr("这次运行在这里还没有可展示的步骤。", "There are no timeline steps to display yet."),
    });
  }

  return `
    <div class="inspector-timeline-list">
      ${(details.timeline || [])
        .map((step) => {
          const screenshotUrl = details.id && step.screenshot ? buildArtifactUrl(details.id, step.screenshot) : null;
          const stepActions = (step.executed_actions || []).slice(0, 4);
          return `
            <article class="timeline-item timeline-item--inspector">
              <div class="timeline-item__head">
                <div>
                  <p>${escapeHtml(tr("步骤", "Step"))} ${escapeHtml(String(step.step))}</p>
                  <h3>${escapeHtml(step.plan?.status_summary || step.task || tr("无摘要", "No summary"))}</h3>
                </div>
                <span class="status-pill ${step.error ? "bad" : "ok"}">${escapeHtml(step.error ? tr("错误", "Error") : tr("完成", "OK"))}</span>
              </div>
              ${stepActions.length ? `<div class="action-row">${stepActions.map(renderActionPill).join("")}</div>` : ""}
              ${
                screenshotUrl
                  ? `
                    <div class="timeline-item__media">
                      <img class="timeline-shot" src="${escapeHtml(screenshotUrl)}" alt="${escapeHtml(tr("步骤截图", "Step screenshot"))}" />
                      <div class="message-actions">
                        <button class="secondary-button" type="button" data-lightbox-src="${escapeHtml(screenshotUrl)}" data-lightbox-caption="${escapeHtml(step.plan?.status_summary || step.task || "")}">
                          ${escapeHtml(tr("放大", "Zoom"))}
                        </button>
                      </div>
                    </div>
                  `
                  : ""
              }
              <div class="timeline-item__meta">${escapeHtml(formatShortTime(step.captured_at))}</div>
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderRunGallery(details) {
  const screenshots = collectRunScreenshots(details);
  if (!screenshots.length) {
    return renderPanelEmptyState({
      eyebrow: tr("Gallery", "Gallery"),
      title: tr("暂无截图", "No screenshots"),
      description: tr("这次运行还没有可以查看的截图。", "This run has no screenshots to review yet."),
    });
  }

  return `
    <div class="inspector-gallery-grid">
      ${screenshots
        .map(
          (shot) => `
            <figure class="inspector-gallery-card">
              <div class="inspector-gallery-card__media">
                <img src="${escapeHtml(shot.src)}" alt="${escapeHtml(shot.alt)}" />
              </div>
              <figcaption class="inspector-gallery-card__caption">
                <div>
                  <strong>${escapeHtml(shot.caption)}</strong>
                  <p>${escapeHtml(shot.alt)}</p>
                </div>
                <button class="secondary-button" type="button" data-lightbox-src="${escapeHtml(shot.src)}" data-lightbox-caption="${escapeHtml(shot.caption)}">
                  ${escapeHtml(tr("放大", "Zoom"))}
                </button>
              </figcaption>
            </figure>
          `
        )
        .join("")}
    </div>
  `;
}

function renderHelpCenter() {
  if (elements.helpCenterTitle) {
    elements.helpCenterTitle.textContent = state.helpTitle || tr("开发者文档", "Developer Docs");
  }
  if (!elements.helpContent) return;

  if (state.helpLoading) {
    elements.helpContent.innerHTML = renderPanelEmptyState({
      eyebrow: tr("Docs", "Docs"),
      title: tr("正在加载开发者文档...", "Loading developer docs..."),
      description: tr("文档内容到达后会直接显示在这里。", "The documentation will appear here as soon as it is ready."),
    });
    return;
  }

  if (state.helpError) {
    elements.helpContent.innerHTML = renderPanelEmptyState({
      eyebrow: tr("Docs", "Docs"),
      title: tr("无法加载文档", "Could not load documentation"),
      description: state.helpError,
      tone: "error",
    });
    return;
  }

  if (!state.helpContent) {
    elements.helpContent.innerHTML = renderPanelEmptyState({
      eyebrow: tr("Docs", "Docs"),
      title: tr("暂无文档内容", "No documentation available"),
      description: tr("这里暂时还没有可用的开发者文档。", "There is no developer documentation available yet."),
    });
    return;
  }

  elements.helpContent.innerHTML = `<div class="help-doc-shell">${renderSimpleMarkdown(state.helpContent)}</div>`;
}

function renderAboutPanel() {
  if (!elements.aboutContent) return;
  const isEnglish = state.locale === "en-US";
  const diagnostics = state.meta?.diagnostics || {};
  const recentRuns = (state.runs || []).slice(0, 6);
  const appTitle = state.meta?.title || "Aoryn";
  const version = state.meta?.version || APP_VERSION;
  const runtimeMode =
    state.meta?.runtime_mode === "packaged"
      ? (isEnglish ? "Installed app" : "已安装应用")
      : (isEnglish ? "Source runtime" : "源码运行");

  if (elements.aboutTitle) {
    elements.aboutTitle.textContent = isEnglish ? "About Aoryn" : "关于 Aoryn";
  }
  if (elements.aboutSubtitle) {
    elements.aboutSubtitle.textContent = isEnglish ? "Version, diagnostics, and logs" : "版本、诊断与日志";
  }

  const pathRows = [
    { key: "install_dir", label: isEnglish ? "Install folder" : "安装目录", value: diagnostics.install_dir || "-" },
    { key: "config_dir", label: isEnglish ? "Config folder" : "配置目录", value: diagnostics.config_dir || "-" },
    { key: "data_dir", label: isEnglish ? "Data folder" : "数据目录", value: diagnostics.data_dir || "-" },
    { key: "run_root", label: isEnglish ? "Run history" : "运行记录目录", value: diagnostics.run_root || "-" },
    { key: "cache_dir", label: isEnglish ? "Cache folder" : "缓存目录", value: diagnostics.cache_dir || "-" },
  ];

  elements.aboutContent.innerHTML = `
    <div class="about-grid">
      <section class="about-card about-card--hero">
        <div class="about-card__header">
          <p class="about-card__eyebrow">${escapeHtml(isEnglish ? "About" : "关于")}</p>
          <h3>${escapeHtml(appTitle)}</h3>
        </div>
        <div class="about-metrics">
          <article class="about-metric"><span>${escapeHtml(isEnglish ? "Version" : "版本")}</span><strong>v${escapeHtml(version)}</strong></article>
          <article class="about-metric"><span>${escapeHtml(isEnglish ? "Runtime" : "运行方式")}</span><strong>${escapeHtml(runtimeMode)}</strong></article>
        </div>
        <p class="about-card__copy">${escapeHtml(isEnglish ? "Share Setup.exe with end users. Use Review.zip when you want to send the build, release manifest, checksums, and a source snapshot for review." : "给最终用户分发时请使用 Setup.exe；如果要给模型或同事做审核，请使用 Review.zip，其中会包含安装包、发布清单、校验值和源码快照。")}</p>
        <div class="about-card__actions button-row">
          <button class="secondary-button" type="button" data-copy-diagnostics="true">${escapeHtml(isEnglish ? "Copy diagnostics" : "复制诊断信息")}</button>
        </div>
      </section>

      <section class="about-card">
        <div class="about-card__header">
          <p class="about-card__eyebrow">${escapeHtml(isEnglish ? "Paths" : "路径")}</p>
          <h3>${escapeHtml(isEnglish ? "Install & data layout" : "安装与数据布局")}</h3>
        </div>
        <p class="about-card__copy">${escapeHtml(isEnglish ? "The install folder can be customized, but Aoryn always keeps config in %APPDATA%\\\\Aoryn and logs, cache, screenshots, and run history in %LOCALAPPDATA%\\\\Aoryn. Uninstall will ask whether you also want to remove that user data." : "安装目录可以自定义，但 Aoryn 会始终把配置保存在 %APPDATA%\\\\Aoryn，把日志、缓存、截图和运行记录保存在 %LOCALAPPDATA%\\\\Aoryn。卸载时会询问你是否同时删除这些用户数据。")}</p>
        <div class="about-paths">
          ${pathRows
            .map(
              (item) => `
                <div class="about-path-row">
                  <div class="about-path-row__copy">
                    <strong>${escapeHtml(item.label)}</strong>
                    <small>${escapeHtml(item.value)}</small>
                  </div>
                  <button class="secondary-button" type="button" data-open-path-key="${escapeHtml(item.key)}">${escapeHtml(isEnglish ? "Open" : "打开")}</button>
                </div>
              `
            )
            .join("")}
        </div>
      </section>

      <section class="about-card about-card--wide">
        <div class="about-card__header">
          <p class="about-card__eyebrow">${escapeHtml(isEnglish ? "Logs & run history" : "日志与运行记录")}</p>
          <h3>${escapeHtml(isEnglish ? "Recent runs" : "最近运行")}</h3>
        </div>
        ${
          recentRuns.length
            ? `<div class="about-run-list">
                ${recentRuns
                  .map(
                    (run) => `
                      <div class="about-run-row">
                        <div class="about-run-row__copy">
                          <strong>${escapeHtml(cleanRunTitle(run.task || run.id))}</strong>
                          <small>${escapeHtml(formatTimestamp(run.started_at || run.created_at))} · ${escapeHtml(renderRunState(run))}</small>
                        </div>
                        <button class="secondary-button" type="button" data-open-run-id="${escapeHtml(run.id)}">${escapeHtml(isEnglish ? "View" : "查看")}</button>
                      </div>
                    `
                  )
                  .join("")}
              </div>`
            : renderPanelEmptyState({
                eyebrow: isEnglish ? "Runs" : "运行",
                title: isEnglish ? "No runs yet." : "还没有运行记录。",
                description: isEnglish ? "Run history and diagnostics shortcuts will appear here after the first task." : "执行第一条任务后，这里会显示最近运行和诊断入口。",
              })
        }
      </section>
    </div>
  `;
}

function renderComposerState(context) {
  const configReady = isConfigHydrated();
  if (state.uiMode === "chat") {
    const chatStopLabel = state.chatStopRequested ? tr("停止中", "Stopping") : t("chat.stop");
    elements.taskInput.disabled = Boolean(state.chatPending);
    elements.submitButton.disabled = Boolean(state.chatPending) || !configReady;
    elements.submitButton.hidden = Boolean(state.chatPending);
    elements.stopButton.hidden = !state.chatPending;
    elements.stopButton.disabled = !state.chatPending || Boolean(state.chatStopRequested);
    elements.stopButton.setAttribute("aria-label", chatStopLabel);
    elements.stopButton.setAttribute("title", chatStopLabel);
    elements.submitHint.textContent = configReady ? "" : getConfigLoadingMessage();
    return;
  }

  const isRunning = Boolean(state.activeJob);
  elements.taskInput.disabled = isRunning;
  elements.submitButton.disabled = isRunning || !configReady;
  elements.submitButton.hidden = isRunning;
  elements.stopButton.disabled = !isRunning || Boolean(state.activeJob?.cancel_requested);
  elements.stopButton.hidden = !isRunning;
  const stopLabel = state.activeJob?.cancel_requested ? tr("\u505c\u6b62\u4e2d", "Stopping") : t("chat.stop");
  elements.stopButton.setAttribute("aria-label", stopLabel);
  elements.stopButton.setAttribute("title", stopLabel);

  if (isRunning) {
    elements.submitHint.textContent = state.activeJob.cancel_requested ? tr("\u6b63\u5728\u505c\u6b62", "Stopping") : tr("\u6b63\u5728\u6267\u884c", "Running");
    return;
  }

  if (state.pendingTask) {
    elements.submitHint.textContent = tr("\u4efb\u52a1\u5df2\u53d1\u9001", "Queued");
    return;
  }

  if (!configReady) {
    elements.submitHint.textContent = getConfigLoadingMessage();
    return;
  }

  if (context.type === "run") {
    elements.submitHint.textContent = tr("\u7ee7\u7eed\u8865\u5145\u8981\u6c42", "Add a follow-up");
    return;
  }

  elements.submitHint.textContent = "";
}

async function handleCopyChatMessage(messageId) {
  const session = getSelectedChatSession();
  const message = session?.messages?.find((item) => item.id === messageId && item.role === "assistant");
  if (!message) return;
  const copied = await copyTextToClipboard(message.content);
  setChatMessageActionFeedback(message.id, "copy", copied ? "success" : "error");
}

async function handleRetryChatMessage(messageId) {
  if (state.chatPending) return;
  const session = getSelectedChatSession();
  const requestMessages = findRetryRequestMessages(session, messageId);
  if (!session || !requestMessages) {
    elements.submitHint.textContent = tr("只能重试最新一条回答。", "Only the latest answer can be retried.");
    renderAll();
    return;
  }
  await requestChatReply({
    sessionId: session.id,
    requestMessages,
  });
}

function getLatestCompletedAssistantMessage(sessionMessages = []) {
  for (let index = sessionMessages.length - 1; index >= 0; index -= 1) {
    const message = sessionMessages[index];
    if (
      message?.role === "assistant" &&
      message?.status !== "stopped" &&
      !normalizeText(message?.error_code || "")
    ) {
      return message;
    }
  }
  return null;
}

function buildChatAssistantErrorMessage(payload) {
  const errorPayload = payload && typeof payload === "object" ? payload : {};
  return {
    role: "assistant",
    content:
      normalizeChatMessageContent(errorPayload.error || "") ||
      tr(
        "\u666e\u901a\u5bf9\u8bdd\u8bf7\u6c42\u88ab\u6a21\u578b\u62d2\u7edd\u6216\u6267\u884c\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u6a21\u578b\u914d\u7f6e\u548c provider \u8fd4\u56de\u3002",
        "The chat request was rejected or failed. Check the model and provider response."
      ),
    error_code: normalizeText(errorPayload.error_code || ""),
    recovery_action: normalizeText(errorPayload.recovery_action || ""),
    recovery_label: normalizeText(errorPayload.recovery_label || ""),
    retry_context: normalizeChatRetryContext(errorPayload.retry_context),
  };
}


function renderNormalAssistantMessage(message, options = {}) {
  const showActions = Boolean(options.showActions);
  const showRecovery =
    message?.recovery_action === "switch_text_model_retry" && Boolean(message?.retry_context);
  const feedback = state.chatMessageActionFeedback;
  const copyLabel =
    feedback?.messageId === message.id && feedback?.action === "copy"
      ? feedback.status === "success"
        ? tr("\u5df2\u590d\u5236", "Copied")
        : tr("\u590d\u5236\u5931\u8d25", "Copy failed")
      : tr("\u590d\u5236", "Copy");
  const retryLabel = tr("\u91cd\u8bd5", "Retry");
  const recoverLabel =
    normalizeText(message?.recovery_label || "") ||
    tr("\u5207\u6362\u5230\u6587\u672c\u6a21\u578b\u91cd\u8bd5", "Retry with a text model");
  const handoffButton =
    showActions && message?.handoff?.suggested_task
      ? `
          <button class="secondary-button" type="button" data-start-agent-task="${escapeHtml(message.handoff.suggested_task)}">
            ${escapeHtml(tr("\u8f6c\u5230 Agent \u6267\u884c", "Send to Agent"))}
          </button>
        `
      : "";
  const handoffReason =
    showActions && message?.handoff?.reason
      ? `<span class="message-meta">${escapeHtml(
          state.locale === "zh-CN"
            ? "\u9002\u5408\u771f\u5b9e\u6267\u884c\u7684\u684c\u9762\u6216\u6d4f\u89c8\u5668\u52a8\u4f5c\u3002"
            : message.handoff.reason
        )}</span>`
      : "";
  const stoppedNote =
    message.status === "stopped"
      ? `<p class="assistant-status">${escapeHtml(
          tr("\u5df2\u505c\u6b62\uff0c\u56de\u7b54\u672a\u5b8c\u6210", "Stopped before completion")
        )}</p>`
      : "";
  const actionButtons = [
    handoffButton,
    showActions
      ? `
          <button class="secondary-button" type="button" data-copy-chat-message="${escapeHtml(message.id)}">
            ${escapeHtml(copyLabel)}
          </button>
        `
      : "",
    showActions
      ? `
          <button class="secondary-button" type="button" data-retry-chat-message="${escapeHtml(message.id)}">
            ${escapeHtml(retryLabel)}
          </button>
        `
      : "",
    showRecovery
      ? `
          <button class="secondary-button" type="button" data-recover-chat-message="${escapeHtml(message.id)}">
            ${escapeHtml(recoverLabel)}
          </button>
        `
      : "",
  ]
    .filter(Boolean)
    .join("");
  const actions =
    actionButtons || handoffReason
      ? `
          <div class="message-actions message-actions--assistant">
            ${actionButtons ? `<div class="message-actions__buttons">${actionButtons}</div>` : ""}
            ${handoffReason ? `<div class="message-actions__meta">${handoffReason}</div>` : ""}
          </div>
        `
      : "";

  return renderAssistantMessageShell(`
    <article class="assistant-card assistant-card--chat">
      <div class="assistant-copy assistant-markdown">${renderChatMarkdown(message.content)}</div>
      ${stoppedNote}
      ${actions}
    </article>
  `);
}

async function streamChatReply(body, handlers = {}, options = {}) {
  const fallbackMessage = tr(
    "\u666e\u901a\u5bf9\u8bdd\u8bf7\u6c42\u88ab\u6a21\u578b\u62d2\u7edd\u6216\u6267\u884c\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u6a21\u578b\u914d\u7f6e\u548c provider \u8fd4\u56de\u3002",
    "The chat request was rejected or failed. Check the model and provider response."
  );
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: options.signal,
  });

  const contentType = response.headers.get("content-type") || "";
  if (!response.ok && !contentType.includes("text/event-stream")) {
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    const error = new Error(payload?.error || fallbackMessage);
    error.payload = payload || { error: error.message };
    throw error;
  }

  if (!response.body) {
    const fallback = await postJson("/api/chat", body);
    if (!fallback.ok) {
      const payload = fallback.payload && typeof fallback.payload === "object" ? fallback.payload : { error: fallbackMessage };
      const error = new Error(payload?.error || fallbackMessage);
      error.payload = payload;
      throw error;
    }
    handlers.onStart?.({ session_meta: body.session_meta || null });
    if (fallback.payload?.assistant_message) {
      handlers.onDelta?.({ content_delta: fallback.payload.assistant_message });
    }
    handlers.onDone?.({
      assistant_message: fallback.payload?.assistant_message || "",
      agent_handoff: fallback.payload?.agent_handoff || null,
      session_meta: fallback.payload?.session_meta || body.session_meta || null,
    });
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let streamClosed = false;

  const processEventBlock = (block) => {
    const lines = block
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    if (!lines.length) return;

    let eventName = "message";
    const dataLines = [];
    for (const line of lines) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trim());
      }
    }

    let payload = {};
    const raw = dataLines.join("\n");
    if (raw) {
      try {
        payload = JSON.parse(raw);
      } catch {
        payload = {};
      }
    }

    if (eventName === "start") {
      handlers.onStart?.(payload);
      return;
    }
    if (eventName === "delta") {
      handlers.onDelta?.(payload);
      return;
    }
    if (eventName === "done") {
      handlers.onDone?.(payload);
      streamClosed = true;
      return;
    }
    if (eventName === "error") {
      handlers.onError?.(payload);
      streamClosed = true;
    }
  };

  const flushBuffer = (finalChunk = false) => {
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      processEventBlock(block);
      boundary = buffer.indexOf("\n\n");
    }
    if (finalChunk && buffer.trim()) {
      processEventBlock(buffer);
      buffer = "";
    }
  };

  while (!streamClosed) {
    const { done, value } = await reader.read();
    if (done) {
      buffer += decoder.decode();
      flushBuffer(true);
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    flushBuffer(false);
  }
}

async function requestChatReply({ sessionId, requestMessages, recoveryContext = null }) {
  state.chatPending = true;
  state.chatStopRequested = false;
  clearChatStreamRenderTimer();
  clearChatStreamRevealTimer();
  clearChatPendingBadgeTimer();
  state.chatStreamDraft = createChatStreamDraft(sessionId);
  state.chatAbortController = new AbortController();
  setChatMessageActionFeedback(null);
  scheduleChatPendingBadgeTick();
  renderAll();

  const requestBody = {
    messages: requestMessages,
    config_overrides: buildConfigOverrides(),
    session_meta: { session_id: sessionId, locale: state.locale },
  };
  const normalizedRecoveryContext = normalizeChatRetryContext(recoveryContext);
  if (normalizedRecoveryContext) {
    requestBody.recovery_context = normalizedRecoveryContext;
  }

  try {
    await streamChatReply(
      requestBody,
      {
        onStart: () => {
          state.chatStreamDraft = createChatStreamDraft(sessionId);
          scheduleChatPendingBadgeTick();
          renderAll();
        },
        onDelta: (payload) => {
          const delta = String(payload?.content_delta || "");
          if (!delta) return;
          const draft = ensureChatStreamDraft(sessionId);
          draft.waiting = false;
          clearChatPendingBadgeTimer();
          draft.content += delta;
          draft.targetContent = draft.content;
          scheduleChatStreamRender();
        },
        onDone: (payload) => {
          const draft = ensureChatStreamDraft(sessionId);
          const finalContent = normalizeChatMessageContent(
            payload?.assistant_message || draft.content || draft.targetContent || ""
          );
          draft.waiting = false;
          clearChatPendingBadgeTimer();
          draft.completed = true;
          draft.status = "complete";
          draft.finalPayload = payload || {};
          draft.content = finalContent || draft.content || draft.targetContent;
          draft.targetContent = draft.content;
          if (!draft.targetContent) {
            clearChatStreamRenderTimer();
            clearChatStreamRevealTimer();
            clearChatPendingBadgeTimer();
            state.chatPending = false;
            state.chatStreamDraft = null;
            clearActiveChatRequest();
            appendChatMessage(sessionId, {
              role: "assistant",
              content: tr("\u6211\u6682\u65f6\u6ca1\u6709\u6536\u5230\u53ef\u7528\u56de\u590d\u3002", "I did not receive a usable reply."),
            });
            renderAll();
            return;
          }
          clearChatStreamRevealTimer();
          clearChatStreamRenderTimer();
          finalizeChatStreamDraft();
        },
        onError: (payload) => {
          clearChatStreamRenderTimer();
          clearChatStreamRevealTimer();
          clearChatPendingBadgeTimer();
          state.chatPending = false;
          state.chatStreamDraft = null;
          clearActiveChatRequest();
          appendChatMessage(sessionId, buildChatAssistantErrorMessage(payload));
          renderAll();
        },
      },
      {
        signal: state.chatAbortController.signal,
      }
    );
  } catch (error) {
    if (isAbortError(error)) {
      if (state.chatStopRequested) {
        finalizeStoppedChatDraft();
        renderAll();
        return;
      }
      stopActiveChatReply();
      renderAll();
      return;
    }
    clearChatStreamRenderTimer();
    clearChatStreamRevealTimer();
    clearChatPendingBadgeTimer();
    state.chatPending = false;
    state.chatStreamDraft = null;
    clearActiveChatRequest();
    appendChatMessage(
      sessionId,
      buildChatAssistantErrorMessage(error?.payload || { error: error?.message || "" })
    );
    renderAll();
  }
}

async function handleRecoverChatMessage(messageId) {
  if (state.chatPending) return;
  const session = getSelectedChatSession();
  const message = session?.messages?.find((item) => item.id === messageId && item.role === "assistant");
  const retryContext = normalizeChatRetryContext(message?.retry_context);
  if (!session || !message || message.recovery_action !== "switch_text_model_retry" || !retryContext) {
    elements.submitHint.textContent = tr(
      "\u5f53\u524d\u8fd9\u6761\u9519\u8bef\u6682\u65f6\u4e0d\u652f\u6301\u6062\u590d\u91cd\u8bd5\u3002",
      "This error cannot be retried with recovery right now."
    );
    renderAll();
    return;
  }
  await requestChatReply({
    sessionId: session.id,
    requestMessages: retryContext.messages,
    recoveryContext: retryContext,
  });
}

function getStoppedDraftMessage() {
  return tr(
    "\u5df2\u505c\u6b62\uff0c\u672c\u6b21\u56de\u590d\u672a\u5b8c\u6210\u3002",
    "Stopped before the reply was completed."
  );
}

function isStoppedPlaceholderChatMessage(content) {
  return normalizeChatMessageContent(content) === normalizeChatMessageContent(getStoppedDraftMessage());
}

function getMathRecoveryQuestionKey(message) {
  if (normalizeText(message?.error_code || "") !== "math_formula_unstable") {
    return "";
  }
  const retryContext = normalizeChatRetryContext(message?.retry_context);
  if (!retryContext?.messages?.length) return "";
  const lastUserMessage = [...retryContext.messages].reverse().find((item) => item.role === "user");
  return normalizeChatMessageContent(lastUserMessage?.content || "");
}

function countMathRecoveryFailures(sessionMessages = [], questionKey = "", currentMessageId = "") {
  if (!questionKey) return 0;
  let count = 0;
  for (const item of Array.isArray(sessionMessages) ? sessionMessages : []) {
    if (getMathRecoveryQuestionKey(item) === questionKey) {
      count += 1;
    }
    if (currentMessageId && item?.id === currentMessageId) {
      break;
    }
  }
  return count;
}

function shouldShowMathRecoveryAction(message, sessionMessages = []) {
  if (normalizeText(message?.error_code || "") !== "math_formula_unstable") {
    return false;
  }
  if (message?.recovery_action !== "switch_text_model_retry" || !message?.retry_context) {
    return false;
  }
  const questionKey = getMathRecoveryQuestionKey(message);
  if (!questionKey) {
    return false;
  }
  return countMathRecoveryFailures(sessionMessages, questionKey, message.id) >= 2;
}

function renderChatActionIcon(kind) {
  if (kind === "copy-success") {
    return `
      <svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="m5 12 4.1 4.1L19 6.2"
          fill="none"
          stroke="currentColor"
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="1.9"
        />
      </svg>
    `;
  }

  if (kind === "retry") {
    return `
      <svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M20 12a8 8 0 1 1-2.34-5.66M20 4v5h-5"
          fill="none"
          stroke="currentColor"
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="1.8"
        />
      </svg>
    `;
  }

  return `
    <svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true">
      <rect
        x="9"
        y="9"
        width="10"
        height="10"
        rx="2.2"
        fill="none"
        stroke="currentColor"
        stroke-linejoin="round"
        stroke-width="1.8"
      />
      <path
        d="M7 15H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v1"
        fill="none"
        stroke="currentColor"
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="1.8"
      />
    </svg>
  `;
}

function renderChatActionIconButton({
  action,
  messageId,
  label,
  icon,
  disabled = false,
  tone = "",
}) {
  const toneClass = tone ? ` message-action-icon-button--${tone}` : "";
  const disabledAttr = disabled ? " disabled" : "";
  return `
    <button
      class="icon-action-button message-action-icon-button${toneClass}"
      type="button"
      data-${action}-chat-message="${escapeHtml(messageId)}"
      title="${escapeHtml(label)}"
      aria-label="${escapeHtml(label)}"${disabledAttr}
    >
      ${renderChatActionIcon(icon)}
    </button>
  `;
}

function finalizeStoppedChatDraft() {
  const draft = state.chatStreamDraft;
  if (!draft) return;

  const stoppedContent = normalizeChatMessageContent(
    draft.content || draft.targetContent || getStoppedDraftMessage()
  );
  draft.content = stoppedContent;
  draft.targetContent = stoppedContent;
  draft.waiting = false;
  draft.completed = true;
  draft.status = "stopped";
  finalizeChatStreamDraft();
}


function renderNormalAssistantMessage(message, options = {}) {
  const showActions = Boolean(options.showActions);
  const sessionMessages = Array.isArray(options.sessionMessages) ? options.sessionMessages : [];
  const showRecovery = shouldShowMathRecoveryAction(message, sessionMessages);
  const feedback = state.chatMessageActionFeedback;
  const copyLabel =
    feedback?.messageId === message.id && feedback?.action === "copy"
      ? feedback.status === "success"
        ? tr("\u5df2\u590d\u5236", "Copied")
        : tr("\u590d\u5236\u5931\u8d25", "Copy failed")
      : tr("\u590d\u5236", "Copy");
  const retryLabel = tr("\u91cd\u8bd5", "Retry");
  const copyIcon =
    feedback?.messageId === message.id && feedback?.action === "copy" && feedback?.status === "success"
      ? "copy-success"
      : "copy";
  const copyTone =
    feedback?.messageId === message.id && feedback?.action === "copy"
      ? feedback.status === "success"
        ? "success"
        : "error"
      : "";
  const recoverLabel =
    normalizeText(message?.recovery_label || "") ||
    tr("\u5207\u6362\u5230\u6587\u672c\u6a21\u578b\u91cd\u8bd5", "Retry with a text model");
  const handoffButton =
    showActions && message?.handoff?.suggested_task
      ? `
          <button class="secondary-button" type="button" data-start-agent-task="${escapeHtml(message.handoff.suggested_task)}">
            ${escapeHtml(tr("\u8f6c\u5230 Agent \u6267\u884c", "Send to Agent"))}
          </button>
        `
      : "";
  const handoffReason =
    showActions && message?.handoff?.reason
      ? `<span class="message-meta">${escapeHtml(
          state.locale === "zh-CN"
            ? "\u9002\u5408\u771f\u5b9e\u6267\u884c\u7684\u684c\u9762\u6216\u6d4f\u89c8\u5668\u52a8\u4f5c\u3002"
            : message.handoff.reason
        )}</span>`
      : "";
  const stoppedNote =
    message.status === "stopped" && !isStoppedPlaceholderChatMessage(message.content)
      ? `<p class="assistant-status">${escapeHtml(
          tr("\u672c\u6b21\u56de\u590d\u672a\u5b8c\u6210\u3002", "This reply was not completed.")
        )}</p>`
      : "";
  const actionButtons = [
    handoffButton,
    showActions
      ? renderChatActionIconButton({
          action: "copy",
          messageId: message.id,
          label: copyLabel,
          icon: copyIcon,
          tone: copyTone,
        })
      : "",
    showActions
      ? renderChatActionIconButton({
          action: "retry",
          messageId: message.id,
          label: retryLabel,
          icon: "retry",
          disabled: Boolean(state.chatPending),
        })
      : "",
    showRecovery
      ? `
          <button class="secondary-button" type="button" data-recover-chat-message="${escapeHtml(message.id)}">
            ${escapeHtml(recoverLabel)}
          </button>
        `
      : "",
  ]
    .filter(Boolean)
    .join("");
  const actions =
    actionButtons || handoffReason
      ? `
          <div class="message-actions message-actions--assistant">
            ${actionButtons ? `<div class="message-actions__buttons">${actionButtons}</div>` : ""}
            ${handoffReason ? `<div class="message-actions__meta">${handoffReason}</div>` : ""}
          </div>
        `
      : "";

  return renderAssistantMessageShell(`
    <article class="assistant-card assistant-card--chat">
      <div class="assistant-copy assistant-markdown">${renderChatMarkdown(message.content)}</div>
      ${stoppedNote}
      ${actions}
    </article>
  `);
}


window.desktopAgentShell = {
  openRun(runId) {
    if (!runId) return;
    openInspectorForRun(runId);
  },
  showAgent() {
    setUiMode("agent");
  },
};

function scheduleDisplayDetection({ immediate = false } = {}) {
  if (state.displayDetectionTimer) {
    window.clearTimeout(state.displayDetectionTimer);
  }
  const run = () => {
    state.displayDetectionTimer = 0;
    refreshDisplayDetection();
  };
  if (immediate) {
    run();
    return;
  }
  state.displayDetectionTimer = window.setTimeout(run, 220);
}

async function refreshDisplayDetection() {
  const token = ++state.displayDetectionToken;
  state.displayDetectionLoading = true;
  if (state.settingsOpen || state.uiMode === "developer") {
    renderAll();
  }
  const payload = await fetchJson("/api/system/display-detection");
  if (token !== state.displayDetectionToken) {
    return;
  }
  state.displayDetectionLoading = false;
  if (payload?.detected && payload?.effective && payload?.override) {
    state.displayDetection = payload;
  } else if (!state.displayDetection) {
    state.displayDetection = null;
  }
  renderAll();
}

function scheduleEnvironmentCheck({ immediate = false } = {}) {
  if (state.environmentCheckTimer) {
    window.clearTimeout(state.environmentCheckTimer);
  }
  const run = () => {
    state.environmentCheckTimer = 0;
    refreshEnvironmentCheck();
  };
  if (immediate) {
    run();
    return;
  }
  state.environmentCheckTimer = window.setTimeout(run, 240);
}

async function refreshEnvironmentCheck() {
  const token = ++state.environmentCheckToken;
  state.environmentCheckLoading = true;
  if (state.settingsOpen) {
    renderAll();
  }
  const payload = await fetchJson("/api/system/environment-check");
  if (token !== state.environmentCheckToken) {
    return;
  }
  state.environmentCheckLoading = false;
  if (payload?.items) {
    state.environmentCheck = payload;
  } else if (!state.environmentCheck) {
    state.environmentCheck = { items: [] };
  }
  renderAll();
}

function getEnvironmentStatusLabel(status) {
  const isEnglish = state.locale === "en-US";
  if (status === "Ready") return isEnglish ? "Ready" : "已就绪";
  if (status === "Connection failed") return isEnglish ? "Connection failed" : "连接失败";
  return isEnglish ? "Needs setup" : "需要设置";
}

function getEnvironmentStatusTone(status) {
  if (status === "Ready") return "is-ready";
  if (status === "Connection failed") return "is-error";
  return "is-pending";
}

function getEnvironmentActionLabel(action) {
  const isEnglish = state.locale === "en-US";
  if (action === "refresh_model_catalog") return isEnglish ? "Refresh model catalog" : "刷新模型目录";
  if (action === "open_about_logs") return isEnglish ? "Open about & logs" : "打开关于与日志";
  return isEnglish ? "Open settings" : "打开设置";
}

function renderEnvironmentCheckGrid() {
  const isEnglish = state.locale === "en-US";
  if (state.environmentCheckLoading && !state.environmentCheck?.items?.length) {
    return `
      <div class="environment-check-empty">
        ${escapeHtml(isEnglish ? "Checking the local environment…" : "正在检查本地环境…")}
      </div>
    `;
  }

  const items = Array.isArray(state.environmentCheck?.items) ? state.environmentCheck.items : [];
  if (!items.length) {
    return `
      <div class="environment-check-empty">
        ${escapeHtml(isEnglish ? "Environment checks will appear here after the first refresh." : "首次刷新后会在这里显示环境检查结果。")}
      </div>
    `;
  }

  return `
    <div class="environment-check-grid">
      ${items
        .map(
          (item) => `
            <article class="environment-check-card ${getEnvironmentStatusTone(item.status)}">
              <div class="environment-check-card__head">
                <strong>${escapeHtml(item.label || "")}</strong>
                <span class="environment-check-card__status">${escapeHtml(getEnvironmentStatusLabel(item.status || ""))}</span>
              </div>
              <p>${escapeHtml(item.detail || "")}</p>
              <button class="secondary-button" type="button" data-environment-action="${escapeHtml(item.action || "open_settings")}">
                ${escapeHtml(getEnvironmentActionLabel(item.action || "open_settings"))}
              </button>
            </article>
          `
        )
        .join("")}
    </div>
  `;
}

function renderOnboardingGuide() {
  if (!elements.onboardingSection) return;
  const completed = isOnboardingComplete();
  elements.onboardingSection.hidden = completed;
  if (completed) {
    elements.onboardingSection.innerHTML = "";
    return;
  }

  const isEnglish = state.locale === "en-US";
  const diagnostics = state.meta?.diagnostics || {};
  const configDir = diagnostics.config_dir || "%APPDATA%\\\\Aoryn";
  const runRoot = diagnostics.run_root || "%LOCALAPPDATA%\\\\Aoryn\\\\runs";

  elements.onboardingSection.innerHTML = `
    <div class="onboarding-card">
      <div class="onboarding-card__head">
        <div>
          <p class="onboarding-card__eyebrow">${escapeHtml(isEnglish ? "First launch guide" : "首次启动引导")}</p>
          <h3 class="onboarding-card__title">${escapeHtml(isEnglish ? "Check the environment before your first task." : "在开始第一条任务前，先确认环境是否就绪。")}</h3>
          <p class="onboarding-card__body">${escapeHtml(isEnglish ? "Aoryn keeps the install folder and the user data folder separate, so upgrades stay predictable even if you install the app to a custom location such as D:\\Apps\\Aoryn." : "Aoryn 会把程序安装目录和用户数据目录分开管理，所以即使你把程序安装到 D:\\Apps\\Aoryn 这类自定义位置，后续升级和卸载也会更稳定。")}</p>
        </div>
        <span class="onboarding-card__badge">${escapeHtml(isEnglish ? "First run" : "首次启动")}</span>
      </div>

      <div class="onboarding-tip">
        <strong>${escapeHtml(isEnglish ? "Data location policy" : "数据目录策略")}</strong>
        <span>${escapeHtml(isEnglish ? `Config and preferences stay in ${configDir}, while logs, cache, screenshots, and run history stay in ${runRoot}.` : `配置与偏好会保存在 ${configDir}，而日志、缓存、截图和运行记录会保存在 ${runRoot}。`)}</span>
      </div>

      ${renderEnvironmentCheckGrid()}

      <div class="onboarding-actions">
        <button class="secondary-button" type="button" data-onboarding-provider="lmstudio_local">${escapeHtml(isEnglish ? "Use local LM Studio" : "使用本地 LM Studio")}</button>
        <button class="secondary-button" type="button" data-onboarding-provider="openai_compatible">${escapeHtml(isEnglish ? "Use hosted / compatible API" : "使用兼容 API")}</button>
        <button class="secondary-button" type="button" data-open-about="true">${escapeHtml(isEnglish ? "Open about & logs" : "打开关于与日志")}</button>
      </div>
      <div class="onboarding-actions onboarding-actions--compact">
        <button class="secondary-button" type="button" data-onboarding-later="true">${escapeHtml(isEnglish ? "Maybe later" : "稍后再说")}</button>
        <button class="primary-button" type="button" data-onboarding-complete="true">${escapeHtml(isEnglish ? "Mark setup done" : "完成引导")}</button>
      </div>
    </div>
  `;
}

function renderAboutPanel() {
  if (!elements.aboutContent) return;
  const isEnglish = state.locale === "en-US";
  const diagnostics = state.meta?.diagnostics || {};
  const recentRuns = (state.runs || []).slice(0, 6);
  const appTitle = state.meta?.title || "Aoryn";
  const version = state.meta?.version || APP_VERSION;
  const runtimeMode =
    state.meta?.runtime_mode === "packaged"
      ? (isEnglish ? "Installed app" : "已安装应用")
      : (isEnglish ? "Source runtime" : "源码运行");

  if (elements.aboutTitle) {
    elements.aboutTitle.textContent = isEnglish ? "About Aoryn" : "关于 Aoryn";
  }
  if (elements.aboutSubtitle) {
    elements.aboutSubtitle.textContent = isEnglish ? "Version, diagnostics, and logs" : "版本、诊断与日志";
  }

  const pathRows = [
    { key: "install_dir", label: isEnglish ? "Install folder" : "安装目录", value: diagnostics.install_dir || "-" },
    { key: "config_dir", label: isEnglish ? "Config folder" : "配置目录", value: diagnostics.config_dir || "-" },
    { key: "data_dir", label: isEnglish ? "Data folder" : "数据目录", value: diagnostics.data_dir || "-" },
    { key: "run_root", label: isEnglish ? "Run history" : "运行记录目录", value: diagnostics.run_root || "-" },
    { key: "cache_dir", label: isEnglish ? "Cache folder" : "缓存目录", value: diagnostics.cache_dir || "-" },
  ];

  elements.aboutContent.innerHTML = `
    <div class="about-grid">
      <section class="about-card">
        <p class="about-card__eyebrow">${escapeHtml(isEnglish ? "About" : "关于")}</p>
        <h3>${escapeHtml(appTitle)}</h3>
        <div class="about-metrics">
          <article class="about-metric"><span>${escapeHtml(isEnglish ? "Version" : "版本")}</span><strong>v${escapeHtml(version)}</strong></article>
          <article class="about-metric"><span>${escapeHtml(isEnglish ? "Runtime" : "运行方式")}</span><strong>${escapeHtml(runtimeMode)}</strong></article>
        </div>
        <p class="about-card__copy">${escapeHtml(isEnglish ? "Share Setup.exe with end users. Use Review.zip when you want to send the build, release manifest, checksums, and a source snapshot for review." : "给最终用户分发时请使用 Setup.exe；如果要给模型或同事做审核，请使用 Review.zip，其中会包含安装包、发布清单、校验值和源码快照。")}</p>
        <div class="button-row">
          <button class="secondary-button" type="button" data-copy-diagnostics="true">${escapeHtml(isEnglish ? "Copy diagnostics" : "复制诊断信息")}</button>
        </div>
      </section>

      <section class="about-card">
        <p class="about-card__eyebrow">${escapeHtml(isEnglish ? "Paths" : "路径")}</p>
        <p class="about-card__copy">${escapeHtml(isEnglish ? "The install folder can be customized, but Aoryn always keeps config in %APPDATA%\\Aoryn and logs, cache, screenshots, and run history in %LOCALAPPDATA%\\Aoryn. Uninstall will ask whether you also want to remove that user data." : "安装目录可以自定义，但 Aoryn 会始终把配置保存在 %APPDATA%\\Aoryn，把日志、缓存、截图和运行记录保存在 %LOCALAPPDATA%\\Aoryn。卸载时会询问你是否同时删除这些用户数据。")}</p>
        <div class="about-paths">
          ${pathRows
            .map(
              (item) => `
                <div class="about-path-row">
                  <div>
                    <strong>${escapeHtml(item.label)}</strong>
                    <small>${escapeHtml(item.value)}</small>
                  </div>
                  <button class="secondary-button" type="button" data-open-path-key="${escapeHtml(item.key)}">${escapeHtml(isEnglish ? "Open" : "打开")}</button>
                </div>
              `
            )
            .join("")}
        </div>
      </section>

      <section class="about-card about-card--wide">
        <p class="about-card__eyebrow">${escapeHtml(isEnglish ? "Logs & run history" : "日志与运行记录")}</p>
        ${
          recentRuns.length
            ? `<div class="about-run-list">
                ${recentRuns
                  .map(
                    (run) => `
                      <div class="about-run-row">
                        <div>
                          <strong>${escapeHtml(cleanRunTitle(run.task || run.id))}</strong>
                          <small>${escapeHtml(formatTimestamp(run.started_at || run.created_at))} · ${escapeHtml(renderRunState(run))}</small>
                        </div>
                        <button class="secondary-button" type="button" data-open-run-id="${escapeHtml(run.id)}">${escapeHtml(isEnglish ? "View" : "查看")}</button>
                      </div>
                    `
                  )
                  .join("")}
              </div>`
            : `<div class="empty-state">${escapeHtml(isEnglish ? "No runs yet." : "还没有运行记录。")}</div>`
        }
      </section>
    </div>
  `;
}

function renderAboutPanel() {
  if (!elements.aboutContent) return;
  const isEnglish = state.locale === "en-US";
  const diagnostics = state.meta?.diagnostics || {};
  const recentRuns = (state.runs || []).slice(0, 6);
  const appTitle = state.meta?.title || "Aoryn";
  const version = state.meta?.version || APP_VERSION;
  const runtimeMode =
    state.meta?.runtime_mode === "packaged"
      ? (isEnglish ? "Installed app" : "已安装应用")
      : (isEnglish ? "Source runtime" : "源码运行");

  if (elements.aboutTitle) {
    elements.aboutTitle.textContent = isEnglish ? "About Aoryn" : "关于 Aoryn";
  }
  if (elements.aboutSubtitle) {
    elements.aboutSubtitle.textContent = isEnglish ? "Version, diagnostics, and logs" : "版本、诊断与日志";
  }

  const pathRows = [
    { key: "install_dir", label: isEnglish ? "Install folder" : "安装目录", value: diagnostics.install_dir || "-" },
    { key: "config_dir", label: isEnglish ? "Config folder" : "配置目录", value: diagnostics.config_dir || "-" },
    { key: "data_dir", label: isEnglish ? "Data folder" : "数据目录", value: diagnostics.data_dir || "-" },
    { key: "run_root", label: isEnglish ? "Run history" : "运行记录目录", value: diagnostics.run_root || "-" },
    { key: "cache_dir", label: isEnglish ? "Cache folder" : "缓存目录", value: diagnostics.cache_dir || "-" },
  ];

  elements.aboutContent.innerHTML = `
    <div class="about-grid">
      <section class="about-card about-card--hero">
        <div class="about-card__header">
          <p class="about-card__eyebrow">${escapeHtml(isEnglish ? "About" : "关于")}</p>
          <h3>${escapeHtml(appTitle)}</h3>
        </div>
        <div class="about-metrics">
          <article class="about-metric"><span>${escapeHtml(isEnglish ? "Version" : "版本")}</span><strong>v${escapeHtml(version)}</strong></article>
          <article class="about-metric"><span>${escapeHtml(isEnglish ? "Runtime" : "运行方式")}</span><strong>${escapeHtml(runtimeMode)}</strong></article>
        </div>
        <p class="about-card__copy">${escapeHtml(isEnglish ? "Share Setup.exe with end users. Use Review.zip when you want to send the build, release manifest, checksums, and a source snapshot for review." : "给最终用户分发时请使用 Setup.exe；如果要给模型或同事做审核，请使用 Review.zip，其中会包含安装包、发布清单、校验值和源码快照。")}</p>
        <div class="about-card__actions button-row">
          <button class="secondary-button" type="button" data-copy-diagnostics="true">${escapeHtml(isEnglish ? "Copy diagnostics" : "复制诊断信息")}</button>
        </div>
      </section>

      <section class="about-card">
        <div class="about-card__header">
          <p class="about-card__eyebrow">${escapeHtml(isEnglish ? "Paths" : "路径")}</p>
          <h3>${escapeHtml(isEnglish ? "Install & data layout" : "安装与数据布局")}</h3>
        </div>
        <p class="about-card__copy">${escapeHtml(isEnglish ? "The install folder can be customized, but Aoryn always keeps config in %APPDATA%\\\\Aoryn and logs, cache, screenshots, and run history in %LOCALAPPDATA%\\\\Aoryn. Uninstall will ask whether you also want to remove that user data." : "安装目录可以自定义，但 Aoryn 会始终把配置保存在 %APPDATA%\\\\Aoryn，把日志、缓存、截图和运行记录保存在 %LOCALAPPDATA%\\\\Aoryn。卸载时会询问你是否同时删除这些用户数据。")}</p>
        <div class="about-paths">
          ${pathRows
            .map(
              (item) => `
                <div class="about-path-row">
                  <div class="about-path-row__copy">
                    <strong>${escapeHtml(item.label)}</strong>
                    <small>${escapeHtml(item.value)}</small>
                  </div>
                  <button class="secondary-button" type="button" data-open-path-key="${escapeHtml(item.key)}">${escapeHtml(isEnglish ? "Open" : "打开")}</button>
                </div>
              `
            )
            .join("")}
        </div>
      </section>

      <section class="about-card about-card--wide">
        <div class="about-card__header">
          <p class="about-card__eyebrow">${escapeHtml(isEnglish ? "Logs & run history" : "日志与运行记录")}</p>
          <h3>${escapeHtml(isEnglish ? "Recent runs" : "最近运行")}</h3>
        </div>
        ${
          recentRuns.length
            ? `<div class="about-run-list">
                ${recentRuns
                  .map(
                    (run) => `
                      <div class="about-run-row">
                        <div class="about-run-row__copy">
                          <strong>${escapeHtml(cleanRunTitle(run.task || run.id))}</strong>
                          <small>${escapeHtml(formatTimestamp(run.started_at || run.created_at))} · ${escapeHtml(renderRunState(run))}</small>
                        </div>
                        <button class="secondary-button" type="button" data-open-run-id="${escapeHtml(run.id)}">${escapeHtml(isEnglish ? "View" : "查看")}</button>
                      </div>
                    `
                  )
                  .join("")}
              </div>`
            : renderPanelEmptyState({
                eyebrow: isEnglish ? "Runs" : "运行",
                title: isEnglish ? "No runs yet." : "还没有运行记录。",
                description: isEnglish ? "Run history and diagnostics shortcuts will appear here after the first task." : "执行第一条任务后，这里会显示最近运行和诊断入口。",
              })
        }
      </section>
    </div>
  `;
}

function applySupplementalStaticCopy() {
  const isEnglish = state.locale === "en-US";
  if (elements.openAboutButton) {
    elements.openAboutButton.textContent = isEnglish ? "About & Logs" : "关于与日志";
  }
  if (elements.aboutAndLogsHint) {
    elements.aboutAndLogsHint.textContent = isEnglish
      ? "Check the app version, install folder, AppData paths, and recent runs."
      : "查看版本、安装目录、AppData 数据目录和最近的运行记录。";
  }
  const aboutAndLogsTitle = document.getElementById("aboutAndLogsTitle");
  if (aboutAndLogsTitle) {
    aboutAndLogsTitle.textContent = isEnglish ? "About & Logs" : "关于与日志";
  }
  if (elements.aboutBackdrop) {
    elements.aboutBackdrop.setAttribute("aria-label", isEnglish ? "Close about panel" : "关闭关于面板");
  }
}

async function handleAboutPanelClick(event) {
  const providerButton = event.target.closest("[data-onboarding-provider]");
  if (providerButton) {
    applyOnboardingProvider(providerButton.dataset.onboardingProvider || "");
    return;
  }
  if (event.target.closest("[data-open-about]")) {
    openAboutPanel();
    return;
  }
  if (event.target.closest("[data-onboarding-later]")) {
    closeSettings();
    return;
  }
  if (event.target.closest("[data-onboarding-complete]")) {
    await updateUiPreferences({ onboarding_completed: true });
    closeSettings();
    return;
  }

  const envActionButton = event.target.closest("[data-environment-action]");
  if (envActionButton) {
    const action = envActionButton.dataset.environmentAction || "";
    if (action === "refresh_model_catalog") {
      handleRefreshCatalog();
      scheduleEnvironmentCheck({ immediate: true });
      return;
    }
    if (action === "open_about_logs") {
      openAboutPanel();
      return;
    }
    openSettings();
    return;
  }

  const openPathButton = event.target.closest("[data-open-path-key]");
  if (openPathButton) {
    try {
      await postJson("/api/system/open-path", { key: openPathButton.dataset.openPathKey || "" });
    } catch {
      // Ignore local shell open failures.
    }
    return;
  }

  const openRunButton = event.target.closest("[data-open-run-id]");
  if (openRunButton) {
    closeAboutPanel();
    openInspectorForRun(openRunButton.dataset.openRunId || "");
    return;
  }

  if (event.target.closest("[data-copy-diagnostics]")) {
    await copyTextToClipboard(buildAboutDiagnosticsSummary());
  }
}
