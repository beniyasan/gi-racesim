"""Atomic local response storage and conservative cache parsing."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping


_TOKEN = re.compile(r'^[A-Za-z0-9_-]+$')


@dataclass(frozen=True)
class CacheEntry:
    raw_ref: str
    path: Path
    metadata_path: Path
    body_sha256: str
    body_bytes: int


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'title':
            self._in_title = True

    def handle_endtag(self, tag):
        if tag.lower() == 'title':
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title_parts.append(data)
        self.text_parts.append(data)


class CacheStore:
    """Store immutable response bytes beneath a caller-selected directory."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)

    def _paths(self, token: str) -> tuple[Path, Path]:
        if not isinstance(token, str) or not _TOKEN.fullmatch(token):
            raise ValueError('unsafe response token')
        return self.root / f'{token}.html', self.root / f'{token}.json'

    @staticmethod
    def _write_new(path: Path, data: bytes) -> None:
        """Write without replacing an existing response or sidecar."""
        fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
        temporary_path = Path(temporary)
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            # A hard link gives us create-if-absent semantics after the temp
            # file is complete; os.replace would silently overwrite evidence.
            os.link(temporary_path, path)
        except FileExistsError:
            raise FileExistsError(f'cache path already exists: {path}')
        finally:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass

    def save(self, token: str, body: bytes, metadata: Mapping[str, Any]) -> CacheEntry:
        if isinstance(body, str):
            body = body.encode('utf-8')
        if not isinstance(body, bytes):
            raise TypeError('cached body must be bytes')
        path, metadata_path = self._paths(token)
        digest = sha256(body).hexdigest()
        raw_ref = f'cache:{token}'
        record = dict(metadata)
        record.update({
            'raw_ref': raw_ref,
            'body_sha256': digest,
            'body_bytes': len(body),
            'path': str(path),
        })
        try:
            encoded = json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2).encode('utf-8')
        except (TypeError, ValueError) as exc:
            raise ValueError('cache metadata must be JSON serializable') from exc
        self._write_new(path, body)
        try:
            self._write_new(metadata_path, encoded)
        except BaseException:
            # Keep the already saved HTML as evidence.  It is never removed or
            # overwritten automatically; an operator can inspect it manually.
            raise
        return CacheEntry(raw_ref, path, metadata_path, digest, len(body))

    def parse(self, response: Mapping[str, Any]) -> dict[str, Any]:
        """Parse a saved response only; this method never invokes a transport."""
        raw_ref = str(response['raw_ref'])
        path = Path(str(response['path']))
        result: dict[str, Any] = {
            'raw_ref': raw_ref,
            'path': str(path),
            'status_code': response.get('status_code'),
        }
        try:
            body = path.read_bytes()
        except FileNotFoundError:
            result['state'] = 'CACHE_MISSING'
            return result
        digest = sha256(body).hexdigest()
        result.update({'body_sha256': digest, 'body_bytes': len(body)})
        if digest != response.get('body_sha256'):
            result['state'] = 'HASH_MISMATCH'
            return result
        parser = _TextParser()
        try:
            parser.feed(body.decode('utf-8', errors='replace'))
            parser.close()
        except Exception as error:
            result['state'] = 'PARSE_ERROR'
            result['error'] = str(error) or error.__class__.__name__
            return result
        result.update({
            'state': 'PARSED',
            'title': ''.join(parser.title_parts).strip(),
            'text': ' '.join(''.join(parser.text_parts).split()),
        })
        return result
