# Aoryn Website Deployment

This website is designed for:

- `https://aoryn.org` as the primary production site
- `https://www.aoryn.org` redirecting to `https://aoryn.org`
- `https://downloads.aoryn.org/Aoryn-Setup-0.1.4.exe` as the Windows installer URL

## 1. GitHub

Repository:

```text
CSZSmaf/aoryn
```

Production branch:

```text
main
```

## 2. Cloudflare Pages

Create a Pages project with Git integration and use:

```text
Framework preset: React
Root directory: web
Build command: npm run build
Build output directory: dist
```

Add these environment variables in Pages:

```text
VITE_DOWNLOAD_URL=https://downloads.aoryn.org/Aoryn-Setup-0.1.4.exe
VITE_REGISTER_ENDPOINT=
```

The registration endpoint can stay empty until the backend is ready.

## 3. Custom Domains

Bind these domains in Cloudflare Pages:

```text
aoryn.org
www.aoryn.org
```

Recommended behavior:

- `aoryn.org` serves the main site
- `www.aoryn.org` redirects to `aoryn.org`

If `aoryn.org` is not already managed by Cloudflare DNS, add the zone first and update the domain registrar nameservers to Cloudflare.

## 4. R2 Download Domain

On the R2 bucket that stores the installer:

- enable the public/custom domain setting
- bind `downloads.aoryn.org`
- keep the installer object path as:

```text
/Aoryn-Setup-0.1.4.exe
```

After the custom download domain becomes active, trigger a new Pages deployment so the website uses the production download hostname.

## 5. Local Build Check

From the `web` directory:

```bash
npm install
npm run build
```

The build output should be written to:

```text
web/dist
```

## 6. Verification Checklist

- GitHub shows the `main` branch code
- Cloudflare Pages build succeeds
- the `*.pages.dev` preview works
- `https://aoryn.org` loads the site
- `https://www.aoryn.org` redirects to `https://aoryn.org`
- `https://downloads.aoryn.org/Aoryn-Setup-0.1.4.exe` downloads the installer
- the website download button points to `downloads.aoryn.org`
