"""Persistent collection controls with an opt-in, replaceable HTTP transport."""

from .cache import CacheEntry, CacheStore
from .gate import Gate, JST, Policy
from .service import Collector, StructureChange, classify_response
from .transport import (
    DisabledTransport,
    ExternalAccessDisabled,
    HttpResponse,
    HttpTransport,
    MockTransport,
    TransportError,
    UrllibTransport,
)

__all__ = [
    'CacheEntry', 'CacheStore', 'Collector', 'DisabledTransport', 'ExternalAccessDisabled',
    'Gate', 'HttpResponse', 'HttpTransport', 'JST', 'MockTransport', 'Policy', 'TransportError',
    'UrllibTransport', 'StructureChange', 'classify_response',
]
