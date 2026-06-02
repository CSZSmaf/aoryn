# Aoryn 开发者文档

## 1. 项目定位

Aoryn 是一个本地优先的桌面 Agent 工作台。

它把三层能力放进同一套 Web 壳里：

- 普通对话模式：基于当前模型配置进行问答，不直接执行桌面操作
- Agent 模式：执行任务、回放步骤、展示截图和运行结果
- 开发控制台：查看 provider 状态、payload、时间线和调试信息

当前项目目标不是做多 Agent 编排，而是把“单任务执行 + 本地可观测 + 可配置模型”打磨成稳定、可持续演进的桌面 Agent 产品。

## 2. 本地启动

### 2.1 环境要求

- Python 3.11+
- Windows 桌面环境
- 已安装浏览器，默认优先使用 `msedge`
- 可选：LM Studio 或任意 OpenAI-compatible 模型服务

### 2.2 日常源码测试

```bash
.\start_dev.bat
```

这会在源码模式下启动 Aoryn 工作台，并尽量同时拉起托管浏览器运行时。源码测试默认使用独立端口，避免误连已经安装并运行中的 Aoryn。默认地址：

```text
Dashboard: http://127.0.0.1:8766
Browser Runtime: http://127.0.0.1:38992
```

等价 Python 命令：

```bash
python scripts/dev_start.py
```

常用开发参数：

```bash
python scripts/dev_start.py --ui web --no-browser-tab
python scripts/dev_start.py --no-managed-browser
python scripts/dev_start.py --port 8770 --managed-browser-port 39000
python scripts/dev_start.py --print-commands
```

开发启动器会生成 `.tmp/source-test/config.yaml`，并把托管浏览器运行时端口写入该源码测试配置。托管浏览器源码运行使用 `.tmp/source-test/browser-profile`，不会写入安装版的 AppData 运行目录。确认源码测试结果后，再生成 EXE 或安装包做发布验证。

### 2.3 逻辑基准测试

打包前可以先跑本地确定性任务逻辑基准，用来检查常见规划路径，例如桌面应用启动、浏览器后续点击、计算器表达式、快捷键和另存为流程：

```bash
python scripts/run_logic_benchmark.py
```

### 2.4 单独入口与发布验证

底层入口仍然保留，方便排查：

```bash
python run_agent.py
python run_agent.py ui --browser --no-browser --port 8766 --config .tmp/source-test/config.yaml
python run_browser.py --port 38992 --profile-root .tmp/source-test/browser-profile --config-path .tmp/source-test/config.yaml
```

生成 EXE 或安装包只用于发布前验证，不需要作为日常测试步骤。

## 3. 目录结构

```text
desktop_agent/
  dashboard.py             HTTP server、静态资源和 API 路由
  chat_support.py          普通对话模式、帮助文档注入、handoff 判断
  controller.py            Agent 主流程和 dashboard 启动
  config.py                AgentConfig 与配置加载
  provider_tools.py        provider 探测、模型目录、LM Studio 集成
  logger.py                运行目录、步骤日志与 summary 输出
  history.py               历史运行读取与序列化
  dashboard_assets/
    index.html             前端 HTML 外壳
    styles.css             前端样式
    app.js                 前端状态、渲染和交互逻辑
    icons/                 logo 和应用图标
```

## 4. 模式设计

### 4.1 普通对话模式

普通对话模式用于：

- 回答产品问题
- 指导模型、浏览器和 provider 配置
- 帮助用户把需求整理成更适合交给 Agent 的任务

它走 `POST /api/chat` 和 `POST /api/chat/stream`，但不会直接触发桌面执行。

如果用户消息明显属于桌面或浏览器执行请求，后端会返回 `agent_handoff`，前端据此渲染“转到 Agent 执行”的入口。

### 4.2 Agent 模式

Agent 模式复用现有执行核心：

1. 截图与感知
2. 生成计划
3. 校验动作
4. 执行动作
5. 写入 `runs/<run_id>/`
6. 由 dashboard 轮询并回放到 Web 界面

### 4.3 开发控制台

开发控制台仍然保留，但不再作为主导航模式显示。

适合用于：

- 检查 provider 连接状态
- 查看 payload 和时间线
- 调试运行细节
- 回归问题排查

推荐从设置里的高级入口进入。

### 4.4 复杂任务：研究 → 综合 → 撰写

