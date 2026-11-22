"""Bound forwarded reply exposure for a switched-on Odoo add-on.

One ticket stays owned by the request until its ASGI response finishes, including
slow readers and cancellation. 64 MiB covers a maximum 8 MiB child event's
worst 3x JSON escaping plus one previous event awaiting server flow control.
The nominal per-profile forwarding and queue quotas remain separate.
"""

MiB = 1024 * 1024
TICKET_BYTES = 64 * MiB
TOTAL_BYTES = 512 * MiB
DEFAULT_TICKETS = 3
EXTRA_TICKETS = 1


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
