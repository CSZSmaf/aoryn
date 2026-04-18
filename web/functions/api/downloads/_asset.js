import { jsonResponse, mergeHeaders, resolveBrowserSession } from "../auth/_shared.js";

function guessContentType(fileName) {
  const lower = String(fileName || "").trim().toLowerCase();
  if (lower.endsWith(".exe")) return "application/vnd.microsoft.portable-executable";
  if (lower.endsWith(".zip")) return "application/zip";
  return "application/octet-stream";
}

function buildFallbackUrl(context, objectKey, urlEnvName, defaultKey) {
  const override = String(context.env[urlEnvName] || "").trim();
  if (override) {
    return override;
  }

  const normalizedKey = String(objectKey || defaultKey).trim() || defaultKey;
  return `https://downloads.aoryn.org/${normalizedKey}`;
}

function redirectToAsset(url, extraHeaders) {
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

export function createProtectedDownloadHandler({
  defaultKey,
  keyEnvName,
  urlEnvName,
  unauthenticatedMessage,
}) {
  return async function onRequestGet(context) {
    const resolved = await resolveBrowserSession(context);
    if (!resolved.authenticated) {
      return jsonResponse(
        {
          message: unauthenticatedMessage,
        },
        401,
        resolved.headers,
      );
    }

    const objectKey = String(context.env[keyEnvName] || defaultKey).trim() || defaultKey;
    const fallbackUrl = buildFallbackUrl(context, objectKey, urlEnvName, defaultKey);
    const bucket = context.env.AORYN_DOWNLOADS;
    if (!bucket || typeof bucket.get !== "function") {
      return redirectToAsset(fallbackUrl, resolved.headers);
    }

    const object = await bucket.get(objectKey);
    if (!object) {
      return redirectToAsset(fallbackUrl, resolved.headers);
    }

    const headers = new Headers();
    if (typeof object.writeHttpMetadata === "function") {
      object.writeHttpMetadata(headers);
    }
    headers.set("content-type", headers.get("content-type") || guessContentType(objectKey));
    headers.set("content-disposition", `attachment; filename="${objectKey.split("/").pop() || objectKey}"`);
    headers.set("cache-control", "private, no-store");

    return new Response(object.body, {
      status: 200,
      headers: mergeHeaders(headers, resolved.headers),
    });
  };
}
