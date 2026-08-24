import ipaddress
import logging
from functools import lru_cache
from typing import FrozenSet, Optional

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _build_trusted_networks() -> (
    FrozenSet[ipaddress.IPv4Network | ipaddress.IPv6Network]
):
    raw = (settings.TRUSTED_PROXY_IPS or "").strip()
    if not raw:
        return frozenset()

    networks: set = set()
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            networks.add(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            logger.warning(
                "TRUSTED_PROXY_IPS: invalid entry %r — skipping.  "
                "Use exact IPs or CIDR notation (e.g. '10.0.0.1' or '10.0.0.0/8').",
                entry,
            )
    return frozenset(networks)


def _is_trusted_proxy(ip_str: Optional[str]) -> bool:
    if not ip_str:
        return False
    trusted = _build_trusted_networks()
    if not trusted:
        return False
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in network for network in trusted)
    except ValueError:
        return False


def _limiter_key_func(request: Request) -> str:
    raw_remote = get_remote_address(request)

    if _is_trusted_proxy(raw_remote):
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
            if client_ip:
                logger.debug(
                    "Rate-limit key from X-Forwarded-For (proxy=%s): %s",
                    raw_remote,
                    client_ip,
                )
                return client_ip

    return raw_remote


shared_limiter = Limiter(key_func=_limiter_key_func)
