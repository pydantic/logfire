from logfire.observe._observe import Observe, ObserveConfig

__all__ = (
    'Observe',
    'ObserveConfig',
    'configure',
    'span',
    'instrument',
    'log',
    'info',
    'debug',
    'notice',
    'warning',
    'error',
    'critical',
    'context_tracer',
)

_instance = Observe()

configure = _instance.configure

tags = _instance.tags

span = _instance.span
instrument = _instance.instrument

log = _instance.log
info = _instance.info
debug = _instance.debug
notice = _instance.notice
warning = _instance.warning
error = _instance.error
critical = _instance.critical

context_tracer = _instance.context_tracer
