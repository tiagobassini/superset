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
"""Built-in AI tools backed by Superset commands and security checks."""

from __future__ import annotations

from typing import Any, Callable

from superset.ai.tools.base import AITool, ToolResult

OBJECT_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}


class BuiltinTool(AITool):
    """Small declarative adapter around a Superset operation."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters_schema: dict[str, Any],
        handler: Callable[[dict[str, Any]], Any],
        *,
        requires_confirmation: bool = False,
        required_permission: str | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.parameters_schema = parameters_schema
        self.handler = handler
        self.requires_confirmation = requires_confirmation
        self.required_permission = required_permission

    def execute(self, user: Any, params: dict[str, Any]) -> ToolResult:
        """Run the handler and turn expected failures into safe tool results."""
        try:
            return ToolResult(success=True, data=self.handler(params))
        except Exception as ex:
            return ToolResult(success=False, data=None, error=str(ex))


def _list_databases(_: dict[str, Any]) -> list[dict[str, Any]]:
    from superset.extensions import db, security_manager
    from superset.models.core import Database

    return [
        {"id": database.id, "name": database.database_name, "backend": database.backend}
        for database in db.session.query(Database).order_by(Database.database_name).all()
        if security_manager.can_access_database(database)
    ]


def _list_database_tables(params: dict[str, Any]) -> list[dict[str, Any]]:
    from superset.commands.database.tables import TablesDatabaseCommand
    from superset.models.core import Database

    database = Database.get(params["database_id"])
    if database is None:
        raise ValueError("Database not found")
    schema = params.get("schema") or database.get_default_schema()
    if not schema:
        raise ValueError("A schema is required for this database")
    result = TablesDatabaseCommand(
        database.id, params.get("catalog"), schema, False
    ).run()
    search = (params.get("search") or "").lower()
    return [
        item for item in result.get("result", []) if search in item["value"].lower()
    ]


def _get_table_schema(params: dict[str, Any]) -> dict[str, Any]:
    from superset.connectors.sqla.models import SqlaTable
    from superset.extensions import db, security_manager

    table = (
        db.session.query(SqlaTable)
        .filter_by(
            database_id=params["database_id"],
            table_name=params["table_name"],
            schema=params.get("schema"),
        )
        .one_or_none()
    )
    if table is None or not security_manager.can_access_datasource(table):
        raise ValueError("Table not found or access denied")
    return {
        "table": table.table_name,
        "schema": table.schema,
        "columns": [
            {"name": column.column_name, "type": column.type, "nullable": column.is_nullable}
            for column in table.columns
        ],
    }


def _list_datasets(params: dict[str, Any]) -> list[dict[str, Any]]:
    from superset.connectors.sqla.models import SqlaTable
    from superset.extensions import db, security_manager

    search = (params.get("search") or "").lower()
    return [
        {"id": dataset.id, "name": dataset.table_name, "database": dataset.database.database_name}
        for dataset in db.session.query(SqlaTable).all()
        if search in dataset.table_name.lower()
        and security_manager.can_access_datasource(dataset)
    ]


def _get_dataset_schema(params: dict[str, Any]) -> dict[str, Any]:
    from superset.connectors.sqla.models import SqlaTable
    from superset.extensions import db, security_manager

    dataset = db.session.get(SqlaTable, params["dataset_id"])
    if dataset is None or not security_manager.can_access_datasource(dataset):
        raise ValueError("Dataset not found or access denied")
    return {
        "id": dataset.id,
        "name": dataset.table_name,
        "columns": [
            {"name": column.column_name, "type": column.type, "nullable": column.is_nullable}
            for column in dataset.columns
        ],
    }


def _list_charts(params: dict[str, Any]) -> list[dict[str, Any]]:
    from superset.extensions import db, security_manager
    from superset.models.slice import Slice

    search = (params.get("search") or "").lower()
    return [
        {"id": chart.id, "name": chart.slice_name, "viz_type": chart.viz_type}
        for chart in db.session.query(Slice).all()
        if search in chart.slice_name.lower() and security_manager.can_access_chart(chart)
    ]


def _list_dashboards(params: dict[str, Any]) -> list[dict[str, Any]]:
    from superset.extensions import db, security_manager
    from superset.models.dashboard import Dashboard

    search = (params.get("search") or "").lower()
    return [
        {"id": dashboard.id, "title": dashboard.dashboard_title, "slug": dashboard.slug}
        for dashboard in db.session.query(Dashboard).all()
        if search in dashboard.dashboard_title.lower()
        and security_manager.can_access_dashboard(dashboard)
    ]


def _list_saved_queries(_: dict[str, Any]) -> list[dict[str, Any]]:
    from flask import g
    from superset.extensions import db
    from superset.models.sql_lab import SavedQuery

    return [
        {"id": query.id, "label": query.label, "database_id": query.db_id}
        for query in db.session.query(SavedQuery).filter(SavedQuery.user_id == g.user.id)
    ]


def _get_current_context(_: dict[str, Any]) -> dict[str, Any]:
    """Return request metadata that is safe to expose to the model."""
    from flask import request

    return {"path": request.path, "endpoint": request.endpoint}


def _create_chart(params: dict[str, Any]) -> dict[str, Any]:
    from superset.commands.chart.create import CreateChartCommand

    chart = CreateChartCommand(params).run()
    return {"id": chart.id, "name": chart.slice_name}


def _edit_chart(params: dict[str, Any]) -> dict[str, Any]:
    from superset.commands.chart.update import UpdateChartCommand

    chart = UpdateChartCommand(params["chart_id"], params["data"]).run()
    return {"id": chart.id, "name": chart.slice_name}


def _create_dashboard(params: dict[str, Any]) -> dict[str, Any]:
    from superset.commands.dashboard.create import CreateDashboardCommand

    dashboard = CreateDashboardCommand(params).run()
    return {"id": dashboard.id, "title": dashboard.dashboard_title}


def _edit_dashboard(params: dict[str, Any]) -> dict[str, Any]:
    from superset.commands.dashboard.update import UpdateDashboardCommand

    dashboard = UpdateDashboardCommand(params["dashboard_id"], params["data"]).run()
    return {"id": dashboard.id, "title": dashboard.dashboard_title}


def _create_dataset(params: dict[str, Any]) -> dict[str, Any]:
    from superset.commands.dataset.create import CreateDatasetCommand

    dataset = CreateDatasetCommand(params).run()
    return {"id": dataset.id, "name": dataset.table_name}


def _run_sql_query(params: dict[str, Any]) -> dict[str, Any]:
    """Execute SQL through the same secured Database API used by MCP tools."""
    from superset.extensions import db, security_manager
    from superset.models.core import Database
    from superset_core.queries.types import QueryOptions

    database = db.session.get(Database, params["database_id"])
    if database is None or not security_manager.can_access_database(database):
        raise ValueError("Database not found or access denied")
    result = database.execute(
        params["sql"],
        QueryOptions(
            catalog=params.get("catalog"),
            schema=params.get("schema"),
            limit=params.get("limit", 1000),
            timeout_seconds=params.get("timeout", 60),
        ),
    )
    return {"status": str(result.status), "data": str(result.data)[:100000]}


def _save_sql_query(params: dict[str, Any]) -> dict[str, Any]:
    from flask import g
    from superset.daos.query import SavedQueryDAO
    from superset.extensions import db, security_manager
    from superset.models.core import Database

    database = db.session.get(Database, params["database_id"])
    if database is None or not security_manager.can_access_database(database):
        raise ValueError("Database not found or access denied")
    query = SavedQueryDAO.create(
        attributes={
            "user_id": g.user.id,
            "db_id": database.id,
            "label": params["label"],
            "sql": params["sql"],
            "schema": params.get("schema", ""),
            "catalog": params.get("catalog"),
            "description": params.get("description", ""),
        }
    )
    db.session.commit()
    return {"id": query.id, "label": query.label}


def _add_chart_to_dashboard(params: dict[str, Any]) -> dict[str, Any]:
    from superset.extensions import db, security_manager
    from superset.models.dashboard import Dashboard
    from superset.models.slice import Slice

    dashboard = db.session.get(Dashboard, params["dashboard_id"])
    chart = db.session.get(Slice, params["chart_id"])
    if dashboard is None or chart is None:
        raise ValueError("Dashboard or chart not found")
    if not security_manager.is_owner(dashboard) or not security_manager.can_access_chart(chart):
        raise ValueError("Access denied")
    if chart not in dashboard.slices:
        dashboard.slices.append(chart)
        db.session.commit()
    return {"dashboard_id": dashboard.id, "chart_id": chart.id}


def default_tools() -> list[AITool]:
    """Return the supported MVP tools with their security requirements."""
    search_schema = {"type": "object", "properties": {"search": {"type": "string"}}}
    database_schema = {
        "type": "object",
        "properties": {"database_id": {"type": "integer"}, "schema": {"type": "string"}},
        "required": ["database_id"],
    }
    return [
        BuiltinTool("list_databases", "List accessible databases.", OBJECT_SCHEMA, _list_databases),
        BuiltinTool("list_database_tables", "List accessible database tables.", database_schema, _list_database_tables),
        BuiltinTool("get_table_schema", "Get an accessible table schema.", {**database_schema, "properties": {**database_schema["properties"], "table_name": {"type": "string"}}, "required": ["database_id", "table_name"]}, _get_table_schema),
        BuiltinTool("list_datasets", "List accessible datasets.", search_schema, _list_datasets),
        BuiltinTool("get_dataset_schema", "Get an accessible dataset schema.", {"type": "object", "properties": {"dataset_id": {"type": "integer"}}, "required": ["dataset_id"]}, _get_dataset_schema),
        BuiltinTool("list_charts", "List accessible charts.", search_schema, _list_charts),
        BuiltinTool("list_dashboards", "List accessible dashboards.", search_schema, _list_dashboards),
        BuiltinTool("list_saved_queries", "List the current user's saved queries.", OBJECT_SCHEMA, _list_saved_queries),
        BuiltinTool("get_current_context", "Get the current Superset request context.", OBJECT_SCHEMA, _get_current_context),
        BuiltinTool("run_sql_query", "Execute a SQL query through SQL Lab.", OBJECT_SCHEMA, _run_sql_query, requires_confirmation=True, required_permission="can_ai_run_sql"),
        BuiltinTool("save_sql_query", "Save a SQL query in SQL Lab.", OBJECT_SCHEMA, _save_sql_query, requires_confirmation=True, required_permission="can_ai_run_sql"),
        BuiltinTool("create_chart", "Create a chart.", OBJECT_SCHEMA, _create_chart, requires_confirmation=True, required_permission="can_ai_create_charts"),
        BuiltinTool("edit_chart", "Edit a chart.", OBJECT_SCHEMA, _edit_chart, requires_confirmation=True, required_permission="can_ai_edit_charts"),
        BuiltinTool("create_dashboard", "Create a dashboard.", OBJECT_SCHEMA, _create_dashboard, requires_confirmation=True, required_permission="can_ai_create_dashboards"),
        BuiltinTool("edit_dashboard", "Edit a dashboard.", OBJECT_SCHEMA, _edit_dashboard, requires_confirmation=True, required_permission="can_ai_edit_dashboards"),
        BuiltinTool("add_chart_to_dashboard", "Add a chart to a dashboard.", OBJECT_SCHEMA, _add_chart_to_dashboard, requires_confirmation=True, required_permission="can_ai_edit_dashboards"),
        BuiltinTool("create_dataset", "Create a dataset.", OBJECT_SCHEMA, _create_dataset, requires_confirmation=True, required_permission="can_ai_create_datasets"),
    ]
