"""Outlook plugin — Microsoft Graph (mail & calendar), device-code OAuth.

Personal, single-user, self-hosted setup:

  * Sign-in uses the OAuth 2.0 *device authorization grant*: the backend asks
    Microsoft for a short ``user_code`` + a ``verification_uri`` link, the user
    signs in once in a browser, and we receive a long-lived **refresh token**.
  * The refresh token is stored in the DB (``oauth_tokens`` / provider
    ``outlook``); access tokens are minted on demand and auto-refreshed, so the
    user never pastes or rotates a token.

Requires a Microsoft Entra app registration with public-client flows enabled
(see backend/.env.example). Set ``OUTLOOK_CLIENT_ID`` (and optionally
``OUTLOOK_TENANT``) in the environment.

The login flow itself is driven by the ``/api/outlook/*`` endpoints in main.py;
this module owns the protocol + the agent-facing Graph tools.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

import db
from plugins.base import PluginSpec, ToolSpec


PLUGIN_ID = "ext.outlook"
PROVIDER = "outlook"

SCOPES = "offline_access User.Read Mail.ReadWrite Mail.Send Calendars.ReadWrite"
GRAPH = "https://graph.microsoft.com/v1.0"

# Refresh a little before the token actually expires.
_EXPIRY_SKEW = 120


INSTRUCTIONS = """Outlook plugin (Microsoft 365 mail & calendar):
- Use the outlook_* tools to read, search, and send mail and manage calendar events.
- Before sending mail or creating events, show the user a clear draft (recipients,
  subject, body / time) and send only after they confirm, unless they explicitly
  asked you to send directly.
- Never invent message contents, addresses, or times — read them from the tools.
- If a tool reports Outlook is not connected, tell the user to enable the Outlook
  plugin and click Connect in the sidebar; do not retry blindly.
