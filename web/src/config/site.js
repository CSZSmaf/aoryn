const releaseVersion = "0.1.22";

const downloads = [
  {
    id: "desktop",
    name: "Aoryn",
    channel: "Desktop Agent",
    fileName: `Aoryn-Setup-${releaseVersion}.exe`,
    fileSize: "197.29 MB",
    platform: "Windows 10 / 11",
    packageType: "EXE Installer",
    hosting: "Cloudflare Pages Functions + R2",
    protectedDownloadPath: "/api/downloads/windows-installer",
  },
  {
    id: "browser",
    name: "Aoryn Browser",
    channel: "Managed Browser",
    fileName: `AorynBrowser-Setup-${releaseVersion}.exe`,
    fileSize: "282.60 MB",
    platform: "Windows 10 / 11",
    packageType: "EXE Installer",
    hosting: "Cloudflare Pages Functions + R2",
    protectedDownloadPath: "/api/downloads/windows-browser-installer",
  },
];

export const siteConfig = {
  siteName: "Aoryn",
  domain: "aoryn.org",
  localeStorageKey: "aoryn-site.locale",
  release: {
    version: releaseVersion,
    ...downloads[0],
  },
  downloads,
  auth: {
    registerEndpoint: "/api/auth/register",
    loginEndpoint: "/api/auth/login",
    logoutEndpoint: "/api/auth/logout",
    meEndpoint: "/api/auth/me",
    refreshEndpoint: "/api/auth/refresh",
  },
};
