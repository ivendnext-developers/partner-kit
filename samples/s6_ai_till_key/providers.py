"""S6 — the providers. Each is ``provider(prompt) -> text``. The shop chooses one; we pay for none of them.

  stub          a local stand-in with no network and no account: the sample runs with this
  chat          any service that speaks the chat-completions request (an open-weight model on the customer's own
                machine — Ollama, llama.cpp, vLLM — or the assistant the customer already pays for): the customer
                sets PP_AI_URL, PP_AI_KEY and PP_AI_MODEL. The key goes only in the request header, never in a log.
"""

import json
import urllib.request


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect would carry the customer's AI key (the Authorization header) to whatever host it names: refuse it."""
    def redirect_request(self, *args, **kwargs):
        return None


_OPEN = urllib.request.build_opener(_NoRedirect).open


def stub(prompt: str) -> str:
    """Deterministic: a tip that names the first item on the sale. Proves the wiring, not the intelligence."""
    first = next((ln[2:].split(" x ")[0] for ln in prompt.splitlines() if ln.startswith("- ")), "the item")
    return f"Ask whether the customer needs a case or a charger with the {first}."


def chat(url: str, key: str, model: str, timeout: float):
    def provider(prompt: str) -> str:
        body = json.dumps({"model": model, "max_tokens": 120,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request(url, body, {"Content-Type": "application/json",
                                                 **({"Authorization": f"Bearer {key}"} if key else {})})
        with _OPEN(req, timeout=timeout) as r:      # a redirect is an error (HTTPError), logged by its class only
            return json.loads(r.read(64 * 1024))["choices"][0]["message"]["content"]
    return provider


def from_env(env: dict):
    kind = env.get("PP_AI_PROVIDER", "stub")
    if kind == "stub":
        return stub
    if kind == "chat":
        return chat(env["PP_AI_URL"], env.get("PP_AI_KEY", ""), env.get("PP_AI_MODEL", ""), float(env.get("PP_AI_TIMEOUT", "8")))
    raise SystemExit(f"PP_AI_PROVIDER must be 'stub' or 'chat', not {kind!r}")
