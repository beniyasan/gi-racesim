"""Replaceable HTTP transports for the collector.

The collector owns request budgeting; a transport is only allowed to perform
the one request represented by a gate token.  ``UrllibTransport`` explicitly
disables redirect handling and has no retry loop.  The default transport is
``DisabledTransport`` so importing or invoking the collector cannot contact a
real site accidentally.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from email.message import Message
from typing import Callable, Iterable, Mapping, Protocol, Union
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


class TransportError(RuntimeError):
    """A transport failure with no response available."""


class ExternalAccessDisabled(TransportError):
    """Raised when external HTTP has not been explicitly enabled."""


@dataclass(frozen=True)
class HttpResponse:
    """The single response returned by one transport invocation."""

    status_code: int
    body: bytes = b''
    headers: Mapping[str, str] = field(default_factory=dict)
    url: str | None = None

    def __post_init__(self):
        if isinstance(self.body, str):
            object.__setattr__(self, 'body', self.body.encode('utf-8'))
        if not isinstance(self.body, bytes):
            raise TypeError('HTTP response body must be bytes')
        if isinstance(self.status_code, bool) or not isinstance(self.status_code, int):
            raise TypeError('HTTP status must be an integer')
        if not 100 <= self.status_code <= 599:
            raise ValueError('HTTP status outside 100..599')
        object.__setattr__(self, 'headers', {
            str(key).lower(): str(value) for key, value in dict(self.headers).items()
        })


class HttpTransport(Protocol):
    """Transport contract: one call, one response or one exception."""

    enabled: bool

    def fetch(self, url: str) -> HttpResponse:
        ...


class DisabledTransport:
    """Fail closed without opening a socket."""

    enabled = False

    def fetch(self, url: str) -> HttpResponse:
        raise ExternalAccessDisabled(
            'external HTTP is disabled; use a mock transport for offline checks'
        )


class _NoRedirectHandler(HTTPRedirectHandler):
    # Returning None makes urllib surface the 3xx response as an HTTPError;
    # importantly it prevents a second request outside the gate ledger.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class UrllibTransport:
    """Minimal opt-in HTTPS transport with redirects and retries disabled."""

    enabled = True

    def __init__(self, *, allow_external: bool = False, timeout: float = 30.0,
                 user_agent: str = 'GIRaceSimCollector/0.1'):
        self.enabled = bool(allow_external)
        self.timeout = float(timeout)
        if self.timeout <= 0:
            raise ValueError('timeout must be positive')
        self.user_agent = user_agent
        self._opener = build_opener(_NoRedirectHandler)

    @staticmethod
    def _headers(message: Message | Mapping[str, str]) -> dict[str, str]:
        if hasattr(message, 'items'):
            return {str(k).lower(): str(v) for k, v in message.items()}
        return {str(k).lower(): str(v) for k, v in dict(message).items()}

    def fetch(self, url: str) -> HttpResponse:
        if not self.enabled:
            raise ExternalAccessDisabled(
                'external HTTP is disabled; pass an explicit opt-in for live transport'
            )
        request = Request(url, headers={'User-Agent': self.user_agent}, method='GET')
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                # Reading the body is part of this one request.  No follow-up
                # operation is performed by this adapter.
                body = response.read()
                return HttpResponse(response.status, body,
                                    self._headers(response.headers), response.geturl())
        except HTTPError as error:
            # HTTPError for 3xx/4xx is still the response to the one request.
            body = error.read()
            return HttpResponse(error.code, body, self._headers(error.headers),
                                error.geturl())
        except (URLError, OSError, TimeoutError) as error:
            raise TransportError(str(error) or error.__class__.__name__) from error


TransportItem = Union[HttpResponse, BaseException, Callable[[str], HttpResponse]]


class MockTransport:
    """Deterministic transport used by tests and the runbook.

    Each ``fetch`` consumes exactly one queued item.  There is intentionally no
    retry or redirect behavior here, so a test can assert the request count
    directly.
    """

    enabled = True

    def __init__(self, responses: Iterable[TransportItem] | TransportItem):
        if isinstance(responses, (HttpResponse, BaseException)) or callable(responses):
            responses = [responses]
        self._responses = list(responses)
        self.calls = 0
        self.urls: list[str] = []

    def fetch(self, url: str) -> HttpResponse:
        self.calls += 1
        self.urls.append(url)
        if not self._responses:
            raise TransportError('mock transport has no response queued')
        item = self._responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        if callable(item):
            item = item(url)
        if not isinstance(item, HttpResponse):
            raise TypeError('mock response must be HttpResponse')
        return item
