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
"""Deterministic intent planning for autonomous analytics requests."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum


class AnalyticsGoal(StrEnum):
    """High-level outcomes recognized before provider tool selection."""

    ANALYZE = "analyze"
    CREATE_DATASET = "create_dataset"
    CREATE_CHART = "create_chart"
    CREATE_DASHBOARD = "create_dashboard"
    CREATE_QUERY = "create_query"
    PUBLISH_CHART = "create_chart_and_add_to_dashboard"


@dataclass(frozen=True)
class AnalyticsIntent:
    """Safe, provider-neutral interpretation of a user analytics request."""

    goal: AnalyticsGoal
    topic: str | None = None
    source_hint: str | None = None
    target_dashboard: str | None = None
    metric: str | None = None
    time_grain: str | None = None


@dataclass(frozen=True)
class AnalyticsPlan:
    """Intent, required tool names and any indispensable clarification."""

    intent: AnalyticsIntent
    tool_names: frozenset[str]
    clarification: str | None = None


class AnalyticsTaskPlanner:
    """Plan multi-domain analytics work without relying on model keywords alone."""

    _PUBLISH_VERBS = ("adicion", "inclu", "coloc", "publi", "insir")
    _CHART_WORDS = ("grafico", "chart", "visualizacao")
    _DASHBOARD_WORDS = ("dashboard", "painel")
    _DATASET_WORDS = ("dataset", "tabela")
    _QUERY_WORDS = ("sql", "query", "consulta")
    _CREATE_WORDS = ("cri", "gere", "mont", "faca", "faça")

    _DISCOVERY_TOOLS = frozenset(
        {
            "list_databases",
            "list_database_tables",
            "get_table_schema",
            "list_datasets",
            "get_dataset_schema",
        }
    )
    _CHART_TOOLS = frozenset(
        {"list_datasets", "get_dataset_schema", "list_charts", "create_chart"}
    )
    _DASHBOARD_TOOLS = frozenset(
        {"list_dashboards", "list_charts", "create_dashboard", "add_chart_to_dashboard"}
    )

    def plan(self, message: str) -> AnalyticsPlan:
        """Return the goal and tools needed to safely advance the request."""
        normalized = self._normalize(message)
        goal = self._goal(normalized)
        source_hint = self._named_after(normalized, r"(?:banco|base de dados|dataset)\s+")
        dashboard = self._named_after(normalized, r"(?:dashboard|painel)\s+")
        if goal is AnalyticsGoal.PUBLISH_CHART and dashboard is None:
            dashboard = self._named_after_publish_target(normalized)
        intent = AnalyticsIntent(
            goal=goal,
            topic=self._topic(normalized),
            source_hint=source_hint,
            target_dashboard=dashboard,
            metric="count" if "quantidade" in normalized or "numero" in normalized else None,
            time_grain="year" if "por ano" in normalized or "anual" in normalized else None,
        )
        clarification = None
        if goal is AnalyticsGoal.PUBLISH_CHART and not dashboard:
            clarification = "Em qual dashboard o gráfico deve ser publicado?"
        return AnalyticsPlan(intent, self._tools_for(goal), clarification)

    @classmethod
    def _goal(cls, message: str) -> AnalyticsGoal:
        publish = any(word in message for word in cls._PUBLISH_VERBS)
        chart = any(word in message for word in cls._CHART_WORDS)
        if publish and chart:
            return AnalyticsGoal.PUBLISH_CHART
        if any(word in message for word in cls._DASHBOARD_WORDS) and any(
            word in message for word in cls._CREATE_WORDS
        ):
            return AnalyticsGoal.CREATE_DASHBOARD
        if chart:
            return AnalyticsGoal.CREATE_CHART
        if any(word in message for word in cls._DATASET_WORDS) and any(
            word in message for word in cls._CREATE_WORDS
        ):
            return AnalyticsGoal.CREATE_DATASET
        if any(word in message for word in cls._QUERY_WORDS):
            return AnalyticsGoal.CREATE_QUERY
        return AnalyticsGoal.ANALYZE

    @classmethod
    def _tools_for(cls, goal: AnalyticsGoal) -> frozenset[str]:
        if goal is AnalyticsGoal.PUBLISH_CHART:
            return (
                cls._DISCOVERY_TOOLS
                | cls._CHART_TOOLS
                | cls._DASHBOARD_TOOLS
                | frozenset({"create_dataset"})
            )
        if goal is AnalyticsGoal.CREATE_CHART:
            return cls._DISCOVERY_TOOLS | cls._CHART_TOOLS
        if goal is AnalyticsGoal.CREATE_DASHBOARD:
            return cls._DISCOVERY_TOOLS | cls._CHART_TOOLS | cls._DASHBOARD_TOOLS
        if goal is AnalyticsGoal.CREATE_DATASET:
            return cls._DISCOVERY_TOOLS | frozenset({"create_dataset"})
        if goal is AnalyticsGoal.CREATE_QUERY:
            return cls._DISCOVERY_TOOLS | frozenset(
                {
                    "run_sql_query",
                    "save_sql_query",
                    "list_saved_queries",
                    "get_saved_query",
                }
            )
        return cls._DISCOVERY_TOOLS | frozenset({"list_charts", "list_dashboards"})

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(
            "".join(
                char
                for char in unicodedata.normalize("NFD", value.casefold())
                if unicodedata.category(char) != "Mn"
            ).split()
        )

    @staticmethod
    def _named_after(message: str, prefix: str) -> str | None:
        match = re.search(prefix + r"[`\"']?([\w-]+)[`\"']?", message)
        return match.group(1) if match else None

    @staticmethod
    def _named_after_publish_target(message: str) -> str | None:
        match = re.search(r"(?:em|no|na|ao)\s+(?:dashboard\s+)?[`\"']?([\w-]+)[`\"']?", message)
        return match.group(1) if match else None

    @staticmethod
    def _topic(message: str) -> str | None:
        match = re.search(
            r"(?:analise|analisar)\s+(?:(?:a|o)\s+)?(?:base\s+de\s+dados\s+|banco\s+)?([\w-]+)",
            message,
        )
        return match.group(1) if match else None
