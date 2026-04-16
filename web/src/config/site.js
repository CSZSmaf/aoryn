export const siteConfig = {
  siteName: "Aoryn",
  domain: "aoryn.org",
  localeStorageKey: "aoryn-site.locale",
  release: {
    version: "0.1.6",
    channel: "Windows Installer",
    fileName: "Aoryn-Setup-0.1.6.exe",
    fileSize: "123.73 MB",
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