Aoryn 把“像人一样坐在电脑前完成复杂任务”拆成三段能力，分别对应大脑、眼、手：

1. 研究（眼 + 手）：当一个检索子目标下游接着综合/撰写步骤时，`browser_dom` 不再"搜完就停"，
   而是**先搜索、再用 `browser_dom_extract` 读取结果页正文**，把抽取到的内容（`extracted_text`）连同
   标题/URL 一起沉淀进 `ExecutionState.workspace` 研究笔记（`[extract]` 优先于 `[web]`）。撰写时综合的是
   **真实页面内容**而非仅搜索摘要，文档更有据可依。纯搜索任务（无下游消费者）保持单步行为不变；
   可用 `research_extract_enabled` 关闭。
2. 综合（大脑）：`desktop_agent/composer.py` 的 `DocumentComposer` 复用当前配置的模型端点
   （LM Studio / OpenAI 兼容），把研究笔记 + 任务目标“想成”一篇结构化长文（标题 + `##` 分节）。
   模型不可用或离线时，回退到确定性大纲，保证 dry-run、基准测试与离线场景仍产出可读文档。
3. 撰写（手）：`document_authoring` capability 先聚焦目标编辑器（Word / 记事本 / WPS），再用
   `insert_text` 动作把成稿一次性写入。`insert_text` 优先走剪贴板粘贴（支持中文、换行、长文），
   不可用时回退到逐行键入，长度上限由 `max_document_length` 控制。

触发方式：任务里出现明确的“写/撰写/整理到/总结/生成报告 …”等动作词，或点名编辑器（Word/记事本/WPS）。
例如“搜索北京旅游攻略然后整理到 Word 里”会被拆成“检索”子目标（走 `browser_dom`）和“整理到 Word”
子目标（走 `document_authoring`）。纯粹的“打开记事本并输入 demo”不会被当成撰写任务。

### 4.5 自主规划：从一句高层目标到研究→撰写

更进一步，对“产出一份需要先查资料的成果”这类高层目标，Agent 会**自己规划步骤**，不需要你把
检索/写作拆开说。`planner.py` 的 `_extract_deliverable_plan` 识别“动词（写/规划/整理/做/撰写/生成…）+
成果名词（报告/计划/方案/攻略/总结/行程/指南…）”的单句目标，自动展开成：

1. `搜索{主题}` → `browser_dom`（自主联网检索，结果沉淀进研究笔记）
2. `撰写{主题}{成果}` → `document_authoring`（调用模型综合研究笔记，写入编辑器）

并标注依赖关系（先研究后撰写）。例如：

- “规划一个北京三日游” → 搜索北京三日游 → 撰写北京三日游行程
- “写一份关于电动汽车的报告” → 搜索电动汽车 → 撰写电动汽车报告
- “create a study plan for calculus” → search for calculus → write the calculus plan

这两个子目标都是低风险（联网检索 + 本地写入），因此在默认的 `conservative` 自主模式下会
**自动放行、端到端执行**，无需逐步确认。撰写子目标只有在“写入动作真正执行进编辑器”后才判定完成
（开编辑器本身不算完成），避免“开了 Word 就以为写完了”。要更激进、连中/高风险步骤也不打断，可把
`desktop_autonomy_mode` 设为 `autonomous`。

### 4.6 自主规划之二：初始规划 model-first + 执行中自适应再规划

**初始规划 model-first**：`_should_use_structured_task_graph` 的 hybrid 路由已从“按关键词/置信度判断”
改为“**非平凡任务一律交给模型**”——只有确定性的单步动作（开应用、单次搜索/访问、计算等，以及浏览器
命令）走快速的启发式/规则路径，其余（多步、产出成果、以及**没有任何关键词命中的新任务**，如“帮我对比三款
笔记软件并给出建议”）都由模型来制定计划。关键词启发式（`_extract_deliverable_plan` 等）因此降级为
**离线兜底 + 能力提示**，不再决定是否动用模型。无模型端点时自动回退启发式（确定性降级）。

**智能澄清（模型决定何时反问）**：模型先**理解用户意图**——能懂就直接规划，对可合理假设的小细节不
啰嗦；只有当请求**确实太模糊/缺关键信息**时（例如“帮我处理一下”没有对象），才返回一个 `clarification`
字段（一句具体问题）或一个 `goal_type=clarify` 子目标，由系统弹出反问而不是瞎猜。例如“帮我处理一下”→
反问“你想让我处理什么？”，而“规划上海周末两日游”→直接出 8 步计划。关键词启发式只兜底极端空指令。

