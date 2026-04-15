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

### 2.2 启动命令

```bash
python run_agent.py
```

默认会启动本地 dashboard，并尝试打开：

```text
http://127.0.0.1:8765
```

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

## 5. 关键配置

`desktop_agent/config.py` 中的 `AgentConfig` 仍然是统一配置来源。

常用字段包括：

- `model_provider`
- `model_base_url`
- `model_name`
- `model_api_key`
- `model_auto_discover`
- `model_structured_output`
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

`0.1.4` 为当前补丁版本，新增了显示识别结果展示与手动运行时纠正能力，用户现在可以查看自动识别到的显示器、DPI/缩放和工作区结果，并在识别不准时进行覆盖修正。

审核用的源码快照是“代码与资源快照”，不是“运行历史归档”：

- 保留代码、前端资源、安装器脚本、构建脚本和文档
- 排除 `runs/`、历史截图、本地日志、缓存和其他机器相关痕迹，避免让审核方被旧界面或旧运行结果带偏
