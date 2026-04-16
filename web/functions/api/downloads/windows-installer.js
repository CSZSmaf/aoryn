import { jsonResponse, mergeHeaders, resolveBrowserSession } from "../auth/_shared.js";

const DEFAULT_WINDOWS_INSTALLER_KEY = "Aoryn-Setup-0.1.5.exe";

function guessContentType(fileName) {
  const lower = String(fileName || "").trim().toLowerCase();
  if (lower.endsWith(".exe")) return "application/vnd.microsoft.portable-executable";
  if (lower.endsWith(".zip")) return "application/zip";
  return "application/octet-stream";
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

  const bucket = context.env.AORYN_DOWNLOADS;
  if (!bucket || typeof bucket.get !== "function") {
    return jsonResponse(
      {
        message: "AORYN_DOWNLOADS is not configured in Cloudflare Pages.",
      },
      500,
      resolved.headers,
    );
  }

  const objectKey = String(context.env.AORYN_WINDOWS_INSTALLER_KEY || DEFAULT_WINDOWS_INSTALLER_KEY).trim();
  const object = await bucket.get(objectKey);
  if (!object) {
    return jsonResponse(
      {
        message: `The configured installer was not found: ${objectKey}`,
      },
      404,
      resolved.headers,
    );
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
