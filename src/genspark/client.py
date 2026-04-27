"""
Unofficial Genspark.ai client - Azure AD B2C login + AI chat.

Uses curl_cffi to impersonate a real Chrome TLS/JA3 fingerprint so the
Cloudflare edge doesn't block the request. Cookies are persisted to a
Netscape-format file so the B2C login dance only happens once.
"""

from __future__ import annotations

import http.cookiejar
import json
import re
import uuid
from typing import Iterator, Optional

from curl_cffi import requests


TENANT = "gensparkad.onmicrosoft.com"
POLICY = "B2C_1_new_login"
LOGIN_HOST = "https://login.genspark.ai"
APP_HOST = "https://www.genspark.ai"
DEFAULT_IMPERSONATE = "chrome124"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)

# Pulled from the Genspark.ai web UI's Nuxt JS bundle on 2026-04-27.
# `label` is what the UI shows; `id` is what /api/agent/ask_proxy expects in
# `ai_chat_model`. `hidden` models are no longer in the model picker but
# still respond when called directly.
KNOWN_MODELS = {
    # OpenAI - GPT-5 family (current)
    "gpt-5.4":                          {"label": "GPT-5.4",                "vendor": "openai", "hidden": False},
    "gpt-5.5":                          {"label": "GPT-5.5",                "vendor": "openai", "hidden": False},
    "gpt-5.4-mini":                     {"label": "GPT-5.4 Mini",           "vendor": "openai", "hidden": False},
    "gpt-5.4-nano":                     {"label": "GPT-5.4 Nano",           "vendor": "openai", "hidden": False},
    "gpt-5.2-pro":                      {"label": "GPT-5.2 Pro",            "vendor": "openai", "hidden": False},
    "gpt-5.4-pro":                      {"label": "GPT-5.4 Pro",            "vendor": "openai", "hidden": False},
    "o3-pro":                           {"label": "o3-pro",                 "vendor": "openai", "hidden": False},
    # OpenAI - GPT-5 family (hidden / legacy in UI)
    "gpt-5-pro":                        {"label": "GPT-5 Pro",              "vendor": "openai", "hidden": True},
    "gpt-5.1-low":                      {"label": "GPT-5.1 Instant",        "vendor": "openai", "hidden": True},
    "gpt-5.1-medium":                   {"label": "GPT-5.1 Thinking",       "vendor": "openai", "hidden": True},
    "gpt-5.1-high":                     {"label": "GPT-5.1 Thinking High",  "vendor": "openai", "hidden": True},
    "gpt-5.2":                          {"label": "GPT-5.2",                "vendor": "openai", "hidden": True},
    # Anthropic Claude (current)
    "claude-sonnet-4-6":                {"label": "Claude Sonnet 4.6",      "vendor": "anthropic", "hidden": False},
    "claude-opus-4-7":                  {"label": "Claude Opus 4.7",        "vendor": "anthropic", "hidden": False},
    "claude-opus-4-6":                  {"label": "Claude Opus 4.6",        "vendor": "anthropic", "hidden": False},
    "claude-4-5-haiku":                 {"label": "Claude Haiku 4.5",       "vendor": "anthropic", "hidden": False},
    # Anthropic Claude (hidden / legacy in UI)
    "claude-sonnet-4":                  {"label": "Claude Sonnet 4",        "vendor": "anthropic", "hidden": True},
    "claude-sonnet-4-5":                {"label": "Claude Sonnet 4.5",      "vendor": "anthropic", "hidden": True},
    "claude-opus-4-1":                  {"label": "Claude Opus 4.1",        "vendor": "anthropic", "hidden": True},
    "claude-opus-4-5":                  {"label": "Claude Opus 4.5",        "vendor": "anthropic", "hidden": True},
    "claude-kindal-eap":                {"label": "claude-kindal-eap",      "vendor": "anthropic", "hidden": True},
    # Google Gemini (current)
    "gemini-2.5-pro":                   {"label": "Gemini 2.5 Pro",         "vendor": "google", "hidden": False},
    "gemini-3-flash-preview":           {"label": "Gemini 3 Flash Preview", "vendor": "google", "hidden": False},
    "gemini-3.1-pro-preview":           {"label": "Gemini 3.1 Pro Preview", "vendor": "google", "hidden": False},
    # Google Gemini (hidden / legacy in UI)
    "gemini-2.5-flash":                 {"label": "Gemini 2.5 Flash",       "vendor": "google", "hidden": True},
    # xAI Grok (current)
    "grok-4.20-0309-reasoning":         {"label": "Grok 4.20 Reasoning",    "vendor": "xai", "hidden": False},
    "grok-4.20-0309-non-reasoning":     {"label": "Grok 4.20",              "vendor": "xai", "hidden": False},
    # xAI Grok (hidden / legacy in UI)
    "grok-4-0709":                      {"label": "Grok4 0709",             "vendor": "xai", "hidden": True},
    # Moonshot Kimi (hidden / legacy in UI)
    "kimi-k2-instruct":                 {"label": "Kimi K2 Instruct",       "vendor": "moonshot", "hidden": True},
    "groq-kimi-k2-instruct":            {"label": "Groq Kimi K2 Instruct",  "vendor": "groq", "hidden": True},
    # Mixture-of-Agents (special: comma-separated ensemble)
    "gpt-5.1-low,claude-sonnet-4-6,gemini-3.1-pro-preview":
                                        {"label": "Mixture-of-Agents",      "vendor": "moa", "hidden": False},
}

