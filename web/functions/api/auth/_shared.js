const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store",
};

const ACCESS_COOKIE_NAME = "aoryn_access_token";
const REFRESH_COOKIE_NAME = "aoryn_refresh_token";
const REFRESH_COOKIE_MAX_AGE = 60 * 60 * 24 * 30;
const DESKTOP_CLIENT_HEADER = "x-aoryn-client";

export function jsonResponse(payload, status = 200, extraHeaders = undefined) {
  const headers = mergeHeaders(JSON_HEADERS, extraHeaders);
  return new Response(JSON.stringify(payload), {
    status,
    headers,
  });
}

export function mergeHeaders(...headerSets) {
  const headers = new Headers();
  headerSets.filter(Boolean).forEach((set) => {
    if (set instanceof Headers) {
      set.forEach((value, key) => headers.append(key, value));
      return;
    }
    if (Array.isArray(set)) {
      set.forEach(([key, value]) => headers.append(key, value));
      return;
    }
    Object.entries(set).forEach(([key, value]) => {
      if (Array.isArray(value)) {
        value.forEach((entry) => headers.append(key, entry));
      } else if (value != null) {
        headers.append(key, String(value));
      }
    });
  });
  return headers;
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

export function isDesktopClient(request) {
  return (
    String(request.headers.get(DESKTOP_CLIENT_HEADER) || "")
      .trim()
      .toLowerCase() === "desktop"
  );
}

export function extractBearer(request) {
  const header = request.headers.get("Authorization") || request.headers.get("authorization") || "";
  return header.startsWith("Bearer ") ? header.slice("Bearer ".length).trim() : "";
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

export function normalizeUser(raw) {
  if (!raw || typeof raw !== "object") return null;
  return {
    id: raw.id ?? null,
    email: raw.email ?? null,
    email_verified: isUserEmailVerified(raw),
  };
}

export function isUserEmailVerified(raw) {
  return Boolean(raw?.email_confirmed_at || raw?.confirmed_at || raw?.email_verified);
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
    },
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

function parseCookies(request) {
  const raw = request.headers.get("Cookie") || request.headers.get("cookie") || "";
  return raw.split(/;\s*/).reduce((accumulator, pair) => {
    if (!pair) return accumulator;
    const index = pair.indexOf("=");
    if (index <= 0) return accumulator;
    const key = pair.slice(0, index).trim();
    const value = pair.slice(index + 1).trim();
    accumulator[key] = decodeURIComponent(value);
    return accumulator;
  }, {});
}

function serializeCookie(name, value, options = {}) {
  const parts = [`${name}=${encodeURIComponent(value)}`];
  parts.push(`Path=${options.path || "/"}`);
  if (Number.isFinite(options.maxAge)) {
    parts.push(`Max-Age=${Math.max(0, Math.floor(options.maxAge))}`);
  }
  if (options.httpOnly !== false) {
    parts.push("HttpOnly");
  }
  if (options.sameSite) {
    parts.push(`SameSite=${options.sameSite}`);
  }
  if (options.secure) {
    parts.push("Secure");
  }
  if (options.expires) {
    parts.push(`Expires=${options.expires.toUTCString()}`);
  }
  return parts.join("; ");
}

export function authCookieHeaders(context, session) {
  const requestUrl = new URL(context.request.url);
  const secure = requestUrl.protocol === "https:";
  const accessExpiresAt = Number(session?.expires_at || 0);
  const accessMaxAge = Number.isFinite(accessExpiresAt) && accessExpiresAt > 0
    ? Math.max(60, Math.floor(accessExpiresAt - Date.now() / 1000))
    : 60 * 60;

  return [
    serializeCookie(ACCESS_COOKIE_NAME, String(session?.access_token || ""), {
      httpOnly: true,
      sameSite: "Lax",
      secure,
      maxAge: accessMaxAge,
    }),
    serializeCookie(REFRESH_COOKIE_NAME, String(session?.refresh_token || ""), {
      httpOnly: true,
      sameSite: "Lax",
      secure,
      maxAge: REFRESH_COOKIE_MAX_AGE,
    }),
  ];
}

export function clearAuthCookieHeaders(context) {
  const requestUrl = new URL(context.request.url);
  const secure = requestUrl.protocol === "https:";
  const expires = new Date(0);
  return [
    serializeCookie(ACCESS_COOKIE_NAME, "", {
      httpOnly: true,
      sameSite: "Lax",
      secure,
      maxAge: 0,
      expires,
    }),
    serializeCookie(REFRESH_COOKIE_NAME, "", {
      httpOnly: true,
      sameSite: "Lax",
      secure,
      maxAge: 0,
      expires,
    }),
  ];
}

export async function createResolvedSession(context, sessionPayload) {
  const accessToken = String(sessionPayload?.access_token || "").trim();
  const refreshToken = String(sessionPayload?.refresh_token || "").trim();
  const user = sessionPayload?.user || (accessToken ? await fetchUser(context, accessToken) : null);
  const profile = accessToken && user?.id ? await fetchProfile(context, accessToken, user.id) : null;

  return {
    session: {
      access_token: accessToken || null,
      refresh_token: refreshToken || null,
      expires_at: sessionPayload?.expires_at ?? null,
      token_type: sessionPayload?.token_type ?? null,
    },
    user: normalizeUser(user),
    profile,
  };
}

export async function refreshResolvedSession(context, refreshToken) {
  const { response, data } = await supabaseRequest(context, "/auth/v1/token?grant_type=refresh_token", {
    method: "POST",
    body: {
      refresh_token: refreshToken,
    },
  });

  if (!response.ok) {
    throw new Error(extractSupabaseMessage(data, "Unable to refresh the session."));
  }

  return createResolvedSession(context, data || {});
}

export async function resolveBrowserSession(context) {
  const cookies = parseCookies(context.request);
  const accessToken = String(cookies[ACCESS_COOKIE_NAME] || "").trim();
  const refreshToken = String(cookies[REFRESH_COOKIE_NAME] || "").trim();

  if (!accessToken && !refreshToken) {
    return { authenticated: false, headers: undefined, session: null, user: null, profile: null };
  }

  if (accessToken) {
    try {
      const user = await fetchUser(context, accessToken);
      if (isUserEmailVerified(user)) {
        const profile = user?.id ? await fetchProfile(context, accessToken, user.id) : null;
        return {
          authenticated: true,
          headers: undefined,
          session: null,
          user: normalizeUser(user),
          profile,
        };
      }
    } catch {
      // fall through to refresh below
    }
  }

  if (refreshToken) {
    try {
      const resolved = await refreshResolvedSession(context, refreshToken);
      if (resolved.user?.email_verified) {
        return {
          authenticated: true,
          headers: { "set-cookie": authCookieHeaders(context, resolved.session) },
          session: null,
          user: resolved.user,
          profile: resolved.profile,
        };
      }
    } catch {
      // clear below
    }
  }

  return {
    authenticated: false,
    headers: { "set-cookie": clearAuthCookieHeaders(context) },
    session: null,
    user: null,
    profile: null,
  };
}
