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
"""Remove AI prompt-suite artifacts from Superset metadata.

The example prompt suite creates resources with the ``AI_TEST_`` prefix. This
script removes those generated charts, virtual datasets, and saved queries while
leaving the source datasets and dashboards intact by default.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

DEFAULT_PREFIX = "AI_TEST_"


@dataclass
class CleanupSummary:
    """Resources selected during cleanup."""

    charts: list[str] = field(default_factory=list)
    datasets: list[str] = field(default_factory=list)
    saved_queries: list[str] = field(default_factory=list)
    dashboards: list[str] = field(default_factory=list)
    skipped_datasets: list[str] = field(default_factory=list)


def matches_prefix(value: str | None, prefix: str) -> bool:
    """Return whether a Superset object name matches the cleanup prefix."""

    return bool(value) and value.casefold().startswith(prefix.casefold())


def object_label(obj: Any, name: str | None) -> str:
    """Build a compact label for CLI output."""

    return f"{name or '<unnamed>'} (id={obj.id})"


def dataset_chart_refs(charts: list[Any], excluded_chart_ids: set[int]) -> dict[int, list[str]]:
    """Return remaining chart references for table-backed datasets."""

    refs: dict[int, list[str]] = defaultdict(list)
    for chart in charts:
        if chart.id in excluded_chart_ids or chart.datasource_type != "table":
            continue
        if chart.datasource_id is None:
            continue
        refs[int(chart.datasource_id)].append(object_label(chart, chart.slice_name))
    return refs


def collect_summary(
    *,
    prefix: str,
    include_dashboards: bool,
    force_datasets: bool,
) -> tuple[CleanupSummary, dict[str, list[Any]]]:
    """Find matching artifacts and return printable labels plus ORM objects."""

    from superset import db
    from superset.connectors.sqla.models import SqlaTable
    from superset.models.dashboard import Dashboard
    from superset.models.slice import Slice
    from superset.models.sql_lab import SavedQuery

    charts = [
        chart
        for chart in db.session.query(Slice).all()
        if matches_prefix(chart.slice_name, prefix)
    ]
    chart_ids = {chart.id for chart in charts}
    remaining_dataset_refs = dataset_chart_refs(db.session.query(Slice).all(), chart_ids)

    datasets = []
    skipped_datasets = []
    for dataset in db.session.query(SqlaTable).all():
        if not matches_prefix(dataset.table_name, prefix):
            continue
        refs = remaining_dataset_refs.get(dataset.id, [])
        if refs and not force_datasets:
            skipped_datasets.append((dataset, refs))
        else:
            datasets.append(dataset)

    saved_queries = [
        saved_query
        for saved_query in db.session.query(SavedQuery).all()
        if matches_prefix(saved_query.label, prefix)
    ]
    dashboards = []
    if include_dashboards:
        dashboards = [
            dashboard
            for dashboard in db.session.query(Dashboard).all()
            if matches_prefix(dashboard.dashboard_title, prefix)
            or matches_prefix(dashboard.slug, prefix)
        ]

    summary = CleanupSummary(
        charts=[object_label(chart, chart.slice_name) for chart in charts],
        datasets=[object_label(dataset, dataset.table_name) for dataset in datasets],
        saved_queries=[
            object_label(saved_query, saved_query.label)
            for saved_query in saved_queries
        ],
        dashboards=[
            object_label(dashboard, dashboard.dashboard_title)
            for dashboard in dashboards
        ],
        skipped_datasets=[
            f"{object_label(dataset, dataset.table_name)} still used by: "
            f"{', '.join(refs)}"
            for dataset, refs in skipped_datasets
        ],
    )
    return summary, {
        "charts": charts,
        "datasets": datasets,
        "saved_queries": saved_queries,
        "dashboards": dashboards,
    }


def print_section(title: str, rows: list[str]) -> None:
    """Print a cleanup section."""

    print(f"\n{title}: {len(rows)}")
    for row in rows:
        print(f"  - {row}")


def print_summary(summary: CleanupSummary) -> None:
    """Print all selected resources."""

    print_section("Charts", summary.charts)
    print_section("Datasets", summary.datasets)
    print_section("Saved queries", summary.saved_queries)
    print_section("Dashboards", summary.dashboards)
    print_section("Skipped datasets", summary.skipped_datasets)


def delete_artifacts(artifacts: dict[str, list[Any]]) -> None:
    """Delete selected resources from the active Superset session."""

    from superset import db

    for chart in artifacts["charts"]:
        for dashboard in list(chart.dashboards):
            dashboard.slices.remove(chart)
        db.session.delete(chart)

    db.session.flush()

    for dataset in artifacts["datasets"]:
        db.session.delete(dataset)

    for saved_query in artifacts["saved_queries"]:
        db.session.delete(saved_query)

    for dashboard in artifacts["dashboards"]:
        db.session.delete(dashboard)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""

    parser = argparse.ArgumentParser(
        description="Clean AI prompt-suite artifacts from Superset metadata.",
    )
    parser.add_argument(
        "--prefix",
        default=DEFAULT_PREFIX,
        help=f"Artifact name prefix to remove. Default: {DEFAULT_PREFIX}",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply the cleanup. Without this flag the script only prints a dry run.",
    )
    parser.add_argument(
        "--include-dashboards",
        action="store_true",
        help="Also remove dashboards whose title or slug starts with the prefix.",
    )
    parser.add_argument(
        "--force-datasets",
        action="store_true",
        help="Remove matching datasets even when non-matching charts still use them.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the cleanup command."""

    args = parse_args()

    from superset import db
    from superset.app import create_app

    app = create_app()
    with app.app_context():
        summary, artifacts = collect_summary(
            prefix=args.prefix,
            include_dashboards=args.include_dashboards,
            force_datasets=args.force_datasets,
        )
        print(
            "AI test artifact cleanup "
            f"({'execute' if args.execute else 'dry run'})"
        )
        print(f"Prefix: {args.prefix}")
        print_summary(summary)

        if not args.execute:
            db.session.rollback()
            print("\nNo changes applied. Re-run with --execute to delete these artifacts.")
            return 0

        delete_artifacts(artifacts)
        db.session.commit()
        print("\nCleanup applied.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
