import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit


class UnsafeTarget(ValueError):
    pass


class HostResolver(Protocol):
    async def resolve(self, hostname: str) -> tuple[str, ...]: ...


class SystemHostResolver:
    async def resolve(self, hostname: str) -> tuple[str, ...]:
        def lookup() -> tuple[str, ...]:
            records = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
            return tuple(sorted({record[4][0] for record in records}))

        try:
            return await asyncio.to_thread(lookup)
        except socket.gaierror as error:
            raise UnsafeTarget("The unsubscribe host could not be resolved") from error


@dataclass(frozen=True)
class ValidatedTarget:
    url: str
    origin: str
    hostname: str
    addresses: tuple[str, ...]


class UrlSafetyPolicy:
    def __init__(self, resolver: HostResolver | None = None) -> None:
        self._resolver = resolver or SystemHostResolver()

    async def validate_at_plan_time(self, target: str) -> ValidatedTarget:
        return await self._validate(target)

    async def revalidate_before_connect(
        self, target: ValidatedTarget
    ) -> ValidatedTarget:
        refreshed = await self._validate(target.url)
        if refreshed.hostname != target.hostname:
            raise UnsafeTarget("The unsubscribe host changed after review")
        return refreshed

    async def allow_browser_request(self, target: str) -> bool:
        try:
            await self._validate(target)
        except UnsafeTarget:
            return False
        return True

    async def _validate(self, target: str) -> ValidatedTarget:
        parsed = urlsplit(target)
        if parsed.scheme.lower() != "https":
            raise UnsafeTarget("Automatic unsubscribe requests require HTTPS")
        if parsed.username is not None or parsed.password is not None:
            raise UnsafeTarget("URL credentials are not allowed")
        if parsed.fragment:
            raise UnsafeTarget("URL fragments are not allowed")
        try:
            port = parsed.port
        except ValueError as error:
            raise UnsafeTarget("The unsubscribe port is invalid") from error
        if port not in (None, 443):
            raise UnsafeTarget("Only the default HTTPS port is allowed")
        hostname = parsed.hostname
        if not hostname or "%" in hostname:
            raise UnsafeTarget("The unsubscribe hostname is invalid")
        try:
            hostname = hostname.encode("idna").decode("ascii").lower().rstrip(".")
        except UnicodeError as error:
            raise UnsafeTarget("The unsubscribe hostname is invalid") from error

        literal = self._literal_address(hostname)
        addresses = (literal,) if literal is not None else await self._resolver.resolve(hostname)
        if not addresses:
            raise UnsafeTarget("The unsubscribe host has no network address")
        if any(not self._is_public(address) for address in addresses):
            raise UnsafeTarget("Every unsubscribe address must be public")

        host_display = f"[{hostname}]" if ":" in hostname else hostname
        netloc = host_display if port is None else f"{host_display}:443"
        canonical = urlunsplit(("https", netloc, parsed.path or "/", parsed.query, ""))
        return ValidatedTarget(
            url=canonical,
            origin=f"https://{netloc}",
            hostname=hostname,
            addresses=tuple(addresses),
        )

    @staticmethod
    def _literal_address(hostname: str) -> str | None:
        try:
            return str(ipaddress.ip_address(hostname.strip("[]")))
        except ValueError:
            return None

    @staticmethod
    def _is_public(address: str) -> bool:
        try:
            return ipaddress.ip_address(address.split("%", 1)[0]).is_global
        except ValueError as error:
            raise UnsafeTarget("DNS returned an invalid network address") from error
