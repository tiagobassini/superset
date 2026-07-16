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
"""Unit tests for the concrete built-in AI tool handlers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from superset.ai.tools import builtin


class Command:
    """Record command payloads while returning a predictable model object."""

    payload: object | None = None
    result: SimpleNamespace

    def __init__(self, *args: object) -> None:
        type(self).payload = args

    def run(self) -> SimpleNamespace:
        return type(self).result


@pytest.mark.parametrize(
    ("handler", "command_path", "params", "result", "expected"),
    [
        (
            builtin._create_chart,
            "superset.commands.chart.create.CreateChartCommand",
            {"slice_name": "Sales"},
            SimpleNamespace(id=11, slice_name="Sales", url="/explore/?slice_id=11"),
            {"id": 11, "name": "Sales", "url": "/explore/?slice_id=11"},
        ),
        (
            builtin._edit_chart,
            "superset.commands.chart.update.UpdateChartCommand",
            {"chart_id": 11, "data": {"slice_name": "Revenue"}},
            SimpleNamespace(id=11, slice_name="Revenue", url="/explore/?slice_id=11"),
            {"id": 11, "name": "Revenue", "url": "/explore/?slice_id=11"},
        ),
        (
            builtin._create_dashboard,
            "superset.commands.dashboard.create.CreateDashboardCommand",
            {"dashboard_title": "Executive"},
            SimpleNamespace(id=12, dashboard_title="Executive", url="/superset/dashboard/12/"),
            {"id": 12, "title": "Executive", "url": "/superset/dashboard/12/"},
        ),
        (
            builtin._edit_dashboard,
            "superset.commands.dashboard.update.UpdateDashboardCommand",
            {"dashboard_id": 12, "data": {"dashboard_title": "Board"}},
            SimpleNamespace(id=12, dashboard_title="Board", url="/superset/dashboard/12/"),
            {"id": 12, "title": "Board", "url": "/superset/dashboard/12/"},
        ),
    ],
)
def test_write_command_handlers_return_safe_resource_summary(
    monkeypatch: pytest.MonkeyPatch,
    handler: object,
    command_path: str,
    params: dict[str, object],
    result: SimpleNamespace,
    expected: dict[str, object],
) -> None:
    Command.result = result
    monkeypatch.setattr(command_path, Command)
    if handler is builtin._create_chart:
        monkeypatch.setattr(builtin, "_validate_created_chart", lambda _: None)

    assert handler(params) == expected  # type: ignore[operator]


def test_create_chart_removes_chart_when_query_validation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Command.result = SimpleNamespace(
        id=11,
        slice_name="Sales",
        url="/explore/?slice_id=11",
    )
    monkeypatch.setattr(
        "superset.commands.chart.create.CreateChartCommand",
        Command,
    )
    monkeypatch.setattr(
        builtin,
        "_validate_created_chart",
        lambda _: (_ for _ in ()).throw(ValueError("invalid metric")),
    )
    deleted: list[SimpleNamespace] = []
    monkeypatch.setattr(
        "superset.extensions.db.session",
        SimpleNamespace(delete=deleted.append, commit=lambda: None),
    )

    with pytest.raises(ValueError, match="could not be queried and was removed"):
        builtin._create_chart({"slice_name": "Sales"})

    assert deleted == [Command.result]


def test_create_chart_reuses_compatible_existing_chart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chart = SimpleNamespace(
        id=11,
        slice_name="AI_TEST_P11",
        datasource_id=7,
        datasource_type="table",
        url="/explore/?slice_id=11",
    )

    class Query:
        @staticmethod
        def all() -> list[SimpleNamespace]:
            return [chart]

    monkeypatch.setattr(
        "superset.extensions.db.session",
        SimpleNamespace(query=lambda _: Query()),
    )
    monkeypatch.setattr(
        "superset.extensions.security_manager.can_access_chart", lambda _: True
    )

    assert builtin._create_chart(
        {
            "slice_name": "AI_TEST_P11",
            "datasource_id": 7,
            "datasource_type": "table",
        }
    ) == {
        "id": 11,
        "name": "AI_TEST_P11",
        "url": "/explore/?slice_id=11",
        "reused": True,
    }


def test_create_dataset_validates_physical_table_before_creating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Command.result = SimpleNamespace(id=7, table_name="orders", url="/tablemodelview/edit/7")
    monkeypatch.setattr(
        "superset.commands.dataset.create.CreateDatasetCommand", Command
    )
    validated: list[dict[str, object]] = []
    monkeypatch.setattr(
        builtin,
        "_get_table_schema",
        lambda params: validated.append(params) or {"columns": []},
    )

    assert builtin._create_dataset(
        {"database": 1, "table_name": "orders", "schema": "public"}
    ) == {"id": 7, "name": "orders", "url": "/tablemodelview/edit/7"}
    assert validated == [
        {"database_id": 1, "table_name": "orders", "schema": "public", "catalog": None}
    ]


def test_create_dataset_uses_owned_saved_query_for_virtual_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Command.result = SimpleNamespace(
        id=8, table_name="monthly_sales", url="/tablemodelview/edit/8"
    )
    monkeypatch.setattr(
        "superset.commands.dataset.create.CreateDatasetCommand", Command
    )
    monkeypatch.setattr(
        builtin,
        "_get_saved_query",
        lambda _: {
            "database_id": 3,
            "schema": "analytics",
            "catalog": None,
            "sql": "select * from sales",
        },
    )

    assert builtin._create_dataset(
        {"saved_query_id": 4, "table_name": "monthly_sales"}
    ) == {"id": 8, "name": "monthly_sales", "url": "/tablemodelview/edit/8"}
    assert Command.payload == (
        {
            "table_name": "monthly_sales",
            "database": 3,
            "schema": "analytics",
            "catalog": None,
            "sql": "select * from sales",
        },
    )


def test_create_dataset_reuses_existing_compatible_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset = SimpleNamespace(
        id=8,
        table_name="AI_TEST_P20",
        database_id=3,
        schema="analytics",
        sql="select * from sales",
        url="/tablemodelview/edit/8",
    )

    class Query:
        @staticmethod
        def all() -> list[SimpleNamespace]:
            return [dataset]

    monkeypatch.setattr(
        "superset.extensions.db.session",
        SimpleNamespace(query=lambda _: Query()),
    )
    monkeypatch.setattr(
        "superset.extensions.security_manager.can_access_datasource", lambda _: True
    )
    monkeypatch.setattr(
        builtin,
        "_get_saved_query",
        lambda _: {
            "database_id": 3,
            "schema": "analytics",
            "catalog": None,
            "sql": "select * from sales",
        },
    )

    assert builtin._create_dataset(
        {"saved_query_id": 4, "table_name": "AI_TEST_P20"}
    ) == {
        "id": 8,
        "name": "AI_TEST_P20",
        "url": "/tablemodelview/edit/8",
        "reused": True,
    }


def test_create_dataset_rejects_database_different_from_saved_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        builtin,
        "_get_saved_query",
        lambda _: {"database_id": 3, "schema": None, "catalog": None, "sql": "x"},
    )

    with pytest.raises(ValueError, match="different database"):
        builtin._create_dataset(
            {"database": 2, "saved_query_id": 4, "table_name": "monthly_sales"}
        )


def test_list_database_tables_filters_the_command_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = SimpleNamespace(id=1, get_default_schema=lambda _: "public")
    session = SimpleNamespace(get=lambda *_: database)
    monkeypatch.setattr("superset.extensions.db.session", session)

    class TablesCommand:
        def __init__(self, *_: object) -> None:
            pass

        @staticmethod
        def run() -> dict[str, list[dict[str, str]]]:
            return {"result": [{"value": "orders"}, {"value": "customers"}]}

    monkeypatch.setattr(
        "superset.commands.database.tables.TablesDatabaseCommand", TablesCommand
    )

    assert builtin._list_database_tables(
        {"database_id": 1, "search": "ord"}
    ) == [{"value": "orders"}]


def test_list_database_tables_requires_database_and_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "superset.extensions.db.session", SimpleNamespace(get=lambda *_: None)
    )
    with pytest.raises(ValueError, match="Database not found"):
        builtin._list_database_tables({"database_id": 1})

    database = SimpleNamespace(id=1, get_default_schema=lambda _: None)
    monkeypatch.setattr(
        "superset.extensions.db.session", SimpleNamespace(get=lambda *_: database)
    )
    with pytest.raises(ValueError, match="schema is required"):
        builtin._list_database_tables({"database_id": 1})


def test_add_chart_to_dashboard_avoids_duplicate_relationship(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chart = SimpleNamespace(id=22)
    dashboard = SimpleNamespace(id=13, slices=[chart])
    session = SimpleNamespace(
        get=lambda model, identifier: dashboard if identifier == 13 else chart,
        commit=lambda: pytest.fail("A duplicate chart relationship must not commit"),
    )
    monkeypatch.setattr("superset.extensions.db.session", session)
    monkeypatch.setattr("superset.extensions.security_manager.is_owner", lambda _: True)
    monkeypatch.setattr(
        "superset.extensions.security_manager.can_access_chart", lambda _: True
    )

    assert builtin._add_chart_to_dashboard({"dashboard_id": 13, "chart_id": 22}) == {
        "dashboard_id": 13,
        "chart_id": 22,
    }


def test_create_dashboard_rejects_ambiguous_existing_dashboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dashboards = [
        SimpleNamespace(id=1, dashboard_title="CBMES", slug="cbmes"),
        SimpleNamespace(id=2, dashboard_title="cbmes", slug="cbmes-copy"),
    ]

    class Query:
        @staticmethod
        def all() -> list[SimpleNamespace]:
            return dashboards

    monkeypatch.setattr(
        "superset.extensions.db.session",
        SimpleNamespace(query=lambda _: Query()),
    )
    monkeypatch.setattr(
        "superset.extensions.security_manager.can_access_dashboard", lambda _: True
    )

    with pytest.raises(ValueError, match="Multiple dashboards"):
        builtin._create_dashboard({"dashboard_title": "CBMES"})


def test_list_handlers_return_only_accessible_matching_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The catalog tools must apply both the search and Superset ACL filters."""
    database = SimpleNamespace(id=1, database_name="Examples", backend="sqlite")
    dataset = SimpleNamespace(
        id=2,
        table_name="sales_data",
        database=database,
    )
    chart = SimpleNamespace(id=3, slice_name="Sales by month", viz_type="line")
    dashboard = SimpleNamespace(id=4, dashboard_title="Sales overview", slug="sales")

    class Query:
        def __init__(self, values: list[object]) -> None:
            self.values = values

        def order_by(self, *_: object) -> "Query":
            return self

        def all(self) -> list[object]:
            return self.values

    monkeypatch.setattr(
        "superset.extensions.db.session",
        SimpleNamespace(
            query=lambda model: Query(
                [database]
                if model.__name__ == "Database"
                else [dataset]
                if model.__name__ == "SqlaTable"
                else [chart]
                if model.__name__ == "Slice"
                else [dashboard]
            )
        ),
    )
    monkeypatch.setattr(
        "superset.extensions.security_manager.can_access_database", lambda _: True
    )
    monkeypatch.setattr(
        "superset.extensions.security_manager.can_access_datasource", lambda _: True
    )
    monkeypatch.setattr(
        "superset.extensions.security_manager.can_access_chart", lambda _: True
    )
    monkeypatch.setattr(
        "superset.extensions.security_manager.can_access_dashboard", lambda _: True
    )

    assert builtin._list_databases({}) == [
        {"id": 1, "name": "Examples", "backend": "sqlite"}
    ]
    assert builtin._list_datasets({"search": "sales"}) == [
        {"id": 2, "name": "sales_data", "database": "Examples"}
    ]
    assert builtin._list_charts({"search": "sales"}) == [
        {"id": 3, "name": "Sales by month", "viz_type": "line"}
    ]
    assert builtin._list_dashboards({"search": "sales"}) == [
        {"id": 4, "title": "Sales overview", "slug": "sales"}
    ]


