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
# One GET stream's resident reply memory bound (what the gateway holds for it: the unsent event, the copies made while
# it is framed and filtered, the escaped result and the previous event the server may not have taken yet). A stream
# relays notifications, never a tools/call reply, so one child event is capped at 128 KiB (STREAM_EVENT_BYTES). The
# worst transient of one such event (3x for JSON escaping of an emoji-only text = 384 KiB, plus the pending message,
# the copies and the previous transport buffer) is about 1.0 to 1.3 MiB (measured by
# tests/test_get_stream_bounds.py::test_a_worst_case_event_stays_inside_the_stream_bound), so the bound is 2 MiB: 16x
# the event cap, with room for those copies. The reserve in request_budget is an estimate of the sum of these bounds.
STREAM_BYTES = 2 * MiB
STREAM_EVENT_BYTES = 128 * 1024


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
