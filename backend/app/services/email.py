"""Resend transactional email — Roadmap 2 / PR #4.

Thin wrapper over the Resend REST API. We don't pull the official Resend
Python SDK (it adds another dep and the surface we need is one POST). On a
missing RESEND_API_KEY we no-op + log so local dev works without a Resend
project provisioned, and tests don't fire real email.

Templates are inline HTML strings — keep them dependency-free. If we ever
grow real React Email templates we move them under ``templates/`` and
render them with ``react-email-render``.
"""
from __future__ import annotations

import logging
import os
from typing import Iterable

try:
    import httpx  # type: ignore
except Exception:  # pragma: no cover
    httpx = None  # surface error only when actually sending

from ..config import settings

log = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"


def _send(to: str, subject: str, html: str, *, tag: str) -> dict | None:
    """Send a single email via Resend. Returns the Resend response JSON, or
    ``None`` when we deliberately skipped (missing key / no recipient).

    Never raises — email is best-effort glue. A failed send must not break
    the calling state transition. Logs at WARNING on transport errors.
    """
    if not to:
        log.info("email.skip tag=%s reason=no_recipient", tag)
        return None
    if not settings.resend_api_key or os.environ.get("PYTEST_CURRENT_TEST"):
        log.info("email.skip tag=%s to=%s reason=no_api_key subject=%r", tag, to, subject)
        return None
    if httpx is None:  # pragma: no cover
        log.warning("email.skip tag=%s reason=httpx_missing", tag)
        return None
    try:
        resp = httpx.post(
            _RESEND_URL,
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.resend_from_email,
                "to": [to],
                "subject": subject,
                "html": html,
                "tags": [{"name": "type", "value": tag}],
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # pragma: no cover - transport failures
        log.warning("email.fail tag=%s to=%s err=%s", tag, to, exc)
        return None


# ---------------------------------------------------------------------------
# Inline HTML templates. Kept intentionally small — no inline images, no CSS
# beyond what every email client renders. Wrapped in a single helper so the
# header/footer stay consistent.
# ---------------------------------------------------------------------------
def _wrap(title: str, body_html: str) -> str:
    return f"""<!doctype html>
<html><body style="font-family:-apple-system,BlinkMacSystemFont,Helvetica,Arial,sans-serif;color:#111;background:#fafaf7;padding:24px;">
  <div style="max-width:560px;margin:0 auto;background:#fff;border:1px solid #e5e3dc;padding:32px;">
    <div style="font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:0.15em;color:#888;margin-bottom:18px;">FRANKLY</div>
    <h1 style="font-size:24px;font-weight:500;margin:0 0 16px;letter-spacing:-0.01em;">{title}</h1>
    {body_html}
    <hr style="border:0;border-top:1px solid #e5e3dc;margin:28px 0 14px;" />
    <div style="font-size:11px;color:#888;">You're receiving this because a recruiter is reviewing your simulated fit profile. Manage notifications in your dashboard.</div>
  </div>
</body></html>"""


def _slots_block(slots: Iterable[str]) -> str:
    rows = "".join(f'<li style="margin:4px 0;">{s}</li>' for s in slots)
    return f'<ul style="padding-left:18px;margin:8px 0 16px;">{rows}</ul>'


def _cta(href: str, label: str) -> str:
    return (
        f'<a href="{href}" style="display:inline-block;background:#111;color:#fff;'
        f'text-decoration:none;padding:12px 20px;font-weight:500;">{label}</a>'
    )


# ---------------------------------------------------------------------------
# Public senders. One per event in the PR #4 flow.
# ---------------------------------------------------------------------------
def send_interview_invite(
    *, to: str, position_name: str, role: str, proposed_slots: list[str]
) -> None:
    href = f"{settings.frontend_url}/candidate#matches"
    body = (
        f'<p>You have an interview invite for <strong>{position_name}</strong> '
        f'({role}). Choose one of the proposed times below, propose your own, '
        f'or decline.</p>'
        + _slots_block(proposed_slots)
        + _cta(href, "Review invite")
    )
    _send(to, f"Interview invite · {position_name}", _wrap("You have an interview invite", body), tag="interview_invite")


def send_interview_accepted(
    *, to: str, candidate_name: str, position_name: str, selected_slot: str
) -> None:
    href = f"{settings.frontend_url}/manager"
    body = (
        f'<p><strong>{candidate_name}</strong> accepted your interview invite for '
        f'<strong>{position_name}</strong>.</p>'
        f'<p>Confirmed time: <strong>{selected_slot}</strong></p>'
        + _cta(href, "Open dashboard")
    )
    _send(to, f"Interview accepted · {candidate_name}", _wrap("Interview accepted", body), tag="interview_accepted")


def send_interview_declined(
    *, to: str, candidate_name: str, position_name: str, message: str | None
) -> None:
    href = f"{settings.frontend_url}/manager"
    msg_html = f'<p style="font-style:italic;color:#555;">"{message}"</p>' if message else ""
    body = (
        f'<p><strong>{candidate_name}</strong> declined the interview invite for '
        f'<strong>{position_name}</strong>.</p>'
        + msg_html
        + _cta(href, "Open dashboard")
    )
    _send(to, f"Interview declined · {candidate_name}", _wrap("Interview declined", body), tag="interview_declined")


def send_interview_counter(
    *, to: str, candidate_name: str, position_name: str, counter_slots: list[str], message: str | None
) -> None:
    href = f"{settings.frontend_url}/manager"
    msg_html = f'<p style="font-style:italic;color:#555;">"{message}"</p>' if message else ""
    body = (
        f'<p><strong>{candidate_name}</strong> counter-proposed new times for '
        f'<strong>{position_name}</strong>.</p>'
        + _slots_block(counter_slots)
        + msg_html
        + _cta(href, "Open dashboard")
    )
    _send(to, f"Counter-proposal · {candidate_name}", _wrap("Counter-proposal", body), tag="interview_counter")
