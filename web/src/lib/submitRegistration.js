const MOCK_DELAY_MS = 700;

function delay(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

export async function submitRegistration({ endpoint, payload, locale, messages }) {
  const body = {
    ...payload,
    locale,
    source: "aoryn-website",
  };

  if (!endpoint) {
    await delay(MOCK_DELAY_MS);
    return {
      ok: true,
      mode: "mock",
      message: messages.successFallback,
    };
  }

  let response;
  try {
    response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error(messages.networkError);
  }

  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    throw new Error(data?.message || messages.networkError);
  }

  return {
    ok: true,
    mode: "live",
    message: data?.message || messages.successLive,
  };
}
