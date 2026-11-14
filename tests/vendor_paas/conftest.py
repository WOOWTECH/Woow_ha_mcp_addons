"""HM-02: the vendored PaaS log redaction tests run with logging as the PaaS suite has it.

The four test_log_redaction_*.py modules here are woow-mcp-server 7d111b1's packages/mcp-admin-core/tests files, byte
for byte: their only import of the module, ``from mcp_admin_core import log_redaction``, already names the vendored
packages/mcp-admin-core/mcp_admin_core/log_redaction.py, so not even an import changed
(docs/provenance/ha-multiprofile-HM-02-20261114.md). They test that module alone; the HA composition (the PaaS rules
first, then the HA rules) is tests/test_redaction_matrix.py's.

Earlier HA tests in the same pytest process leave the HA layer installed: redact.install()'s record factory and
redact.guard_handlers()' RedactSecretPaths on uvicorn's and the root's handlers. Both scrub again around the PaaS
module, so a PaaS test that times a record or reads the PaaS mask would see the HA composition instead (without this
file, two of them fail after tests/test_secret_path.py::test_real_uvicorn_logs_never_show_the_secret). Each test here
therefore starts from the standard record factory with the PaaS module not installed and without those handler
filters, and logging is put back afterwards: the record factory, the PaaS module's install flag, every logger's filters
and every handler's filters. No PaaS factory or PathTokenRedactionFilter stays behind for the HA tests that run later.
"""
import logging

import pytest

from mcp_admin_core import log_redaction, redact


def _loggers():
    return [logging.getLogger(), *(logger for logger in list(logging.Logger.manager.loggerDict.values())
                                   if isinstance(logger, logging.Logger))]


@pytest.fixture(autouse=True)
def paas_logging(monkeypatch):
    monkeypatch.setattr(logging, '_logRecordFactory', logging.LogRecord)
    monkeypatch.setattr(log_redaction, '_factory_installed', False)
    loggers = {id(logger): (logger, list(logger.filters)) for logger in _loggers()}
    handlers = {}
    for logger, _ in loggers.values():
        for handler in logger.handlers:
            if id(handler) not in handlers:
                handlers[id(handler)] = (handler, list(handler.filters))
                handler.filters[:] = [f for f in handler.filters if not isinstance(f, redact.RedactSecretPaths)]
    try:
        yield
    finally:
        for handler, filters in handlers.values():
            handler.filters[:] = filters
        for logger in _loggers():
            if id(logger) in loggers:
                logger.filters[:] = loggers[id(logger)][1]
            else:  # a logger the test created: only the PaaS filter install() may have put there goes
                logger.filters[:] = [f for f in logger.filters
                                     if not isinstance(f, log_redaction.PathTokenRedactionFilter)]