在此之上，真正的“引导 Agent 制定计划”是让**模型在执行过程中自己反思、修订计划**：当 Agent 检索到
新信息后，`orchestrator.reflect_on_plan` → `planner.reflect_on_plan`
会把**目标 + 已完成步骤 + 剩余步骤 + 已获取的知识（研究笔记/事实/世界模型）**交给模型，让它判断
“剩下的计划还能不能达成目标”，据此**插入/调整剩余子目标**（例如发现信息不足就先补查一项再写）。

要点：

- **模型来规划，系统来引导**：决定“何时反思”用的是运行时状态（刚刚是否做了 `browser_dom` 检索、
  是否还有剩余工作），不是从你的措辞里抠行为；具体“改成什么计划”由模型产出。
- **护栏**：每次运行最多反思 `max_plan_reflections`（默认 2）次；已完成的子目标只保留不改；模型
  返回与现状一致就不动；离线/无模型端点时直接跳过（确定性降级）；新计划若抬高风险等级会触发
  stage review。
- **触发点**：当前对 `research_summary`（研究→产出成果）类任务，在一次检索子目标完成且仍有剩余
  工作时反思一次。

例：跑“写一份关于电动汽车的报告”，模型在第一轮检索后插入“搜索电动汽车充电桩分布”，于是实际执行
变成 `检索 → 检索(模型新增) → 打开Word → 写入`。开关：`plan_reflection_enabled` / `max_plan_reflections`。

相关配置：

- `composition_enabled`：是否允许综合步骤调用模型（关闭则只用确定性大纲）。
- `document_default_app`：未点名编辑器时的默认目标（默认 `word`）。
- `max_document_length`：单次写入的最大字符数。

### 4.7 执行层：稳健的按步骤点击（手）

桌面应用的点击优先走 UI Automation（`uia_invoke`/`uia_set_value` 等，按可见标签定位），比 VLM 猜坐标
准得多。`executor._resolve_uia_element` 不再只做**精确标签匹配**——以前标签差一点（`登 录` vs `登录`、
`OK (确定)`、中英混排、部分文字）就解析失败、整步报错。现在按一组策略**依次回退**：

1. 显式 selector（`auto_id`/`control_type`/`class_name` 等）
2. 精确标签 → 不区分大小写的**包含匹配** → pywinauto `best_match` 模糊
3. 按控件类型（Button/MenuItem/Hyperlink/ListItem/TabItem/CheckBox…）+ 包含匹配
4. 兜底：遍历后代控件，按归一化标签（去空格、去符号）做**模糊评分**挑最佳

所以"点击登录"即使真实标签是"登 录 (Login)"也能命中正确元素。逻辑抽成 `_resolve_uia_element_in_window`
便于单测（`test_executor.py` 用假窗口覆盖精确失败→包含命中、全失败→模糊后代扫描、无匹配则报错）。

**坐标兜底（再加一层保险）。** 元素找到后，点击本身也分级回退，单步只有在所有手段都失败时才报错：

1. `element.invoke()`（程序化调用，最稳）
2. 控件不支持 invoke → `element.click_input()`
3. invoke / click_input 都失败（控件被遮挡、不在前台）→ 取元素**矩形中心**，用 pyautogui 按**像素坐标**点击
4. 元素**完全找不到** → 若动作带有模型给的 `(x, y)`，退回到该坐标点击

第 3、4 层就是"截图/坐标兜底"：UIA 定位或点击失效时，仍能用坐标把这一步点下去。坐标兜底会发
`coordinate_fallback` 进度事件，便于在 Dashboard 观察何时降级。相关单测覆盖 invoke→click_input→矩形
中心三级回退、解析失败时用模型坐标、无坐标则报错，以及 `_uia_element_center` 的矩形/`mid_point` 读取。

### 4.8 OpenAI Computer Use API 模式

若希望行为更接近 Codex computer use 的“截图 → 模型判断下一步 → 执行动作 → 再截图”循环，可以把
`planner_mode` 设为 `computer_use`，并使用 OpenAI API：

