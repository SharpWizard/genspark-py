# genspark-py — Unofficial Genspark.ai Python API Client

[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Last Verified](https://img.shields.io/badge/last%20verified%20working-2026--04--27-brightgreen)](#status)
[![Stars](https://img.shields.io/github/stars/SharpWizard/genspark-py?style=social)](https://github.com/SharpWizard/genspark-py/stargazers)
[![Issues](https://img.shields.io/github/issues/SharpWizard/genspark-py)](https://github.com/SharpWizard/genspark-py/issues)
[![curl_cffi](https://img.shields.io/badge/HTTP-curl__cffi-orange)](https://github.com/lexiforest/curl_cffi)

> **Reverse-engineered Python wrapper for the [genspark.ai](https://www.genspark.ai) AI Chat web app.**
> Logs in with your real Genspark account via Azure AD B2C, persists cookies,
> and streams replies from **Claude Sonnet 4.6, Claude Haiku 4.5, Claude Opus 4.7,
> Gemini 2.5 Pro, GPT-4o, Grok-4** and any other model the web UI exposes —
> all over a Chrome-impersonated TLS handshake so Cloudflare doesn't block you.
> **No reCAPTCHA solver required.**

---

## ⚠️ Disclaimer — Read This First

**This project is published strictly for educational and research purposes.**

- **NOT affiliated** with, endorsed by, or sponsored by Genspark, MainFunc Inc.,
  Anthropic, OpenAI, Google, xAI, Microsoft, or any other vendor.
- Talks to **undocumented internal endpoints** that can change or break at any
  moment without notice.
- Using this client may **violate Genspark's Terms of Service**. You alone are
  responsible for whether and how you use it.
- The authors and contributors **accept no responsibility** for account bans,
  data loss, billing surprises, legal issues, or any other harm — direct or
  indirect — arising from use or misuse of this software.
- **Do not** use this for spam, scraping at scale, abuse, resale of access,
  account sharing, or anything that materially harms Genspark or other users.
- Bring your **own** Genspark account. Don't use stolen, shared, or trial-abused
  credentials. Don't post your credentials anywhere — least of all in issues
  on this repo.

By installing or running this code you confirm you've read and understood the
above and accept full responsibility for your usage.

---

## ✅ Status

| Date         | What happened                                               |
| ------------ | ----------------------------------------------------------- |
| `2026-04-27` | **Last verified working** — login + chat across all models. |

If a future Genspark UI/API change breaks this client, you may need to update
the B2C policy name, the `transId` regex, or the SSE event parsing. PRs are
very welcome. See the [Need an update?](#need-an-update) section if you'd
prefer paid maintenance.

---

## 🚀 Why This Library Exists

Most "free GPT-4 / Claude / Gemini" wrappers on GitHub die within weeks
because they rely on:

- **reCAPTCHA bypass services** (paid, brittle, against ToS).
- **Headless browsers** (slow, heavy, easy to detect).
- **Plain `requests`** that get instantly blocked by Cloudflare's JA3
  fingerprinting.

This client takes a different route:

1. **Native TLS impersonation via [`curl_cffi`](https://github.com/lexiforest/curl_cffi).**
   The TCP handshake is byte-identical to real Chrome, so Cloudflare lets us
   in.
2. **Real OAuth/PKCE login** through Genspark's Azure AD B2C tenant — no
   token theft, no cookie sniffing, just the same flow your browser uses.
3. **Cookies persist to disk** (Netscape format), so the multi-step login
   only runs once.

The result: a tiny, dependency-light Python module you can `import` and use
in any script, bot, or pipeline.

---

## 📦 Install

```bash
pip install git+https://github.com/SharpWizard/genspark-py.git
```

Or clone and install editable:

```bash
git clone https://github.com/SharpWizard/genspark-py
cd genspark-py
pip install -e .
```

Single dependency: [`curl_cffi`](https://pypi.org/project/curl_cffi/).

---

## ⚡ Quick Start

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

The first call runs the full Azure AD B2C login (a handful of HTTP
round-trips). After that, cookies in `genspark_cookies.txt` are reused
on every subsequent run — no re-login needed until they expire.

---

## 🖥️ CLI Example

```bash
cp examples/.env.example examples/.env
# put your credentials in examples/.env
python examples/chat.py "Write a haiku about TLS fingerprinting"
```

Switch models with the `GENSPARK_MODEL` env var:

```bash
GENSPARK_MODEL=gemini-2.5-pro python examples/chat.py "Compare Rust and Go"
```

---

## 🤖 Supported Models

`KNOWN_MODELS` ships with the IDs the web UI surfaced at the time of
recording:

```python
from genspark import KNOWN_MODELS
print(KNOWN_MODELS)
# ['claude-sonnet-4-6',
#  'claude-haiku-4-5',
#  'claude-opus-4-7',
#  'gemini-2.5-pro',
#  'gpt-4o',
#  'grok-4']
```

Any string accepted by the web UI works — just pass it to `chat(model=...)`.
You can also call `client.models_config()` to fetch the current catalogue
straight from the server.

---

## 📚 API Reference

| Method                            | What it does                                                       |
| --------------------------------- | ------------------------------------------------------------------ |
| `GensparkClient(cookie_file=…)`   | Construct a session; auto-loads cookies if the file exists.        |
| `.login(email, password)`         | Run the full B2C OAuth/PKCE flow. Saves cookies on success.        |
| `.is_logged_in()`                 | `GET /api/is_login` — `True` if the saved session still works.     |
| `.get_user()`                     | `GET /api/user` — profile, plan, feature flags.                    |
| `.models_config()`                | `GET /api/models_config` — server-side model catalogue.            |
| `.chat(prompt, model=…)`          | `POST /api/agent/ask_proxy` — returns a streaming response object. |
| `.cookies_dict()`                 | Snapshot of all current cookies as a dict.                         |
| `.save_cookies()`                 | Persist the current jar back to disk.                              |
| `stream_text(response)`           | Generator that yields assistant text deltas from the SSE stream.   |

---

## 🔐 How Login Works

1. `GET /api/login?redirect_url=…` — genspark.ai picks a fresh PKCE
   `code_verifier`, stores it server-side, and 302s us to Azure AD B2C
   (`b2c_1_new_login` policy).
2. We follow the redirect to the B2C login page and scrape `transId`
   plus the `x-ms-cpim-csrf` cookie.
3. `POST .../SelfAsserted` with email + password and the CSRF header.
4. `GET .../api/CombinedSigninAndSignup/confirmed` — B2C 302s back to
   `https://www.genspark.ai/api/auth?code=…`.
5. genspark.ai exchanges the code (using its stored `code_verifier`),
   sets a `session_id` cookie, and we're authenticated.

> ⚠️ **Don't roll your own PKCE pair.** If you call the B2C `authorize`
> endpoint directly with your own `code_challenge`, genspark's `/api/auth`
> won't recognise the returned code and 307s straight to `/api/logout`.

---

## 🧯 Troubleshooting

- **`Login flow finished but /api/is_login is still false`** — usually a
  bad password, or Genspark changed the B2C policy name. Open an issue.
- **`SelfAsserted non-JSON`** — Cloudflare served a challenge page; bump
  to a newer impersonation profile (e.g. `GensparkClient(impersonate="chrome131")`)
  or wait a few minutes.
- **Empty chat reply** — check `response.status_code`; non-200 usually
  means the cookie expired. Delete `genspark_cookies.txt` and re-login.
- **`ModuleNotFoundError: No module named 'curl_cffi'`** — `pip install curl_cffi`.

---

## 📅 Need an update?

This is a **community-maintained, best-effort** project. If Genspark changes
their API and the client breaks, the fastest fixes will land via community
PRs. Watch the repo for updates.

If you need a **guaranteed turnaround** when something breaks, want a
**custom integration**, a **private fork**, or **enterprise support**:
👉 open a [GitHub Discussion](https://github.com/SharpWizard/genspark-py/discussions)
or file an [issue tagged `paid-support`](https://github.com/SharpWizard/genspark-py/issues/new?labels=paid-support).
Paid maintenance and consulting are available on request.

---

## 🤝 Contributing

PRs are very welcome — especially:

- Bumping `chrome124` → newer impersonation profiles when Cloudflare rotates.
- Adding tests against fixture SSE responses.
- Adding new model presets when Genspark exposes them.
- Translating the README.

Please **never** include real credentials, real cookies, or real auth
codes in PRs, issues, or screenshots. Redact aggressively.

---

## 📄 License

[MIT](LICENSE) — do whatever you want, but you accept all risk.
The disclaimer above is **not optional**.

---

## 🔎 Keywords

genspark, genspark.ai, genspark api, genspark python, genspark client,
unofficial genspark api, free claude api, free gpt-4 api, free gemini api,
free grok api, claude sonnet 4.6 python, claude haiku 4.5 api,
claude opus 4.7 api, gemini 2.5 pro python, gpt-4o python wrapper,
grok-4 api, multi-model ai chat client, ai aggregator, oauth pkce python,
azure ad b2c python, cloudflare bypass python, jа3 fingerprint bypass,
curl_cffi example, tls impersonation, server-sent events parser,
streaming chat completion, reverse engineered api, web scraping ai chat,
no captcha api client, no recaptcha bypass, headless-less ai client.
