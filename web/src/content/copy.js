import { siteConfig } from "../config/site";

const releaseMeta = [
  { key: "version", value: siteConfig.release.version },
  { key: "platform", value: siteConfig.release.platform },
  { key: "package", value: siteConfig.release.packageType },
  { key: "size", value: siteConfig.release.fileSize },
  { key: "hosting", value: siteConfig.release.hosting },
  { key: "file", value: siteConfig.release.fileName },
];

export const siteCopy = {
  "zh-CN": {
    brandDescriptor: "桌面 Agent 工作台",
    langSwitch: "EN",
    nav: {
      home: "首页",
      product: "产品",
      workspace: "界面",
      download: "下载",
      register: "注册",
      menu: "打开菜单",
      closeMenu: "关闭菜单",
    },
    pages: {
      home: {
        meta: {
          title: "Aoryn | 让桌面执行更像一件产品",
          description:
            "Aoryn 是一个面向 Windows 的本地优先桌面 Agent 工作台，让对话、执行与历史留在同一块可见界面中。",
        },
        hero: {
          eyebrow: "Aoryn for Windows",
          titleLines: ["让桌面执行", "更像一件产品。"],
          body: "本地优先的 Windows Agent 工作台，让任务继续保持可见、可控、可接管。",
          primaryCta: "下载 Windows 安装包",
          secondaryCta: "创建账号",
        },
        stage: {
          ariaLabel: "Aoryn hero stage",
          windowLabel: "Aoryn Workspace",
          windowMeta: "本地优先桌面 Agent",
          status: "运行可见",
          railLabel: "当前层级",
          railItems: ["对话", "执行", "历史"],
          chips: ["Windows 感知", "步骤回看", "人工接管"],
          focusLabel: "当前任务",
          focusTitle: "从目标到执行，始终留在同一块工作表面上。",
          focusBody: "不是脚本黑箱，而是可继续推进的产品界面。",
          metrics: [
            { value: "显示感知", label: "Display aware" },
            { value: "历史保留", label: "Run memory" },
            { value: "单任务", label: "Stable flow" },
          ],
          floatingCards: [
            { eyebrow: "运行链路", title: "对话 → 执行 → 截图" },
            { eyebrow: "桌面状态", title: "窗口、工作区、DPI 已识别" },
          ],
        },
        capabilities: {
          eyebrow: "核心能力",
          title: "只保留最重要的三件事。",
          body: "首页不再负责解释全部，只负责说明它为什么值得被下载。",
          items: [
            {
              note: "01",
              title: "可见执行",
              body: "重要状态始终能回看。",
              href: "/product",
              linkLabel: "查看产品",
            },
            {
              note: "02",
              title: "本地优先",
              body: "数据、截图与缓存都留在本机。",
              href: "/workspace",
              linkLabel: "查看界面",
            },
            {
              note: "03",
              title: "Windows 感知",
              body: "显示器、工作区与 DPI 可以核对并修正。",
              href: "/download",
              linkLabel: "查看下载",
            },
          ],
        },
        spotlight: {
          eyebrow: "产品舞台",
          title: "不是一段自动化脚本，而是一块可以接管的工作表面。",
          body: "真正的价值在于运行过程仍然被看见，而不是被藏起来。",
          primaryCta: "查看界面",
          secondaryCta: "查看产品",
          preview: {
            ariaLabel: "Aoryn workspace preview",
            windowLabel: "Aoryn 工作台",
            windowMeta: "运行与历史同列可见",
            status: "状态在线",
            railLabel: "工作区",
            railItems: ["对话规划", "Agent 执行", "历史恢复", "显示纠正"],
            chips: ["截图链路", "运行记录", "显示覆盖"],
            focusLabel: "当前视图",
            focusTitle: "聊天、运行与状态快照留在同一列里。",
            focusBody: "从同一个界面继续，而不是在多个工具间来回跳。",
            cards: [
              { title: "运行历史", value: "重启后继续保留" },
              { title: "显示识别", value: "结果可见且可改" },
            ],
            metrics: [
              { value: "GUI + DOM", label: "混合控制" },
              { value: "本地", label: "环境贴身" },
              { value: "可接管", label: "人始终在回路中" },
            ],
            footerLabel: "继续方式",
            footerValue: "从当前状态继续执行，或在此刻人工接管。",
          },
        },
        cta: {
          eyebrow: "公开下载",
          title: "从一个干净的入口开始。",
          body: "安装包已经准备好，主界面则保持克制，只把最重要的事留在首屏。",
          primaryCta: "下载 Windows 安装包",
          secondaryCta: "创建账号",
        },
      },
      product: {
        meta: {
          title: "Aoryn 产品 | 可见执行的桌面 Agent",
          description:
            "了解 Aoryn 如何把对话、执行、截图与运行历史重新组织成一条清晰可见的桌面执行链路。",
        },
        hero: {
          eyebrow: "产品",
          title: "把桌面 Agent 变成一个可以理解、可以接管的产品。",
          body: "Aoryn 把对话、执行、截图与运行历史放回同一条清晰链路里，让桌面自动化不再像一段失控脚本。",
          stats: [
            { value: "Visible", label: "执行保持可见" },
            { value: "Local-first", label: "环境贴身工作" },
            { value: "Windows-aware", label: "显示结果可校正" },
          ],
        },
        pillars: {
          eyebrow: "产品原则",
          title: "三层结构，决定它为什么不像普通聊天。",
          body: "真正的区别不在回答得更像 AI，而在运行过程是否仍然是一块能被理解的产品表面。",
          items: [
            {
              note: "01",
              title: "可见执行",
              body: "从目标、步骤、截图到结果，关键状态会持续留在界面上，而不是只给你一个最终答案。",
            },
            {
              note: "02",
              title: "本地优先",
              body: "配置、历史、截图与缓存都围绕本机环境工作，更适合桌面任务的真实上下文。",
            },
            {
              note: "03",
              title: "人仍在回路中",
              body: "任何节点都可以停下、检查，再继续推进，而不是被一条全自动黑箱流程拖着走。",
            },
          ],
        },
        workflow: {
          eyebrow: "工作方式",
          title: "四个阶段，始终留在同一产品面内。",
          body: "Aoryn 不把动作拆散到多个工具里，而是让整条链路保持连续。",
          items: [
            { step: "01", title: "明确目标", body: "先把自然语言目标收敛成清楚的执行方向。" },
            { step: "02", title: "采集环境", body: "把窗口、显示器、工作区与状态信号一起纳入判断。" },
            { step: "03", title: "继续执行", body: "在同一个界面里推进任务，而不是跳到另一套不可见流程。" },
            { step: "04", title: "保留历史", body: "聊天与运行记录一起保留下来，便于回看与恢复。" },
          ],
        },
        evidence: {
          eyebrow: "产品判断",
          title: "真正的差异，在于运行过程依然像一个系统。",
          body: "它不追求把自动化藏起来，而是追求让人类在任何时刻都知道系统正在做什么。",
          metrics: [
            { value: "步骤可见", label: "执行链路" },
            { value: "截图保留", label: "状态证据" },
            { value: "可继续", label: "重启后恢复" },
          ],
        },
      },
      workspace: {
        meta: {
          title: "Aoryn 界面 | 工作台与运行历史",
          description:
            "查看 Aoryn 如何把工作台、运行历史、显示识别与人工接管点组织在同一个桌面执行表面上。",
        },
        hero: {
          eyebrow: "界面",
          title: "把聊天、执行、历史与显示识别放回同一块工作台中。",
          body: "界面不是装饰，而是系统可信度的一部分。它必须让状态足够清楚，才能承接真正的桌面执行。",
          stats: [
            { value: "History", label: "聊天与运行同列" },
            { value: "Display", label: "识别结果可核对" },
            { value: "Handoff", label: "支持人工接管" },
          ],
        },
        preview: {
          ariaLabel: "Aoryn workspace page preview",
          windowLabel: "Aoryn Workspace",
          windowMeta: "对话、运行、快照与历史",
          status: "工作台在线",
          railLabel: "当前视图",
          railItems: ["主线程", "历史恢复", "显示识别", "开发台"],
          chips: ["会话保留", "运行概览", "DPI 覆盖"],
          focusLabel: "当前焦点",
          focusTitle: "所有重要状态仍然停留在同一块界面里。",
          focusBody: "从提问、执行到回看，每一步都有自己的位置，而不是散落在看不见的后台。",
          cards: [
            { title: "活跃会话", value: "上次选中的历史项" },
            { title: "显示结果", value: "detected / effective 对照" },
          ],
          metrics: [
            { value: "Run summary", label: "概览可直达" },
            { value: "Screenshot", label: "快照随步保留" },
            { value: "Developer view", label: "诊断信息外露" },
          ],
          footerLabel: "界面原则",
          footerValue: "保持可见、可核对、可在任意节点继续。",
        },
        modules: {
          eyebrow: "关键模块",
          title: "工作台真正承担的是状态组织，而不是视觉堆砌。",
          body: "这块表面需要同时承接运行、历史与校正，而又保持足够清爽。",
          items: [
            {
              title: "历史记录",
              body: "聊天 session 与 Agent run 混排展示，重启后仍能恢复到上次选中的历史项。",
            },
            {
              title: "显示识别",
              body: "系统检测结果直接展示给用户看，同时允许通过运行时覆盖值进行手动纠正。",
            },
            {
              title: "人工接管",
              body: "任何时候都可以从当前状态停下、检查，再决定继续自动执行还是转由人工操作。",
            },
          ],
        },
        timeline: {
          eyebrow: "执行链路",
          title: "每一次运行都像一条连续的工作轨迹。",
          body: "不是一次性的问答，而是一条可以回看、可以恢复、可以继续的桌面任务流。",
          items: [
            { step: "01", title: "进入任务", body: "在工作台中明确当前目标与上下文。" },
            { step: "02", title: "采集快照", body: "持续记录截图、窗口状态与关键检查点。" },
            { step: "03", title: "恢复上下文", body: "重启或返回后，仍然可以从上次选中项继续。" },
            { step: "04", title: "调整执行", body: "根据显示结果或现场状态，立即人工修正并继续推进。" },
          ],
        },
      },
      download: {
        meta: {
          title: "Aoryn 下载 | Windows 安装包与常见问题",
          description:
            "下载适用于 Windows 的 Aoryn 正式安装包，查看版本信息、安装步骤和最常见的问题说明。",
        },
        hero: {
          eyebrow: "下载安装",
          title: "从正式安装包开始，把工作台放到你的 Windows 桌面上。",
          body: "公开版本保持干净直接：一个正式下载地址、一个稳定的产品入口，以及为后续账号体系预留好的位置。",
          primaryCta: "下载 Windows 安装包",
          secondaryCta: "创建账号",
        },
        metaGrid: releaseMeta.map((item) => ({
          label:
            {
              version: "版本",
              platform: "平台",
              package: "安装包类型",
              size: "文件大小",
              hosting: "托管方式",
              file: "文件名",
            }[item.key],
          value: item.value,
        })),
        steps: {
          eyebrow: "开始使用",
          title: "三步进入工作台。",
          body: "入口足够简单，安装之后就能从主界面开始体验完整的产品路径。",
          items: [
            { step: "01", title: "下载安装包", body: "使用官网公开下载地址获取正式 Windows 安装包。" },
            { step: "02", title: "完成安装", body: "在安装器中选择目录，使用默认配置完成部署。" },
            { step: "03", title: "打开工作台", body: "进入 Aoryn 主界面，从下载入口开始你的第一条任务链路。" },
          ],
        },
        faq: {
          eyebrow: "常见问题",
          title: "下载前后最常见的几个问题。",
          body: "把真正会影响判断的问题放在这里，而不是重新堆回首页。",
          items: [
            {
              question: "现在支持哪些系统？",
              answer: "当前公开版本聚焦 Windows 10 / 11 桌面环境。",
            },
            {
              question: "用户数据保存在哪里？",
              answer:
                "配置保存在 %APPDATA%\\Aoryn，运行记录、截图与缓存保存在 %LOCALAPPDATA%\\Aoryn。",
            },
            {
              question: "必须先注册才能使用吗？",
              answer: "不需要。下载是公开入口，注册是保留给账号体系的次级产品入口。",
            },
          ],
        },
      },
    },
    register: {
      eyebrow: "账号入口",
      modalTitle: "创建你的 Aoryn 账号",
      modalBody: "注册继续保留为次级入口。当前前端表单、校验和成功态已经准备好，后续只需要接入你的后端接口。",
      benefits: ["产品化表单交互", "完整校验与反馈", "可直接接后端接口"],
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
        successFallback: "账号入口前端已经准备完成，接入后端接口后即可正式使用。",
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
    footer: {
      tagline: "本地优先的桌面 Agent 工作台，让执行过程保持可见、可接管、可继续。",
      copyright: "Aoryn",
    },
  },
  "en-US": {
    brandDescriptor: "Desktop agent workspace",
    langSwitch: "中文",
    nav: {
      home: "Home",
      product: "Product",
      workspace: "Workspace",
      download: "Download",
      register: "Create account",
      menu: "Open menu",
      closeMenu: "Close menu",
    },
    pages: {
      home: {
        meta: {
          title: "Aoryn | Make desktop execution feel like a product",
          description:
            "Aoryn is a local-first Windows agent workspace that keeps chat, execution, and history on one visible surface.",
        },
        hero: {
          eyebrow: "Aoryn for Windows",
          titleLines: ["Make desktop execution", "feel like a product."],
          body: "A local-first Windows workspace that keeps desktop work visible, controllable, and easy to resume.",
          primaryCta: "Download for Windows",
          secondaryCta: "Create account",
        },
        stage: {
          ariaLabel: "Aoryn hero stage",
          windowLabel: "Aoryn Workspace",
          windowMeta: "Local-first desktop agent",
          status: "Run visible",
          railLabel: "Current stack",
          railItems: ["Chat", "Runs", "History"],
          chips: ["Windows aware", "Steps visible", "Human handoff"],
          focusLabel: "Current task",
          focusTitle: "From intent to execution, the surface stays legible.",
          focusBody: "Not a black-box script, but a product surface that can keep moving.",
          metrics: [
            { value: "Display aware", label: "Geometry" },
            { value: "Run memory", label: "History" },
            { value: "Single-task", label: "Flow" },
          ],
          floatingCards: [
            { eyebrow: "Run chain", title: "Chat → Execute → Snapshot" },
            { eyebrow: "Desktop state", title: "Window, work-area, and DPI captured" },
          ],
        },
        capabilities: {
          eyebrow: "Core capabilities",
          title: "Three reasons are enough.",
          body: "The homepage should explain why Aoryn matters, not explain everything.",
          items: [
            {
              note: "01",
              title: "Visible execution",
              body: "Important states remain inspectable.",
              href: "/product",
              linkLabel: "View product",
            },
            {
              note: "02",
              title: "Local-first runs",
              body: "Runs, screenshots, and cache stay on the machine.",
              href: "/workspace",
              linkLabel: "View workspace",
            },
            {
              note: "03",
              title: "Windows-aware",
              body: "Monitor, work-area, and DPI can be verified and corrected.",
              href: "/download",
              linkLabel: "View download",
            },
          ],
        },
        spotlight: {
          eyebrow: "Product stage",
          title: "Not a script, but a surface you can actually take over.",
          body: "The point is not automation alone. The point is that the run still remains visible while it moves.",
          primaryCta: "View workspace",
          secondaryCta: "View product",
          preview: {
            ariaLabel: "Aoryn workspace preview",
            windowLabel: "Aoryn workspace",
            windowMeta: "Runs and history stay aligned",
            status: "Live state",
            railLabel: "Current view",
            railItems: ["Chat planning", "Agent execution", "History restore", "Display override"],
            chips: ["Snapshots", "Run history", "Display correction"],
            focusLabel: "Current view",
            focusTitle: "Chat, runs, and state snapshots stay in one column.",
            focusBody: "Continue from the same interface instead of jumping between disconnected tools.",
            cards: [
              { title: "Run history", value: "Restores after restart" },
              { title: "Display results", value: "Visible and editable" },
            ],
            metrics: [
              { value: "GUI + DOM", label: "Hybrid control" },
              { value: "Local", label: "Machine context" },
              { value: "Handoff", label: "Human stays in the loop" },
            ],
            footerLabel: "Continue mode",
            footerValue: "Resume from the current state, or take control manually.",
          },
        },
        cta: {
          eyebrow: "Public release",
          title: "Start from a clean entry point.",
          body: "The installer is ready, while the homepage stays deliberately restrained and product-first.",
          primaryCta: "Download for Windows",
          secondaryCta: "Create account",
        },
      },
      product: {
        meta: {
          title: "Aoryn Product | A visible desktop agent",
          description:
            "See how Aoryn turns chat, execution, screenshots, and run history into a clearer product surface for desktop work.",
        },
        hero: {
          eyebrow: "Product",
          title: "Turn a desktop agent into something you can understand and take over.",
          body: "Aoryn keeps chat, execution, screenshots, and run history on the same visible chain so desktop automation stops feeling like an opaque script.",
          stats: [
            { value: "Visible", label: "Execution stays legible" },
            { value: "Local-first", label: "Grounded on-device" },
            { value: "Windows-aware", label: "Display results can be corrected" },
          ],
        },
        pillars: {
          eyebrow: "Product principles",
          title: "Three layers explain why this is not just another chat UI.",
          body: "The real difference is not better wording. It is whether the run still behaves like a product surface while it is happening.",
          items: [
            {
              note: "01",
              title: "Visible execution",
              body: "From goal to result, the important states stay on screen instead of disappearing behind automation.",
            },
            {
              note: "02",
              title: "Local-first behavior",
              body: "Config, history, screenshots, and cache stay grounded on the same machine as the task itself.",
            },
            {
              note: "03",
              title: "Human in the loop",
              body: "Any moment can become a checkpoint where the user inspects, corrects, and then continues.",
            },
          ],
        },
        workflow: {
          eyebrow: "Workflow",
          title: "Four stages, one continuous product surface.",
          body: "Aoryn keeps the chain together instead of scattering it across hidden layers.",
          items: [
            { step: "01", title: "Clarify intent", body: "Turn the prompt into a clearer execution direction first." },
            { step: "02", title: "Capture context", body: "Bring windows, displays, work-area, and state signals into the loop." },
            { step: "03", title: "Continue execution", body: "Keep moving from the same visible surface rather than switching to a hidden backend flow." },
            { step: "04", title: "Keep the history", body: "Leave chat and run records together so work can be reviewed and resumed." },
          ],
        },
        evidence: {
          eyebrow: "Product judgment",
          title: "The difference is that the run still feels like a system.",
          body: "Aoryn does not hide automation. It makes the machine state understandable while work is happening.",
          metrics: [
            { value: "Step visible", label: "Run chain" },
            { value: "Snapshots kept", label: "State evidence" },
            { value: "Resume ready", label: "Restore path" },
          ],
        },
      },
      workspace: {
        meta: {
          title: "Aoryn Workspace | Interface, history, and display state",
          description:
            "Explore how Aoryn keeps the workspace, run history, display detection, and handoff points on one desktop execution surface.",
        },
        hero: {
          eyebrow: "Workspace",
          title: "Bring chat, runs, history, and display state back into one surface.",
          body: "The interface is part of the product promise. If the surface is unclear, the system is harder to trust.",
          stats: [
            { value: "History", label: "Chat and runs stay aligned" },
            { value: "Display", label: "Detection can be checked" },
            { value: "Handoff", label: "Manual takeover stays available" },
          ],
        },
        preview: {
          ariaLabel: "Aoryn workspace page preview",
          windowLabel: "Aoryn Workspace",
          windowMeta: "Chat, runs, snapshots, and history",
          status: "Workspace live",
          railLabel: "Current view",
          railItems: ["Main thread", "History restore", "Display detection", "Developer console"],
          chips: ["Session restore", "Run overview", "DPI override"],
          focusLabel: "Current focus",
          focusTitle: "All important state still lives on one surface.",
          focusBody: "From asking to executing to reviewing, each state gets a place instead of getting lost in the background.",
          cards: [
            { title: "Active history", value: "Last selected item restored" },
            { title: "Display state", value: "detected / effective shown together" },
          ],
          metrics: [
            { value: "Run summary", label: "Direct overview" },
            { value: "Screenshot", label: "Snapshots kept" },
            { value: "Developer view", label: "Diagnostics exposed" },
          ],
          footerLabel: "Workspace rule",
          footerValue: "Stay visible, stay checkable, stay resumable.",
        },
        modules: {
          eyebrow: "Key modules",
          title: "The workspace is about state organization, not decoration.",
          body: "It has to hold runs, history, and correction points together without becoming noisy.",
          items: [
            {
              title: "Run history",
              body: "Chat sessions and agent runs are mixed into one history stream and can be restored after restart.",
            },
            {
              title: "Display detection",
              body: "System-detected monitor, work-area, and DPI values are shown directly and can be overridden when needed.",
            },
            {
              title: "Manual handoff",
              body: "At any point the user can stop, inspect, adjust, and then continue from the current state.",
            },
          ],
        },
        timeline: {
          eyebrow: "Execution chain",
          title: "Each run behaves like a continuous trail of work.",
          body: "Not a disposable answer, but a desktop task flow that can be reviewed, resumed, and continued.",
          items: [
            { step: "01", title: "Enter the task", body: "Define the active goal and context inside the workspace." },
            { step: "02", title: "Capture snapshots", body: "Keep screenshots, window state, and checkpoints attached to the run." },
            { step: "03", title: "Restore context", body: "Return to the previously selected history item after restart." },
            { step: "04", title: "Adjust execution", body: "Correct display or runtime assumptions and continue without losing the trail." },
          ],
        },
      },
      download: {
        meta: {
          title: "Aoryn Download | Windows installer and practical details",
          description:
            "Download the official Aoryn Windows installer and review release metadata, install steps, and the most common questions.",
        },
        hero: {
          eyebrow: "Download",
          title: "Start with the official Windows installer.",
          body: "The public release stays simple: one installer, one product site, and one clean entry point for the desktop workspace.",
          primaryCta: "Download for Windows",
          secondaryCta: "Create account",
        },
        metaGrid: releaseMeta.map((item) => ({
          label:
            {
              version: "Version",
              platform: "Platform",
              package: "Package",
              size: "Size",
              hosting: "Hosting",
              file: "Filename",
            }[item.key],
          value: item.value,
        })),
        steps: {
          eyebrow: "Getting started",
          title: "Three steps into the workspace.",
          body: "The entry should stay easy. After install, the main surface is ready right away.",
          items: [
            { step: "01", title: "Download the installer", body: "Use the public website entry point to fetch the official Windows installer." },
            { step: "02", title: "Complete setup", body: "Choose the install directory and finish the setup with the default flow." },
            { step: "03", title: "Open the workspace", body: "Launch Aoryn and start from the main interface instead of a complex setup flow." },
          ],
        },
        faq: {
          eyebrow: "FAQ",
          title: "The questions that actually affect the decision.",
          body: "Keep them off the homepage, but keep them easy to find.",
          items: [
            {
              question: "Which systems are supported right now?",
              answer: "The public release currently focuses on Windows 10 / 11 desktop environments.",
            },
            {
              question: "Where does Aoryn store user data?",
              answer:
                "Configuration lives under %APPDATA%\\Aoryn, while runs, screenshots, and cache live under %LOCALAPPDATA%\\Aoryn.",
            },
            {
              question: "Do I need an account before downloading?",
              answer: "No. Download is public. Registration is kept as a secondary product entry point.",
            },
          ],
        },
      },
    },
    register: {
      eyebrow: "Account",
      modalTitle: "Create your Aoryn account",
      modalBody: "Registration stays secondary. The UI, validation, and success states are already ready for a future backend endpoint.",
      benefits: ["Product-ready form flow", "Complete validation", "Direct backend integration path"],
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
        successFallback: "The account entry UI is ready. Connect your backend endpoint next.",
        successLive: "Your registration request was submitted successfully.",
        networkError: "We could not reach the signup service. Please try again.",
      },
      validation: {
        nameRequired: "Please enter your name.",
        nameShort: "Please enter at least 2 characters.",
        emailRequired: "Please enter your email address.",
        emailInvalid: "Please enter a valid email address.",
        passwordRequired: "Please enter a password.",
        passwordShort: "Password must be at least 8 characters.",
        confirmRequired: "Please confirm your password.",
        confirmMismatch: "Passwords do not match.",
        acceptRequired: "Please accept the terms to continue.",
      },
    },
    footer: {
      tagline: "A local-first desktop agent workspace for visible, resumable execution.",
      copyright: "Aoryn",
    },
  },
};
