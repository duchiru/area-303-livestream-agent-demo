# Copyright (C) 2026 Nguyen The Viet, Vu Thi Mai Anh, Do Huu An Phu, Phan Thuy Tram
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""BlobPath — a pathlib.Path-compatible interface backed by Vercel Blob Storage.

Drop-in replacement for pathlib.Path for the writable STORAGE_DIR.
Only the methods actively used in the services layer are implemented.
"""

import fnmatch
from dataclasses import dataclass
from typing import Iterator

import vercel.blob as blob
from vercel.blob.errors import BlobNotFoundError


@dataclass
class BlobStat:
    """Mimics the fields of os.stat_result used by the service layer."""
    st_size: int    # file size in bytes
    st_mtime: float # last-modified as POSIX timestamp


class BlobPath:
    """pathlib.Path-compatible object whose I/O is routed to Vercel Blob Storage."""

    def __init__(self, *parts: str) -> None:
        raw = "/".join(str(p).replace("\\", "/") for p in parts)
        self._key: str = "/".join(seg for seg in raw.split("/") if seg)

    # ── Path joining ──────────────────────────────────────────────────── #
    def __truediv__(self, other: str) -> "BlobPath":
        return BlobPath(self._key, str(other))

    def __str__(self) -> str:
        return self._key

    def __repr__(self) -> str:
        return f"BlobPath({self._key!r})"

    def __fspath__(self) -> str:
        return self._key

    # ── Properties ───────────────────────────────────────────────────── #
    @property
    def name(self) -> str:
        return self._key.split("/")[-1] if "/" in self._key else self._key

    @property
    def parent(self) -> "BlobPath":
        parts = self._key.rsplit("/", 1)
        return BlobPath(parts[0]) if len(parts) > 1 else BlobPath("")

    # ── Internal helpers ──────────────────────────────────────────────── #
    def _try_head(self):
        try:
            return blob.head(self._key)
        except Exception:
            return None

    # ── Existence / metadata ──────────────────────────────────────────── #
    def exists(self) -> bool:
        if self._try_head() is not None:
            return True
        result = blob.list_objects(prefix=self._key + "/", limit=1)
        return bool(result.blobs)

    def is_dir(self) -> bool:
        result = blob.list_objects(prefix=self._key + "/", limit=1)
        return bool(result.blobs)

    def stat(self) -> BlobStat:
        meta = self._try_head()
        if meta is None:
            raise FileNotFoundError(f"No such blob: {self._key!r}")
        return BlobStat(
            st_size=meta.size,
            st_mtime=meta.uploaded_at.timestamp(),
        )

    # ── Read ─────────────────────────────────────────────────────────── #
    def read_bytes(self) -> bytes:
        try:
            return blob.get(self._key, access="private", use_cache=False).content
        except BlobNotFoundError:
            raise FileNotFoundError(f"No such blob: {self._key!r}")

    def read_text(self, encoding: str = "utf-8") -> str:
        return self.read_bytes().decode(encoding)

    # ── Write ────────────────────────────────────────────────────────── #
    def write_bytes(self, data: bytes) -> int:
        blob.put(self._key, data, access="private", overwrite=True)
        return len(data)

    def write_text(self, data: str, encoding: str = "utf-8") -> int:
        blob.put(self._key, data.encode(encoding), access="private", overwrite=True)
        return len(data)

    # ── Delete ───────────────────────────────────────────────────────── #
    def unlink(self, missing_ok: bool = True) -> None:
        try:
            blob.delete(self._key)
        except BlobNotFoundError:
            if not missing_ok:
                raise FileNotFoundError(f"No such blob: {self._key!r}")

    # ── Directory simulation ──────────────────────────────────────────── #
    def mkdir(self, parents: bool = False, exist_ok: bool = False) -> None:
        """No-op on blob storage (flat namespace). Kept for API compatibility."""
        try:
            blob.create_folder(self._key + "/", overwrite=exist_ok)
        except Exception:
            pass  # Not critical — blobs can exist without an explicit folder marker.

    def iterdir(self) -> Iterator["BlobPath"]:
        prefix = self._key.rstrip("/") + "/"
        for item in blob.iter_objects(prefix=prefix):
            yield BlobPath(item.pathname)

    def glob(self, pattern: str) -> Iterator["BlobPath"]:
        prefix = self._key.rstrip("/") + "/"
        full_pattern = prefix + pattern
        for item in blob.iter_objects(prefix=prefix):
            if fnmatch.fnmatch(item.pathname, full_pattern):
                yield BlobPath(item.pathname)
