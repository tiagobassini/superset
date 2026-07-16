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
"""Safe, multilingual helpers for analytics resource discovery."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

SemanticExpander = Callable[[str, str], Iterable[str]]

MAX_DISCOVERY_TERMS = 24
MAX_SEMANTIC_TERMS = 8
MAX_SEMANTIC_TERM_LENGTH = 80

# This small, versioned vocabulary is intentionally local and deterministic.
# Provider-suggested terms are optional additions and never replace lexical search.
MULTILINGUAL_TERM_GROUPS: tuple[frozenset[str], ...] = (
    frozenset(
        {"venda", "vendas", "sale", "sales", "venta", "ventas", "vente", "ventes"}
    ),
    frozenset({"receita", "revenue", "ingreso", "ingresos", "recette", "recettes"}),
    frozenset({"pedido", "pedidos", "order", "orders", "commande", "commandes"}),
    frozenset({"cliente", "clientes", "customer", "customers", "client", "clients"}),
    frozenset(
        {
            "produto",
            "produtos",
            "product",
            "products",
            "producto",
            "productos",
            "produit",
            "produits",
        }
    ),
)


@dataclass(frozen=True)
class DiscoveryQuery:
    """An in-memory, multilingual representation of an analytics topic.

    The original topic is retained for display only. Normalized and expanded
    terms are derived values used for safe resource matching; they are never
    persisted back to Superset metadata.
    """

    topic: str
    prompt_language: str
    normalized_topic: str
    lexical_terms: tuple[str, ...]
    synonyms: tuple[str, ...]
    expanded_terms: tuple[str, ...]


def build_discovery_query(
    topic: str,
    prompt_language: str | None = None,
    semantic_expander: SemanticExpander | None = None,
) -> DiscoveryQuery:
    """Build a bounded query with lexical and multilingual expansion.

    A semantic expander is optional because discovery must remain available
    when the provider is unavailable, slow, or returns unsuitable terms.
    """
    normalized_topic = normalize_discovery_text(topic)
    tokens = _tokenize(normalized_topic)
    lexical_terms = _unique_terms((normalized_topic, *tokens, *_singular_forms(tokens)))
    language = prompt_language or _detect_language(lexical_terms)
    synonyms = _dictionary_synonyms(lexical_terms)
    semantic_terms = _semantic_terms(
        semantic_expander if not synonyms else None,
        normalized_topic,
        language,
    )
    expanded_terms = _unique_terms(
        (*lexical_terms, *synonyms, *semantic_terms), limit=MAX_DISCOVERY_TERMS
    )
    return DiscoveryQuery(
        topic=topic,
        prompt_language=language,
        normalized_topic=normalized_topic,
        lexical_terms=lexical_terms,
        synonyms=synonyms,
        expanded_terms=expanded_terms,
    )


def normalize_discovery_text(value: str) -> str:
    """Normalize text for matching without changing the original resource name."""
    decomposed = unicodedata.normalize("NFD", value.casefold())
    without_accents = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    without_punctuation = re.sub(r"[^\w\s_-]", " ", without_accents)
    return " ".join(re.sub(r"[_-]+", " ", without_punctuation).split())


def rank_resources(
    resources: Iterable[dict[str, Any]], search: str | DiscoveryQuery
) -> list[dict[str, Any]]:
    """Return accessible resources ordered by deterministic name relevance."""
    terms = (
        search.expanded_terms
        if isinstance(search, DiscoveryQuery)
        else build_discovery_query(search).expanded_terms
    )
    return sorted(
        resources,
        key=lambda resource: (
            -_score(_resource_name(resource), terms),
            _resource_name(resource),
        ),
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
        elif normalized == "id" or normalized.endswith(" id"):
            groups["identifiers"].append(name)
        elif any(
            token in column_type
            for token in ("int", "numeric", "decimal", "float", "double")
        ):
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
    return _tokenize(normalize_discovery_text(value))


def _normalize(value: str) -> str:
    return normalize_discovery_text(value)


def _tokenize(value: str) -> tuple[str, ...]:
    return tuple(term for term in re.split(r"\W+", value) if len(term) > 1)


def _singular_forms(terms: Iterable[str]) -> tuple[str, ...]:
    """Add conservative singular variants without modifying stored metadata."""
    singulars: list[str] = []
    for term in terms:
        if len(term) > 3 and term.endswith("s"):
            singulars.append(term[:-1])
    return tuple(singulars)


def _unique_terms(
    values: Iterable[str], limit: int = MAX_DISCOVERY_TERMS
) -> tuple[str, ...]:
    """Return stable, normalized unique terms subject to a strict bound."""
    terms: list[str] = []
    for value in values:
        normalized = normalize_discovery_text(value)
        if normalized and normalized not in terms:
            terms.append(normalized)
        if len(terms) == limit:
            break
    return tuple(terms)


def _dictionary_synonyms(terms: Iterable[str]) -> tuple[str, ...]:
    expanded: list[str] = []
    term_set = set(terms)
    for group in MULTILINGUAL_TERM_GROUPS:
        if term_set.intersection(group):
            expanded.extend(sorted(group))
    return _unique_terms(expanded)


def _semantic_terms(
    semantic_expander: SemanticExpander | None,
    topic: str,
    language: str,
) -> tuple[str, ...]:
    """Use optional provider expansion while keeping lexical fallback reliable."""
    if semantic_expander is None or not topic:
        return ()
    try:
        candidates = semantic_expander(topic, language)
    except Exception:  # pylint: disable=broad-except
        return ()
    return _unique_terms(
        (
            candidate
            for candidate in candidates
            if isinstance(candidate, str) and len(candidate) <= MAX_SEMANTIC_TERM_LENGTH
        ),
        limit=MAX_SEMANTIC_TERMS,
    )


def _detect_language(terms: Iterable[str]) -> str:
    term_set = set(terms)
    language_markers = {
        "pt-BR": {
            "venda",
            "vendas",
            "receita",
            "pedido",
            "pedidos",
            "cliente",
            "clientes",
            "produto",
            "produtos",
        },
        "en-US": {
            "sale",
            "sales",
            "revenue",
            "order",
            "orders",
            "customer",
            "customers",
            "product",
            "products",
        },
        "es-ES": {
            "venta",
            "ventas",
            "ingreso",
            "ingresos",
            "pedido",
            "pedidos",
            "cliente",
            "clientes",
            "producto",
            "productos",
        },
        "fr-FR": {
            "vente",
            "ventes",
            "recette",
            "recettes",
            "commande",
            "commandes",
            "client",
            "clients",
            "produit",
            "produits",
        },
    }
    return max(
        language_markers,
        key=lambda language: len(term_set.intersection(language_markers[language])),
        default="pt-BR",
    )
