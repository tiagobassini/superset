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
from superset.utils import json

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
            if self.required_permission:
                from superset.extensions import security_manager

                if not security_manager.can_access(
                    self.required_permission, "AIAgentResource"
                ):
                    return ToolResult(False, None, "Tool access denied")
            return ToolResult(success=True, data=self.handler(params))
        except Exception as ex:
            return ToolResult(success=False, data=None, error=str(ex))


def _list_databases(_: dict[str, Any]) -> list[dict[str, Any]]:
    from superset.extensions import db, security_manager
    from superset.models.core import Database

    return [
        {
            "id": database.id,
            "name": database.database_name,
            "backend": database.backend,
        }
        for database in db.session.query(Database)
        .order_by(Database.database_name)
        .all()
        if security_manager.can_access_database(database)
    ]


def _list_database_tables(params: dict[str, Any]) -> list[dict[str, Any]]:
    from superset.commands.database.tables import TablesDatabaseCommand
    from superset.extensions import db
    from superset.models.core import Database

    database = db.session.get(Database, params["database_id"])
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
    from superset.commands.database.tables import TablesDatabaseCommand
    from superset.databases.utils import get_table_metadata
    from superset.extensions import db
    from superset.models.core import Database
    from superset.sql.parse import Table

    database = db.session.get(Database, params["database_id"])
    if database is None:
        raise ValueError("Database not found")
    schema = params.get("schema") or database.get_default_schema()
    if not schema:
        raise ValueError("A schema is required for this database")
    tables = TablesDatabaseCommand(
        database.id, params.get("catalog"), schema, False
    ).run()
    if params["table_name"] not in {item["value"] for item in tables["result"]}:
        raise ValueError("Table not found or access denied")
    return dict(
        get_table_metadata(
            database,
            Table(params["table_name"], schema, params.get("catalog")),
        )
    )


def _list_datasets(params: dict[str, Any]) -> list[dict[str, Any]]:
    from superset.connectors.sqla.models import SqlaTable
    from superset.extensions import db, security_manager

    search = (params.get("search") or "").lower()
    return [
        {
            "id": dataset.id,
            "name": dataset.table_name,
            "database": dataset.database.database_name,
        }
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
            {
                "name": column.column_name,
                "type": column.type,
                "nullable": column.is_nullable,
            }
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
        if search in chart.slice_name.lower()
        and security_manager.can_access_chart(chart)
    ]


