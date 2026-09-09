/* Minimal multi-turn chat client for gemma3_js.
 * History lives here; each send POSTs the full messages[] to /chat.
 */
(() => {
  const log = document.getElementById("log");
  const form = document.getElementById("form");
  const input = document.getElementById("prompt");
  const sendBtn = document.getElementById("send");

  /** @type {{role: string, content: string}[]} */
  const messages = [];

  function bubble(role, text) {
    const el = document.createElement("div");
    el.className = `bubble ${role}`;
    el.textContent = text;
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
  }

  function meta(text) {
    const el = document.createElement("div");
    el.className = "meta";
    el.textContent = text;
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
  }

  // /ui/ is the mount; API routes stay at service root (/chat).
  const chatUrl = new URL("/chat", window.location.origin).toString();

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const text = input.value.trim();
    if (!text) return;

    input.value = "";
    messages.push({ role: "user", content: text });
    bubble("user", text);
    sendBtn.disabled = true;

    try {
      const res = await fetch(chatUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages,
          max_new_tokens: 128,
          temperature: 0.0,
        }),
      });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(`${res.status}: ${errText}`);
      }
      const data = await res.json();
      const reply = (data.text || "").trim() || "(empty)";
      messages.push({ role: "assistant", content: reply });
      bubble("assistant", reply);
    } catch (err) {
      messages.pop();
      meta(`Error: ${err.message || err}`);
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  });

  meta("Ready. Try: “My name is Ada.” then “What is my name?”");
  input.focus();
})();
