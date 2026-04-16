# Aoryn 官网部署说明

当前官网部署链路固定为 Cloudflare Pages + Pages Functions + R2：

- `https://aoryn.org` 作为正式官网
- `https://www.aoryn.org` 跳转到 `https://aoryn.org`
- `GET /api/downloads/windows-installer` 作为登录保护的安装包下载入口
- 一个名为 `AORYN_DOWNLOADS` 的 R2 bucket binding，用来存放 `Aoryn-Setup-0.1.6.exe`

## 1. GitHub 仓库

GitHub 仓库：

```text
CSZSmaf/aoryn
```

生产分支：

```text
main
```

## 2. Cloudflare Pages 配置

在 Cloudflare Pages 中使用 Git 集成，并填写：

```text
Framework preset: React
Root directory: web
Build command: npm run build
Build output directory: dist
```

在 Pages 环境变量中配置：

```text
SUPABASE_URL=<你的 Supabase 项目地址>
SUPABASE_ANON_KEY=<你的 Supabase anon key>
SUPABASE_SITE_URL=https://aoryn.org
AORYN_WINDOWS_INSTALLER_KEY=Aoryn-Setup-0.1.6.exe
```

同时添加一个 R2 bucket binding：

```text
Binding name: AORYN_DOWNLOADS
Bucket: <存放安装包的 R2 bucket>
```

前端不再读取 `VITE_DOWNLOAD_URL`。官网下载按钮固定指向：

```text
/api/downloads/windows-installer
```

## 3. 官网域名绑定

在 Cloudflare Pages 项目中绑定以下域名：

```text
aoryn.org
www.aoryn.org
```

推荐行为：

- `aoryn.org` 作为正式官网地址
- `www.aoryn.org` 通过 `301` Bulk Redirect 跳转到 `aoryn.org`

如果 `aoryn.org` 还没有接入 Cloudflare DNS，需要先把域名 zone 加入 Cloudflare，并把注册商 nameserver 改到 Cloudflare。

推荐跳转规则：

- Source URL: `www.aoryn.org`
- Target URL: `https://aoryn.org`
- Status code: `301`
- 勾选保留 query string、子路径匹配、路径后缀保留

## 4. R2 发布物

在存放安装包的 R2 bucket 中：

- 上传 `Aoryn-Setup-0.1.6.exe`
- 保证对象 key 与 `AORYN_WINDOWS_INSTALLER_KEY` 一致
- 如有需要，可以继续绑定 `downloads.aoryn.org` 作为运维或审计用的文件托管域名

官网已经不再把公开下载直链当成主入口。即使保留 `downloads.aoryn.org`，它也只是对象存储层的运维细节，不再是页面下载按钮直接暴露给用户的地址。

## 5. 本地构建验证

在 `web` 目录下执行：

```bash
npm install
npm run build
```

构建产物应输出到：

```text
web/dist
```

## 6. 正式发布清单

1. 将包含新版官网与发布元数据的代码推送到 `main`。
2. 把 `Aoryn-Setup-0.1.6.exe` 上传到绑定的 R2 bucket。
3. 确认 `AORYN_WINDOWS_INSTALLER_KEY` 与上传后的对象 key 一致。
4. 触发一次 Pages 生产部署。
5. 在 `https://aoryn.org/download` 登录后验证受保护下载流程。

## 7. 上线后检查清单

- GitHub 上可以看到 `main` 分支最新代码
- Cloudflare Pages 构建成功
- `*.pages.dev` 预览可正常访问
- `https://aoryn.org` 正常打开
- `https://www.aoryn.org` 会跳转到 `https://aoryn.org`
- 未登录访问 `https://aoryn.org/api/downloads/windows-installer` 时返回 `401`
- 已登录访问时能下载 `Aoryn-Setup-0.1.6.exe`
- 官网下载按钮指向 `/api/downloads/windows-installer`

## 8. 官方参考文档

- Cloudflare Pages Git 集成：
  `https://developers.cloudflare.com/pages/get-started/git-integration/`
- Cloudflare Pages 自定义域名：
  `https://developers.cloudflare.com/pages/configuration/custom-domains/`
- Cloudflare Pages `www -> 根域名` 跳转：
  `https://developers.cloudflare.com/pages/how-to/www-redirect/`
- Cloudflare R2 公共访问与自定义域名：
  `https://developers.cloudflare.com/r2/data-access/public-buckets/`
