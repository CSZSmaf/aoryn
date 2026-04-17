export const siteConfig = {
  siteName: "Aoryn",
  domain: "aoryn.org",
  localeStorageKey: "aoryn-site.locale",
  release: {
    version: "0.1.11",
    channel: "Windows Installer",
    fileName: "Aoryn-Setup-0.1.11.exe",
    fileSize: "197.15 MB",
    platform: "Windows 10 / 11",
    packageType: "EXE Installer",
    hosting: "Cloudflare Pages Functions + R2",
    protectedDownloadPath: "/api/downloads/windows-installer",
  },
  auth: {
    registerEndpoint: "/api/auth/register",
    loginEndpoint: "/api/auth/login",
    logoutEndpoint: "/api/auth/logout",
    meEndpoint: "/api/auth/me",
    refreshEndpoint: "/api/auth/refresh",
  },
};
