export const siteCopy = {
  "en-US": {
    localeName: "English",
    langSwitch: "切换到中文",
    announcement: "Windows build available now",
    nav: {
      product: "Product",
      workflow: "Workflow",
      download: "Download",
      faq: "FAQ",
      register: "Create account",
    },
    hero: {
      eyebrow: "Local-first desktop agent workspace",
      title: "Ship real desktop execution without turning your product into a black box.",
      body:
        "Aoryn brings chat, agent execution, live screenshots, run history, and Windows-aware planning into one clean workspace for desktop automation.",
      primaryCta: "Download for Windows",
      secondaryCta: "Create account",
      availability: "Public installer available now. Account system is being prepared next.",
      stats: [
        { value: "Chat + Agent", label: "Two execution modes in one workspace" },
        { value: "Local-first", label: "Config, runs, screenshots, and history stay on device" },
        { value: "GUI + DOM", label: "Hybrid browser and desktop control" },
      ],
      proof: [
        "Single-task execution designed for reliability",
        "Observable timeline with screenshots and state",
        "Display-aware planning with manual correction controls",
      ],
    },
    preview: {
      windowLabel: "Aoryn workspace",
      status: "Agent active",
      chips: ["Chat", "Agent", "History"],
      panelTitle: "Aoryn",
      panelBody: "Windows-aware planning, run observability, and a clean execution handoff.",
      metrics: [
        { value: "GUI + DOM", label: "Hybrid control" },
        { value: "Local-first", label: "Stored on device" },
        { value: "Display-aware", label: "Monitor + DPI" },
      ],
      cards: [
        {
          label: "Current goal",
          value: "Open the target site, sign in, and continue from the visible state.",
        },
        {
          label: "Execution surface",
          value: "Windows desktop + browser tabs + run history",
        },
        {
          label: "Display detection",
          value: "Auto-detected monitor, work area, and DPI with override support",
        },
      ],
      timelineTitle: "Recent run snapshots",
      timeline: [
        "Captured the current workspace and browser state",
        "Planned the next action with Windows-aware geometry",
        "Logged the result and kept the run fully inspectable",
      ],
    },
    product: {
      eyebrow: "What it is",
      title: "A product workspace for desktop execution, not just another chat shell.",
      body:
        "Aoryn is built for people who need to move from instructions to observable action on a real Windows desktop. It keeps the loop understandable at every step.",
      items: [
        {
          title: "One workspace for asking and acting",
          body: "Switch between regular chat and agent execution without losing context or history.",
        },
        {
          title: "Runs you can actually inspect",
          body: "Timelines, screenshots, diagnostics, and state snapshots stay attached to every task.",
        },
        {
          title: "Hybrid GUI + DOM control",
          body: "Use browser structure when available, and fall back to desktop interaction when needed.",
        },
        {
          title: "Windows-aware positioning",
          body: "Aoryn understands monitors, work areas, and DPI scale, and now exposes that detection for manual correction.",
        },
      ],
    },
    difference: {
      eyebrow: "Why it feels different",
      title: "Designed for visible execution, not hidden automation.",
      items: [
        {
          title: "Understand before action",
          body: "Use chat for planning and clarification, then hand off to the agent only when real desktop work should begin.",
        },
        {
          title: "See every step",
          body: "Screenshots, status snapshots, and run history keep the system debuggable instead of mysterious.",
        },
        {
          title: "Stay grounded in the local machine",
          body: "Display geometry, install paths, browser choices, and user data locations all stay explicit.",
        },
      ],
    },
    workflow: {
      eyebrow: "How it works",
      title: "A cleaner loop from instruction to execution.",
      steps: [
        {
          title: "Configure the environment once",
          body: "Set your model, browser channel, and runtime preferences for the next task.",
        },
        {
          title: "Describe the real goal",
          body: "Ask in natural language, from simple navigation to multi-step desktop workflows.",
        },
        {
          title: "Watch the run stay observable",
          body: "Track screenshots, environment snapshots, and action progress as the agent moves.",
        },
        {
          title: "Adjust and continue",
          body: "Intervene when needed, refine the task, and continue from the current visible state.",
        },
      ],
    },
    download: {
      eyebrow: "Download",
      title: "Start with the current Windows installer.",
      body:
        "The first release path is intentionally simple: one clean public installer for Windows, plus a product-ready landing page that can evolve without changing the download structure.",
      primaryCta: "Download installer",
      secondaryCta: "Create account",
      labels: {
        version: "Version",
        platform: "Platform",
        packageType: "Package",
        fileSize: "Size",
        hosting: "Hosting",
      },
      notes: [
        "The install directory can be customized during setup.",
        "Configuration stays in %APPDATA%\\Aoryn.",
        "Runs, logs, screenshots, and cache stay in %LOCALAPPDATA%\\Aoryn.",
      ],
    },
    register: {
      eyebrow: "Account",
      title: "Create your Aoryn account",
      body:
        "The frontend flow is ready now. You can use it as the product-facing entry point while the backend registration service is wired in next.",
      cta: "Open registration",
      benefits: [
        "A clean public account entry point for aoryn.org",
        "Ready to connect to your future backend without redesigning the UI",
        "Built-in validation, success state, and service adapter separation",
      ],
      modalTitle: "Create your account",
      modalBody:
        "This first version validates the full product-facing form now, and can switch to a real signup endpoint later without changing the page structure.",
      form: {
        name: "Name",
        namePlaceholder: "Your name",
        email: "Email",
        emailPlaceholder: "you@company.com",
        password: "Password",
        passwordPlaceholder: "At least 8 characters",
        confirmPassword: "Confirm password",
        confirmPasswordPlaceholder: "Repeat your password",
        acceptTerms: "I agree to the Aoryn product terms and privacy notice.",
        submit: "Create account",
        submitting: "Creating account...",
        close: "Close",
        successFallback:
          "The registration frontend is ready. Connect your backend endpoint next to start creating real accounts.",
        successLive: "Your registration request was submitted successfully.",
        networkError: "We could not reach the signup service. Please try again.",
      },
      validation: {
        nameRequired: "Please enter your name.",
        nameShort: "Please enter at least 2 characters.",
        emailRequired: "Please enter your email address.",
        emailInvalid: "Please enter a valid email address.",
        passwordRequired: "Please create a password.",
        passwordShort: "Password must be at least 8 characters.",
        confirmRequired: "Please confirm your password.",
        confirmMismatch: "Passwords do not match.",
        acceptRequired: "Please accept the terms to continue.",
      },
    },
    faq: {
      eyebrow: "FAQ",
      title: "A few practical answers before you download.",
      items: [
        {
          question: "Is Aoryn Windows-only right now?",
          answer:
            "Yes. The current product and installer focus on a Windows desktop environment, including monitor, work-area, and runtime detection.",
        },
        {
          question: "Do I need an account to download the app?",
          answer:
            "No. The installer is publicly downloadable. Account creation is a separate product-facing step for the upcoming backend flow.",
        },
        {
          question: "Where does Aoryn store user data?",
          answer:
            "Configuration stays under %APPDATA%\\Aoryn, while runs, screenshots, logs, and cache stay under %LOCALAPPDATA%\\Aoryn.",
        },
        {
          question: "What is the registration form doing today?",
          answer:
            "The UI is complete and validates real product fields. Until the backend endpoint is connected, it uses a mock success path designed to be swapped later.",
        },
      ],
    },
    footer: {
      tagline: "Local-first desktop execution for visible, debuggable agent workflows.",
      copyright: "Aoryn. Built for the next step after chat.",
    },
  },
  "zh-CN": {
    localeName: "中文",
    langSwitch: "Switch to English",
    announcement: "Windows 安装包现已可用",
    nav: {
      product: "产品",
      workflow: "流程",
      download: "下载",
      faq: "常见问题",
      register: "注册",
    },
    hero: {
      eyebrow: "本地优先桌面 Agent 工作台",
      title: "把真实桌面执行做成可见、可控、可追踪的产品体验。",
      body:
        "Aoryn 将普通对话、Agent 执行、实时截图、运行记录和 Windows 感知规划整合到一个干净的工作台里，让桌面自动化不再像黑箱。",
      primaryCta: "下载 Windows 安装包",
      secondaryCta: "创建账号",
      availability: "当前可直接公开下载安装包，账号系统将在下一阶段接入。",
      stats: [
        { value: "Chat + Agent", label: "一个工作台里完成问答与执行" },
        { value: "本地优先", label: "配置、运行、截图与历史都保留在本机" },
        { value: "GUI + DOM", label: "浏览器结构化控制与桌面操作协同" },
      ],
      proof: [
        "围绕单任务执行稳定性而设计",
        "截图、时间线与状态快照让过程可观测",
        "支持显示器、工作区与 DPI 识别及手动纠正",
      ],
    },
    preview: {
      windowLabel: "Aoryn 工作台",
      status: "Agent 运行中",
      chips: ["对话", "Agent", "历史"],
      panelTitle: "Aoryn",
      panelBody: "理解 Windows 桌面环境、保持运行可观测，并把聊天与执行之间的切换做得更清晰。",
      metrics: [
        { value: "GUI + DOM", label: "混合控制" },
        { value: "本地优先", label: "数据留在设备上" },
        { value: "显示感知", label: "显示器 + DPI" },
      ],
      cards: [
        {
          label: "当前任务",
          value: "打开目标网站、登录，并从当前可见状态继续执行。",
        },
        {
          label: "执行界面",
          value: "Windows 桌面 + 浏览器标签页 + 运行记录",
        },
        {
          label: "显示识别",
          value: "自动识别显示器、工作区和 DPI，并支持手动覆盖",
        },
      ],
      timelineTitle: "最近运行快照",
      timeline: [
        "采集当前桌面与浏览器状态",
        "结合 Windows 几何信息规划下一步动作",
        "记录结果并保持运行过程可审查",
      ],
    },
    product: {
      eyebrow: "它是什么",
      title: "它不是另一个聊天壳，而是一个面向桌面执行的产品工作台。",
      body:
        "Aoryn 面向的是“从指令走到真实 Windows 执行”的场景。它把过程保持在可理解、可排查、可继续推进的状态，而不是只给出最终回答。",
      items: [
        {
          title: "一个工作台里完成提问与执行",
          body: "在普通对话与 Agent 执行之间切换时，不丢上下文，也不丢历史记录。",
        },
        {
          title: "真正可检查的运行记录",
          body: "时间线、截图、诊断信息和状态快照都会跟随每个任务一起保留。",
        },
        {
          title: "GUI + DOM 混合控制",
          body: "能用浏览器结构化信息时就用结构化信息，必要时再落回真实桌面操作。",
        },
        {
          title: "理解 Windows 显示环境",
          body: "Aoryn 能识别显示器、工作区与 DPI，并把这些结果展示给用户手动纠正。",
        },
      ],
    },
    difference: {
      eyebrow: "为什么和普通聊天不同",
      title: "它更像一个可见执行系统，而不是一个隐藏自动化黑箱。",
      items: [
        {
          title: "先理解，再执行",
          body: "你可以先在聊天模式中明确目标，只有在需要真实桌面动作时才切到 Agent。",
        },
        {
          title: "每一步都能看见",
          body: "截图、状态快照和运行历史让系统可调试、可回溯，而不是神秘地自己运行。",
        },
        {
          title: "始终贴着本机环境工作",
          body: "显示器布局、安装目录、浏览器选择与用户数据位置都保持明确，不藏在暗处。",
        },
      ],
    },
    workflow: {
      eyebrow: "如何工作",
      title: "从目标到执行，路径更清晰。",
      steps: [
        {
          title: "先配置运行环境",
          body: "设置模型、浏览器通道和下一次任务的运行偏好。",
        },
        {
          title: "再描述真实目标",
          body: "从简单浏览到多步骤桌面任务，都可以用自然语言表达。",
        },
        {
          title: "运行过程保持可观测",
          body: "随着 Agent 推进，持续查看截图、环境快照与执行状态。",
        },
        {
          title: "必要时人工介入并继续",
          body: "可以在任意时刻调整目标、接管流程，再从当前状态继续。",
        },
      ],
    },
    download: {
      eyebrow: "下载安装",
      title: "先从当前 Windows 安装包开始。",
      body:
        "首版发布路径刻意保持简单：一个对外公开的主安装包，一个干净的产品官网入口，以及后续可平滑演进的账户体系。",
      primaryCta: "下载主安装包",
      secondaryCta: "创建账号",
      labels: {
        version: "版本",
        platform: "平台",
        packageType: "安装包类型",
        fileSize: "文件大小",
        hosting: "托管方式",
      },
      notes: [
        "安装时支持自定义程序目录。",
        "配置保存在 %APPDATA%\\Aoryn。",
        "运行记录、日志、截图和缓存保存在 %LOCALAPPDATA%\\Aoryn。",
      ],
    },
    register: {
      eyebrow: "账号入口",
      title: "为 Aoryn 准备一个正式的注册入口",
      body:
        "这版先把面向用户的注册体验做完整。你后面接入真实后端时，只需要替换接口适配层，不必重做页面结构。",
      cta: "打开注册表单",
      benefits: [
        "给 aoryn.org 一个正式的产品账号入口",
        "后续可直接对接真实注册服务，不需要推翻 UI",
        "内置校验、成功态与网络适配层，方便继续演进",
      ],
      modalTitle: "创建你的 Aoryn 账号",
      modalBody:
        "这一版已经完成完整前端表单、交互和校验；等你的后端接口准备好之后，可以直接接入到同一套提交逻辑中。",
      form: {
        name: "姓名",
        namePlaceholder: "请输入你的姓名",
        email: "邮箱",
        emailPlaceholder: "you@company.com",
        password: "密码",
        passwordPlaceholder: "至少 8 位字符",
        confirmPassword: "确认密码",
        confirmPasswordPlaceholder: "再次输入密码",
        acceptTerms: "我同意 Aoryn 的产品条款与隐私说明。",
        submit: "创建账号",
        submitting: "正在创建账号...",
        close: "关闭",
        successFallback:
          "注册前端已经准备完成。下一步只需要接入你的后端接口，就可以开始创建真实账号。",
        successLive: "注册请求已提交成功。",
        networkError: "当前无法连接注册服务，请稍后重试。",
      },
      validation: {
        nameRequired: "请输入姓名。",
        nameShort: "姓名至少需要 2 个字符。",
        emailRequired: "请输入邮箱地址。",
        emailInvalid: "请输入有效的邮箱地址。",
        passwordRequired: "请输入密码。",
        passwordShort: "密码至少需要 8 位字符。",
        confirmRequired: "请再次输入密码。",
        confirmMismatch: "两次输入的密码不一致。",
        acceptRequired: "请先勾选同意条款。",
      },
    },
    faq: {
      eyebrow: "常见问题",
      title: "在下载安装之前，先把关键问题说清楚。",
      items: [
        {
          question: "Aoryn 目前只支持 Windows 吗？",
          answer:
            "是的。当前产品和安装包都聚焦在 Windows 桌面环境，包括显示器、工作区与运行时识别能力。",
        },
        {
          question: "下载应用前必须先注册吗？",
          answer:
            "不需要。当前主安装包是公开可下载的，注册入口是为后续账号体系和产品服务准备的独立流程。",
        },
        {
          question: "Aoryn 的用户数据存在哪里？",
          answer:
            "配置保存在 %APPDATA%\\Aoryn，而运行记录、截图、日志和缓存保存在 %LOCALAPPDATA%\\Aoryn。",
        },
        {
          question: "现在这个注册表单实际会做什么？",
          answer:
            "当前表单已经具备完整的产品前端体验和真实字段校验；在你接入后端接口前，它会走一个可替换的 mock 成功流程。",
        },
      ],
    },
    footer: {
      tagline: "本地优先的桌面执行工作台，让 Agent 流程保持可见、可调试、可持续推进。",
      copyright: "Aoryn。为聊天之后的真实执行而生。",
    },
  },
};
