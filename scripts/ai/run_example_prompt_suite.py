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
"""Run the documented Examples database prompts with structured oracles.

The Markdown table in ``docs/ai-integration/example-database-ai-prompts.md`` is
the single source of truth for prompt text and expectations. This runner turns
each row into a repeatable regression case, executes it through the real AI task
flow, confirms complete execution plans when the table says so, and emits one
JSONL record per prompt plus a compact summary.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CASE_PATTERN = re.compile(
    r"^\| (?P<id>P\d{2}) \| `(?P<prompt>.+)` \| (?P<expected>.+) \| "
    r"(?P<confirm>sim|não) \|$"
)
AI_RESOURCE_PATTERN = re.compile(r"\bAI_TEST_[A-Z0-9_]+\b", re.IGNORECASE)
KNOWN_SOURCES = (
    "international_sales",
    "cleaned_sales_data",
    "video_game_sales",
    "flights",
    "birth_names",
    "wb_health_population",
    "messages",
    "users",
    "data_hora_atual",
)
KNOWN_COLUMNS = (
    "transaction_date",
    "order_date",
    "year",
    "month",
    "region",
    "country",
    "territory",
    "product_category",
    "product_line",
    "quantity",
    "quantity_ordered",
    "revenue",
    "sales",
    "cost",
    "profit",
    "global_sales",
    "na_sales",
    "eu_sales",
    "genre",
    "platform",
    "publisher",
    "YEAR",
    "MONTH",
    "AIRLINE",
    "ARRIVAL_DELAY",
    "DEPARTURE_DELAY",
    "CANCELLED",
    "DISTANCE",
    "ORIGIN_AIRPORT",
    "ds",
    "gender",
    "name",
    "num",
    "state",
    "country_name",
    "SP_POP_TOTL",
    "SP_DYN_LE00_IN",
    "SH_DYN_MORT",
)
ORACLE_COLUMN_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (r"\b(receita|faturamento)\b", ("revenue",)),
    (r"\b(lucro|profit)\b", ("profit",)),
    (r"\b(custo|cost)\b", ("cost",)),
    (r"\bquantidade_ordered\b", ("quantity_ordered",)),
    (r"\bquantidade\b", ("quantity",)),
    (r"\bvendas globais\b|\bglobal_sales\b", ("global_sales",)),
    (r"\beuropa\b|\beu_sales\b", ("eu_sales",)),
    (r"\bamerica do norte\b|\bnorth america\b|\bna_sales\b", ("na_sales",)),
    (r"\batraso.*chegada\b|\barrival_delay\b", ("ARRIVAL_DELAY",)),
    (r"\batraso.*partida\b|\bdeparture_delay\b", ("DEPARTURE_DELAY",)),
    (r"\bcancelamentos?\b|\bcancelled\b", ("CANCELLED",)),
    (r"\bdist[aâ]ncia\b|\bdistance\b", ("DISTANCE",)),
    (r"\bnascimentos?\b|\bbirths?\b", ("num",)),
    (r"\bpopula[cç][aã]o total\b|\bsp_pop_totl\b", ("SP_POP_TOTL",)),
    (r"\bexpectativa de vida\b|\blife expectancy\b", ("SP_DYN_LE00_IN",)),
    (r"\bmortalidade\b|\bmortality\b", ("SH_DYN_MORT",)),
)
TERMINAL_STATES = {
    "awaiting_confirmation",
    "awaiting_user_input",
    "completed",
    "failed",
}


@dataclass(frozen=True)
class PromptOracle:
    """Facts that must be true for a prompt result."""

    expected_sources: tuple[str, ...] = ()
    expected_columns: tuple[str, ...] = ()
    expected_resources: tuple[str, ...] = ()
    expected_dashboard: str | None = None
    requires_confirmation: bool = False
    expects_plan: bool = False
    expects_creation: bool = False
    expects_rejection: bool = False
    max_alternatives: int | None = None


@dataclass(frozen=True)
class PromptCase:
    """A documented prompt and its derived oracle."""

    id: str
    prompt: str
    expected: str
    confirm: bool
    oracle: PromptOracle


@dataclass
class PromptMetrics:
    """Per-prompt timing and observability values."""

    latency_ms: int = 0
    planning_latency_ms: int = 0
    execution_latency_ms: int = 0
    events: int = 0
    tool_steps: int = 0
    terminal_state: str | None = None
    error: str | None = None


@dataclass
class PromptResult:
    """Structured output for a single executed prompt."""

    id: str
    prompt: str
    status: str | None
    passed: bool
    failures: list[str]
    metrics: PromptMetrics
    confirmation: str
    response: str | None = None
    pending_actions: list[dict[str, Any]] = field(default_factory=list)
    resources: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


def load_cases(path: Path) -> list[PromptCase]:
    """Read the stable prompt table without duplicating prompt fixtures."""
    cases: list[PromptCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if match := CASE_PATTERN.match(line):
            data = match.groupdict()
            confirm = data["confirm"] == "sim"
            cases.append(
                PromptCase(
                    id=data["id"],
                    prompt=data["prompt"],
                    expected=data["expected"],
                    confirm=confirm,
                    oracle=build_oracle(
                        data["id"], data["prompt"], data["expected"], confirm
                    ),
                )
            )
    if len(cases) != 50:
        raise ValueError(f"Expected exactly 50 prompts, found {len(cases)}")
    return cases


def build_oracle(
    case_id: str, prompt: str, expected: str, confirm: bool
) -> PromptOracle:
    """Infer a factual oracle from the documented prompt expectation."""
    text = f"{prompt}\n{expected}"
    expected_resources = tuple(_unique(AI_RESOURCE_PATTERN.findall(text)))
    expected_sources = tuple(
        source for source in KNOWN_SOURCES if re.search(rf"\b{source}\b", text, re.I)
    )
    expected_columns = tuple(
        _unique(
            [
                column
                for column in KNOWN_COLUMNS
                if re.search(rf"\b{column}\b", text, re.I)
            ]
            + [
                column
                for pattern, columns in ORACLE_COLUMN_ALIASES
                if re.search(pattern, text, re.I)
                for column in columns
            ]
        )
    )
    expects_rejection = case_id == "P48" or "não cria" in expected.casefold()
    max_alternatives = 3 if "alternativas" in expected.casefold() else None
    return PromptOracle(
        expected_sources=expected_sources,
        expected_columns=expected_columns,
        expected_resources=expected_resources,
        expected_dashboard="CBMES" if re.search(r"\bCBMES\b", text, re.I) else None,
        requires_confirmation=confirm,
        expects_plan=confirm,
        expects_creation=confirm and not expects_rejection,
        expects_rejection=expects_rejection,
        max_alternatives=max_alternatives,
    )


def evaluate_result(
    case: PromptCase,
    snapshot: dict[str, Any],
    resources: dict[str, list[dict[str, Any]]],
    confirmation: str,
) -> tuple[bool, list[str]]:
    """Validate structured facts without depending on model wording."""
    failures: list[str] = []
    status = snapshot.get("status")
    text = _searchable_text(snapshot, resources)
    if status not in TERMINAL_STATES:
        failures.append(f"non-terminal status {status!r}")
    if case.oracle.requires_confirmation and confirmation != "executed":
        failures.append("expected one confirmed execution plan")
    if not case.oracle.requires_confirmation and confirmation == "executed":
        failures.append("unexpected write confirmation")
    if case.oracle.expects_rejection and status == "completed" and resources:
        failures.append("expected rejection but resources were created or reused")
    if case.oracle.expects_plan and "execution_plan" not in text:
        failures.append("missing execution plan evidence")
    if case.oracle.expected_sources and not any(
        source.casefold() in text for source in case.oracle.expected_sources
    ):
        failures.append(
            "missing expected source option "
            f"{', '.join(case.oracle.expected_sources)}"
        )
    if case.oracle.expected_columns:
        column_matches = [
            column
            for column in case.oracle.expected_columns
            if column.casefold() in text
        ]
        if "e/ou" in case.expected.casefold() or "and/or" in case.expected.casefold():
            if not column_matches:
                failures.append(
                    "missing expected column option "
                    f"{', '.join(case.oracle.expected_columns)}"
                )
        else:
            for column in case.oracle.expected_columns:
                if column.casefold() not in text:
                    failures.append(f"missing expected column {column}")
    for resource in case.oracle.expected_resources:
        if resource.casefold() not in text:
            failures.append(f"missing expected resource {resource}")
    if case.oracle.expected_dashboard and case.oracle.expected_dashboard.casefold() not in text:
        failures.append(f"missing dashboard {case.oracle.expected_dashboard}")
    if case.oracle.max_alternatives is not None:
        alternatives = _count_numbered_alternatives(snapshot.get("response") or "")
        if alternatives > case.oracle.max_alternatives:
            failures.append(
                f"too many alternatives: {alternatives} > {case.oracle.max_alternatives}"
            )
    return not failures, failures


def collect_resources(case: PromptCase) -> dict[str, list[dict[str, Any]]]:
    """Inspect Superset metadata for resources named by the prompt contract."""
    names = {name.casefold() for name in case.oracle.expected_resources}
    if not names:
        return {}
    from superset.connectors.sqla.models import SqlaTable
    from superset.extensions import db, security_manager
    from superset.models.dashboard import Dashboard
    from superset.models.slice import Slice
    from superset.models.sql_lab import SavedQuery

    resources: dict[str, list[dict[str, Any]]] = {
        "charts": [],
        "dashboards": [],
        "datasets": [],
        "saved_queries": [],
    }
    charts = [
        chart
        for chart in db.session.query(Slice).all()
        if chart.slice_name.casefold() in names
        and security_manager.can_access_chart(chart)
    ]
    for chart in charts:
        resources["charts"].append(
            {"id": chart.id, "name": chart.slice_name, "url": chart.url}
        )
        try:
            from superset.ai.tools.builtin import _validate_created_chart

            _validate_created_chart(chart)
        except Exception as ex:  # pylint: disable=broad-except
            resources["charts"][-1]["render_error"] = str(ex)
    for dashboard in db.session.query(Dashboard).all():
        if (
            dashboard.dashboard_title.casefold() in names
            or str(dashboard.slug or "").casefold() in names
        ):
            resources["dashboards"].append(
                {
                    "id": dashboard.id,
                    "title": dashboard.dashboard_title,
                    "slug": dashboard.slug,
                }
            )
    for dataset in db.session.query(SqlaTable).all():
        if dataset.table_name.casefold() in names and security_manager.can_access_datasource(
            dataset
        ):
            resources["datasets"].append(
                {"id": dataset.id, "name": dataset.table_name, "url": dataset.url}
            )
    for saved_query in db.session.query(SavedQuery).all():
        if saved_query.label.casefold() in names:
            resources["saved_queries"].append(
                {"id": saved_query.id, "label": saved_query.label}
            )
    return {key: value for key, value in resources.items() if value}


def execute_case(case: PromptCase, user_id: int, agent_id: str) -> PromptResult:
    """Run one prompt through the real task and optional plan confirmation."""
    from superset.ai.task_progress import AITaskProgress
    from superset.ai.tasks import run_ai_plan_task, run_ai_task
    from superset.extensions import cache_manager

    metrics = PromptMetrics()
    started = time.monotonic()
    confirmation = "not_requested"
    progress = AITaskProgress(cache_manager.cache, user_id, agent_id)
    task_id = progress.create()
    try:
        planning_started = time.monotonic()
        run_ai_task.apply(
            args=(
                task_id,
                agent_id,
                user_id,
                {
                    "message": case.prompt,
                    "history": [],
                    "context": {"page": "other"},
                },
            )
        ).get()
        metrics.planning_latency_ms = int((time.monotonic() - planning_started) * 1000)
        snapshot = progress.snapshot(task_id)
        if case.confirm:
            plan = _execution_plan_action(snapshot)
            if plan is None:
                confirmation = "missing_plan"
            else:
                confirmation = "executed"
                execution_started = time.monotonic()
                run_ai_plan_task.apply(
                    args=(task_id, plan["id"], agent_id, user_id)
                ).get()
                metrics.execution_latency_ms = int(
                    (time.monotonic() - execution_started) * 1000
                )
                snapshot = progress.snapshot(task_id)
        from flask import current_app
        from superset.extensions import security_manager
        from superset.utils.core import override_user

        user = security_manager.get_user_by_id(user_id)
        with current_app.test_request_context():
            with override_user(user):
                resources = collect_resources(case)
        metrics.latency_ms = int((time.monotonic() - started) * 1000)
        metrics.events = len(snapshot.get("events") or [])
        metrics.tool_steps = sum(
            1
            for event in snapshot.get("events") or []
            if event.get("state") == "executing" and event.get("data")
        )
        metrics.terminal_state = snapshot.get("status")
        passed, failures = evaluate_result(case, snapshot, resources, confirmation)
        return PromptResult(
            id=case.id,
            prompt=case.prompt,
            status=snapshot.get("status"),
            passed=passed,
            failures=failures,
            metrics=metrics,
            confirmation=confirmation,
            response=snapshot.get("response"),
            pending_actions=snapshot.get("pending_actions") or [],
            resources=resources,
        )
    except Exception as ex:  # pylint: disable=broad-except
        metrics.latency_ms = int((time.monotonic() - started) * 1000)
        metrics.error = str(ex)
        return PromptResult(
            id=case.id,
            prompt=case.prompt,
            status="failed",
            passed=False,
            failures=[str(ex)],
            metrics=metrics,
            confirmation=confirmation,
        )


def main() -> int:
    """Execute selected prompts and write JSONL records plus a summary."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--file",
        type=Path,
        default=Path("docs/ai-integration/example-database-ai-prompts.md"),
    )
    parser.add_argument("--only", nargs="*", help="Optional case IDs, e.g. P01 P50")
    parser.add_argument("--output", type=Path, help="Optional JSONL output path")
    parser.add_argument("--fail-fast", action="store_true")
    args = parser.parse_args()

    from superset.app import create_app

    app = create_app()
    with app.app_context():
        from superset.ai.models import AIAgent
        from superset.extensions import db, security_manager

        user = security_manager.find_user(username="admin")
        agent = (
            db.session.query(AIAgent)
            .filter_by(is_active=True, is_default=True)
            .first()
        )
        if user is None or agent is None:
            raise RuntimeError("An active default AI agent and admin user are required")
        user_id = user.id
        agent_id = str(agent.id)
        selected = set(args.only or [])
        cases = [
            case
            for case in load_cases(args.file)
            if not selected or case.id in selected
        ]
        if selected and len(cases) != len(selected):
            raise ValueError("One or more requested case IDs were not found")
        results: list[PromptResult] = []
        output = args.output.open("w", encoding="utf-8") if args.output else None
        try:
            for case in cases:
                result = execute_case(case, user_id, agent_id)
                results.append(result)
                line = json.dumps(_result_payload(result), default=str)
                print(line, flush=True)
                if output:
                    output.write(line + "\n")
                    output.flush()
                if args.fail_fast and not result.passed:
                    break
        finally:
            if output:
                output.close()
        summary = _summary(results)
        print(json.dumps(summary, default=str), file=sys.stderr)
        return 0 if summary["failed"] == 0 and summary["total"] == len(cases) else 1


