export const siteCopy = {
  "zh-CN": {
    brandDescriptor: "可见执行，本地优先的桌面工作台",
    langSwitch: "EN",
    nav: {
      home: "首页",
      product: "产品",
      workspace: "工作台",
      download: "下载",
      login: "登录",
      register: "注册",
      account: "账号",
      logout: "退出登录",
      menu: "打开菜单",
      closeMenu: "关闭菜单",
      terms: "用户协议",
      privacy: "隐私政策",
    },
    auth: {
      tabs: {
        login: "登录",
        register: "注册",
      },
      dialogTitle: "访问 Aoryn",
      dialogBody: "账号只负责官网身份和下载权限。任务、截图、历史和设置仍然保留在你的设备上。",
      signedInAs: "当前账号",
      signedOut: "未登录",
      loginTitle: "登录后下载桌面版",
      registerTitle: "创建 Aoryn 账号",
      loginButton: "登录",
      registerButton: "创建账号",
      logoutButton: "退出登录",
      submitBusy: "处理中...",
      verifyHint: "注册成功，请先完成邮箱验证后再回来登录。",
      fields: {
        name: "显示名称",
        email: "邮箱",
        password: "密码",
        confirmPassword: "确认密码",
        namePlaceholder: "你希望被如何称呼",
        emailPlaceholder: "you@example.com",
        passwordPlaceholder: "至少 8 位",
        confirmPasswordPlaceholder: "再次输入密码",
        acceptTermsPrefix: "我已阅读并同意",
        acceptTermsLink: "《Aoryn 用户协议》",
        acceptPrivacyMiddle: "和",
        acceptPrivacyLink: "《Aoryn 隐私政策》",
      },
      validation: {
        nameRequired: "请输入显示名称。",
        nameShort: "显示名称至少需要 2 个字符。",
        emailRequired: "请输入邮箱地址。",
        emailInvalid: "请输入有效的邮箱地址。",
        passwordRequired: "请输入密码。",
        passwordShort: "密码至少需要 8 位。",
        confirmRequired: "请再次输入密码。",
        confirmMismatch: "两次输入的密码不一致。",
        acceptRequired: "请先同意用户协议和隐私政策。",
      },
      messages: {
        loginSuccess: "登录成功。",
        logoutSuccess: "已退出登录。",
        registerSuccess: "账号创建成功，请先完成邮箱验证。",
        networkError: "认证服务暂时不可用，请稍后再试。",
      },
    },
    footer: {
      tagline: "账号在云端，工作流和运行记录留在本地。",
      copyright: "Aoryn. All rights reserved.",
    },
    pages: {
      home: {
        meta: {
          title: "Aoryn | 可见执行，本地优先的桌面工作台",
          description: "让桌面任务保持可见、可恢复、可交接。",
        },
        hero: {
          eyebrow: "本地优先桌面 Agent 工作台",
          title: "让桌面任务保持可见、可恢复、可交接。",
          body: "Aoryn 把对话、执行、截图和时间线放进同一个工作台里，让你始终知道它做了什么、停在了哪里、下一步该怎么接手。",
          primaryCta: "下载桌面版",
          secondaryCta: "查看工作台",
          tertiaryCta: "了解产品",
        },
        cards: [
          {
            title: "从一句目标到真实执行",
            body: "先说清你想完成什么，再让桌面执行层按当前环境逐步推进。",
            href: "/product",
          },
          {
            title: "每次运行都能回看和恢复",
            body: "截图、状态变化和关键步骤沿着同一条时间线留下来。",
            href: "/workspace",
          },
          {
            title: "下载前登录，安装后直接进入工作台",
            body: "账号只管理身份和下载权限，不接管你的本地任务数据。",
            href: "/download",
          },
        ],
        stage: {
          eyebrow: "工作台视角",
          title: "桌面执行在本地，账号只管理访问入口。",
          body: "桌面应用负责真正的执行和回放，官网账号只负责身份、下载和后续访问边界。",
          windowLabel: "Aoryn Workbench",
          windowMeta: "Visible runs, local history, recoverable workflow",
          status: "Ready after install",
          railLabel: "Workbench",
          railItems: ["Agent", "Chat", "Timeline", "History"],
          focusLabel: "当前主线",
          focusTitle: "任务 → 执行 → 时间线",
          focusBody: "把一次桌面任务拆成你能观察、暂停、恢复和交接的一条工作链。",
          chips: ["Visible execution", "Local-first data", "Recoverable runs"],
          metrics: [
            { label: "云端保存", value: "身份与下载权限" },
            { label: "运行记录", value: "保留在本地" },
            { label: "桌面端", value: "安装后可直接使用" },
          ],
        },
        cta: {
          eyebrow: "开始使用",
          title: "了解产品后登录下载，安装完成后直接进入本地工作台。",
          body: "Aoryn 不会把你的任务历史、截图和设置自动上传到云端。账号只负责官网身份和安装包访问，桌面端负责实际工作流。",
          primaryCta: "前往下载",
          secondaryCta: "登录 / 注册",
        },
      },
      product: {
        meta: {
          title: "产品 | Aoryn",
          description: "Aoryn 如何把可见执行、本地优先和可恢复工作流整合成一个桌面产品。",
        },
        hero: {
          eyebrow: "产品",
          title: "不是只会回答，而是能把执行过程完整交给你看。",
          body: "Aoryn 用工作台把目标理解、桌面动作、截图回放和恢复入口连成同一条产品路径。",
        },
        pillars: {
          eyebrow: "核心能力",
          title: "三条主线，定义 Aoryn 是什么。",
          body: "它不是开发者面板的集合，而是一套面向真实任务闭环的桌面产品体验。",
          items: [
            {
              note: "Visible execution",
              title: "执行不是黑盒，而是你看得见的过程",
              body: "任务推进、截图变化和运行状态始终留在工作台里，而不是消失在一段不可见的后台逻辑中。",
            },
            {
              note: "Local-first",
              title: "工作数据留在设备，不被账号接管",
              body: "历史、截图、模型设置和浏览器设置继续保存在本地，账号只负责身份和下载入口。",
            },
            {
              note: "Recoverable workflow",
              title: "停下来之后，依然能从当前状态继续",
              body: "你可以回看时间线、处理人工复核节点，再从中断的位置继续，而不是每次都从头开始。",
            },
          ],
        },
        workflow: {
          eyebrow: "产品流程",
          title: "从一句目标开始，到一条可恢复的桌面工作流结束。",
          body: "Aoryn 的重点不是隐藏复杂度，而是把复杂度整理成你能理解和接手的执行路径。",
          items: [
            { step: "01", title: "说明目标", body: "先告诉 Aoryn 想完成的结果，而不是提前把每一步点击都写死。" },
            { step: "02", title: "读取当前环境", body: "系统结合屏幕、浏览器、窗口和本地设置，决定下一步最合理的动作。" },
            { step: "03", title: "逐步执行并保留证据", body: "每一步动作都会连同截图和状态写进时间线，而不是在黑盒里完成。" },
            { step: "04", title: "必要时暂停、恢复、交接", body: "当流程需要人工确认或中途停止时，你可以直接从当前状态继续推进。" },
          ],
        },
      },
      workspace: {
        meta: {
          title: "工作台 | Aoryn",
          description: "查看 Aoryn 如何把 Agent、聊天、时间线、历史和设置收进同一个桌面工作台。",
        },
        hero: {
          eyebrow: "工作台",
          title: "把 Agent、执行和回放放进一个更像产品的主界面里。",
          body: "安装后直接进入工作台，用 Agent 作为主入口，把聊天、时间线、历史和设置作为辅助能力组织起来。",
        },
        sections: [
          {
            title: "Agent 作为主入口",
            body: "默认视角围绕任务执行展开，聊天作为辅助说明和准备动作，而不是主界面的唯一中心。",
          },
          {
            title: "时间线和截图并排出现",
            body: "结果不会只停留在模型上下文中，而会以运行节点和截图证据的形式保留下来。",
          },
          {
            title: "设置、历史和恢复都在本地",
            body: "模型、浏览器、显示环境和本地偏好仍然写回当前设备，而不是写进账号资料页。",
          },
        ],
        preview: {
          eyebrow: "工作台预览",
          title: "安装完成后就能直接进入的主界面。",
          body: "账号解决的是官网访问和下载权限，桌面应用负责的是本地执行和回放，而数据始终由你的设备掌握。",
          cards: [
            { label: "账号职责", value: "身份与下载" },
            { label: "本地历史", value: "不上传云端" },
            { label: "可见诊断", value: "应用内可查看" },
          ],
        },
      },
      download: {
        meta: {
          title: "下载 | Aoryn",
          description: "登录后下载 Windows 安装包，并明确账号、下载和本地数据之间的边界。",
        },
        hero: {
          eyebrow: "下载",
          title: "下载入口受账号保护，桌面工作流仍然保持本地优先。",
          body: "官网账号用于身份验证和安装包访问。安装完成后，桌面版会直接进入本地工作台，不再追加登录门槛。",
        },
        locked: {
          eyebrow: "需要登录",
          title: "先登录，再下载 Windows 安装包。",
          body: "创建账号并完成邮箱验证后，这里会解锁安装包下载入口。",
          primaryCta: "登录 / 注册",
        },
        unlocked: {
          eyebrow: "Windows 安装包",
          title: "下载桌面版安装包",
          body: "账号只负责官网身份和下载权限。任务、截图、历史和设置仍然不会自动上传到云端。",
          primaryCta: "下载 Windows 安装包",
        },
        packageMeta: {
          version: "版本",
          platform: "平台",
          size: "大小",
          format: "格式",
        },
        steps: {
          eyebrow: "下载路径",
          title: "从官网到桌面工作台，一条清晰的路径。",
          body: "下载保持登录门槛，但桌面端安装完成后会直接进入本地工作台，让首次用户尽快跑通第一条任务。",
          items: [
            { step: "01", title: "了解产品并完成注册", body: "先创建账号并完成邮箱验证，明确你的下载权限和身份信息。" },
            { step: "02", title: "登录后下载安装包", body: "认证成功后，官网会展示受保护的 Windows 安装包下载入口。" },
            { step: "03", title: "安装后直接进入工作台", body: "桌面版不会追加二次登录门槛，打开后就能开始本地任务和回放。" },
          ],
        },
        faq: {
          eyebrow: "FAQ",
          title: "关于账号、下载和本地数据边界",
          body: "云端只保留真正需要放在云端的最少信息。",
          items: [
            {
              question: "云端会保存我的任务、截图和历史吗？",
              answer: "不会。当前云端只保存账号身份、邮箱、显示名称和认证会话。任务、截图、运行记录和本地设置都留在设备上。",
            },
            {
              question: "为什么下载需要先登录？",
              answer: "这样可以把官网、安装包和后续访问状态统一到同一条产品路径里，同时清楚区分账号权限和本地工作数据。",
            },
            {
              question: "离线时还能查看本地历史吗？",
              answer: "可以。离线只会影响注册、登录和下载，不会影响桌面应用读取已经存在于本地的任务和历史记录。",
            },
          ],
        },
      },
      terms: {
        meta: {
          title: "用户协议 | Aoryn",
          description: "说明账号、下载权限、本地优先数据模式以及用户责任边界。",
        },
        hero: {
          eyebrow: "用户协议",
          title: "Aoryn 产品使用条款",
          body: "这是一份面向当前产品阶段的简明使用说明，重点说明账号、下载权限和本地优先的数据边界。",
        },
        sections: [
          {
            title: "1. 账号与访问",
            body: "Aoryn 账号用于注册、登录、下载权限和未来访问边界。你应当妥善保管自己的登录凭据，不得冒用他人身份。",
          },
          {
            title: "2. 本地优先的数据模式",
            body: "当前版本不会把任务历史、截图、运行记录、模型设置或缓存同步到云端。你需要自行负责本地设备和相关文件的安全。",
          },
          {
            title: "3. 允许与禁止的使用方式",
            body: "你可以在遵守适用法律和本协议的前提下使用 Aoryn，不得利用产品实施违法、侵权、破坏系统或绕过访问控制的行为。",
          },
          {
            title: "4. 产品变化与访问策略",
            body: "随着产品迭代，我们可能调整下载方式、账号要求、界面结构和功能边界。重大变化会在官网或产品内提示中说明。",
          },
          {
            title: "5. 最终判断责任",
            body: "Aoryn 旨在帮助你更清晰地管理桌面执行流程，但你仍需对登录、支付、提交、删除等敏感操作的最终结果承担判断责任。",
          },
        ],
      },
      privacy: {
        meta: {
          title: "隐私政策 | Aoryn",
          description: "说明当前哪些信息保存在云端，哪些工作数据继续留在你的设备本地。",
        },
        hero: {
          eyebrow: "隐私政策",
          title: "Aoryn 隐私说明",
          body: "我们尽量把身份和工作数据的边界划清：账号在云端，任务和运行记录留在本地。",
        },
        sections: [
          {
            title: "1. 云端最少身份信息",
            body: "当前账号系统只保存邮箱、显示名称、账号创建时间和登录所需的认证会话信息，用于注册、登录和下载权限控制。",
          },
          {
            title: "2. 本地工作数据",
            body: "任务、聊天记录、截图、运行时间线、模型设置、浏览器设置、显示修正和缓存都保存在设备本地，不会自动同步到云端。",
          },
          {
            title: "3. 登录与下载日志",
            body: "当你登录官网或请求受保护的下载入口时，认证服务和网络基础设施可能处理必要的访问与安全日志，用于限流、安全和故障排查。",
          },
          {
            title: "4. 你的控制权",
            body: "你可以通过退出登录、清理本地数据或后续申请删除账号的方式，控制身份信息和本地工作数据的保留范围。",
          },
          {
            title: "5. 更新说明",
            body: "如果账号体系、下载策略或云端保存范围发生变化，本页面会同步更新，反映最新的数据边界。",
          },
        ],
      },
    },
  },
  "en-US": {
    brandDescriptor: "Visible execution, local-first desktop workbench",
    langSwitch: "中",
    nav: {
      home: "Home",
      product: "Product",
      workspace: "Workbench",
      download: "Download",
      login: "Login",
      register: "Register",
      account: "Account",
      logout: "Logout",
      menu: "Open menu",
      closeMenu: "Close menu",
      terms: "Terms",
      privacy: "Privacy",
    },
    auth: {
      tabs: {
        login: "Login",
        register: "Register",
      },
      dialogTitle: "Access Aoryn",
      dialogBody: "Your account only handles website identity and download access. Tasks, screenshots, history, and settings remain on your device.",
      signedInAs: "Signed in as",
      signedOut: "Signed out",
      loginTitle: "Sign in to download the desktop app",
      registerTitle: "Create your Aoryn account",
      loginButton: "Login",
      registerButton: "Create account",
      logoutButton: "Logout",
      submitBusy: "Working...",
      verifyHint: "Registration succeeded. Please verify your email before signing in.",
      fields: {
        name: "Display name",
        email: "Email",
        password: "Password",
        confirmPassword: "Confirm password",
        namePlaceholder: "How should we call you?",
        emailPlaceholder: "you@example.com",
        passwordPlaceholder: "At least 8 characters",
        confirmPasswordPlaceholder: "Type it again",
        acceptTermsPrefix: "I agree to the",
        acceptTermsLink: "Aoryn Terms",
        acceptPrivacyMiddle: "and",
        acceptPrivacyLink: "Privacy Notice",
      },
      validation: {
        nameRequired: "Please enter a display name.",
        nameShort: "Display name must be at least 2 characters.",
        emailRequired: "Please enter an email address.",
        emailInvalid: "Please enter a valid email address.",
        passwordRequired: "Please enter a password.",
        passwordShort: "Password must be at least 8 characters.",
        confirmRequired: "Please confirm your password.",
        confirmMismatch: "The passwords do not match.",
        acceptRequired: "Please accept the terms and privacy notice.",
      },
      messages: {
        loginSuccess: "Signed in successfully.",
        logoutSuccess: "Signed out successfully.",
        registerSuccess: "Account created. Please verify your email before signing in.",
        networkError: "The authentication service is currently unavailable.",
      },
    },
    footer: {
      tagline: "Identity in the cloud, workflow and run history on your device.",
      copyright: "Aoryn. All rights reserved.",
    },
    pages: {
      home: {
        meta: {
          title: "Aoryn | Visible execution, local-first desktop workbench",
          description: "Keep desktop work visible, recoverable, and ready for handoff.",
        },
        hero: {
          eyebrow: "Local-first desktop agent workbench",
          title: "Keep desktop work visible, recoverable, and ready for handoff.",
          body: "Aoryn brings conversation, execution, screenshots, and timelines into one workbench so you can always see what happened, where it paused, and how to continue.",
          primaryCta: "Download desktop app",
          secondaryCta: "View workbench",
          tertiaryCta: "Explore product",
        },
        cards: [
          {
            title: "From one goal to real execution",
            body: "Start with the outcome you want, then let the desktop execution layer move step by step in the current environment.",
            href: "/product",
          },
          {
            title: "Every run stays reviewable and recoverable",
            body: "Screenshots, status changes, and key steps stay aligned on one timeline you can reopen later.",
            href: "/workspace",
          },
          {
            title: "Sign in before download, open the workbench after install",
            body: "The account handles identity and release access. Your local work data stays outside that boundary.",
            href: "/download",
          },
        ],
        stage: {
          eyebrow: "Workbench view",
          title: "Desktop execution stays local while the account only manages access.",
          body: "The desktop app owns execution and replay. The website account only owns identity, downloads, and future access boundaries.",
          windowLabel: "Aoryn Workbench",
          windowMeta: "Visible runs, local history, recoverable workflow",
          status: "Ready after install",
          railLabel: "Workbench",
          railItems: ["Agent", "Chat", "Timeline", "History"],
          focusLabel: "Current flow",
          focusTitle: "Task -> Execution -> Timeline",
          focusBody: "Turn one desktop goal into a chain you can observe, pause, resume, and hand off.",
          chips: ["Visible execution", "Local-first data", "Recoverable runs"],
          metrics: [
            { label: "Cloud scope", value: "Identity and download access" },
            { label: "Run history", value: "Stays local" },
            { label: "Desktop app", value: "Ready after install" },
          ],
        },
        cta: {
          eyebrow: "Get started",
          title: "Explore the product, sign in to download, then launch straight into the local workbench.",
          body: "Aoryn does not automatically upload your task history, screenshots, or settings. The account only gates website identity and installer access while the desktop app owns the workflow.",
          primaryCta: "Go to download",
          secondaryCta: "Login / Register",
        },
      },
      product: {
        meta: {
          title: "Product | Aoryn",
          description: "See how Aoryn combines visible execution, local-first data boundaries, and recoverable workflows into one desktop product.",
        },
        hero: {
          eyebrow: "Product",
          title: "Not just answers, but a full execution path you can actually inspect.",
          body: "Aoryn turns task understanding, desktop action, screenshot replay, and recovery points into one product flow.",
        },
        pillars: {
          eyebrow: "Core ideas",
          title: "Three product principles define Aoryn.",
          body: "It is not a loose collection of developer panels. It is a desktop product built around the first successful task loop.",
          items: [
            {
              note: "Visible execution",
              title: "Execution stays observable instead of hidden",
              body: "Progress, screenshots, and run state remain inside the workbench instead of disappearing behind a single opaque response.",
            },
            {
              note: "Local-first",
              title: "Work data stays on the device",
              body: "History, screenshots, model settings, and browser settings remain local while the account only handles website identity and downloads.",
            },
            {
              note: "Recoverable workflow",
              title: "A stopped run can continue from where it paused",
              body: "You can reopen timelines, review human-check moments, and keep moving from the current state instead of restarting everything.",
            },
          ],
        },
        workflow: {
          eyebrow: "Workflow",
          title: "Start from one goal and finish with a recoverable desktop run.",
          body: "Aoryn does not try to hide complexity. It organizes complexity into an execution path you can understand and take over.",
          items: [
            { step: "01", title: "Describe the goal", body: "Tell Aoryn what outcome you want instead of hard-coding every click in advance." },
            { step: "02", title: "Read the current environment", body: "The system combines screen state, browser state, windows, and local settings before choosing the next action." },
            { step: "03", title: "Execute and keep evidence", body: "Each action is written into the timeline together with screenshots and status updates." },
            { step: "04", title: "Pause, recover, and hand off when needed", body: "When a flow needs human review or stops midway, you can continue from the current state instead of starting over." },
          ],
        },
      },
      workspace: {
        meta: {
          title: "Workbench | Aoryn",
          description: "See how Aoryn organizes agent runs, chat, timelines, history, and settings inside one desktop workbench.",
        },
        hero: {
          eyebrow: "Workbench",
          title: "A main interface that feels like a product, not a debug surface.",
          body: "Launch directly into a workbench where Agent is the primary entry, chat is supportive, and timelines, history, and settings stay within reach.",
        },
        sections: [
          {
            title: "Agent-first entry",
            body: "The main view is centered on getting work done. Chat helps with setup and rewriting, but it no longer competes with the run workflow.",
          },
          {
            title: "Timelines and screenshots side by side",
            body: "Results do not vanish into model context. They stay visible as timeline entries and captured evidence you can reopen later.",
          },
          {
            title: "Settings and recovery stay local",
            body: "Model, browser, display, and local preference changes keep living on the current device instead of moving into the account profile.",
          },
        ],
        preview: {
          eyebrow: "Workbench preview",
          title: "The main desktop surface you enter right after install.",
          body: "The account owns website access and downloads. The desktop app owns execution and replay. Your device still owns the data.",
          cards: [
            { label: "Account scope", value: "Identity and downloads" },
            { label: "History", value: "Local-only" },
            { label: "Diagnostics", value: "Visible in-app" },
          ],
        },
      },
      download: {
        meta: {
          title: "Download | Aoryn",
          description: "Sign in to download the Windows installer and understand the boundary between account access and local work data.",
        },
        hero: {
          eyebrow: "Download",
          title: "Downloads are protected by account access, while the desktop workflow stays local-first.",
          body: "The website account handles identity verification and installer access. After installation, the desktop app opens straight into the local workbench without another sign-in gate.",
        },
        locked: {
          eyebrow: "Sign-in required",
          title: "Sign in before downloading the Windows installer.",
          body: "Create an account, verify your email, then return here to unlock the protected installer.",
          primaryCta: "Login / Register",
        },
        unlocked: {
          eyebrow: "Windows installer",
          title: "Download the desktop installer",
          body: "Sign-in only handles website identity and download access. Tasks, screenshots, history, and settings are still not automatically uploaded to the cloud.",
          primaryCta: "Download Windows installer",
        },
        packageMeta: {
          version: "Version",
          platform: "Platform",
          size: "Size",
          format: "Format",
        },
        steps: {
          eyebrow: "Install flow",
          title: "One clear path from website to desktop workbench.",
          body: "Download remains gated by account access, but the desktop app is designed to get first-time users to their first successful task quickly.",
          items: [
            { step: "01", title: "Learn the product and register", body: "Create an account and verify your email so your download access and identity are in place." },
            { step: "02", title: "Sign in and get the installer", body: "Once authenticated, the site reveals the protected Windows installer entry." },
            { step: "03", title: "Install and open the workbench", body: "The desktop app launches directly into the local workbench instead of asking for another sign-in." },
          ],
        },
        faq: {
          eyebrow: "FAQ",
          title: "About accounts, downloads, and local data boundaries",
          body: "Only the pieces that truly belong in the cloud are stored there.",
          items: [
            {
              question: "Does the cloud store my runs, screenshots, and history?",
              answer: "No. The cloud currently stores account identity, email, display name, and auth session data only. Tasks, screenshots, run records, and settings remain on the device.",
            },
            {
              question: "Why is download gated by sign-in?",
              answer: "A gated installer keeps the website, installer access, and future account states inside one product path while keeping a clean boundary around local work data.",
            },
            {
              question: "Can I still read local history while offline?",
              answer: "Yes. Offline mode affects registration, sign-in, and downloads, but it does not stop the desktop app from reading work that already exists on your device.",
            },
          ],
        },
      },
      terms: {
        meta: {
          title: "Terms | Aoryn",
          description: "Understand the account model, protected downloads, local-first data boundary, and operator responsibility.",
        },
        hero: {
          eyebrow: "Terms",
          title: "Aoryn product terms",
          body: "This short-form policy explains the current account model, download access, and local-first data boundary for the product.",
        },
        sections: [
          {
            title: "1. Accounts and access",
            body: "Aoryn accounts are used for sign-up, sign-in, download access, and future access boundaries. You are responsible for the credentials tied to your account.",
          },
          {
            title: "2. Local-first data model",
            body: "The current product does not sync your task history, screenshots, run records, model settings, or cache to the cloud. You remain responsible for the security of the device and local files you use with Aoryn.",
          },
          {
            title: "3. Allowed and disallowed use",
            body: "You may use Aoryn in accordance with applicable law and these terms. You must not use the product for unlawful, abusive, infringing, destructive, or access-control-bypassing activity.",
          },
          {
            title: "4. Product and access changes",
            body: "We may change download flow, account requirements, UI structure, and feature boundaries as the product evolves. Material changes will appear on the website or in-product notices.",
          },
          {
            title: "5. Operator judgment",
            body: "Aoryn is designed to make desktop execution more visible, but you remain responsible for reviewing sensitive actions such as login, purchase, submission, and deletion flows.",
          },
        ],
      },
      privacy: {
        meta: {
          title: "Privacy | Aoryn",
          description: "See what Aoryn stores in the cloud today and what remains local on your device.",
        },
        hero: {
          eyebrow: "Privacy",
          title: "Aoryn privacy notice",
          body: "We keep a deliberate boundary between cloud identity and local work data: the account lives in the cloud, while work history remains on your device.",
        },
        sections: [
          {
            title: "1. Minimum cloud identity data",
            body: "The current account system stores email, display name, account creation time, and the auth session data needed for sign-in and protected downloads.",
          },
          {
            title: "2. Local work data",
            body: "Tasks, chat history, screenshots, run timelines, model settings, browser settings, display overrides, and cache remain on the current device and are not automatically synced to the cloud.",
          },
          {
            title: "3. Sign-in and download logs",
            body: "When you sign in or request a protected download, the auth service and network infrastructure may process the minimum access and security logs required to operate the service.",
          },
          {
            title: "4. Your controls",
            body: "You can sign out, clear local data, or later request account removal to control how much identity or local work data remains available.",
          },
          {
            title: "5. Updates",
            body: "If the account system, download policy, or cloud storage scope changes, this page will be updated to reflect the new boundary.",
          },
        ],
      },
    },
  },
};
