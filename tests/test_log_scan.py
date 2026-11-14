"""HM-01: tests/log_scan.py finds a watched value wherever a log record can carry it, and never reports the value."""
import io
import logging
import secrets
import threading

import pytest

from log_scan import TOKEN_WINDOW, LogScan, log_scan  # noqa: F401  (log_scan: the fixture under test)
from mcp_admin_core import redact


@pytest.fixture
def scan():
    value = LogScan().start()
    try:
        yield value
    finally:
        value.stop()


def kinds(scan):
    return sorted(kind for kind, *_ in scan.hits())


def test_message_arguments_exception_stack_and_extra_are_all_scanned(scan):
    token = secrets.token_urlsafe(32)
    scan.watch(token)
    logger = logging.getLogger('hm01.logscan.sites')
    logger.warning('in the message ' + token)
    logger.warning('in an argument %s', token)
    try:
        raise RuntimeError('in an exception ' + token)
    except RuntimeError:
        logger.exception('failed')
    logger.warning('stack', stack_info=True, extra={'note': 'in an extra ' + token})
    hits = scan.hits()
    assert [kind for kind, *_ in hits] == ['token'] * 4
    assert {name for _, name, _, _ in hits} == {'hm01.logscan.sites'}


def test_records_are_seen_before_any_handler_level_or_propagation_filter(scan):
    token = secrets.token_urlsafe(32)
    scan.watch(token)
    private = logging.getLogger('hm01.logscan.private')
    private.propagate = False  # as uvicorn's own loggers
    private.addHandler(logging.NullHandler())
    try:
        private.info('quiet ' + token)
        # A logger without its own level follows the root, lowered to DEBUG while the scan runs.
        logging.getLogger('hm01.logscan.debug').debug('debug ' + token)
        worker = threading.Thread(target=lambda: logging.getLogger('hm01.logscan.thread').error('thread ' + token))
        worker.start()
        worker.join()
    finally:
        private.handlers.clear()
        private.propagate = True
    assert sorted(name for _, name, _, _ in scan.hits()) == [
        'hm01.logscan.debug', 'hm01.logscan.private', 'hm01.logscan.thread']


def test_token_fragments_and_name_case_count(scan):
    token = secrets.token_urlsafe(32)
    scan.watch(token)
    scan.watch('Alpha Prod Synthetic', kind='name')
    logger = logging.getLogger('hm01.logscan.fragments')
    logger.warning(token[3:3 + TOKEN_WINDOW])          # a piece as long as the window
    logger.warning(token[:TOKEN_WINDOW - 1])           # one character shorter: not a token leak
    logger.warning('profile ALPHA PROD SYNTHETIC')     # another letter case
    assert kinds(scan) == ['name', 'token']


def test_secret_path_scrubbed_by_redaction_is_not_a_hit(scan):
    """What every handler gets: the record after mcp_admin_core.redact's record factory scrubbed it."""
    token = secrets.token_urlsafe(32)
    redact.install()
    scan.watch(token)
    logger = logging.getLogger('hm01.logscan.redacted')
    logger.warning('POST %s 200', f'/private_{token}/mcp')          # in an argument
    logger.warning('POST /private_' + token + '/mcp 404')           # in the message
    logger.warning('POST /private_%s/mcp 404', token)               # in an argument of a secret-path template
    assert scan.hits() == []
    rendered = [text for name, _, _, text in scan.seen if name == 'hm01.logscan.redacted']
    assert len(rendered) == 3 and all(token[:TOKEN_WINDOW] not in text for text in rendered)
    assert rendered[0].endswith('POST /private_[REDACTED]/mcp 200')
    assert rendered[1].endswith('POST /private_[REDACTED]/mcp 404')


