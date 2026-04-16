import {
  extractBearer,
  fetchProfile,
  fetchUser,
  isDesktopClient,
  isUserEmailVerified,
  jsonResponse,
  normalizeUser,
  resolveBrowserSession,
} from "./_shared.js";

export async function onRequestGet(context) {
  if (isDesktopClient(context.request)) {
    const accessToken = extractBearer(context.request);
    if (!accessToken) {
      return jsonResponse({ message: "Authorization bearer token is required." }, 401);
    }

    try {
      const user = await fetchUser(context, accessToken);
      if (!isUserEmailVerified(user)) {
        return jsonResponse(
          {
            message: "Please verify your email before signing in.",
            requiresEmailVerification: true,
          },
          403,
        );
      }
      const profile = user?.id ? await fetchProfile(context, accessToken, user.id) : null;
      return jsonResponse(
        {
          ok: true,
          authenticated: true,
          user: normalizeUser(user),
          profile,
        },
        200,
      );
    } catch (error) {
      return jsonResponse(
        {
          message: error instanceof Error ? error.message : "Unable to load the current user.",
        },
        401,
      );
    }
  }

  const resolved = await resolveBrowserSession(context);
  return jsonResponse(
    {
      ok: true,
      authenticated: Boolean(resolved.authenticated),
      user: resolved.user,
      profile: resolved.profile,
    },
    200,
    resolved.headers,
  );
}