def _list_dashboards(params: dict[str, Any]) -> list[dict[str, Any]]:
    from superset.extensions import db, security_manager
    from superset.models.dashboard import Dashboard

    search = (params.get("search") or "").lower()
    return [
        {
            "id": dashboard.id,
            "title": dashboard.dashboard_title,
            "slug": dashboard.slug,
        }
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
        for query in db.session.query(SavedQuery).filter(
            SavedQuery.user_id == g.user.id
        )
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
    """Execute SQL through the exact command path used by SQL Lab's REST API."""
    from uuid import uuid4

    from superset.sqllab.api import SqlLabRestApi
    from superset.sqllab.sqllab_execution_context import SqlJsonExecutionContext

    context = SqlJsonExecutionContext(
        {
            "database_id": params["database_id"],
            "catalog": params.get("catalog"),
            "schema": params.get("schema"),
            "sql": params["sql"],
            "runAsync": False,
            "queryLimit": params.get("limit", 1000),
            "status": "running",
            "client_id": str(uuid4()),
            "sql_editor_id": str(uuid4()),
            "tab": "AI Assistant",
            "templateParams": json.dumps(params.get("template_params", {})),
        }
    )
    result = SqlLabRestApi._create_sql_json_command(context, None).run()
    return result["payload"]


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
    if not security_manager.is_owner(
        dashboard
    ) or not security_manager.can_access_chart(chart):
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
        "properties": {
            "database_id": {"type": "integer"},
            "catalog": {"type": "string"},
            "schema": {"type": "string"},
            "search": {"type": "string"},
        },
        "required": ["database_id"],
    }
    table_schema = {
        **database_schema,
        "properties": {
            **database_schema["properties"],
            "table_name": {"type": "string"},
        },
        "required": ["database_id", "table_name"],
    }
    dataset_schema = {
        "type": "object",
        "properties": {"dataset_id": {"type": "integer"}},
        "required": ["dataset_id"],
    }
    sql_schema = {
        "type": "object",
        "properties": {
            "database_id": {"type": "integer"},
            "sql": {"type": "string"},
            "catalog": {"type": "string"},
            "schema": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10000},
            "template_params": {"type": "object"},
        },
        "required": ["database_id", "sql"],
    }
    save_query_schema = {
        **sql_schema,
        "properties": {
            **sql_schema["properties"],
            "label": {"type": "string"},
            "description": {"type": "string"},
        },
        "required": ["database_id", "sql", "label"],
    }
    chart_schema = {
        "type": "object",
        "properties": {
            "datasource_id": {"type": "integer"},
            "datasource_type": {"type": "string"},
            "slice_name": {"type": "string"},
            "viz_type": {"type": "string"},
            "params": {"type": "string"},
        },
        "required": ["datasource_id", "datasource_type", "slice_name", "viz_type"],
    }
    edit_chart_schema = {
        "type": "object",
        "properties": {"chart_id": {"type": "integer"}, "data": {"type": "object"}},
        "required": ["chart_id", "data"],
    }
    dashboard_schema = {
        "type": "object",
        "properties": {
            "dashboard_title": {"type": "string"},
            "slug": {"type": "string"},
        },
        "required": ["dashboard_title"],
    }
    edit_dashboard_schema = {
        "type": "object",
        "properties": {"dashboard_id": {"type": "integer"}, "data": {"type": "object"}},
        "required": ["dashboard_id", "data"],
    }
    add_chart_schema = {
        "type": "object",
        "properties": {
            "dashboard_id": {"type": "integer"},
            "chart_id": {"type": "integer"},
        },
        "required": ["dashboard_id", "chart_id"],
    }
    create_dataset_schema = {
        "type": "object",
        "properties": {
            "database": {"type": "integer"},
            "table_name": {"type": "string"},
            "schema": {"type": "string"},
            "catalog": {"type": "string"},
            "sql": {"type": "string"},
        },
        "required": ["database", "table_name"],
    }
    return [
        BuiltinTool(
            "list_databases",
            "List accessible databases.",
            OBJECT_SCHEMA,
            _list_databases,
        ),
        BuiltinTool(
            "list_database_tables",
            "List accessible database tables.",
            database_schema,
            _list_database_tables,
        ),
        BuiltinTool(
            "get_table_schema",
            "Get an accessible table schema.",
            table_schema,
            _get_table_schema,
        ),
        BuiltinTool(
            "list_datasets", "List accessible datasets.", search_schema, _list_datasets
        ),
        BuiltinTool(
            "get_dataset_schema",
            "Get an accessible dataset schema.",
            dataset_schema,
            _get_dataset_schema,
        ),
        BuiltinTool(
            "list_charts", "List accessible charts.", search_schema, _list_charts
        ),
        BuiltinTool(
            "list_dashboards",
            "List accessible dashboards.",
            search_schema,
            _list_dashboards,
        ),
        BuiltinTool(
            "list_saved_queries",
            "List the current user's saved queries.",
            OBJECT_SCHEMA,
            _list_saved_queries,
        ),
        BuiltinTool(
            "get_current_context",
            "Get the current Superset request context.",
            OBJECT_SCHEMA,
            _get_current_context,
        ),
        BuiltinTool(
            "run_sql_query",
            "Execute a SQL query through SQL Lab.",
            sql_schema,
            _run_sql_query,
            requires_confirmation=True,
            required_permission="can_ai_run_sql",
        ),
        BuiltinTool(
            "save_sql_query",
            "Save a SQL query in SQL Lab.",
            save_query_schema,
            _save_sql_query,
            requires_confirmation=True,
            required_permission="can_ai_run_sql",
        ),
        BuiltinTool(
            "create_chart",
            "Create a chart.",
            chart_schema,
            _create_chart,
            requires_confirmation=True,
            required_permission="can_ai_create_charts",
        ),
        BuiltinTool(
            "edit_chart",
            "Edit a chart.",
            edit_chart_schema,
            _edit_chart,
            requires_confirmation=True,
            required_permission="can_ai_edit_charts",
        ),
        BuiltinTool(
            "create_dashboard",
            "Create a dashboard.",
            dashboard_schema,
            _create_dashboard,
            requires_confirmation=True,
            required_permission="can_ai_create_dashboards",
        ),
        BuiltinTool(
            "edit_dashboard",
            "Edit a dashboard.",
            edit_dashboard_schema,
            _edit_dashboard,
            requires_confirmation=True,
            required_permission="can_ai_edit_dashboards",
        ),
        BuiltinTool(
            "add_chart_to_dashboard",
            "Add a chart to a dashboard.",
            add_chart_schema,
            _add_chart_to_dashboard,
            requires_confirmation=True,
            required_permission="can_ai_edit_dashboards",
        ),
        BuiltinTool(
            "create_dataset",
            "Create a dataset.",
            create_dataset_schema,
            _create_dataset,
            requires_confirmation=True,
            required_permission="can_ai_create_datasets",
        ),
    ]
