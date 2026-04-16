async function parseJson(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

async function requestJson(url, options = {}) {
  let response;
  try {
    response = await fetch(url, {
      credentials: "include",
      cache: "no-store",
      ...options,
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.headers || {}),
      },
    });
  } catch {
    throw new Error("Unable to reach the authentication service right now.");
  }

  const payload = await parseJson(response);
  if (!response.ok) {
    throw new Error(payload?.message || "The request could not be completed.");
  }
  return payload || {};
}

export async function loadCurrentSession(endpoint) {
  return requestJson(endpoint, {
    method: "GET",
  });
}

export async function registerAccount(endpoint, payload) {
  return requestJson(endpoint, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function loginAccount(endpoint, payload) {
  return requestJson(endpoint, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function logoutAccount(endpoint) {
  return requestJson(endpoint, {
    method: "POST",
    body: JSON.stringify({}),
  });
}
