"""
Minimal end-to-end example.

Reads credentials from environment variables (or a .env file if you
`pip install python-dotenv`), logs in, prints the user profile, then
streams a single chat reply.

    cp examples/.env.example examples/.env
    # edit .env with your credentials
    python examples/chat.py
"""

import os
import sys

from genspark import GensparkClient, KNOWN_MODELS, stream_text


def _load_dotenv():
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for candidate in ("examples/.env", ".env"):
        if os.path.isfile(candidate):
            load_dotenv(candidate)
            return


def main():
    _load_dotenv()
    email = os.environ.get("GENSPARK_EMAIL")
    password = os.environ.get("GENSPARK_PASSWORD")
    if not (email and password):
        sys.exit("Set GENSPARK_EMAIL and GENSPARK_PASSWORD env vars first.")

    client = GensparkClient(cookie_file="genspark_cookies.txt")

    if client.is_logged_in():
        print("[*] Reusing saved cookies.")
    else:
        print(f"[*] Logging in as {email} ...")
        client.login(email, password)
        print("[+] Logged in. Cookies saved to genspark_cookies.txt")

    user = client.get_user().get("data", {}).get("cogen", {})
    print(f"[*] Logged in: {user.get('email')}  plan={user.get('plan')}")

    model = os.environ.get("GENSPARK_MODEL", "claude-sonnet-4-6")
    if model not in KNOWN_MODELS:
        print(f"[!] Warning: model {model!r} is not in KNOWN_MODELS - sending anyway.")

    prompt = " ".join(sys.argv[1:]) or "Hi, in one sentence: what model are you?"
    print(f"[*] {model}: {prompt}")

    response = client.chat(prompt, model=model)
    if response.status_code != 200:
        sys.exit(f"chat failed: {response.status_code} {response.text[:500]}")

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, Exception):
        pass

    for chunk in stream_text(response):
        sys.stdout.write(chunk)
        sys.stdout.flush()
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