"""


class OutlookNotConnected(Exception):
    pass


class OutlookNotConfigured(Exception):
    pass


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def client_id() -> str:
    cid = os.environ.get("OUTLOOK_CLIENT_ID", "").strip()
    if not cid:
        raise OutlookNotConfigured(
            "OUTLOOK_CLIENT_ID is not set. Register a Microsoft Entra app and set it."
        )
    return cid


def _tenant() -> str:
    return os.environ.get("OUTLOOK_TENANT", "common").strip() or "common"


def _authority() -> str:
    return f"https://login.microsoftonline.com/{_tenant()}/oauth2/v2.0"


def is_configured() -> bool:
    return bool(os.environ.get("OUTLOOK_CLIENT_ID", "").strip())


def is_connected() -> bool:
    token = db.get_oauth_token(PROVIDER)
    return bool(token and token.get("refresh_token"))


def connection_status() -> dict[str, Any]:
    token = db.get_oauth_token(PROVIDER)
    return {
        "configured": is_configured(),
        "connected": bool(token and token.get("refresh_token")),
        "account": (token or {}).get("account") or None,
        "pending": _pending is not None,
    }


# ---------------------------------------------------------------------------
# Device-code login
# ---------------------------------------------------------------------------

# Single-user: a module-level pending flow is sufficient. Lost on restart, in
# which case the user simply clicks Connect again.
_pending: dict[str, Any] | None = None


async def start_device_login() -> dict[str, Any]:
    """Begin the device-code flow; returns the code + link to show the user."""
    global _pending
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{_authority()}/devicecode",
            data={"client_id": client_id(), "scope": SCOPES},
        )
    if resp.status_code != 200:
        raise RuntimeError(f"device code request failed: {resp.status_code} {resp.text}")
    data = resp.json()
    _pending = {
        "device_code": data["device_code"],
        "interval": int(data.get("interval", 5)),
        "expires_at": time.time() + int(data.get("expires_in", 900)),
    }
    return {
        "userCode": data["user_code"],
        "verificationUri": data["verification_uri"],
        "message": data.get("message", ""),
        "expiresIn": int(data.get("expires_in", 900)),
        "interval": int(data.get("interval", 5)),
    }


async def poll_device_login() -> dict[str, Any]:
    """Poll once for completion of the pending device-code flow."""
    global _pending
    if _pending is None:
        return {"status": "idle"}
    if time.time() > _pending["expires_at"]:
        _pending = None
        return {"status": "expired"}

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{_authority()}/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": client_id(),
                "device_code": _pending["device_code"],
            },
        )
    data = resp.json()
    if resp.status_code == 200:
        await _store_token_response(data, fetch_account=True)
        _pending = None
        token = db.get_oauth_token(PROVIDER) or {}
        return {"status": "connected", "account": token.get("account") or None}

    error = data.get("error")
    if error in ("authorization_pending", "slow_down"):
        return {"status": "pending", "interval": _pending["interval"]}
    # authorization_declined / expired_token / bad_verification_code / other
    _pending = None
    return {"status": "error", "error": error, "detail": data.get("error_description", "")}


def disconnect() -> None:
    global _pending
    _pending = None
    db.delete_oauth_token(PROVIDER)


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------

async def _store_token_response(data: dict[str, Any], fetch_account: bool = False) -> None:
    expires_at = time.time() + int(data.get("expires_in", 3600))
    access = data.get("access_token")
    db.set_oauth_token(
        PROVIDER,
        access_token=access,
        refresh_token=data.get("refresh_token"),
        expires_at=expires_at,
        scope=data.get("scope", ""),
    )
    if fetch_account and access:
        try:
            account = await _fetch_account(access)
            if account:
                db.set_oauth_token(
                    PROVIDER, access_token=access, refresh_token=None,
                    expires_at=expires_at, scope=data.get("scope", ""), account=account,
                )
        except Exception:
            pass


async def _fetch_account(access_token: str) -> str:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{GRAPH}/me",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"$select": "userPrincipalName,mail,displayName"},
        )
    if resp.status_code == 200:
        me = resp.json()
        return me.get("mail") or me.get("userPrincipalName") or me.get("displayName") or ""
    return ""


async def _refresh(refresh_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{_authority()}/token",
            data={
                "grant_type": "refresh_token",
                "client_id": client_id(),
                "refresh_token": refresh_token,
                "scope": SCOPES,
            },
        )
    if resp.status_code != 200:
        raise OutlookNotConnected(
            f"token refresh failed ({resp.status_code}); reconnect Outlook."
        )
    data = resp.json()
    await _store_token_response(data)
    return data


async def get_access_token(force_refresh: bool = False) -> str:
    token = db.get_oauth_token(PROVIDER)
    if not token or not token.get("refresh_token"):
        raise OutlookNotConnected("Outlook is not connected.")
    if (
        not force_refresh
        and token.get("access_token")
        and token.get("expires_at", 0) > time.time() + _EXPIRY_SKEW
    ):
        return token["access_token"]
    data = await _refresh(token["refresh_token"])
    return data["access_token"]


# ---------------------------------------------------------------------------
# Graph request helper
# ---------------------------------------------------------------------------

async def _graph(method: str, path: str, **kwargs) -> httpx.Response:
    token = await get_access_token()
    url = path if path.startswith("http") else f"{GRAPH}{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(
            method, url, headers={"Authorization": f"Bearer {token}"}, **kwargs
        )
        if resp.status_code == 401:
            token = await get_access_token(force_refresh=True)
            resp = await client.request(
                method, url, headers={"Authorization": f"Bearer {token}"}, **kwargs
            )
    return resp


def _err(resp: httpx.Response) -> dict[str, Any]:
    try:
        body = resp.json().get("error", {})
        detail = body.get("message") or str(body)
    except Exception:
        detail = resp.text[:300]
    return {"error": f"Graph error {resp.status_code}: {detail}"}


def _recipients(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    items = value if isinstance(value, list) else str(value).replace(";", ",").split(",")
    return [
        {"emailAddress": {"address": addr.strip()}}
        for addr in items
        if str(addr).strip()
    ]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

async def outlook_list_messages(
    folder: str = "inbox", limit: int = 10, unread_only: bool = False
) -> dict[str, Any]:
    """List recent messages from a mail folder (default inbox)."""
    params: dict[str, Any] = {
        "$top": max(1, min(int(limit), 50)),
        "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead,webLink",
        "$orderby": "receivedDateTime desc",
    }
    if unread_only:
        params["$filter"] = "isRead eq false"
    resp = await _graph("GET", f"/me/mailFolders/{folder}/messages", params=params)
    if resp.status_code != 200:
        return _err(resp)
    out = []
    for m in resp.json().get("value", []):
        sender = (m.get("from") or {}).get("emailAddress", {})
        out.append({
            "id": m.get("id"),
            "subject": m.get("subject"),
            "from": sender.get("address"),
            "fromName": sender.get("name"),
            "received": m.get("receivedDateTime"),
            "preview": m.get("bodyPreview"),
            "unread": not m.get("isRead", True),
            "webLink": m.get("webLink"),
        })
    return {"folder": folder, "count": len(out), "messages": out}


async def outlook_search_messages(query: str, limit: int = 10) -> dict[str, Any]:
    """Full-text search across the mailbox."""
    resp = await _graph(
        "GET",
        "/me/messages",
        params={
            "$search": f'"{query}"',
            "$top": max(1, min(int(limit), 50)),
            "$select": "id,subject,from,receivedDateTime,bodyPreview,webLink",
        },
    )
    if resp.status_code != 200:
        return _err(resp)
    out = []
    for m in resp.json().get("value", []):
        sender = (m.get("from") or {}).get("emailAddress", {})
        out.append({
            "id": m.get("id"),
            "subject": m.get("subject"),
            "from": sender.get("address"),
            "received": m.get("receivedDateTime"),
            "preview": m.get("bodyPreview"),
            "webLink": m.get("webLink"),
        })
    return {"query": query, "count": len(out), "messages": out}


async def outlook_read_message(message_id: str) -> dict[str, Any]:
    """Read a single message's full body and recipients by id."""
    resp = await _graph(
        "GET",
        f"/me/messages/{message_id}",
        params={"$select": "subject,from,toRecipients,ccRecipients,receivedDateTime,body"},
    )
    if resp.status_code != 200:
        return _err(resp)
    m = resp.json()
    body = m.get("body", {}) or {}
    content = (body.get("content") or "")[:12000]
    return {
        "id": message_id,
        "subject": m.get("subject"),
        "from": (m.get("from") or {}).get("emailAddress", {}).get("address"),
        "to": [r["emailAddress"]["address"] for r in m.get("toRecipients", [])],
        "cc": [r["emailAddress"]["address"] for r in m.get("ccRecipients", [])],
        "received": m.get("receivedDateTime"),
        "bodyType": body.get("contentType"),
        "body": content,
    }


