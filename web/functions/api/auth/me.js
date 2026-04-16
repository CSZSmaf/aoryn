import { fetchProfile, fetchUser, jsonResponse } from "./_shared.js";

function extractBearer(request) {
  const header = request.headers.get("Authorization") || request.headers.get("authorization") || "";
  return header.startsWith("Bearer ") ? header.slice("Bearer ".length).trim() : "";
}

export async function onRequestGet(context) {
  const accessToken = extractBearer(context.request);
  if (!accessToken) {
    return jsonResponse({ message: "Authorization bearer token is required." }, 401);
  }

  try {
    const user = await fetchUser(context, accessToken);
    const profile = user?.id ? await fetchProfile(context, accessToken, user.id) : null;
    return jsonResponse(
      {
        ok: true,
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
  } catch (error) {
    return jsonResponse(
      {
        message: error instanceof Error ? error.message : "Unable to load the current user.",
      },
      401,
    );
  }
}
