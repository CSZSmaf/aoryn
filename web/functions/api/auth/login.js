import {
  authCookieHeaders,
  createResolvedSession,
  extractSupabaseMessage,
  isDesktopClient,
  isUserEmailVerified,
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

  const resolved = await createResolvedSession(context, data || {});
  if (!isUserEmailVerified(data?.user)) {
    return jsonResponse(
      {
        message: "Please verify your email before signing in.",
        requiresEmailVerification: true,
      },
      403,
    );
  }

  if (isDesktopClient(context.request)) {
    return jsonResponse(
      {
        ok: true,
        message: "Signed in successfully.",
        session: resolved.session,
        user: resolved.user,
        profile: resolved.profile,
      },
      200,
    );
  }

  return jsonResponse(
    {
      ok: true,
      authenticated: true,
      message: "Signed in successfully.",
      user: resolved.user,
      profile: resolved.profile,
    },
    200,
    {
      "set-cookie": authCookieHeaders(context, resolved.session),
    },
  );
}
