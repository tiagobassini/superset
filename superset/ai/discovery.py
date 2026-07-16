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
"""Safe ranking helpers for analytics resource discovery."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any


def rank_resources(resources: Iterable[dict[str, Any]], search: str) -> list[dict[str, Any]]:
    """Return accessible resources ordered by deterministic name relevance."""
    terms = _terms(search)
    return sorted(
        resources,
        key=lambda resource: (-_score(_resource_name(resource), terms), _resource_name(resource)),
    )


def classify_columns(columns: Iterable[dict[str, Any]]) -> dict[str, list[str]]:
    """Identify useful temporal, measure, identifier and dimension columns."""
    groups = {"temporal": [], "measures": [], "identifiers": [], "dimensions": []}
    for column in columns:
        name = str(column.get("name") or column.get("column_name") or "")
        column_type = str(column.get("type") or "").casefold()
        normalized = _normalize(name)
        if any(token in column_type for token in ("date", "time")) or any(
            token in normalized for token in ("date", "data", "year", "ano")
        ):
            groups["temporal"].append(name)
        elif normalized == "id" or normalized.endswith("_id"):
            groups["identifiers"].append(name)
        elif any(token in column_type for token in ("int", "numeric", "decimal", "float", "double")):
            groups["measures"].append(name)
        else:
            groups["dimensions"].append(name)
    return groups


def _resource_name(resource: dict[str, Any]) -> str:
    return _normalize(str(resource.get("name") or resource.get("title") or ""))


def _score(name: str, terms: tuple[str, ...]) -> int:
    if not terms:
        return 0
    return sum(4 if term == name else 2 if term in name else 0 for term in terms)


def _terms(value: str) -> tuple[str, ...]:
    return tuple(term for term in re.split(r"\W+", _normalize(value)) if len(term) > 1)


def _normalize(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value.casefold())
        if unicodedata.category(char) != "Mn"
    )
