import {
  extractSupabaseMessage,
  fetchProfile,
  jsonResponse,
  readJsonBody,
  supabaseRequest,
} from "./_shared.js";

export async function onRequestPost(context) {
  const body = await readJsonBody(context.request);
  if (!body) {
    return jsonResponse({ message: "Expected a JSON body." }, 400);
  }

  const refreshToken = String(body.refreshToken || "").trim();
  if (!refreshToken) {
    return jsonResponse({ message: "refreshToken is required." }, 400);
  }

  const { response, data } = await supabaseRequest(context, "/auth/v1/token?grant_type=refresh_token", {
    method: "POST",
    body: {
      refresh_token: refreshToken,
    },
  });

  if (!response.ok) {
    return jsonResponse(
      {
        message: extractSupabaseMessage(data, "Unable to refresh the session."),
      },
      response.status,
    );
  }

  const accessToken = data?.access_token;
  const user = data?.user || null;
  const profile = accessToken && user?.id ? await fetchProfile(context, accessToken, user.id) : null;

  return jsonResponse(
    {
      ok: true,
      session: {
        access_token: data?.access_token ?? null,
        refresh_token: data?.refresh_token ?? refreshToken,
        expires_at: data?.expires_at ?? null,
        token_type: data?.token_type ?? null,
      },
      profile,
    },
    200,
  );
}
