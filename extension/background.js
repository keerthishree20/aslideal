// The only part of the extension allowed to talk to the AsliDeal server.
// A content script on https://www.amazon.in can't fetch http://localhost, but the
// service worker can, because localhost is in host_permissions.

const SERVER = "http://localhost:8000";

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg.type !== "check") return;
  fetch(`${SERVER}/api/check/${encodeURIComponent(msg.asin)}`)
    .then(async (res) => {
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || `Server returned ${res.status}`);
      reply({ ok: true, data: body, server: SERVER });
    })
    .catch((err) => reply({
      ok: false,
      server: SERVER,
      error: err instanceof TypeError
        ? "AsliDeal isn't running. Start it with ./run.sh and reload this page."
        : err.message,
    }));
  return true; // keep the message channel open for the async reply
});

chrome.action.onClicked.addListener(() => chrome.tabs.create({ url: SERVER }));
