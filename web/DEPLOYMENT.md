# Aoryn Website Deployment

This website is deployed as a Cloudflare Pages project backed by:

- `https://aoryn.org` as the primary production site
- `https://www.aoryn.org` redirecting to `https://aoryn.org`
- `GET /api/downloads/windows-installer` as the gated installer route
- an optional R2 bucket binding named `AORYN_DOWNLOADS` that can stream `latest/Aoryn-Setup-latest.exe`
- a fallback public installer URL on `downloads.aoryn.org` for Pages environments where R2 bindings cannot be published

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

Set these Pages environment variables:

```text
SUPABASE_URL=<your Supabase project URL>
SUPABASE_ANON_KEY=<your Supabase anon key>
SUPABASE_SITE_URL=https://aoryn.org
AORYN_WINDOWS_INSTALLER_KEY=latest/Aoryn-Setup-latest.exe
AORYN_WINDOWS_INSTALLER_URL=https://downloads.aoryn.org/latest/Aoryn-Setup-latest.exe
```

Optional: add an R2 bucket binding if your Pages project can publish Functions with R2 successfully:

```text
Binding name: AORYN_DOWNLOADS
Bucket: <the bucket that stores release installers>
```

If Cloudflare Pages rejects the R2 binding during deploy, remove the binding and keep `AORYN_WINDOWS_INSTALLER_URL` set. The authenticated download route will then redirect signed-in users to the fallback installer URL instead of streaming from R2 directly.

The frontend does not use `VITE_DOWNLOAD_URL`. The download button always points to the authenticated route:

```text
/api/downloads/windows-installer
```

## 3. Custom Domains

Bind these domains in Cloudflare Pages:

```text
aoryn.org
www.aoryn.org
```

Recommended behavior:

- `aoryn.org` serves the main site
- `www.aoryn.org` redirects to `aoryn.org` with a `301` Bulk Redirect

If `aoryn.org` is not already managed by Cloudflare DNS, add the zone first and update the domain registrar nameservers to Cloudflare.

Recommended redirect setup:

- Source URL: `www.aoryn.org`
- Target URL: `https://aoryn.org`
- Status code: `301`
- Enable: preserve query string, subpath matching, preserve path suffix

## 4. R2 Release Object

On the R2 bucket that stores the installer:

- upload the versioned installer, for example `Aoryn-Setup-0.1.5.exe`
- upload or overwrite `latest/Aoryn-Setup-latest.exe`
- keep `AORYN_WINDOWS_INSTALLER_KEY` pointed at the stable latest alias
- keep `downloads.aoryn.org` pointed at the bucket if you want the authenticated route to fall back to a public installer URL

The website button still points to `/api/downloads/windows-installer`. When R2 bindings are healthy, the Function streams from R2. When Pages cannot publish the binding, the Function can fall back to `AORYN_WINDOWS_INSTALLER_URL` after login.

To avoid manual Cloudflare dashboard updates for every installer release, use the local publish helper:

```bash
python -m pip install --user -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File .\publish_installer.ps1
```

Set these environment variables once on the publishing machine:

```text
AORYN_R2_ACCOUNT_ID=<your Cloudflare account id>
AORYN_R2_BUCKET=aoryn-downloads
AORYN_R2_ACCESS_KEY_ID=<your R2 access key id>
AORYN_R2_SECRET_ACCESS_KEY=<your R2 secret access key>
AORYN_R2_PUBLIC_BASE_URL=https://downloads.aoryn.org
AORYN_R2_LATEST_KEY=latest/Aoryn-Setup-latest.exe
```

Optional, to have the publish step also sync Cloudflare Pages production env vars and retry the current deployment:

```text
AORYN_CF_API_TOKEN=<Cloudflare API token with Pages edit access>
AORYN_PAGES_PROJECT=aoryn
```

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

## 6. Production Release Checklist

1. Push the `main` branch changes that contain the new website and release metadata.
2. Run `powershell -ExecutionPolicy Bypass -File .\publish_installer.ps1` to build the installer, upload both the versioned object and the stable latest alias, and optionally resync Pages download env vars.
3. If R2 bindings work in your Pages project, keep `AORYN_DOWNLOADS`; otherwise keep `AORYN_WINDOWS_INSTALLER_URL` pointed at the latest alias.
4. Sign in on `https://aoryn.org/download` and verify the protected download flow.

## 7. Verification Checklist

- GitHub shows the `main` branch code
- Cloudflare Pages build succeeds
- the `*.pages.dev` preview works
- `https://aoryn.org` loads the site
- `https://www.aoryn.org` redirects to `https://aoryn.org`
- unauthenticated requests to `https://aoryn.org/api/downloads/windows-installer` return `401`
- authenticated requests download the current installer release
- the website download button points to `/api/downloads/windows-installer`

## 8. References

- Cloudflare Pages Git integration:
  `https://developers.cloudflare.com/pages/get-started/git-integration/`
- Cloudflare Pages custom domains:
  `https://developers.cloudflare.com/pages/configuration/custom-domains/`
- Cloudflare Pages www redirect:
  `https://developers.cloudflare.com/pages/how-to/www-redirect/`
- Cloudflare R2 public buckets and custom domains:
  `https://developers.cloudflare.com/r2/data-access/public-buckets/`
