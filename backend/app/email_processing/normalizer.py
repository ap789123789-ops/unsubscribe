import base64
import hashlib
import re
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup

from app.gmail.protocols import GmailMessage

MAX_MESSAGE_SIZE = 10 * 1024 * 1024
MAX_DECODED_TEXT = 2 * 1024 * 1024
MAX_MODEL_CHARS = 20_000


@dataclass(frozen=True)
class NormalizedEmail:
    gmail_id: str
    thread_id: str
    headers: dict[str, str]
    text: str
    model_text: str
    safe_excerpt: str
    body_hash: str
    links: tuple[str, ...]
    oversized: bool


class EmailNormalizer:
    def normalize(self, message: GmailMessage) -> NormalizedEmail:
        headers = self._headers(message.payload)
        if message.size_estimate > MAX_MESSAGE_SIZE:
            return NormalizedEmail(
                gmail_id=message.id,
                thread_id=message.thread_id,
                headers=headers,
                text="",
                model_text="",
                safe_excerpt="",
                body_hash=hashlib.sha256(b"").hexdigest(),
                links=(),
                oversized=True,
            )

        plain_parts: list[str] = []
        html_parts: list[str] = []
        links: list[str] = []
        decoded_bytes = 0
        for mime_type, raw in self._text_parts(message.payload):
            remaining = MAX_DECODED_TEXT - decoded_bytes
            if remaining <= 0:
                break
            raw = raw[:remaining]
            decoded_bytes += len(raw)
            decoded = raw.decode("utf-8", errors="replace")
            if mime_type == "text/plain":
                plain_parts.append(decoded)
            else:
                safe_text, found_links = self._html_to_text(decoded)
                html_parts.append(safe_text)
                links.extend(found_links)

        selected = "\n\n".join(plain_parts or html_parts)
        selected = self._remove_quoted_history(selected)
        digest = hashlib.sha256(selected.encode("utf-8")).hexdigest()
        return NormalizedEmail(
            gmail_id=message.id,
            thread_id=message.thread_id,
            headers=headers,
            text=selected,
            model_text=self._model_budget(selected),
            safe_excerpt=selected[:500],
            body_hash=digest,
            links=tuple(dict.fromkeys(links)),
            oversized=False,
        )

    def _headers(self, payload: Any) -> dict[str, str]:
        return {
            str(item.get("name", "")).lower(): str(item.get("value", ""))
            for item in payload.get("headers", [])
            if item.get("name")
        }

    def _text_parts(self, payload: Any) -> list[tuple[str, bytes]]:
        result: list[tuple[str, bytes]] = []
        mime_type = str(payload.get("mimeType", "")).lower()
        filename = str(payload.get("filename", ""))
        data = payload.get("body", {}).get("data")
        if not filename and mime_type in {"text/plain", "text/html"} and data:
            result.append((mime_type, self._decode_base64url(str(data))))
        for part in payload.get("parts", []) or []:
            result.extend(self._text_parts(part))
        return result

    @staticmethod
    def _decode_base64url(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        try:
            return base64.urlsafe_b64decode(value + padding)
        except ValueError:
            return b""

    @staticmethod
    def _html_to_text(html: str) -> tuple[str, list[str]]:
        soup = BeautifulSoup(html, "html.parser")
        for element in soup(["script", "style", "noscript", "svg", "template"]):
            element.decompose()
        for element in list(soup.find_all(True)):
            style = str(element.get("style", "")).replace(" ", "").lower()
            if (
                element.has_attr("hidden")
                or str(element.get("aria-hidden", "")).lower() == "true"
                or "display:none" in style
                or "visibility:hidden" in style
            ):
                element.decompose()
        links = [
            str(anchor.get("href"))
            for anchor in soup.find_all("a", href=True)
            if re.search(r"unsubscrib|preferences?", anchor.get_text(" ", strip=True), re.I)
        ]
        text = soup.get_text("\n", strip=True)
        return text, links

    @staticmethod
    def _remove_quoted_history(text: str) -> str:
        kept: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(">") or re.match(r"^On .+ wrote:$", stripped):
                break
            kept.append(line.rstrip())
        return "\n".join(kept).strip()

    @staticmethod
    def _model_budget(text: str) -> str:
        if len(text) <= MAX_MODEL_CHARS:
            return text
        signal = re.search(r"unsubscrib|preferences?|sale|offer|receipt|security", text, re.I)
        signal_start = max(0, (signal.start() if signal else len(text) // 2) - 2_000)
        high_signal = text[signal_start : signal_start + 4_000]
        return (
            text[:12_000]
            + "\n[content truncated]\n"
            + high_signal
            + "\n[content truncated]\n"
            + text[-4_000:]
        )