DEFAULT_MODEL = "claude-sonnet-4-6"


class GensparkAuthError(RuntimeError):
    """Raised when login fails (bad credentials, captcha, parse error, etc.)."""


class GensparkClient:
    """
    A thin wrapper around the Genspark.ai web app's HTTP endpoints.

    Typical use:

        client = GensparkClient(cookie_file="genspark_cookies.txt")
        if not client.is_logged_in():
            client.login(email, password)
        for chunk in stream_text(client.chat("Hi", model="claude-sonnet-4-6")):
            print(chunk, end="")
    """

    def __init__(
        self,
        cookie_file: str = "genspark_cookies.txt",
        impersonate: str = DEFAULT_IMPERSONATE,
        user_agent: str = DEFAULT_UA,
    ):
        self.session = requests.Session(impersonate=impersonate)
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept-Language": "en-US,en;q=0.9",
        })
        self.cookie_file = cookie_file
        self._jar = http.cookiejar.MozillaCookieJar(cookie_file)
        try:
            self._jar.load(ignore_discard=True, ignore_expires=True)
            for c in self._jar:
                self.session.cookies.set(
                    c.name, c.value, domain=c.domain, path=c.path
                )
        except FileNotFoundError:
            pass

    def save_cookies(self) -> None:
        self._jar.clear()
        for c in self.session.cookies.jar:
            self._jar.set_cookie(c)
        self._jar.save(ignore_discard=True, ignore_expires=True)

    def is_logged_in(self) -> bool:
        try:
            r = self.session.get(f"{APP_HOST}/api/is_login", timeout=15)
            data = r.json()
        except Exception:
            return False
        return bool(data.get("data", {}).get("is_login") or data.get("is_login"))

    def login(self, email: str, password: str) -> bool:
        """
        Run the full Azure AD B2C OAuth/PKCE login flow.

        IMPORTANT: we let `/api/login` initiate the flow so the genspark
        backend stores the PKCE code_verifier server-side. Generating our
        own PKCE pair here would orphan the auth code and `/api/auth` on
        the way back would 307 to `/api/logout`.
        """
        r = self.session.get(
            f"{APP_HOST}/api/login",
            params={"redirect_url": f"{APP_HOST}/"},
            allow_redirects=True,
        )
        r.raise_for_status()
        authorize_referer = r.url

        csrf = self.session.cookies.get("x-ms-cpim-csrf")
        m = re.search(r'"transId"\s*:\s*"([^"]+)"', r.text)
        if not (csrf and m):
            raise GensparkAuthError(
                "B2C login page parse failed - csrf or transId missing"
            )
        tx = m.group(1)

        sa_url = f"{LOGIN_HOST}/{TENANT}/B2C_1_new_login/SelfAsserted"
        r = self.session.post(
            sa_url,
            params={"tx": tx, "p": POLICY},
            headers={
                "x-csrf-token": csrf,
                "x-requested-with": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": LOGIN_HOST,
                "Referer": authorize_referer,
                "Accept": "application/json, text/javascript, */*; q=0.01",
            },
            data={"request_type": "RESPONSE", "email": email, "password": password},
        )
        r.raise_for_status()
        try:
            sa = r.json()
        except Exception:
            raise GensparkAuthError(
                f"SelfAsserted non-JSON: {r.text[:200]!r}"
            )
        if str(sa.get("status")) != "200":
            raise GensparkAuthError(f"Credentials rejected by B2C: {sa}")

        confirm_url = (
            f"{LOGIN_HOST}/{TENANT}/B2C_1_new_login"
            "/api/CombinedSigninAndSignup/confirmed"
        )
        r = self.session.get(
            confirm_url,
            params={
                "rememberMe": "false",
                "csrf_token": csrf,
                "tx": tx,
                "p": POLICY,
            },
            headers={"Referer": authorize_referer},
            allow_redirects=True,
        )
        r.raise_for_status()

        if not self.is_logged_in():
            raise GensparkAuthError(
                "Login flow finished but /api/is_login is still false"
            )
        self.save_cookies()
        return True

    def cookies_dict(self) -> dict:
        return {c.name: c.value for c in self.session.cookies.jar}

    def get_user(self) -> dict:
        r = self.session.get(f"{APP_HOST}/api/user")
        r.raise_for_status()
        return r.json()

    def models_config(self) -> dict:
        r = self.session.get(f"{APP_HOST}/api/models_config")
        r.raise_for_status()
        return r.json()

    def chat(
        self,
        prompt: str,
        model: str = DEFAULT_MODEL,
        enable_search: bool = True,
        is_private: bool = True,
        project_id: Optional[str] = None,
    ):
        """
        Send one user turn. Returns the streaming `curl_cffi` response -
        iterate `.iter_lines()` directly, or pass it to `stream_text()`
        for assistant text deltas only.
        """
        msg_id = str(uuid.uuid4())
        message = {"role": "user", "id": msg_id, "content": prompt}
        payload = {
            "ai_chat_model": model,
            "ai_chat_enable_search": enable_search,
            "ai_chat_disable_personalization": False,
            "use_moa_proxy": False,
            "moa_models": [],
            "writingContent": None,
            "type": "ai_chat",
            "project_id": project_id,
            "messages": [message],
            "user_s_input": prompt,
            "g_recaptcha_token": "",
            "is_private": is_private,
            "push_token": "",
            "session_state": {"steps": [], "messages": [message]},
        }
        return self.session.post(
            f"{APP_HOST}/api/agent/ask_proxy",
            headers={
                "Origin": APP_HOST,
                "Referer": f"{APP_HOST}/agents?type=ai_chat",
                "Content-Type": "application/json",
                "Accept": "*/*",
            },
            json=payload,
            stream=True,
        )


def stream_text(response) -> Iterator[str]:
    """
    Yield assistant text chunks from an `ask_proxy` SSE stream.

    Each event looks like:
        data: {"type": "message_field_delta",
               "field_name": "content",
               "delta": "Hello"}
    """
    for raw in response.iter_lines():
        if not raw:
            continue
        line = (
            raw.decode("utf-8", errors="replace")
            if isinstance(raw, (bytes, bytearray))
            else raw
        )
        if line.startswith("data:"):
            line = line[5:].strip()
        if not line or line == "[DONE]":
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if (
            obj.get("type") == "message_field_delta"
            and obj.get("field_name") == "content"
        ):
            delta = obj.get("delta")
            if delta:
                yield delta
