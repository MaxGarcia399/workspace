"""Local Google desktop OAuth: browser + loopback + PKCE, Calendar read only.

Credentials and refresh tokens stay in secret_store, never in the repository.
No network from renderers. Public results contain no tokens or server errors.
"""
import base64
import datetime as dt
import hashlib
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import secret_store

CLIENT_VAR = "WORKSPACE_GOOGLE_OAUTH_CLIENT"
ACCOUNTS_VAR = "WORKSPACE_GOOGLE_OAUTH_ACCOUNTS"
SCOPE = "https://www.googleapis.com/auth/calendar.events.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
_lock = threading.RLock()


class AuthError(Exception):
    """Only a fixed, safe error code may leave the transport layer."""


def _read(name, default):
    try:
        return json.loads(secret_store.get(name))
    except (TypeError, ValueError):
        return default


def client():
    value = _read(CLIENT_VAR, {})
    return value if isinstance(value, dict) else {}


def configured():
    return bool(client().get("client_id"))


def import_client(path):
    """Import the downloaded Desktop client JSON locally, with fixed endpoints."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        value = data.get("installed", {})
        cid = value.get("client_id", "")
        if not isinstance(cid, str) or not cid.endswith(".apps.googleusercontent.com"):
            return {"ok": False, "error": "invalid_client"}
        clean = {"client_id": cid, "client_secret": str(value.get("client_secret") or "")}
        if not secret_store.set_secret(CLIENT_VAR, json.dumps(clean)).get("ok"):
            return {"ok": False, "error": "save_failed"}
        return {"ok": True}
    except (OSError, ValueError, TypeError, AttributeError):
        return {"ok": False, "error": "invalid_client"}


def _accounts():
    data = _read(ACCOUNTS_VAR, [])
    return [a for a in data if isinstance(a, dict) and a.get("id")
            and a.get("refresh_token")] if isinstance(data, list) else []


def accounts():
    """Public metadata only. Account IDs occupy a separate namespace from iCal."""
    with _lock:
        return [{"id": a["id"], "label": a.get("label") or "Google",
                 "kind": "oauth", "oauth": True,
                 "auth_error": a.get("auth_error", "")}
                for a in _accounts()]


def _save(data):
    if data:
        ok = secret_store.set_secret(ACCOUNTS_VAR, json.dumps(data)).get("ok")
    else:
        ok = secret_store.remove(ACCOUNTS_VAR).get("ok")
    if not ok:
        raise AuthError("save_failed")


def remove(aid):
    with _lock:
        data = _accounts()
        new = [a for a in data if a["id"] != aid]
        if len(new) == len(data):
            return {"ok": False, "error": "not_found"}
        try:
            _save(new)
            return {"ok": True, "id": aid}
        except AuthError:
            return {"ok": False, "error": "save_failed"}


def rename(aid, label):
    label = str(label or "").strip()[:60]
    if not label:
        return {"ok": False, "error": "empty"}
    with _lock:
        data = _accounts()
        for a in data:
            if a["id"] == aid:
                a["label"] = label
                try:
                    _save(data)
                    return {"ok": True, "id": aid, "label": label}
                except AuthError:
                    return {"ok": False, "error": "save_failed"}
    return {"ok": False, "error": "not_found"}


def _request(url, form=None, token=None, timeout=10):
    headers = {"Accept": "application/json"}
    body = None
    if form is not None:
        body = urllib.parse.urlencode(form).encode("ascii")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=body, headers=headers)
    # Credentials must never follow a redirect to another host.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=timeout) as response:
            raw = response.read(5 * 1024 * 1024 + 1)
        if len(raw) > 5 * 1024 * 1024:
            raise AuthError("response_too_large")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise AuthError("invalid_response")
        return data
    except urllib.error.HTTPError as e:
        code = "api_failed"
        if e.code == 401:
            code = "reconnect"
        elif e.code == 403:
            code = "permission_denied"
        elif e.code == 400 and url == TOKEN_URL:
            try:
                if json.loads(e.read(8192)).get("error") == "invalid_grant":
                    code = "reconnect"
            except (ValueError, OSError):
                pass
        raise AuthError(code) from None
    except (OSError, ValueError, urllib.error.URLError):
        raise AuthError("network_failed") from None


def _token_record(response, previous=None):
    previous = previous or {}
    access = response.get("access_token")
    refresh = response.get("refresh_token") or previous.get("refresh_token")
    scopes = response.get("scope", SCOPE).split()
    if SCOPE not in scopes:
        raise AuthError("permission_denied")
    if not isinstance(access, str) or not access or not refresh:
        raise AuthError("no_refresh_token")
    try:
        expiry = time.time() + max(0, int(response.get("expires_in", 3600)))
    except (ValueError, TypeError):
        raise AuthError("invalid_response") from None
    return dict(previous, access_token=access, refresh_token=refresh,
                expires_at=expiry, auth_error="")


class Login:
    """One short-lived listener, bound only to loopback; explicitly cancellable."""
    def __init__(self, label="Google", timeout=180, opener=None):
        self.done = threading.Event()
        self.result = None
        self.label = (label or "Google").strip()[:60]
        self.client = client()
        self.state = secrets.token_urlsafe(32)
        self.verifier = secrets.token_urlsafe(64)
        self._cancel = threading.Event()
        self._finish_lock = threading.Lock()
        self._closed = threading.Event()
        self.server = None
        if not self.client.get("client_id"):
            self._finish({"ok": False, "error": "client_missing"})
            return
        login = self
        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                self.request.settimeout(2)
                super().setup()

            def log_message(self, *args):
                pass  # callback code and query strings are secrets

            def do_GET(self):
                parsed = urllib.parse.urlsplit(self.path)
                params = urllib.parse.parse_qs(parsed.query)
                if (parsed.path != "/callback" or len(params.get("state", [])) != 1
                        or not secrets.compare_digest(params["state"][0], login.state)):
                    self.send_error(400, "Invalid authorization response")
                    return
                if params.get("error"):
                    result = {"ok": False, "error": "access_denied"}
                elif len(params.get("code", [])) != 1:
                    result = {"ok": False, "error": "invalid_response"}
                else:
                    result = login._exchange(params["code"][0])
                login._finish(result)
                body = b"You can return to Workspace."
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except OSError:
                    pass
        try:
            self.server = HTTPServer(("127.0.0.1", 0), Handler)
            self.server.timeout = 0.25
            self.redirect = "http://127.0.0.1:%d/callback" % self.server.server_port
            challenge = base64.urlsafe_b64encode(hashlib.sha256(
                self.verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
            self.url = AUTH_URL + "?" + urllib.parse.urlencode({
                "client_id": self.client["client_id"], "redirect_uri": self.redirect,
                "response_type": "code", "scope": SCOPE, "state": self.state,
                "code_challenge": challenge, "code_challenge_method": "S256",
                "access_type": "offline", "prompt": "consent select_account"})
            self.deadline = time.monotonic() + timeout
            threading.Thread(target=self._serve, daemon=True, name="google-login").start()
            if not (opener or webbrowser.open)(self.url):
                self.cancel("browser_failed")
        except Exception:
            if self.server:
                self.server.server_close()
            self._finish({"ok": False, "error": "listener_failed"})

    def _finish(self, result):
        with self._finish_lock:
            if not self.done.is_set():
                self.result = result
                self.done.set()

    def _exchange(self, code):
        try:
            response = _request(TOKEN_URL, form={
                "client_id": self.client["client_id"],
                "client_secret": self.client.get("client_secret", ""),
                "code": code, "code_verifier": self.verifier,
                "redirect_uri": self.redirect, "grant_type": "authorization_code"})
            record = _token_record(response)
            record.update(id="oauth-" + uuid.uuid4().hex[:16], label=self.label,
                          client_id=self.client["client_id"],
                          client_secret=self.client.get("client_secret", ""))
            # Serialize cancel with commit: cancellation cannot persist an account.
            with self._finish_lock:
                if self._cancel.is_set():
                    return {"ok": False, "error": "cancelled"}
                with _lock:
                    data = _accounts()
                    data.append(record)
                    _save(data)
                self.result = {"ok": True, "id": record["id"], "label": self.label}
                self.done.set()
            return {"ok": True, "id": record["id"], "label": self.label}
        except AuthError as e:
            return {"ok": False, "error": str(e)}
        except Exception:
            return {"ok": False, "error": "invalid_response"}

    def _serve(self):
        try:
            while not self.done.is_set() and time.monotonic() < self.deadline:
                self.server.handle_request()
            if not self.done.is_set():
                self._finish({"ok": False, "error": "timeout"})
        finally:
            self.server.server_close()
            self._closed.set()

    def cancel(self, reason="cancelled"):
        with self._finish_lock:
            self._cancel.set()
            if not self.done.is_set():
                self.result = {"ok": False, "error": reason}
                self.done.set()


def _access_token(aid):
    with _lock:
        data = _accounts()
        acc = next((a for a in data if a["id"] == aid), None)
        if not acc:
            raise AuthError("not_found")
        if acc.get("auth_error") == "reconnect":
            raise AuthError("reconnect")
        if acc.get("access_token") and float(acc.get("expires_at") or 0) > time.time() + 60:
            return acc["access_token"]
        try:
            response = _request(TOKEN_URL, form={
                "grant_type": "refresh_token", "refresh_token": acc["refresh_token"],
                "client_id": acc["client_id"], "client_secret": acc.get("client_secret", "")})
            acc.update(_token_record(response, acc))
            _save(data)
            return acc["access_token"]
        except AuthError as e:
            if str(e) == "reconnect":
                acc["auth_error"] = "reconnect"
                _save(data)
            raise


def fetch_events(aid, timeout=10):
    """Google expands recurrence and exceptions; pagination completes before commit."""
    token = _access_token(aid)
    today = dt.datetime.now(dt.timezone.utc)
    params = {"singleEvents": "true", "orderBy": "startTime", "maxResults": "2500",
              "timeMin": (today - dt.timedelta(days=370)).isoformat(),
              "timeMax": (today + dt.timedelta(days=370)).isoformat()}
    out, pages = [], set()
    for _ in range(100):
        try:
            response = _request(API_URL + "?" + urllib.parse.urlencode(params),
                                token=token, timeout=timeout)
        except AuthError as e:
            if str(e) == "reconnect":
                with _lock:
                    data = _accounts()
                    for acc in data:
                        if acc["id"] == aid:
                            acc["auth_error"] = "reconnect"
                    _save(data)
            raise
        for event in response.get("items", []):
            if event.get("status") == "cancelled":
                continue
            start = event.get("start", {})
            value = start.get("dateTime") or start.get("date")
            if not value:
                continue
            try:
                if start.get("dateTime"):
                    stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
                    if stamp.tzinfo is None:
                        from zoneinfo import ZoneInfo
                        stamp = stamp.replace(tzinfo=ZoneInfo(start.get("timeZone") or response["timeZone"]))
                    stamp = stamp.astimezone()
                    date, hhmm = stamp.date().isoformat(), stamp.strftime("%H:%M")
                else:
                    date, hhmm = dt.date.fromisoformat(value).isoformat(), ""
            except (ValueError, KeyError):
                continue
            out.append({"uid": event.get("id", ""), "date": date, "time": hhmm,
                        "title": str(event.get("summary") or "(untitled)")})
        page = response.get("nextPageToken")
        if not page:
            return out
        if page in pages:
            raise AuthError("invalid_response")
        pages.add(page)
        params["pageToken"] = page
    raise AuthError("response_too_large")
