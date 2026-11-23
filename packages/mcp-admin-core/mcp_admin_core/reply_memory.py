"""Bound forwarded reply exposure for a switched-on Odoo add-on.

One ticket stays owned by the request until its ASGI response finishes, including
slow readers and cancellation. 64 MiB covers a maximum 8 MiB child event's
worst 3x JSON escaping plus one previous event awaiting server flow control.
The nominal per-profile forwarding and queue quotas remain separate.

0.5.1 (F1): an event stream (GET) takes no ticket. The ticket stays the bound of a POST that may carry a large reply.
A stream is bounded by its own small numbers below, so the add-on's worst case adds "most streams x STREAM_BYTES"
(request_budget.ODOO_STREAM_RESERVE_MIB) beside the 512 MiB of tickets.
"""

MiB = 1024 * 1024
TICKET_BYTES = 64 * MiB
TOTAL_BYTES = 512 * MiB
DEFAULT_TICKETS = 3
EXTRA_TICKETS = 1
# One GET stream's whole resident reply memory (what the gateway holds for it: the unsent event, the copies made while
# it is framed and filtered, the escaped result and the previous event the server may not have taken yet). A ticket
# covers an 8 MiB child event with 8x its size (64 MiB); a stream relays notifications, never a tools/call reply, so
# its event is capped at 1/8 of this (STREAM_EVENT_BYTES) with the same 8x allowance: 128 KiB x 8 = 1 MiB.
STREAM_BYTES = 1 * MiB
STREAM_EVENT_BYTES = STREAM_BYTES // 8


class ReplyMemory:
    TICKET_BYTES = TICKET_BYTES

    def __init__(self):
        self.held = 0
        self.by_profile = {}

    def take(self, profile_id):
        limit = DEFAULT_TICKETS if profile_id == 'default' else EXTRA_TICKETS
        count = self.by_profile.get(profile_id, 0)
        if count >= limit or self.held + TICKET_BYTES > TOTAL_BYTES:
            return False
        self.by_profile[profile_id] = count + 1
        self.held += TICKET_BYTES
        return True

    def give(self, profile_id):
        count = self.by_profile[profile_id]
        if count == 1:
            del self.by_profile[profile_id]
        else:
            self.by_profile[profile_id] = count - 1
        self.held -= TICKET_BYTES
