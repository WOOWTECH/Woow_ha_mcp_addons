"""Test-only adaptation of the real multi-profile guard to the owned private port."""
from pathlib import Path

from mcp_admin_core import features, products, profile_runtime


def install(endpoint, marker):
    features.MULTI_PROFILE_PRODUCTS = frozenset({'odoo'})
    # The disposable XML-RPC backend is loopback; HM-20 rejects it when enabled.
    products.loopback_refused = lambda product: False
    original = profile_runtime.ListenerGuard

    class ObservedGuard(original):
        def __init__(self, process, port, *, limits):
            # The owned harness moves the real child from 3000 to an ephemeral port.
            super().__init__(process, endpoint.port, limits=limits)

        async def handle_async_request(self, request):
            response = await super().handle_async_request(request)
            assert self.status == 'owned', self.status
            Path(marker).write_text('owned\n')
            return response

    profile_runtime.ListenerGuard = ObservedGuard
