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
    hosting: "Cloudflare R2",
    downloadUrl:
      import.meta.env.VITE_DOWNLOAD_URL ||
      "https://pub-f8c02666c6c44dd0ae78a6c0f430bee6.r2.dev/Aoryn-Setup-0.1.4.exe",
  },
  registration: {
    endpoint: import.meta.env.VITE_REGISTER_ENDPOINT || "",
  },
};
