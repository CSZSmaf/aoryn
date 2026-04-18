import { createProtectedDownloadHandler } from "./_asset.js";

const DEFAULT_WINDOWS_INSTALLER_KEY = "latest/Aoryn-Setup-latest.exe";

export const onRequestGet = createProtectedDownloadHandler({
  defaultKey: DEFAULT_WINDOWS_INSTALLER_KEY,
  keyEnvName: "AORYN_WINDOWS_INSTALLER_KEY",
  urlEnvName: "AORYN_WINDOWS_INSTALLER_URL",
  unauthenticatedMessage: "Please sign in to download Aoryn.",
});
