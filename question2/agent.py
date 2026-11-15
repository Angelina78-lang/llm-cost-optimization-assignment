from __future__ import annotations

import json
from dataclasses import dataclass

from shared.billing import CostSession
from shared.kb import all_articles_blob, article_ids
from shared.llm import ChatMessage, LlmClient
from shared.tools import format_thread, get_order, get_ticket

from question1.agent import parse_resolution

ALLOWED_ACTIONS = {"REFUND", "REPLACE", "SEND_ARTICLE", "ESCALATE_TIER2"}


@dataclass
class TicketResolution:
    action: str
    kb_article: str


class SupportPipeline:
    """Triage and audit are plain code; the help center is a cached prefix;
    only one LLM call is made per ticket."""

    def __init__(self, session: CostSession | None = None):
        self.session = session or CostSession()
        self.llm = LlmClient(self.session)
        # Static and identical for every ticket, so it can be cached.
        # Real articles only: the padding notes in the expanded blob say
        # they do not change policy, so they are not sent.
        self._system = "\n\n".join(
            [
                "You are ShopAssist, a Tier-1 support agent.",
                "Allowed actions: REFUND, REPLACE, SEND_ARTICLE, ESCALATE_TIER2. "
                "kb_article must be the id of one help-center article.",
                "HELP CENTER:",
                all_articles_blob(),
                'Reply with ONLY one line of JSON: {"action":"...","kb_article":"..."}. '
                "No other text.",
            ]
        )
        self._cached_prefix = "SYSTEM:\n" + self._system

    def handle_ticket(self, ticket_id: str) -> TicketResolution:
        case = self._triage(ticket_id)
        raw = self._compose(case)
        return self._audit(raw)

    def _triage(self, ticket_id: str) -> str:
        """No LLM: just build a compact case description."""
        ticket = get_ticket(ticket_id)
        order = get_order(ticket["order_id"])
        thread = format_thread(ticket)
        snapshot = json.dumps(order, separators=(",", ":"))
        return (
            f"TICKET_ID: {ticket_id}\nTHREAD:\n{thread}\n"
            f"ORDER_SNAPSHOT:\n{snapshot}\nEND_SNAPSHOT"
        )

    def _compose(self, case: str) -> str:
        """The only LLM call."""
        messages = [ChatMessage("system", self._system), ChatMessage("user", case)]
        return self.llm.chat("compose", messages, cached_prefix=self._cached_prefix)

    def _audit(self, raw: str) -> TicketResolution:
        """No LLM: validate the answer with code."""
        parsed = parse_resolution(raw)
        if parsed.action not in ALLOWED_ACTIONS:
            raise ValueError(f"Invalid action: {parsed.action}")
        if parsed.kb_article not in article_ids():
            raise ValueError(f"Unknown article: {parsed.kb_article}")
        return TicketResolution(parsed.action, parsed.kb_article)