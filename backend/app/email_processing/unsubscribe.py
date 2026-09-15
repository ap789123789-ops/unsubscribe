import re
from dataclasses import dataclass
from urllib.parse import urlparse

from app.domain.models import UnsubscribeMethod
from app.email_processing.normalizer import NormalizedEmail


@dataclass(frozen=True)
class DiscoveredMethod:
    method: UnsubscribeMethod
    target: str
    source: str


class UnsubscribeDiscovery:
    def discover(self, email: NormalizedEmail) -> tuple[DiscoveredMethod, ...]:
        discovered: list[DiscoveredMethod] = []
        header = email.headers.get("list-unsubscribe", "")
        targets = re.findall(r"<([^>]+)>", header)
        one_click = email.headers.get("list-unsubscribe-post", "").lower()

        https_targets = [target for target in targets if target.lower().startswith("https://")]
        mail_targets = [target for target in targets if target.lower().startswith("mailto:")]
        if "list-unsubscribe=one-click" in one_click:
            discovered.extend(
                DiscoveredMethod(UnsubscribeMethod.RFC8058, target, "header")
                for target in https_targets
            )
        discovered.extend(
            DiscoveredMethod(UnsubscribeMethod.MAILTO, target, "header") for target in mail_targets
        )

        header_web = https_targets if "list-unsubscribe=one-click" not in one_click else []
        for target in (*header_web, *email.links):
            parsed = urlparse(target)
            if (
                parsed.scheme == "https"
                and parsed.hostname
                and re.search(r"unsubscrib|preferences?", target, re.I)
            ):
                discovered.append(
                    DiscoveredMethod(UnsubscribeMethod.BROWSER, target, "header-or-body")
                )
        return tuple(dict.fromkeys(discovered))
