# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Non-authoritative, permission-safe metadata catalog for AI discovery."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import Any, TYPE_CHECKING

from flask import current_app
from sqlalchemy.exc import OperationalError

from superset.ai.models import AIDataSourceCatalogEntry
from superset.extensions import db

if TYPE_CHECKING:
    from superset.ai.discovery import DiscoveryCandidate

DEFAULT_CATALOG_TTL_SECONDS = 3_600


class MetadataCatalogService:
    """Persist safe source metadata without making it authoritative.

    The caller must apply RBAC before consuming a catalog candidate. Entries
    contain no rows, SQL text, credentials, or user-provided chat content.
    """

    def __init__(self, ttl_seconds: int | None = None) -> None:
        if ttl_seconds is None:
            ttl_seconds = current_app.config.get(
                "AI_METADATA_CATALOG_TTL_SECONDS", DEFAULT_CATALOG_TTL_SECONDS
            )
        self.ttl_seconds = max(1, int(ttl_seconds))

    def get_fresh_candidate(self, source_key: str) -> DiscoveryCandidate | None:
        """Return a cached candidate only while its freshness is known."""
        try:
            entry = db.session.get(AIDataSourceCatalogEntry, source_key)
        except (OperationalError, AttributeError):
            return None
        if entry is None or not self._is_fresh(entry):
            return None
        return self._to_candidate(entry)

    def upsert(self, candidate: DiscoveryCandidate) -> None:
        """Store a safe snapshot of a source after live, authorized discovery."""
        now = datetime.now(timezone.utc)
        payload = self._payload(candidate)
        try:
            entry = db.session.get(AIDataSourceCatalogEntry, candidate.source_key)
            if entry is None:
                entry = AIDataSourceCatalogEntry(source_key=candidate.source_key)
                db.session.add(entry)
            for key, value in payload.items():
                setattr(entry, key, value)
            entry.version = self._version(payload)
            entry.indexed_at = now
            entry.expires_at = now + timedelta(seconds=self.ttl_seconds)
            entry.invalidated_at = None
        except (OperationalError, AttributeError):
            # Deployments that have not applied the migration retain live
            # discovery instead of failing a chat request.
            rollback = getattr(db.session, "rollback", None)
            if rollback is not None:
                rollback()

    def upsert_many(self, candidates: Iterable[DiscoveryCandidate]) -> int:
        """Refresh all live candidates in one transaction."""
        count = 0
        try:
            for candidate in candidates:
                self.upsert(candidate)
                count += 1
            db.session.commit()
        except (OperationalError, AttributeError):
            rollback = getattr(db.session, "rollback", None)
            if rollback is not None:
                rollback()
            return 0
        return count

    def invalidate(
        self,
        *,
        source_key: str | None = None,
        database_id: int | None = None,
    ) -> int:
        """Mark entries stale for manual and metadata-synchronization events."""
        try:
            query = db.session.query(AIDataSourceCatalogEntry)
            if source_key is not None:
                query = query.filter_by(source_key=source_key)
            if database_id is not None:
                query = query.filter_by(database_id=database_id)
            entries = query.all()
            now = datetime.now(timezone.utc)
            for entry in entries:
                entry.invalidated_at = now
                entry.expires_at = now
            db.session.commit()
            return len(entries)
        except (OperationalError, AttributeError):
            rollback = getattr(db.session, "rollback", None)
            if rollback is not None:
                rollback()
            return 0

    def rebuild(self, candidates: Iterable[DiscoveryCandidate]) -> int:
        """Replace/refresh entries from an administrator-triggered live scan."""
        return self.upsert_many(candidates)

    @staticmethod
    def _is_fresh(entry: AIDataSourceCatalogEntry) -> bool:
        now = datetime.now(timezone.utc)
        expires_at = entry.expires_at
        indexed_at = entry.indexed_at
        if expires_at is None or indexed_at is None or entry.invalidated_at is not None:
            return False
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at > now

    @staticmethod
    def _payload(candidate: DiscoveryCandidate) -> dict[str, Any]:
        from superset.ai.discovery import (
            infer_metadata_topics,
            normalize_discovery_text,
        )

        searchable_values = (
            candidate.name,
            candidate.description,
            *candidate.related_names,
            *(name for name, _ in candidate.columns),
        )
        normalized_terms = sorted(
            {
                term
                for value in searchable_values
                for term in normalize_discovery_text(value).split()
                if term
            }
        )
        return {
            "resource_type": candidate.resource_type,
            "resource_id": candidate.resource_id,
            "database_id": candidate.database_id,
            "database_name": candidate.database_name,
            "schema": candidate.schema,
            "name": candidate.name,
            "description": candidate.description,
            "columns": [
                {"name": name, "type": column_type}
                for name, column_type in candidate.columns
            ],
            "related_names": list(candidate.related_names),
            "normalized_terms": normalized_terms,
            "detected_languages": sorted(
                {
                    language
                    for value in searchable_values
                    for language in _languages(value)
                }
            ),
            "inferred_topics": list(infer_metadata_topics(searchable_values)),
        }

    @staticmethod
    def _version(payload: dict[str, Any]) -> str:
        encoded = repr(sorted(payload.items())).encode()
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _to_candidate(entry: AIDataSourceCatalogEntry) -> DiscoveryCandidate:
        from superset.ai.discovery import DiscoveryCandidate

        return DiscoveryCandidate(
            resource_type=entry.resource_type,
            resource_id=entry.resource_id,
            name=entry.name,
            database_id=entry.database_id,
            database_name=entry.database_name,
            schema=entry.schema,
            columns=tuple(
                (str(column.get("name", "")), str(column.get("type", "UNKNOWN")))
                for column in (entry.columns or [])
                if isinstance(column, dict) and column.get("name")
            ),
            source_key=entry.source_key,
            description=entry.description or "",
            related_names=tuple(entry.related_names or []),
        )


def _languages(value: str) -> set[str]:
    """Best-effort language markers retained solely as ranking metadata."""
    normalized = value.casefold()
    language_tokens = {
        "pt-BR": ("venda", "receita", "cliente", "ano"),
        "en-US": ("sale", "revenue", "customer", "year"),
        "es-ES": ("venta", "ingreso", "cliente", "año"),
        "fr-FR": ("vente", "recette", "client", "année"),
    }
    return {
        language
        for language, tokens in language_tokens.items()
        if any(token in normalized for token in tokens)
    }
