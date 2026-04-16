# Aoryn Website Deployment

This website is deployed as a Cloudflare Pages project backed by:

- `https://aoryn.org` as the primary production site
- `https://www.aoryn.org` redirecting to `https://aoryn.org`
- `GET /api/downloads/windows-installer` as the gated installer route
- an R2 bucket binding named `AORYN_DOWNLOADS` that stores `Aoryn-Setup-0.1.5.exe`

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
AORYN_WINDOWS_INSTALLER_KEY=Aoryn-Setup-0.1.5.exe
```

Add an R2 bucket binding:

```text
Binding name: AORYN_DOWNLOADS
Bucket: <the bucket that stores release installers>
```

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

- upload `Aoryn-Setup-0.1.5.exe`
- keep the object key aligned with `AORYN_WINDOWS_INSTALLER_KEY`
- optionally bind `downloads.aoryn.org` if you want a dedicated file-hosting domain for operations or auditing

The website no longer depends on a public download URL as its main entry point. Public R2 domains are optional operational detail, not the button target shown to users.

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
2. Upload `Aoryn-Setup-0.1.5.exe` to the bound R2 bucket.
3. Confirm `AORYN_WINDOWS_INSTALLER_KEY` matches the uploaded object key.
4. Trigger a production Pages deployment.
5. Sign in on `https://aoryn.org/download` and verify the protected download flow.

## 7. Verification Checklist

- GitHub shows the `main` branch code
- Cloudflare Pages build succeeds
- the `*.pages.dev` preview works
- `https://aoryn.org` loads the site
- `https://www.aoryn.org` redirects to `https://aoryn.org`
- unauthenticated requests to `https://aoryn.org/api/downloads/windows-installer` return `401`
- authenticated requests download `Aoryn-Setup-0.1.5.exe`
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
