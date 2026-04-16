import {
  clearAuthCookieHeaders,
  extractBearer,
  extractSupabaseMessage,
  isDesktopClient,
  jsonResponse,
  supabaseRequest,
} from "./_shared.js";

export async function onRequestPost(context) {
  if (isDesktopClient(context.request)) {
    const accessToken = extractBearer(context.request);
    if (!accessToken) {
      return jsonResponse({ message: "Authorization bearer token is required." }, 401);
    }

    const { response, data } = await supabaseRequest(context, "/auth/v1/logout", {
      method: "POST",
      accessToken,
    });

    if (!response.ok) {
      return jsonResponse(
        {
          message: extractSupabaseMessage(data, "Unable to sign out right now."),
        },
        response.status,
      );
    }

    return jsonResponse({ ok: true, message: "Signed out successfully." }, 200);
  }

  const accessToken = extractBearer(context.request);
  if (accessToken) {
    await supabaseRequest(context, "/auth/v1/logout", {
      method: "POST",
      accessToken,
    }).catch(() => null);
  }

  return jsonResponse(
    {
      ok: true,
      authenticated: false,
      message: "Signed out successfully.",
    },
    200,
    {
      "set-cookie": clearAuthCookieHeaders(context),
    },
  );
}
