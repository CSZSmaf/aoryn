export const siteConfig = {
  siteName: "Aoryn",
  domain: "aoryn.org",
  localeStorageKey: "aoryn-site.locale",
  release: {
    version: "0.1.4",
    channel: "Windows Installer",
    fileName: "Aoryn-Setup-0.1.4.exe",
    fileSize: "191.63 MB",
    platform: "Windows 10 / 11",
    packageType: "EXE",
    hosting: "Cloudflare R2 via downloads.aoryn.org",
    protectedDownloadPath: "/api/downloads/windows-installer",
    downloadUrl:
      import.meta.env.VITE_DOWNLOAD_URL ||
      "https://downloads.aoryn.org/Aoryn-Setup-0.1.4.exe",
  },
  auth: {
    registerEndpoint: "/api/auth/register",
    loginEndpoint: "/api/auth/login",
    logoutEndpoint: "/api/auth/logout",
    meEndpoint: "/api/auth/me",
    refreshEndpoint: "/api/auth/refresh",
  },
};
