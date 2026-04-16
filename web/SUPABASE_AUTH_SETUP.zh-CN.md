# Aoryn Supabase 认证接入说明

这个项目把 Supabase 只用在“身份”和“最小资料”上。
任务、历史、截图、缓存和配置仍然保存在用户本地，不做云同步。

## 1. 先执行 SQL 初始化脚本

在 Supabase SQL Editor 中执行：

- [scripts/supabase_auth_setup.sql](../scripts/supabase_auth_setup.sql)

这个脚本会完成：

- 把 `public.profiles` 继续挂在 `auth.users` 下面
- 加固 `handle_new_user()`，避免触发器异常阻塞注册
- 给 `public.profiles` 开启 RLS
- 只允许用户读取和修改自己的 profile

## 2. 配置 Supabase Auth

在 Supabase Auth 设置里：

- 开启 Email / Password 登录
- 开启邮箱确认
- 把 `Site URL` 设为 `https://aoryn.org`
- 至少加入这些 redirect URL：
  - `https://aoryn.org`
  - `https://www.aoryn.org`
  - `https://aoryn.pages.dev`

## 3. 配置 Cloudflare Pages Functions

在 Pages 项目里配置这些环境变量：

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SITE_URL=https://aoryn.org`

官网注册弹窗默认已经会调用：

- `VITE_REGISTER_ENDPOINT=/api/auth/register`

Pages Functions 暴露的认证接口包括：

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `POST /api/auth/refresh`

## 4. 桌面端的行为边界

桌面端会复用同一套认证接口，但只把会话保存在本地。
在 Windows 上，本地会话使用 DPAPI 保护。

允许进云端的数据：

- 账号本体
- 邮箱
- 显示名称
- 创建时间
- 认证会话 / token

明确不进云端的数据：

- 任务
- 对话历史
- Agent 运行记录
- 截图
- 运行时偏好
- 模型配置
- 缓存
