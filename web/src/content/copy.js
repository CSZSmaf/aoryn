export const siteCopy = {
  "zh-CN": {
    brandDescriptor: "可见的桌面 Agent 工作台",
    langSwitch: "EN",
    nav: {
      home: "首页",
      product: "产品",
      workspace: "界面",
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
      dialogTitle: "登录 Aoryn",
      dialogBody: "账号只用于身份验证与下载权限，任务、历史、截图与配置仍然只保存在你的设备本地。",
      signedInAs: "当前账号",
      signedOut: "未登录",
      loginTitle: "继续使用桌面工作台",
      registerTitle: "创建 Aoryn 账号",
      loginButton: "登录",
      registerButton: "创建账号",
      logoutButton: "退出登录",
      submitBusy: "处理中...",
      verifyHint: "注册成功，请先前往邮箱完成验证，再回来登录。",
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
        acceptPrivacyMiddle: "与",
        acceptPrivacyLink: "《Aoryn 隐私政策》",
      },
      validation: {
        nameRequired: "请输入显示名称。",
        nameShort: "显示名称至少 2 个字符。",
        emailRequired: "请输入邮箱地址。",
        emailInvalid: "请输入有效的邮箱地址。",
        passwordRequired: "请输入密码。",
        passwordShort: "密码至少需要 8 位。",
        confirmRequired: "请再次输入密码。",
        confirmMismatch: "两次输入的密码不一致。",
        acceptRequired: "请先同意用户协议与隐私政策。",
      },
      messages: {
        loginSuccess: "登录成功。",
        logoutSuccess: "已退出登录。",
        registerSuccess: "注册成功，请先完成邮箱验证。",
        networkError: "认证服务暂时不可用，请稍后重试。",
      },
    },
    footer: {
      tagline: "身份在云端，工作流仍留在本地。",
      copyright: "Aoryn. All rights reserved.",
    },
    pages: {
      home: {
        meta: {
          title: "Aoryn | 可见的桌面 Agent 工作台",
          description: "让桌面执行保持可见、可控、可恢复。",
        },
        hero: {
          eyebrow: "Windows 桌面 Agent 工作台",
          title: "让桌面执行保持可见，而不是失控。",
          body: "Aoryn 把对话、执行、截图与运行记录收进一个本地优先的工作台里。",
          primaryCta: "登录后下载",
          secondaryCta: "创建账号",
          tertiaryCta: "查看产品",
        },
        cards: [
          {
            title: "从对话到执行",
            body: "先明确目标，再把下一步交给桌面执行层。",
            href: "/product",
          },
          {
            title: "运行链路可回看",
            body: "截图、步骤与状态沿同一条时间线保留。",
            href: "/workspace",
          },
          {
            title: "下载前先完成登录",
            body: "账号只管理身份与下载权限，不同步本地工作数据。",
            href: "/download",
          },
        ],
        stage: {
          eyebrow: "主舞台",
          title: "本地执行，云端只保留最小身份。",
          body: "桌面工作台负责真实执行，账号只负责登录、下载与后续的授权边界。",
          windowLabel: "Aoryn Workspace",
          windowMeta: "Visible runs, local history, protected access",
          status: "Authenticated access",
          railLabel: "Workspace",
          railItems: ["Runs", "Chat", "Screenshots", "Diagnostics"],
          focusLabel: "Current focus",
          focusTitle: "Task → Execution → Timeline",
          focusBody: "把一次桌面任务拆成能被观察、被暂停、被恢复的一条链路。",
          chips: ["Desktop-first", "Protected downloads", "Local-only history"],
          metrics: [
            { label: "Cloud data", value: "Identity only" },
            { label: "Run history", value: "Stays local" },
            { label: "Desktop mode", value: "Gated" },
          ],
        },
        cta: {
          eyebrow: "Ready",
          title: "先登录，再解锁安装与桌面工作台。",
          body: "你不会把任务历史上传到云端，但你需要一个账号来下载并启动产品。",
          primaryCta: "前往下载页",
          secondaryCta: "登录 / 注册",
        },
      },
      product: {
        meta: {
          title: "产品 | Aoryn",
          description: "Aoryn 如何把对话、执行与桌面观察收进同一个入口。",
        },
        hero: {
          eyebrow: "产品",
          title: "不是普通聊天，而是一条可见的执行链。",
          body: "Aoryn 把任务理解、桌面执行和回放记录并在同一个工作台里。",
        },
        pillars: {
          eyebrow: "核心能力",
          title: "三件事情足够说明它是什么。",
          body: "首页只负责入口，细节放在这里说清楚。",
          items: [
            {
              note: "Task planning",
              title: "先确定目标，再生成下一步动作",
              body: "任务不是一次性吐出，而是按当前屏幕与环境逐步推进。",
            },
            {
              note: "Desktop execution",
              title: "每一步都落到真实桌面",
              body: "浏览器、窗口、截图与视觉判断都围绕当前设备执行。",
            },
            {
              note: "Traceability",
              title: "执行后果可回看，可中断，可恢复",
              body: "运行时间线与截图保留在本地，方便你复盘和接管。",
            },
          ],
        },
        workflow: {
          eyebrow: "工作流",
          title: "从一句目标到桌面动作，保持同一条链路。",
          body: "这不是把脚本藏起来，而是把执行过程尽量公开给使用者。",
          items: [
            { step: "01", title: "输入目标", body: "先定义你要完成什么，而不是手工编排每个点击。" },
            { step: "02", title: "观察当前环境", body: "系统读取屏幕、窗口、浏览器与本地设置作为上下文。" },
            { step: "03", title: "逐步执行", body: "Agent 每次只做一个明确动作，并写入运行时间线。" },
            { step: "04", title: "保留本地记录", body: "任务结果、截图与配置仍只保存在你的机器上。" },
          ],
        },
      },
      workspace: {
        meta: {
          title: "界面 | Aoryn",
          description: "Aoryn 工作台如何呈现对话、截图、运行时间线与本地诊断。",
        },
        hero: {
          eyebrow: "界面",
          title: "把对话、执行与回放合并成一个工作台。",
          body: "启动后先登录，再进入可见的桌面执行界面，而不是直接暴露一堆脚本细节。",
        },
        sections: [
          {
            title: "历史与运行时间线",
            body: "每次任务都会保留自己的运行记录和最近状态，方便回看和恢复。",
          },
          {
            title: "截图与状态并排出现",
            body: "屏幕结果不会只停留在模型上下文里，而是以截图和事件的形式被保存。",
          },
          {
            title: "设置留在本地",
            body: "模型、浏览器、显示环境和本地偏好设置仍写回当前设备，而不是账号云端。",
          },
        ],
        preview: {
          eyebrow: "Workspace preview",
          title: "登录后才会解锁的主界面",
          body: "账号负责身份，会话负责入口，本地文件继续负责你的工作数据。",
          cards: [
            { label: "Auth", value: "Required on launch" },
            { label: "History", value: "Local-only" },
            { label: "Diagnostics", value: "Visible in-app" },
          ],
        },
      },
      download: {
        meta: {
          title: "下载 | Aoryn",
          description: "登录后下载 Windows 安装包，并了解认证与本地数据边界。",
        },
        hero: {
          eyebrow: "下载",
          title: "下载权限现在受登录态保护。",
          body: "公开直链将退役，安装包只通过认证后的下载接口提供。",
        },
        locked: {
          eyebrow: "Locked",
          title: "先登录，再下载 Windows 安装包。",
          body: "你可以先创建账号并完成邮箱验证。下载按钮只会在登录成功后出现。",
          primaryCta: "登录 / 注册",
        },
        unlocked: {
          eyebrow: "Windows Installer",
          title: "下载桌面版安装包",
          body: "登录只用于验证身份与下载权限，任务、截图、历史与配置不会被上传到云端。",
          primaryCta: "下载 Windows 安装包",
        },
        packageMeta: [
          { label: "版本", value: "0.1.4" },
          { label: "平台", value: "Windows 10 / 11" },
          { label: "体积", value: "191.63 MB" },
          { label: "格式", value: "EXE Installer" },
        ],
        steps: {
          eyebrow: "安装流程",
          title: "下载前后你会看到什么。",
          body: "下载和启动都改成基于账号的门槛，但执行数据仍在本机。",
          items: [
            { step: "01", title: "注册并验证邮箱", body: "首次使用前先完成账号创建与邮箱验证。" },
            { step: "02", title: "登录并下载", body: "认证后下载按钮才会解锁，不再暴露公开安装包直链。" },
            { step: "03", title: "启动后再次登录", body: "桌面应用会先验证本地会话，再解锁工作台。" },
          ],
        },
        faq: {
          eyebrow: "FAQ",
          title: "关于账号与本地数据",
          body: "只保留下载和认证真正需要的几件事情。",
          items: [
            {
              question: "云端会保存我的任务和截图吗？",
              answer: "不会。当前只保存账号、邮箱、显示名与认证会话，任务、历史、截图和运行记录都留在本地。",
            },
            {
              question: "为什么现在要登录后才能下载？",
              answer: "下载门槛让官网、软件与账号体系保持同一套入口，也为后续授权状态留出清晰边界。",
            },
            {
              question: "没有网络时还能看本地历史吗？",
              answer: "可以。离线只会影响注册、登录与下载，不影响本地已有任务与记录的读取。",
            },
          ],
        },
      },
      terms: {
        meta: {
          title: "用户协议 | Aoryn",
          description: "Aoryn 的账号、下载、使用边界与责任说明。",
        },
        hero: {
          eyebrow: "用户协议",
          title: "Aoryn 产品使用条款",
          body: "这是一份面向当前产品阶段的简明使用条款，重点说明账号、下载权限和本地数据边界。",
        },
        sections: [
          {
            title: "1. 账号与访问",
            body: "Aoryn 账号用于注册、登录、下载权限和后续授权边界。你应当为自己的登录凭据负责，不得冒用他人身份。",
          },
          {
            title: "2. 本地优先的数据模式",
            body: "当前版本不会把任务历史、截图、运行记录、模型配置和缓存同步到云端。你应自行负责本地设备与本地文件的安全。",
          },
          {
            title: "3. 许可与限制",
            body: "你可以在遵守适用法律和本条款的前提下使用 Aoryn。你不得利用本产品实施违法、侵权、破坏系统或绕过访问控制的行为。",
          },
          {
            title: "4. 产品变化",
            body: "我们可能调整下载方式、账号策略、界面和功能边界。涉及重大变化时，会通过官网或产品内提示进行说明。",
          },
          {
            title: "5. 责任说明",
            body: "Aoryn 旨在帮助你更清晰地管理桌面执行流程，但你仍需对最终操作结果承担判断责任，尤其是在登录、支付、提交和删除场景中。",
          },
        ],
      },
      privacy: {
        meta: {
          title: "隐私政策 | Aoryn",
          description: "Aoryn 当前会在云端和本地分别保存什么数据。",
        },
        hero: {
          eyebrow: "隐私政策",
          title: "Aoryn 隐私说明",
          body: "我们把云端与本地的边界尽量划清：身份放云端，工作数据留在设备本地。",
        },
        sections: [
          {
            title: "1. 云端最小资料",
            body: "当前账号体系仅保存邮箱、显示名、账号创建时间以及认证所需的会话信息，用于注册、登录和下载权限控制。",
          },
          {
            title: "2. 本地数据",
            body: "任务、对话、截图、运行记录、模型设置、浏览器设置、显示环境修正和缓存都继续保存在本地目录，不会自动上传到 Supabase。",
          },
          {
            title: "3. 下载与认证日志",
            body: "当你登录官网或请求下载时，认证服务与 Cloudflare 可能记录必要的访问日志，用于安全、限流和故障排查。",
          },
          {
            title: "4. 你的控制权",
            body: "你可以通过注销账号、退出登录或清理本地数据目录来控制身份信息与本地工作数据的保留范围。",
          },
          {
            title: "5. 联系与更新",
            body: "当产品身份系统、下载方式或云端保存范围发生变化时，本页面会同步更新。",
          },
        ],
      },
    },
  },
  "en-US": {
    brandDescriptor: "Visible desktop agent workspace",
    langSwitch: "中",
    nav: {
      home: "Home",
      product: "Product",
      workspace: "Workspace",
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
      dialogBody: "The cloud only stores identity and download access. Tasks, screenshots, history, and config still stay on your device.",
      signedInAs: "Signed in as",
      signedOut: "Signed out",
      loginTitle: "Unlock the desktop workspace",
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
      tagline: "Identity in the cloud, workflow on your device.",
      copyright: "Aoryn. All rights reserved.",
    },
    pages: {
      home: {
        meta: {
          title: "Aoryn | Visible desktop agent workspace",
          description: "Keep desktop execution visible, reviewable, and under your control.",
        },
        hero: {
          eyebrow: "Windows desktop agent workspace",
          title: "Keep desktop execution visible instead of opaque.",
          body: "Aoryn keeps conversation, execution, screenshots, and run history inside one local-first workspace.",
          primaryCta: "Download after login",
          secondaryCta: "Create account",
          tertiaryCta: "Explore product",
        },
        cards: [
          {
            title: "From conversation to action",
            body: "Start with a goal, then hand the next step to the desktop execution layer.",
            href: "/product",
          },
          {
            title: "Runs stay reviewable",
            body: "Screenshots, steps, and state changes stay aligned on one timeline.",
            href: "/workspace",
          },
          {
            title: "Downloads are gated",
            body: "The account only manages identity and access. Work data still stays local.",
            href: "/download",
          },
        ],
        stage: {
          eyebrow: "Main stage",
          title: "Local execution, cloud identity only.",
          body: "The desktop workspace handles real execution. The account only handles sign-in, downloads, and future access boundaries.",
          windowLabel: "Aoryn Workspace",
          windowMeta: "Visible runs, local history, protected access",
          status: "Authenticated access",
          railLabel: "Workspace",
          railItems: ["Runs", "Chat", "Screenshots", "Diagnostics"],
          focusLabel: "Current focus",
          focusTitle: "Task → Execution → Timeline",
          focusBody: "Break a desktop task into a chain that can be observed, paused, and resumed.",
          chips: ["Desktop-first", "Protected downloads", "Local-only history"],
          metrics: [
            { label: "Cloud data", value: "Identity only" },
            { label: "Run history", value: "Stays local" },
            { label: "Desktop mode", value: "Gated" },
          ],
        },
        cta: {
          eyebrow: "Ready",
          title: "Sign in first, then unlock downloads and the desktop workspace.",
          body: "You do not upload your task history, but you do need an account to download and launch the product.",
          primaryCta: "Go to download",
          secondaryCta: "Login / Register",
        },
      },
      product: {
        meta: {
          title: "Product | Aoryn",
          description: "How Aoryn keeps planning, desktop execution, and review inside one workflow.",
        },
        hero: {
          eyebrow: "Product",
          title: "Not just chat, but a visible execution chain.",
          body: "Aoryn keeps task understanding, desktop action, and local review inside one workspace.",
        },
        pillars: {
          eyebrow: "Core capabilities",
          title: "Three ideas explain what it is.",
          body: "The homepage stays light. The details live here.",
          items: [
            {
              note: "Task planning",
              title: "Start with a goal, not a brittle script",
              body: "Tasks move step by step according to the current screen, browser, and local environment.",
            },
            {
              note: "Desktop execution",
              title: "Every action lands on the real desktop",
              body: "Browser sessions, windows, screenshots, and visual reasoning all stay grounded in the current machine.",
            },
            {
              note: "Traceability",
              title: "Every run stays reviewable",
              body: "Run timelines and screenshots stay local so you can inspect and take over when needed.",
            },
          ],
        },
        workflow: {
          eyebrow: "Workflow",
          title: "From one goal to real desktop steps.",
          body: "The system stays observable instead of hiding everything behind a single answer.",
          items: [
            { step: "01", title: "Define the goal", body: "Describe the outcome you want instead of manually chaining every click." },
            { step: "02", title: "Observe the environment", body: "The system reads the current screen, browser, and local runtime context." },
            { step: "03", title: "Execute step by step", body: "Each action is committed into the run timeline rather than disappearing into a black box." },
            { step: "04", title: "Keep the evidence local", body: "Tasks, screenshots, and settings remain on the device instead of syncing to the cloud." },
          ],
        },
      },
      workspace: {
        meta: {
          title: "Workspace | Aoryn",
          description: "How Aoryn combines chat, screenshots, diagnostics, and run history into one interface.",
        },
        hero: {
          eyebrow: "Workspace",
          title: "One workspace for chat, execution, and replay.",
          body: "Sign in first, then unlock the desktop shell instead of exposing a pile of scripts and hidden logs.",
        },
        sections: [
          {
            title: "Runs and timelines",
            body: "Each task keeps its own run record and recent state, so it can be reviewed and resumed later.",
          },
          {
            title: "Screenshots beside state",
            body: "Screen outcomes do not disappear into model context. They stay visible as captured evidence.",
          },
          {
            title: "Settings stay local",
            body: "Model preferences, browser settings, and display overrides still live on the device instead of in the account profile.",
          },
        ],
        preview: {
          eyebrow: "Workspace preview",
          title: "A main interface unlocked only after authentication.",
          body: "The account owns identity, the local app owns the workflow, and the device still owns the data.",
          cards: [
            { label: "Auth", value: "Required on launch" },
            { label: "History", value: "Local-only" },
            { label: "Diagnostics", value: "Visible in-app" },
          ],
        },
      },
      download: {
        meta: {
          title: "Download | Aoryn",
          description: "Download the Windows installer after signing in and verifying your account.",
        },
        hero: {
          eyebrow: "Download",
          title: "Downloads are now protected by sign-in.",
          body: "Public installer links are being retired. The Windows package now sits behind authenticated access.",
        },
        locked: {
          eyebrow: "Locked",
          title: "Sign in before downloading the Windows installer.",
          body: "Create an account, verify your email, then return here to unlock the installer.",
          primaryCta: "Login / Register",
        },
        unlocked: {
          eyebrow: "Windows Installer",
          title: "Download the desktop installer",
          body: "Sign-in only controls identity and download access. Tasks, screenshots, history, and config are still not uploaded to the cloud.",
          primaryCta: "Download Windows installer",
        },
        packageMeta: [
          { label: "Version", value: "0.1.4" },
          { label: "Platform", value: "Windows 10 / 11" },
          { label: "Size", value: "191.63 MB" },
          { label: "Format", value: "EXE Installer" },
        ],
        steps: {
          eyebrow: "Install flow",
          title: "What happens before and after download.",
          body: "Downloads and launch are both gated now, while the actual work data remains local.",
          items: [
            { step: "01", title: "Register and verify", body: "Create an account first and complete the email verification step." },
            { step: "02", title: "Sign in and download", body: "The installer button only appears after a valid authenticated session." },
            { step: "03", title: "Sign in on launch", body: "The desktop app unlocks the workspace only after a valid local session is present." },
          ],
        },
        faq: {
          eyebrow: "FAQ",
          title: "About accounts and local data",
          body: "Only the pieces required for identity and download access are kept in the cloud.",
          items: [
            {
              question: "Does the cloud store my runs and screenshots?",
              answer: "No. The cloud currently stores account identity, email, display name, and auth session data only. Tasks, history, screenshots, and runtime records stay local.",
            },
            {
              question: "Why is download gated now?",
              answer: "A gated installer keeps the website, the desktop app, and the identity model aligned under one entry point and leaves room for future access states.",
            },
            {
              question: "Can I still read local history while offline?",
              answer: "Yes. Offline mode blocks registration, sign-in, and download, but it does not prevent the app from reading local files that already exist on your device.",
            },
          ],
        },
      },
      terms: {
        meta: {
          title: "Terms | Aoryn",
          description: "A short-form product terms page for account, download, and local-first usage boundaries.",
        },
        hero: {
          eyebrow: "Terms",
          title: "Aoryn product terms",
          body: "This short-form policy focuses on the current product stage, including sign-in, download access, and local-first data boundaries.",
        },
        sections: [
          {
            title: "1. Accounts and access",
            body: "Aoryn accounts are used for sign-up, sign-in, download access, and future access boundaries. You are responsible for the credentials tied to your account.",
          },
          {
            title: "2. Local-first data model",
            body: "The current product does not upload your task history, screenshots, run records, model settings, or cache to the cloud. You remain responsible for the security of the device and local files you use with Aoryn.",
          },
          {
            title: "3. Allowed use",
            body: "You may use Aoryn in accordance with applicable law and these terms. You must not use the product for unlawful, abusive, infringing, or access-control-bypassing activity.",
          },
          {
            title: "4. Product changes",
            body: "We may change download flow, account requirements, UI, and feature boundaries as the product evolves. Material changes will be reflected on the website or in-product notices.",
          },
          {
            title: "5. Operator judgment",
            body: "Aoryn is designed to make desktop execution more visible, but you remain responsible for reviewing and approving sensitive actions such as login, purchase, submission, and deletion flows.",
          },
        ],
      },
      privacy: {
        meta: {
          title: "Privacy | Aoryn",
          description: "What Aoryn currently stores in the cloud and what remains local on the device.",
        },
        hero: {
          eyebrow: "Privacy",
          title: "Aoryn privacy notice",
          body: "The product keeps a hard boundary between cloud identity and local work data.",
        },
        sections: [
          {
            title: "1. Cloud identity data",
            body: "The current account system stores email, display name, account creation time, and the auth session data needed for sign-in and protected downloads.",
          },
          {
            title: "2. Local work data",
            body: "Tasks, chat history, screenshots, run records, model settings, browser settings, display overrides, and cache remain on the device and are not automatically synced to Supabase.",
          },
          {
            title: "3. Download and auth logs",
            body: "When you sign in or request a protected download, Supabase and Cloudflare may process the minimum network and security logs required to operate the service.",
          },
          {
            title: "4. Your controls",
            body: "You can sign out, delete local files, or later request account removal to control how much identity or local data remains available.",
          },
          {
            title: "5. Updates",
            body: "If the account system, download policy, or cloud data boundary changes, this page will be updated to reflect the new scope.",
          },
        ],
      },
    },
  },
};
