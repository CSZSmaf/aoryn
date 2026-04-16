import {
  clearAuthCookieHeaders,
  isDesktopClient,
  jsonResponse,
  readJsonBody,
  refreshResolvedSession,
  resolveBrowserSession,
} from "./_shared.js";

export async function onRequestPost(context) {
  if (isDesktopClient(context.request)) {
    const body = await readJsonBody(context.request);
    if (!body) {
      return jsonResponse({ message: "Expected a JSON body." }, 400);
    }

    const refreshToken = String(body.refreshToken || "").trim();
    if (!refreshToken) {
      return jsonResponse({ message: "refreshToken is required." }, 400);
    }

    try {
      const resolved = await refreshResolvedSession(context, refreshToken);
      if (!resolved.user?.email_verified) {
        return jsonResponse(
          {
            message: "Please verify your email before signing in.",
            requiresEmailVerification: true,
          },
          403,
        );
      }
      return jsonResponse(
        {
          ok: true,
          session: resolved.session,
          user: resolved.user,
          profile: resolved.profile,
        },
        200,
      );
    } catch (error) {
      return jsonResponse(
        {
          message: error instanceof Error ? error.message : "Unable to refresh the session.",
        },
        401,
      );
    }
  }

  const resolved = await resolveBrowserSession(context);
  if (!resolved.authenticated) {
    return jsonResponse(
      {
        ok: false,
        authenticated: false,
        message: "No authenticated browser session is available.",
      },
      401,
      resolved.headers || { "set-cookie": clearAuthCookieHeaders(context) },
    );
  }

  return jsonResponse(
    {
      ok: true,
      authenticated: true,
      user: resolved.user,
      profile: resolved.profile,
    },
    200,
    resolved.headers,
  );
}