def test_a_value_only_a_handler_filter_hides_still_counts(scan):
    """A record is taken as a logger dispatches it: a handler filter that scrubs it afterwards (redact's second layer,
    RedactSecretPaths on uvicorn's and the root's handlers) does not hide a value the record factory let through, as
    other handlers (logging.lastResort, a handler added later) would write it unscrubbed."""
    token = secrets.token_urlsafe(32)
    scan.watch(token)

    class Scrub(logging.Filter):
        def filter(self, record):
            record.msg, record.args = 'scrubbed by a handler filter', ()
            return True

    logger = logging.getLogger('hm01.logscan.second-layer')
    written = io.StringIO()
    handler = logging.StreamHandler(written)
    handler.addFilter(Scrub())
    logger.addHandler(handler)
    logger.propagate = False
    try:
        logger.warning('token %s', token)
    finally:
        logger.removeHandler(handler)
        logger.propagate = True
    (record,) = [record for record in scan.records if record.name == 'hm01.logscan.second-layer']
    # The filter ran on the same record and the filtered handler wrote the scrubbed text.
    assert record.getMessage() == written.getvalue().strip() == 'scrubbed by a handler filter'
    assert kinds(scan) == ['token']


def test_watch_state_covers_tokens_and_credentials(scan, tmp_path):
    from mcp_admin_core.products import ProductStore
    store = ProductStore(tmp_path / 'state', 'odoo')
    try:
        state = store.update(connection={'url': 'https://odoo.invalid', 'database': 'DUMMY-db',
                                         'username': 'DUMMY-user', 'password': 'DUMMY-hm01-logscan-password'})
    finally:
        store.close()
    scan.watch_state(state)
    watched = dict((value, kind) for kind, value in scan.watched)
    assert watched[state.token] == watched[state.child_token] == 'token'
    assert watched['DUMMY-hm01-logscan-password'] == 'secret'
    logging.getLogger('hm01.logscan.state').warning('child said %s', state.child_token)
    logging.getLogger('hm01.logscan.state').warning('backend said DUMMY-hm01-logscan-password')
    assert kinds(scan) == ['secret', 'token']


def test_report_names_the_place_never_the_value(scan):
    token = secrets.token_urlsafe(32)
    scan.watch(token)
    scan.watch('Beta Synthetic', kind='name')
    logging.getLogger('hm01.logscan.report').error('leak %s for Beta Synthetic', token)
    with pytest.raises(pytest.fail.Exception) as failure:
        scan.assert_clean()
    message = str(failure.value)
    assert 'hm01.logscan.report' in message and 'token' in message and 'name' in message
    assert 'test_log_scan.py:' in message
    assert token[:TOKEN_WINDOW] not in message and 'Beta Synthetic' not in message and 'leak' not in message


def test_watch_refuses_values_too_short_to_scan(scan):
    for value, kind in (('x' * (TOKEN_WINDOW - 1), 'token'), ('abc', 'name'), ('', 'secret'), (None, 'token')):
        with pytest.raises(ValueError):
            scan.watch(value, kind=kind)
    with pytest.raises(ValueError):
        scan.watch('Valid Name', kind='profile')


def test_stop_restores_root_level_and_dispatch_and_leaves_the_factory():
    root = logging.getLogger()
    level, handle, factory = root.level, logging.Logger.handle, logging.getLogRecordFactory()
    scan = LogScan().start()
    assert root.level == logging.DEBUG and logging.Logger.handle is not handle
    assert logging.getLogRecordFactory() is factory  # redact's layer (or none) is never touched
    scan.stop()
    assert root.level == level and logging.Logger.handle is handle and logging.getLogRecordFactory() is factory
    logging.getLogger('hm01.logscan.after').warning('not collected')
    assert scan.records == [] and scan.seen == []


def test_scans_started_inside_each_other_keep_the_chain():
    """Stopping the outer scan first leaves the inner one installed and collecting; each stop restores its own."""
    handle = logging.Logger.handle
    outer, inner = LogScan().start(), None
    try:
        inner = LogScan().start()
        outer.stop()
        logging.getLogger('hm01.logscan.chain').warning('inner only')
        assert [record.getMessage() for record in inner.records] == ['inner only'] and outer.records == []
        inner.stop()
        logging.getLogger('hm01.logscan.chain').warning('neither')
        assert len(inner.records) == 1 and outer.records == []
    finally:
        for scan in (inner, outer):
            if scan is not None:
                scan.stop()
        logging.Logger.handle = handle  # the outer layer, now pass-through, is dropped here


def test_the_fixture_collects_while_the_test_runs(log_scan):
    log_scan.watch(secrets.token_urlsafe(32))
    logging.getLogger('hm01.logscan.fixture').info('an ordinary record')
    assert any(record.name == 'hm01.logscan.fixture' for record in log_scan.records)
    assert log_scan.hits() == []
