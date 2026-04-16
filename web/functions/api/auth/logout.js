import { extractSupabaseMessage, jsonResponse, supabaseRequest } from "./_shared.js";

function extractBearer(request) {
  const header = request.headers.get("Authorization") || request.headers.get("authorization") || "";
  return header.startsWith("Bearer ") ? header.slice("Bearer ".length).trim() : "";
}

export async function onRequestPost(context) {
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