def _execution_plan_action(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    return next(
        (
            action
            for action in snapshot.get("pending_actions") or []
            if action.get("type") == "execution_plan"
        ),
        None,
    )


def _result_payload(result: PromptResult) -> dict[str, Any]:
    return {
        "id": result.id,
        "prompt": result.prompt,
        "status": result.status,
        "passed": result.passed,
        "failures": result.failures,
        "metrics": asdict(result.metrics),
        "confirmation": result.confirmation,
        "response": result.response,
        "pending_actions": result.pending_actions,
        "resources": result.resources,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


def _summary(results: list[PromptResult]) -> dict[str, Any]:
    passed = sum(result.passed for result in results)
    latencies = [result.metrics.latency_ms for result in results]
    return {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "latency_ms": {
            "min": min(latencies, default=0),
            "max": max(latencies, default=0),
            "avg": int(sum(latencies) / len(latencies)) if latencies else 0,
        },
        "failed_ids": [result.id for result in results if not result.passed],
    }


def _searchable_text(
    snapshot: dict[str, Any], resources: dict[str, list[dict[str, Any]]]
) -> str:
    return json.dumps(
        {
            "response": snapshot.get("response"),
            "pending_actions": snapshot.get("pending_actions"),
            "execution_plan": snapshot.get("execution_plan"),
            "events": snapshot.get("events"),
            "resources": resources,
        },
        default=str,
    ).casefold()


def _count_numbered_alternatives(response: str) -> int:
    return len(re.findall(r"(?m)^\s*\d+\.\s+", response))


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.casefold()
        if normalized not in seen:
            seen.add(normalized)
            result.append(value)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