async def outlook_send_mail(
    to: Any,
    subject: str,
    body: str,
    cc: Any = None,
    html: bool = False,
) -> dict[str, Any]:
    """Send an email. `to`/`cc` accept an address or list/comma-separated list."""
    recipients = _recipients(to)
    if not recipients:
        return {"error": "no valid 'to' recipients"}
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML" if html else "Text", "content": body},
            "toRecipients": recipients,
            "ccRecipients": _recipients(cc),
        },
        "saveToSentItems": True,
    }
    resp = await _graph("POST", "/me/sendMail", json=payload)
    if resp.status_code not in (200, 202):
        return _err(resp)
    return {
        "sent": True,
        "to": [r["emailAddress"]["address"] for r in recipients],
        "subject": subject,
    }


async def outlook_list_events(days_ahead: int = 7, limit: int = 10) -> dict[str, Any]:
    """List upcoming calendar events within the next `days_ahead` days."""
    now = time.time()
    start = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    end = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + days_ahead * 86400))
    resp = await _graph(
        "GET",
        "/me/calendarView",
        params={
            "startDateTime": start,
            "endDateTime": end,
            "$top": max(1, min(int(limit), 50)),
            "$select": "id,subject,start,end,location,organizer,webLink,isAllDay",
            "$orderby": "start/dateTime",
        },
        headers={"Prefer": 'outlook.timezone="UTC"'},
    )
    if resp.status_code != 200:
        return _err(resp)
    out = []
    for e in resp.json().get("value", []):
        out.append({
            "id": e.get("id"),
            "subject": e.get("subject"),
            "start": (e.get("start") or {}).get("dateTime"),
            "end": (e.get("end") or {}).get("dateTime"),
            "allDay": e.get("isAllDay"),
            "location": (e.get("location") or {}).get("displayName"),
            "organizer": (e.get("organizer") or {}).get("emailAddress", {}).get("address"),
            "webLink": e.get("webLink"),
        })
    return {"window": {"start": start, "end": end}, "count": len(out), "events": out}


