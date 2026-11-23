"""HM-19c integration: the density limit of the envelope path.

The density limit bounds what the child parses (a container costs 56 to 260 bytes there, a body byte one): at most
gateway.ENVELOPE_MAX_CONTAINERS_PER_KIB containers per KiB of a body above gateway.ENVELOPE_BYTES. Strings that contain
brackets are not containers; a file's text, base64, Odoo batches and every list of scalars below the element cap are not
refused by it."""
import json

import pytest

from mcp_admin_core import gateway, request_envelope as E

LIMITS = gateway.ENVELOPE_LIMITS
KiB = 1024


def call(arguments, ident=7):
    return json.dumps({'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call',
                       'params': {'name': 't', 'arguments': arguments}}, separators=(',', ':')).encode()


def scan(raw):
    return E.scan_sync(raw, LIMITS, lambda name: ())


def refused(raw):
    with pytest.raises(E.EnvelopeRefused) as caught:
        scan(raw)
    return caught.value.reason


def test_the_gateway_enables_the_density_limit():
    assert LIMITS.max_containers_per_kib == gateway.ENVELOPE_MAX_CONTAINERS_PER_KIB == 40
    assert LIMITS.max_depth == 64 and LIMITS.max_elements == 200_000


def test_the_hm19c_objects_shape_is_refused_before_any_child_parses_it():
    # 800 KB, 99,990 objects `{"a":1}`: 125 containers per KiB, 25 times in the child's memory
    raw = call({'items': [{'a': 1}] * 99_990})
    assert len(raw) > 700 * KiB
    assert 'containers per KiB' in refused(raw)


def test_a_body_at_the_limit_is_served_and_a_denser_one_is_not():
    count = 99_000                                   # 2 elements each with the comma: under the 200,000 cap
    size = count * 1024 // 40                        # the byte size at which 99,000 containers are 40 per KiB

    def body(pad):
        return call({'items': [{'p': 'x' * pad}] * count})

    pad = (size - len(body(0))) // count + 1         # a little over the limit's size: the envelope, arguments and list count too
    at_limit = body(pad)
    assert scan(at_limit).containers == count + 4   # + the envelope, arguments and the list
    assert 'containers per KiB' in refused(body(pad - 4))


def test_brackets_inside_strings_are_not_containers():
    found = scan(call({'content': '{[' * (300 * KiB // 2)}))   # 300 KiB of bracket characters in one string
    assert found.containers == 3 and found.elements == 7    # the envelope's own: no container comes from the string


def test_an_odoo_batch_of_3000_records_by_30_fields_is_served():
    records = [{('f%d' % n): ('value %d of record %d' % (n, row)) for n in range(30)} for row in range(3000)]
    raw = call({'records': records})
    assert len(raw) > 64 * KiB
    assert scan(raw).containers == 3004                      # the envelope's 3, the arguments object and its 3000 records


def test_five_thousand_topics_and_fifty_thousand_short_strings_are_served():
    scan(call({'topics': ['sensors/room/%05d/temperature' % n for n in range(5000)]}))
    scan(call({'ids': ['a%d' % n for n in range(50_000)]}))


def test_a_list_of_numbers_at_the_element_cap_is_served_and_past_it_is_not():
    scan(call({'ids': list(range(150_000))}))
    assert 'JSON elements' in refused(call({'ids': list(range(250_000))}))
