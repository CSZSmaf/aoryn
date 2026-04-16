import {
  extractSupabaseMessage,
  getSiteUrl,
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
  const displayName = String(body.displayName || body.name || "").trim();

  if (!isValidEmail(email)) {
    return jsonResponse({ message: "Please enter a valid email address." }, 400);
  }
  if (password.length < 8) {
    return jsonResponse({ message: "Password must be at least 8 characters long." }, 400);
  }

  const emailRedirectTo = getSiteUrl(context);
  const { response, data } = await supabaseRequest(context, "/auth/v1/signup", {
    method: "POST",
    body: {
      email,
      password,
      data: {
        display_name: displayName,
      },
      options: {
        emailRedirectTo,
      },
    },
  });

  if (!response.ok) {
    return jsonResponse(
      {
        message: extractSupabaseMessage(data, "Unable to create the account right now."),
      },
      response.status,
    );
  }

  return jsonResponse(
    {
      ok: true,
      requiresEmailVerification: true,
      message: "Please check your email to verify the account before signing in.",
      user: data?.user
        ? {
            id: data.user.id,
            email: data.user.email,
            email_verified: false,
          }
        : null,
    },
    201,
  );
}