async def outlook_create_event(
    subject: str,
    start: str,
    end: str,
    timezone: str = "UTC",
    attendees: Any = None,
    location: str | None = None,
    body: str | None = None,
) -> dict[str, Any]:
    """Create a calendar event. `start`/`end` are ISO 8601 datetimes."""
    payload: dict[str, Any] = {
        "subject": subject,
        "start": {"dateTime": start, "timeZone": timezone},
        "end": {"dateTime": end, "timeZone": timezone},
    }
    if location:
        payload["location"] = {"displayName": location}
    if body:
        payload["body"] = {"contentType": "Text", "content": body}
    attendee_list = _recipients(attendees)
    if attendee_list:
        payload["attendees"] = [
            {"emailAddress": a["emailAddress"], "type": "required"} for a in attendee_list
        ]
    resp = await _graph("POST", "/me/events", json=payload)
    if resp.status_code not in (200, 201):
        return _err(resp)
    e = resp.json()
    return {"created": True, "id": e.get("id"), "subject": e.get("subject"), "webLink": e.get("webLink")}


# ---------------------------------------------------------------------------
# Tool wrapping — surface auth state as a clean message instead of an exception.
# ---------------------------------------------------------------------------

_NOT_CONNECTED_MSG = {
    "error": "Outlook is not connected. Ask the user to enable the Outlook "
    "plugin and click Connect in the sidebar."
}
_NOT_CONFIGURED_MSG = {
    "error": "Outlook is not configured. OUTLOOK_CLIENT_ID must be set "
    "(register a Microsoft Entra app)."
}


def _guarded(fn):
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except OutlookNotConnected:
            return dict(_NOT_CONNECTED_MSG)
        except OutlookNotConfigured:
            return dict(_NOT_CONFIGURED_MSG)

    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


def get_plugin() -> PluginSpec:
    return PluginSpec(
        id=PLUGIN_ID,
        name="Outlook",
        type="external",
        description=(
            "Microsoft Outlook mail & calendar via Graph. Connect once with your "
            "Microsoft account (device-code sign-in); the token auto-refreshes."
        ),
        instructions=INSTRUCTIONS,
        tools=[
            ToolSpec(name="outlook_list_messages", handler=_guarded(outlook_list_messages)),
            ToolSpec(name="outlook_search_messages", handler=_guarded(outlook_search_messages)),
            ToolSpec(name="outlook_read_message", handler=_guarded(outlook_read_message)),
            ToolSpec(name="outlook_send_mail", handler=_guarded(outlook_send_mail)),
            ToolSpec(name="outlook_list_events", handler=_guarded(outlook_list_events)),
            ToolSpec(name="outlook_create_event", handler=_guarded(outlook_create_event)),
        ],
    )