```yaml
planner_mode: computer_use
model_provider: openai_api
model_base_url: https://api.openai.com/v1
model_name: gpt-5.5
model_auto_discover: false
desktop_autonomy_mode: autonomous
shell_start_mode: main
```

该模式优先走 Responses API 的内置 `computer` 工具；如果配置的是 gptsapi 等 OpenAI-compatible
中转服务，且 `/responses` 不支持 `computer` 工具，系统会自动降级到 `/chat/completions` 的视觉 JSON
动作规划，仍然由 API 根据截图返回坐标/键盘动作。如果配置仍保留默认的本地 LM Studio 地址，
系统会改用 `https://api.openai.com/v1`，不会探测或加载本地模型。模型返回的
`click`、`keypress`、`type`、`scroll`、`drag`、`wait` 等动作会被映射到现有安全执行器；每一步执行后
仍由运行循环重新截屏；Responses 路径会用 `previous_response_id` + `computer_call_output` 回传 `computer_screenshot` 给 API，
并做本地验证。API key 可填入 `model_api_key`，也可通过 `OPENAI_API_KEY` 环境变量提供。若显式配置
`model_name: computer-use-preview`，系统会保留旧版 `computer_use_preview` 工具兼容路径。
软件刚打开时默认显示主界面；一旦任务开始执行，桌面壳会自动收起主界面，只保留悬浮窗显示执行状态。

真实 API smoke test 可以只请求下一步动作、不执行鼠标键盘：

```bash
python scripts/smoke_computer_use_api.py
python scripts/smoke_computer_use_api.py --config path/to/config.yaml
```

### 4.9 软件插件接口

特定软件可以通过插件补充更稳的识别、规划和验证逻辑。插件模块通过 `plugin_modules` 启用，模块中暴露
`register_plugin(context)`，然后调用：

```python
def register_plugin(context):
    context.register_driver(MyAppDriver())
    context.register_capability(MyAppCapability())
```

`driver` 负责判断当前窗口是不是目标软件，并声明偏好的 capability；`capability` 负责为该软件生成更稳定的
动作和验证证据。这样通用 `computer_use` 截图坐标能力仍作为兜底，后续可以逐个为常用软件添加专用插件。
仓库内提供了一个最小示例插件：`desktop_agent.software_plugins.notepad`。

## 5. 关键配置

`desktop_agent/config.py` 中的 `AgentConfig` 仍然是统一配置来源。

常用字段包括：

- `model_provider`
- `model_base_url`
- `model_name`
- `model_api_key`
- `model_auto_discover`
- `model_structured_output`
- `shell_start_mode`
- `plugin_modules`
- `plugin_fail_fast`
- `composition_enabled`
- `document_default_app`
- `max_document_length`
- `max_steps`
- `pause_after_action`
- `browser_dom_backend`
- `browser_dom_timeout`
- `browser_channel`
- `browser_executable_path`
- `browser_headless`

当前内置的 DOM backend 只有 `playwright`。

## 6. Dashboard 接口

### 6.1 元数据与运行概览

- `GET /api/meta`
  - 返回 UI 元数据、默认配置、provider 选项、浏览器选项等
- `GET /api/overview`
  - 返回 `meta + active_job + jobs + runs`
- `GET /api/runs/:id`
  - 返回某次运行的 summary、timeline 和截图

### 6.2 Provider 接口

- `POST /api/provider/models`
  - 拉取模型目录、已加载模型和 provider 错误
- `POST /api/provider/load-model`
  - 目前仅对 `lmstudio_local` 可用

### 6.3 普通对话接口

- `POST /api/chat`
- `POST /api/chat/stream`

请求体包括：

- `messages`
- 可选 `config_overrides`
- 可选 `session_meta`

`session_meta.locale` 会影响：

- 注入的帮助文档语言
- 回复语言
- handoff 文案语言

### 6.4 帮助文档

- `GET /api/help?locale=zh-CN|en-US`

该接口返回开发者文档镜像：

- `zh-CN` 读取 `README.md`
- `en-US` 读取 `README.en.md`

## 7. 前端状态流

前端主状态集中在 `desktop_agent/dashboard_assets/app.js`。

关键状态包括：

- `uiMode`
  - `chat / agent / developer`
- 本地 chat session
  - 存在浏览器本地存储中
- Agent 历史
  - 来自 `/api/overview` 和 `/api/runs/:id`
