const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store",
};

export function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: JSON_HEADERS,
  });
}

export async function readJsonBody(request) {
  try {
    return await request.json();
  } catch {
    return null;
  }
}

export function getSupabaseConfig(context) {
  const supabaseUrl = String(context.env.SUPABASE_URL || "").trim().replace(/\/$/, "");
  const anonKey = String(context.env.SUPABASE_ANON_KEY || "").trim();

  if (!supabaseUrl || !anonKey) {
    throw new Error("SUPABASE_URL and SUPABASE_ANON_KEY must be configured in Cloudflare Pages.");
  }

  return {
    supabaseUrl,
    anonKey,
  };
}

export function getSiteUrl(context) {
  return (
    String(context.env.SUPABASE_SITE_URL || "").trim() ||
    new URL(context.request.url).origin
  );
}

export function isValidEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(value || "").trim());
}

export function normalizeProfile(raw) {
  if (!raw || typeof raw !== "object") return null;
  return {
    id: raw.id ?? null,
    email: raw.email ?? null,
    display_name: raw.display_name ?? null,
    created_at: raw.created_at ?? null,
  };
}

export function extractSupabaseMessage(data, fallback) {
  if (!data || typeof data !== "object") return fallback;
  return (
    String(data.msg || "").trim() ||
    String(data.error_description || "").trim() ||
    String(data.message || "").trim() ||
    String(data.error || "").trim() ||
    fallback
  );
}

export async function supabaseRequest(context, path, options = {}) {
  const { supabaseUrl, anonKey } = getSupabaseConfig(context);
  const headers = {
    apikey: anonKey,
    "content-type": "application/json",
    ...(options.accessToken ? { Authorization: `Bearer ${options.accessToken}` } : {}),
    ...(options.headers || {}),
  };

  const response = await fetch(`${supabaseUrl}${path}`, {
    method: options.method || "GET",
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  return { response, data, anonKey, supabaseUrl };
}

export async function fetchProfile(context, accessToken, userId) {
  const { response, data } = await supabaseRequest(
    context,
    `/rest/v1/profiles?select=id,email,display_name,created_at&id=eq.${encodeURIComponent(userId)}`,
    {
      method: "GET",
      accessToken,
      headers: {
        Accept: "application/json",
      },
    }
  );

  if (!response.ok) {
    throw new Error(extractSupabaseMessage(data, "Unable to load the profile."));
  }

  if (Array.isArray(data) && data.length) {
    return normalizeProfile(data[0]);
  }
  return null;
}

export async function fetchUser(context, accessToken) {
  const { response, data } = await supabaseRequest(context, "/auth/v1/user", {
    method: "GET",
    accessToken,
  });
  if (!response.ok) {
    throw new Error(extractSupabaseMessage(data, "Unable to load the current user."));
  }
  return data;
}
