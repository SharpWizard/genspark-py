# genspark-py

Unofficial Python client for [genspark.ai](https://www.genspark.ai)'s AI Chat
web app. Logs in via the site's Azure AD B2C OAuth/PKCE flow, persists
cookies to disk, and streams chat replies from any model the web UI exposes
(Claude, Gemini, GPT, Grok, …).

> **Disclaimer.** Not affiliated with or endorsed by Genspark. This package
> talks to undocumented internal endpoints that can change at any time.
> Use at your own risk and respect Genspark's Terms of Service. Don't share
> accounts or run abusive workloads.

## Why curl_cffi?

Genspark's edge (Cloudflare) fingerprints the TLS/JA3 handshake. Plain
`requests` is silently downgraded or blocked. `curl_cffi` impersonates a
real Chrome handshake and the requests sail through — **no captcha solver
required**.

## Install

```bash
pip install git+https://github.com/SharpWizard/genspark-py.git
```

Local clone:

```bash
git clone https://github.com/SharpWizard/genspark-py
cd genspark-py
pip install -e .
```

## Quick start

```python
from genspark import GensparkClient, stream_text

client = GensparkClient(cookie_file="genspark_cookies.txt")

if not client.is_logged_in():
    client.login(email="you@example.com", password="hunter2")

response = client.chat(
    "Explain CRDTs in two sentences.",
    model="claude-sonnet-4-6",
)
for chunk in stream_text(response):
    print(chunk, end="", flush=True)
```

The first call triggers the full B2C login (a few HTTP round-trips); after
that, cookies in `genspark_cookies.txt` are reused on every subsequent run.

## CLI example

```bash
cp examples/.env.example examples/.env
# put your credentials in examples/.env
python examples/chat.py "Write a haiku about TLS fingerprinting"
```

Pick a different model by setting `GENSPARK_MODEL` in `.env` or the
environment.

## Models

`KNOWN_MODELS` ships with the IDs the web UI surfaced at the time of
recording:

```python
from genspark import KNOWN_MODELS
print(KNOWN_MODELS)
# ['claude-sonnet-4-6', 'claude-haiku-4-5', 'claude-opus-4-7',
#  'gemini-2.5-pro', 'gpt-4o', 'grok-4']
```

Any string accepted by the web UI works — pass it to `chat(model=...)`.
You can also call `client.models_config()` to fetch the current list from
the server.

## API surface

| Method                           | What it does                                                      |
|----------------------------------|-------------------------------------------------------------------|
| `GensparkClient(cookie_file=…)`  | Construct a session; auto-loads cookies if the file exists.       |
| `.login(email, password)`        | Run the full B2C OAuth/PKCE flow. Saves cookies on success.       |
| `.is_logged_in()`                | `GET /api/is_login` — `True` if the saved session still works.    |
| `.get_user()`                    | `GET /api/user` — profile + plan + feature flags.                 |
| `.models_config()`               | `GET /api/models_config` — server-side model catalogue.           |
| `.chat(prompt, model=…)`         | `POST /api/agent/ask_proxy` — returns a streaming response.       |
| `.cookies_dict()`                | Snapshot of current cookies.                                      |
| `.save_cookies()`                | Persist the current jar back to disk.                             |
| `stream_text(response)`          | Generator that yields assistant text deltas from the SSE stream.  |

## How login works

1. `GET /api/login?redirect_url=…` — genspark.ai picks a fresh PKCE
   `code_verifier`, stores it server-side, and 302s to Azure AD B2C
   (`b2c_1_new_login` policy).
2. We follow the redirect to the B2C login page and scrape `transId` plus
   the `x-ms-cpim-csrf` cookie.
3. `POST .../SelfAsserted` with email + password and the CSRF header.
4. `GET .../api/CombinedSigninAndSignup/confirmed` — B2C 302s back to
   `https://www.genspark.ai/api/auth?code=…`.
5. genspark.ai exchanges the code (using its stored `code_verifier`),
   sets a `session_id` cookie, and we're in.

> ⚠️ **Don't roll your own PKCE pair.** If you call the B2C `authorize`
> endpoint directly with your own `code_challenge`, genspark's `/api/auth`
> won't recognise the returned code and 307s straight to `/api/logout`.

## Troubleshooting

- **`Login flow finished but /api/is_login is still false`** — usually a
  bad password, or genspark changed the B2C policy name. Open an issue.
- **`SelfAsserted non-JSON`** — Cloudflare served a challenge page; bump
  to a newer `impersonate=` (e.g. `chrome131`) or wait a few minutes.
- **Empty chat reply** — check `response.status_code`; non-200 usually
  means the cookie expired. Delete `genspark_cookies.txt` and re-login.

## License

MIT — see [LICENSE](LICENSE).