- 帮助中心
  - 按当前 locale 拉取 `/api/help`
- 设置
  - 任务配置写入 `config_overrides`
  - UI 偏好保存在本地

左侧历史栏当前混合渲染两类记录：

- 普通对话 session
- Agent run

统一按最近更新时间排序。

历史记录的恢复规则：

- chat session 和 Agent run 都会在重开程序后继续保留
- 前端会额外持久化“上次选中的历史项”，并在启动后优先恢复
- 如果上次选中的是 chat，但该 session 已失效，且当前处于 chat 模式，则回退到最近更新的非空 chat session
- 如果上次选中的是 run，但该 run 已不在当前概览列表中，则回到 Agent 欢迎态，不会强行跳到别的 run

## 8. 帮助中心与多语言

帮助中心展示的是开发者文档，而不是面向终端用户的操作说明。

设计原则：

- 中文界面加载中文开发文档
- 英文界面加载英文开发文档
- 普通对话模式使用同语言的开发文档作为产品知识底座

因此，`README.md` 和 `README.en.md` 的修改会直接影响：

- `/api/help`
- 普通对话模式的产品问答

## 9. 静态壳

前端静态资源位于 `desktop_agent/dashboard_assets/`。

关键文件：

- `index.html`
- `styles.css`
- `app.js`

源码运行时仍然可以直接用浏览器访问 dashboard，但不再支持“安装为应用”。修改静态壳后，记得同步提升资源版本号，避免浏览器继续命中旧缓存。

## 10. 常见排障

### 10.1 帮助中心语言不切换

检查：

- `/api/help?locale=en-US` 是否返回英文文档
- 前端 `loadHelpContent()` 是否带上当前 locale
- 切换语言后是否清空了旧的帮助缓存

### 10.2 LM Studio 已启动但没有模型

检查：

- `Base URL` 是否为 `http://127.0.0.1:1234/v1`
- 设置打开时是否触发 `POST /api/provider/models`
- `/v1/models` 是否真的返回了模型列表
- 当前 `model_name` 是否被旧值覆盖

### 10.3 页面还是旧 UI

优先排查缓存：

1. 关闭当前 dashboard 标签页
2. 重新打开页面
3. 如果仍是旧壳，执行 `Ctrl+F5`
4. 检查资源 query version 是否一起提升

## 11. 后续建议

当前最适合继续迭代的方向：

- 为普通对话补更细粒度的 handoff 分类
- 为帮助中心增加目录和锚点
- 为运行中 timeline 增加实时增量流
- 为开发控制台拆出更明确的诊断面板
- 为桌面壳资源和 favicon 统一生成流程

## 12. 变更约定

如果继续维护这个项目，建议遵守这些约定：

- 帮助中心优先写给开发者，而不是终端用户
- 静态说明性文案尽量少，优先保留状态反馈
- 普通对话模式不自动执行任务
- 修改静态壳时同步提升缓存版本
- 新增接口补 pytest，前端主逻辑至少运行 `node --check`

## 13. 发布包说明

面向普通用户的主安装包是：

- `Aoryn-Setup-<version>.exe`

额外会生成以下发布物，供留档和审核使用：

- `Aoryn-<version>-win64.zip`
  - 目录版压缩包
- `Aoryn-Review-<version>.zip`
  - 审核包，包含安装包、目录版 zip、源码快照、发布清单、校验和与双语 README
- `Aoryn-Source-<version>.zip`
  - 源码与资源快照，不包含构建产物、运行历史、截图、日志和缓存
- `release-manifest.json`
- `SHA256SUMS.txt`

建议这样使用：

- 普通用户分发 `Setup.exe`
- 审核、留档或交给模型审阅时分发 `Review.zip`
- 目录版 zip 用于手工检查或备份

`0.1.6` 为当前补丁版本，在保留显示识别结果展示与手动运行时纠正能力的同时，移除了桌面端的登录门槛，并继续把官网与安装包下载流程保留在基于 Cloudflare Pages Functions + R2 的登录保护发布链路上。

审核用的源码快照是“代码与资源快照”，不是“运行历史归档”：

- 保留代码、前端资源、安装器脚本、构建脚本和文档
- 排除 `runs/`、历史截图、本地日志、缓存和其他机器相关痕迹，避免让审核方被旧界面或旧运行结果带偏
