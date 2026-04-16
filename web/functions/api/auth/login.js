import {
  extractSupabaseMessage,
  fetchProfile,
  isValidEmail,
  jsonResponse,
  readJsonBody,
  supabaseRequest,
} from "./_shared.js";

export async function onRequestPost(context) {
  const body = await readJsonBody(context.request);
  if (!body) {
    return jsonResponse({ message: "Expected a JSON body." }, 400);
  }

  const email = String(body.email || "").trim().toLowerCase();
  const password = String(body.password || "");

  if (!isValidEmail(email)) {
    return jsonResponse({ message: "Please enter a valid email address." }, 400);
  }
  if (!password) {
    return jsonResponse({ message: "Password is required." }, 400);
  }

  const { response, data } = await supabaseRequest(context, "/auth/v1/token?grant_type=password", {
    method: "POST",
    body: {
      email,
      password,
    },
  });

  if (!response.ok) {
    return jsonResponse(
      {
        message: extractSupabaseMessage(data, "Unable to sign in right now."),
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
      message: "Signed in successfully.",
      session: {
        access_token: data?.access_token ?? null,
        refresh_token: data?.refresh_token ?? null,
        expires_at: data?.expires_at ?? null,
        token_type: data?.token_type ?? null,
      },
      user: user
        ? {
            id: user.id,
            email: user.email,
          }
        : null,
      profile,
    },
    200,
  );
}
