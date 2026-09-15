from collections import Counter

from app.gmail.protocols import GmailMessage, GmailPage


class FakeGmailGateway:
    def __init__(
        self,
        *,
        pages: dict[str | None, GmailPage],
        messages: dict[str, GmailMessage],
        read_failures: dict[str, int] | None = None,
        email: str = "reader@example.com",
    ) -> None:
        self.pages = pages
        self.messages = messages
        self.remaining_failures = dict(read_failures or {})
        self.read_attempts: Counter[str] = Counter()
        self.email = email

    async def list_messages(
        self,
        *,
        query: str,
        max_results: int,
        page_token: str | None,
    ) -> GmailPage:
        page = self.pages[page_token]
        return GmailPage(messages=page.messages[:max_results], next_page_token=page.next_page_token)

    async def get_message(self, message_id: str) -> GmailMessage:
        self.read_attempts[message_id] += 1
        remaining = self.remaining_failures.get(message_id, 0)
        if remaining:
            self.remaining_failures[message_id] = remaining - 1
            raise ConnectionError("Synthetic Gmail read failure")
        return self.messages[message_id]

    async def profile_email(self) -> str:
        return self.email
