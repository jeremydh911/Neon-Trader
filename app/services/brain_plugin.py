"""Plug-in agent brain for AhanaTrade.

A Grok Bot or any OpenAI-compatible / webhook agent can drive the desk when
AHANA_BRAIN_URL is set. AHANA_BRAIN_TOKEN is optional bearer auth.

If those env vars are unset, callers keep the existing Tina / Eddie / Gloria /
Victor / Riley council. This module never logs the token.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

BRAIN_URL_ENV = "AHANA_BRAIN_URL"
BRAIN_TOKEN_ENV = "AHANA_BRAIN_TOKEN"
BRAIN_MODEL_ENV = "AHANA_BRAIN_MODEL"
DEFAULT_MODEL = "grok"
COUNCIL_NAMES = ("Tina", "Eddie", "Gloria", "Victor", "Riley")

_ACTIONS = {"BUY", "SELL", "HOLD"}


def brain_url() -> str:
    return (os.getenv(BRAIN_URL_ENV) or "").strip()


def brain_configured() -> bool:
    """True when an external brain endpoint is wired via env."""
    return bool(brain_url())


def active_brain() -> str:
    return "plugin" if brain_configured() else "council"


def _token() -> str:
    return (os.getenv(BRAIN_TOKEN_ENV) or "").strip()


def _headers() -> Dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "AhanaTrade-brain-plugin/1.0",
    }
    token = _token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _looks_openai(url: str) -> bool:
    path = (urlparse(url).path or "").rstrip("/")
    lowered = url.lower()
    return (
        "chat/completions" in lowered
        or path.endswith("/v1")
        or "/v1/" in path
    )


def _resolve_url(url: str) -> str:
    parsed = urlparse(url)
    path = (parsed.path or "").rstrip("/")
    if path.endswith("/v1"):
        return url.rstrip("/") + "/chat/completions"
    return url


def _strip_fences(text: str) -> str:
    raw = (text or "").strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    return raw


def _normalize_proposal(payload: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    action = str(payload.get("action") or payload.get("side") or "HOLD").upper()
    if action not in _ACTIONS:
        action = "HOLD"
    try:
        confidence = float(payload.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    plan = str(payload.get("plan") or payload.get("rationale") or payload.get("content") or "")
    approved = payload.get("approved")
    if approved is None:
        approved = action in ("BUY", "SELL") and confidence >= 0.5
    return {
        "agent": payload.get("agent") or "plugin-brain",
        "role": "plugin",
        "specialty": "external_brain",
        "symbol": payload.get("symbol") or symbol,
        "action": action,
        "confidence": confidence,
        "plan": plan,
        "approved": bool(approved),
        "brain": "plugin",
        "raw": {k: v for k, v in payload.items() if k != "raw"},
    }


def _post_json(url: str, body: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        # Never include headers (token) in the log.
        logger.warning("Plugin brain HTTP %s from %s", exc.code, urlparse(url).netloc)
        raise
    except Exception:
        logger.warning("Plugin brain request failed for host %s", urlparse(url).netloc)
        raise
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"plan": raw, "action": "HOLD", "confidence": 0.0}
    return parsed if isinstance(parsed, dict) else {"plan": raw, "action": "HOLD"}


def _from_openai_response(parsed: Dict[str, Any]) -> Dict[str, Any]:
    choices = parsed.get("choices") or []
    if not choices:
        return parsed
    message = (choices[0] or {}).get("message") or {}
    content = message.get("content") or ""
    text = _strip_fences(content)
    try:
        inner = json.loads(text)
        if isinstance(inner, dict):
            return inner
    except json.JSONDecodeError:
        pass
    return {"action": "HOLD", "confidence": 0.0, "plan": text}


def consult_brain(
    symbol: str,
    current_price: float,
    indicators: Optional[Dict[str, Any]] = None,
    available_capital: float = 10000.0,
    market_sentiment: str = "neutral",
    extra: Optional[Dict[str, Any]] = None,
    timeout: float = 20.0,
) -> Dict[str, Any]:
    """POST the market context to the configured brain and normalize a proposal."""
    url = brain_url()
    if not url:
        raise RuntimeError("AHANA_BRAIN_URL is not set")

    context = {
        "symbol": symbol,
        "current_price": current_price,
        "indicators": indicators or {},
        "available_capital": available_capital,
        "market_sentiment": market_sentiment,
        "product": "AhanaTrade",
        "constraints": {
            "session": "07:00-20:00 ET",
            "order_type": "LIMIT",
            "max_deployed_out": 10000,
        },
    }
    if extra:
        context["extra"] = extra

    resolved = _resolve_url(url)
    if _looks_openai(url) or _looks_openai(resolved):
        body: Dict[str, Any] = {
            "model": (os.getenv(BRAIN_MODEL_ENV) or DEFAULT_MODEL).strip() or DEFAULT_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the AhanaTrade desk brain. Reply with JSON only: "
                        '{"action":"BUY|SELL|HOLD","confidence":0-1,"plan":"..."}'
                    ),
                },
                {"role": "user", "content": json.dumps(context)},
            ],
            "temperature": 0.2,
        }
        parsed = _post_json(resolved, body, timeout)
        payload = _from_openai_response(parsed)
    else:
        payload = _post_json(resolved, context, timeout)

    proposal = _normalize_proposal(payload, symbol)
    _notify_adapters("brain_proposal", proposal)
    return proposal


def plugin_proposal(
    symbol: str,
    current_price: float,
    indicators: Optional[Dict[str, Any]] = None,
    available_capital: float = 10000.0,
    market_sentiment: str = "neutral",
    extra: Optional[Dict[str, Any]] = None,
    timeout: float = 20.0,
) -> Optional[Dict[str, Any]]:
    """Return a plugin proposal, or None so the caller keeps the council."""
    if not brain_configured():
        return None
    try:
        return consult_brain(
            symbol=symbol,
            current_price=current_price,
            indicators=indicators,
            available_capital=available_capital,
            market_sentiment=market_sentiment,
            extra=extra,
            timeout=timeout,
        )
    except Exception as exc:
        logger.warning("Plugin brain failed; falling back to council: %s", exc)
        return None


def _notify_adapters(event: str, payload: Dict[str, Any]) -> None:
    try:
        from .adapters.ahanaflow import publish_session
        publish_session(event, payload)
    except Exception:
        logger.debug("AhanaFlow notify skipped", exc_info=False)
    try:
        from .adapters.chatwire import send_message
        send_message(event, payload)
    except Exception:
        logger.debug("Chatwire notify skipped", exc_info=False)




def annotate_catch(plan: Dict[str, Any], current_price: float = 0.0) -> Dict[str, Any]:
    """Annotate a mechanical catch. Plugin brain if URL set, else local council stub."""
    symbol = str((plan or {}).get("symbol") or "")
    price = float(current_price or (plan or {}).get("limit_hi") or 0.0)
    extra = {"catch": plan, "role": "annotate_setup"}
    plugin = plugin_proposal(
        symbol=symbol,
        current_price=price,
        indicators={"setup": (plan or {}).get("setup"), "why": (plan or {}).get("why")},
        available_capital=float((plan or {}).get("remaining_budget") or 10000.0),
        extra=extra,
        timeout=12.0,
    )
    if plugin:
        try:
            from .ahana_memory import get_ahana_memory
            get_ahana_memory().ingest(
                {"kind": "brain_note", "symbol": symbol, "setup": (plan or {}).get("setup"), "payload": plugin}
            )
        except Exception:
            logger.debug("brain_note ingest skipped", exc_info=False)
        return plugin
    stub = {
        "agent": "council-stub",
        "role": "council",
        "symbol": symbol,
        "action": (plan or {}).get("side") or "HOLD",
        "confidence": 0.55,
        "plan": (
            "Local council stub: mechanical {setup} on {symbol}. "
            "Plug in AHANA_BRAIN_URL to annotate catches."
        ).format(setup=(plan or {}).get("setup") or "setup", symbol=symbol or "the tape"),
        "approved": False,
        "brain": "council",
        "brain_note": "Local detector (council stub): mechanical levels only.",
    }
    try:
        from .ahana_memory import get_ahana_memory
        get_ahana_memory().ingest(
            {"kind": "council_note", "symbol": symbol, "setup": (plan or {}).get("setup"), "payload": stub}
        )
    except Exception:
        logger.debug("council_note ingest skipped", exc_info=False)
    return stub
