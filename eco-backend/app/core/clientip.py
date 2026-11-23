"""The real client IP behind our own web server / load balancer (QA BUG-10).

X-Forwarded-For is only believed when the request comes from a TRUSTED_PROXIES address (the Next.js server, the
load balancer). We read it right-to-left and take the first address that isn't one of our proxies, so entries a
client puts on the left itself are ignored. Called directly from an untrusted address, the socket address is used.
If a trusted proxy forwarded no client address, the IP is unknown (None): never our own server's address.
"""
from __future__ import annotations

import hmac
import ipaddress
from functools import lru_cache

from fastapi import Request

from app.core.config import get_settings


@lru_cache
def _trusted() -> tuple:
    return tuple(ipaddress.ip_network(n, strict=False) for n in get_settings().trusted_proxies)


def _is_trusted(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(a in n for n in _trusted())


def _right_most_untrusted(header: str) -> str | None:
    chain = [p.strip() for p in header.split(",") if p.strip()]
    for hop in reversed(chain):
        try:
            ip = str(ipaddress.ip_address(hop))
        except ValueError:
            return None  # malformed chain: don't guess
        if not _is_trusted(ip):
            return ip
    return None


def _from_our_web_server(request: Request) -> str | None:
    """Our web server's view of the visitor, when it reaches us over the public internet (Render free plan).

    Believed only with the shared WEB_FORWARD_SECRET (constant-time compare); the chain is the one OUR web server
    received from its own load balancer, read right-to-left like X-Forwarded-For.
    """
    secret = get_settings().web_forward_secret
    sent = request.headers.get("x-eco-forward-secret")
    if not secret or not sent or not hmac.compare_digest(sent.encode(), secret.get_secret_value().encode()):
        return None
    return _right_most_untrusted(request.headers.get("x-eco-forwarded-for", ""))


def client_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    via_web = _from_our_web_server(request)
    if via_web:
        return via_web
    peer = request.client.host
    if not _is_trusted(peer):
        try:
            return str(ipaddress.ip_address(peer))
        except ValueError:
            return None
    return _right_most_untrusted(request.headers.get("x-forwarded-for", ""))
