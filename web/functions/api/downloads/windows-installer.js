import { jsonResponse, mergeHeaders, resolveBrowserSession } from "../auth/_shared.js";

const DEFAULT_WINDOWS_INSTALLER_KEY = "latest/Aoryn-Setup-latest.exe";
const DEFAULT_WINDOWS_INSTALLER_URL = `https://downloads.aoryn.org/${DEFAULT_WINDOWS_INSTALLER_KEY}`;

function guessContentType(fileName) {
  const lower = String(fileName || "").trim().toLowerCase();
  if (lower.endsWith(".exe")) return "application/vnd.microsoft.portable-executable";
  if (lower.endsWith(".zip")) return "application/zip";
  return "application/octet-stream";
}

function buildFallbackUrl(context, objectKey) {
  const override = String(context.env.AORYN_WINDOWS_INSTALLER_URL || "").trim();
  if (override) {
    return override;
  }

  const safeKey = encodeURIComponent(String(objectKey || DEFAULT_WINDOWS_INSTALLER_KEY).trim() || DEFAULT_WINDOWS_INSTALLER_KEY);
  return `https://downloads.aoryn.org/${safeKey}`;
}

function redirectToInstaller(url, extraHeaders) {
  const headers = mergeHeaders(
    {
      location: url,
      "cache-control": "private, no-store",
    },
    extraHeaders,
  );
  return new Response(null, {
    status: 302,
    headers,
  });
}

export async function onRequestGet(context) {
  const resolved = await resolveBrowserSession(context);
  if (!resolved.authenticated) {
    return jsonResponse(
      {
        message: "Please sign in to download Aoryn.",
      },
      401,
      resolved.headers,
    );
  }

  const objectKey = String(context.env.AORYN_WINDOWS_INSTALLER_KEY || DEFAULT_WINDOWS_INSTALLER_KEY).trim();
  const fallbackUrl = buildFallbackUrl(context, objectKey);
  const bucket = context.env.AORYN_DOWNLOADS;
  if (!bucket || typeof bucket.get !== "function") {
    return redirectToInstaller(fallbackUrl, resolved.headers);
  }

  const object = await bucket.get(objectKey);
  if (!object) {
    return redirectToInstaller(fallbackUrl, resolved.headers);
  }

  const headers = new Headers();
  if (typeof object.writeHttpMetadata === "function") {
    object.writeHttpMetadata(headers);
  }
  headers.set("content-type", headers.get("content-type") || guessContentType(objectKey));
  headers.set("content-disposition", `attachment; filename="${objectKey}"`);
  headers.set("cache-control", "private, no-store");

  return new Response(object.body, {
    status: 200,
    headers: mergeHeaders(headers, resolved.headers),
  });
}
