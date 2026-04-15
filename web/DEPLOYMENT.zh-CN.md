# Aoryn 官网部署说明

本官网的目标上线结构如下：

- 主站：`https://aoryn.org`
- `www` 跳转：`https://www.aoryn.org` -> `https://aoryn.org`
- 安装包下载：`https://downloads.aoryn.org/Aoryn-Setup-0.1.4.exe`

## 1. GitHub 仓库

GitHub 仓库固定为：

```text
CSZSmaf/aoryn
```

生产分支固定为：

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

在 Pages 的环境变量中添加：

```text
VITE_DOWNLOAD_URL=https://downloads.aoryn.org/Aoryn-Setup-0.1.4.exe
VITE_REGISTER_ENDPOINT=
```

注册后端还没接入前，`VITE_REGISTER_ENDPOINT` 可以保持为空。

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

推荐的跳转规则：

- Source URL: `www.aoryn.org`
- Target URL: `https://aoryn.org`
- Status code: `301`
- 勾选保留 query string、子路径匹配、路径后缀保留

## 4. R2 下载域名

在存放安装包的 R2 bucket 上：

- 开启公开访问 / 自定义域名
- 绑定 `downloads.aoryn.org`
- 保持安装包对象路径为：

```text
/Aoryn-Setup-0.1.4.exe
```

当下载域名生效后，重新触发一次 Pages 部署，让官网按钮使用正式下载域名。

## 5. 本地构建验证

在 `web` 目录下执行：

```bash
npm install
npm run build
```

构建产物会输出到：

```text
web/dist
```

## 6. 上线后检查清单

- GitHub 仓库的 `main` 分支代码可见
- Cloudflare Pages 首次构建成功
- `*.pages.dev` 预览地址可以正常访问
- `https://aoryn.org` 可以打开官网
- `https://www.aoryn.org` 会跳转到 `https://aoryn.org`
- `https://downloads.aoryn.org/Aoryn-Setup-0.1.4.exe` 可以正常下载安装包
- 官网下载按钮指向 `downloads.aoryn.org`

## 7. 官方参考文档

- Cloudflare Pages Git 集成：
  `https://developers.cloudflare.com/pages/get-started/git-integration/`
- Cloudflare Pages 自定义域名：
  `https://developers.cloudflare.com/pages/configuration/custom-domains/`
- Cloudflare Pages `www -> 根域名` 跳转：
  `https://developers.cloudflare.com/pages/how-to/www-redirect/`
- Cloudflare R2 公共访问与自定义域名：
  `https://developers.cloudflare.com/r2/data-access/public-buckets/`