def test_get_dataset_schema_checks_access_before_returning_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset = SimpleNamespace(
        id=2,
        table_name="sales",
        columns=[
            SimpleNamespace(column_name="amount", type="NUMERIC", is_nullable=False)
        ],
    )
    monkeypatch.setattr(
        "superset.extensions.db.session", SimpleNamespace(get=lambda *_: dataset)
    )
    monkeypatch.setattr(
        "superset.extensions.security_manager.can_access_datasource", lambda _: True
    )

    assert builtin._get_dataset_schema({"dataset_id": 2}) == {
        "id": 2,
        "name": "sales",
        "columns": [{"name": "amount", "type": "NUMERIC", "nullable": False}],
    }

    monkeypatch.setattr(
        "superset.extensions.security_manager.can_access_datasource", lambda _: False
    )
    with pytest.raises(ValueError, match="access denied"):
        builtin._get_dataset_schema({"dataset_id": 2})


def test_profile_dataset_returns_only_aggregate_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = SimpleNamespace(id=3, quote_identifier=lambda value: f'"{value}"')
    dataset = SimpleNamespace(
        id=2,
        table_name="sales",
        schema="public",
        catalog=None,
        sql=None,
        database=database,
        columns=[
            SimpleNamespace(column_name="order_date", type="DATE"),
            SimpleNamespace(column_name="amount", type="NUMERIC"),
        ],
    )
    monkeypatch.setattr(
        "superset.extensions.db.session", SimpleNamespace(get=lambda *_: dataset)
    )
    monkeypatch.setattr(
        "superset.extensions.security_manager.can_access_datasource", lambda _: True
    )
    monkeypatch.setattr(builtin, "_run_sql_query", lambda _: {"data": [[42]]})

    result = builtin._profile_dataset({"dataset_id": 2})

    assert result["dataset_id"] == 2
    assert result["row_count"] == {"data": [[42]]}
    assert result["columns"]["temporal"] == ["order_date"]
    assert result["columns"]["measures"] == ["amount"]
