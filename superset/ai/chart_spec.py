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
"""Typed chart specifications used by autonomous analytics plans."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from superset.utils import json


@dataclass(frozen=True)
class ChartSpecification:
    """Minimum valid analytical chart definition before Superset conversion."""

    datasource_id: int
    datasource_type: str
    chart_title: str
    viz_type: str
    time_column: str
    metric: str
    time_grain: str | None = "P1Y"
    group_by: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ChartSpecification":
        """Validate an untrusted model payload and construct an immutable spec."""
        required = (
            "datasource_id",
            "datasource_type",
            "chart_title",
            "viz_type",
            "time_column",
            "metric",
        )
        missing = [field for field in required if not value.get(field)]
        if missing:
            raise ValueError(
                f"Missing chart specification fields: {', '.join(missing)}"
            )
        datasource_id = value["datasource_id"]
        if not isinstance(datasource_id, int) or isinstance(datasource_id, bool):
            raise ValueError("Chart datasource_id must be an integer")
        group_by = value.get("group_by", [])
        if not isinstance(group_by, list) or not all(
            isinstance(item, str) for item in group_by
        ):
            raise ValueError("Chart group_by must be a list of column names")
        return cls(
            datasource_id=datasource_id,
            datasource_type=str(value["datasource_type"]),
            chart_title=str(value["chart_title"]).strip(),
            viz_type=str(value["viz_type"]),
            time_column=str(value["time_column"]),
            metric=str(value["metric"]),
            time_grain=cls._time_grain(value),
            group_by=tuple(group_by),
        )

    @staticmethod
    def _time_grain(value: dict[str, Any]) -> str | None:
        if "time_grain" not in value:
            return "P1Y"
        time_grain = value.get("time_grain")
        return str(time_grain) if time_grain not in (None, "") else None

    def to_chart_payload(self) -> dict[str, Any]:
        """Build the validated CreateChartCommand payload expected by Superset."""
        metric = self._metric_payload()
        form_data = {
            "granularity_sqla": self.time_column,
            "time_grain_sqla": self.time_grain,
            "adhoc_filters": [
                {
                    "clause": "WHERE",
                    "comparator": "No filter",
                    "expressionType": "SIMPLE",
                    "operator": "TEMPORAL_RANGE",
                    "subject": self.time_column,
                }
            ],
            "annotation_layers": [],
            "extra_form_data": {},
            "metrics": [metric],
            "groupby": list(self.group_by),
            "metric": metric,
            "row_limit": 10000,
            "viz_type": self.viz_type,
        }
        if self.viz_type == "pie":
            form_data.update(
                {
                    "label_type": "key",
                    "show_labels": True,
                    "donut": False,
                    "sort_by_metric": True,
                }
            )
        elif self.viz_type == "sankey_v2":
            if len(self.group_by) < 2:
                raise ValueError("Sankey charts require source and target dimensions")
            form_data.update(
                {
                    "source": self.group_by[0],
                    "target": self.group_by[1],
                    "groupby": list(self.group_by[:2]),
                    "sort_by_metric": True,
                }
            )
        elif self.viz_type == "big_number_total":
            form_data.update(
                {
                    "header_font_size": 0.4,
                    "subheader_font_size": 0.15,
                    "time_format": "smart_date",
                    "y_axis_format": "SMART_NUMBER",
                }
            )
        return {
            "datasource_id": self.datasource_id,
            "datasource_type": self.datasource_type,
            "slice_name": self.chart_title,
            "viz_type": self.viz_type,
            "params": json.dumps(form_data),
        }

    def _metric_payload(self) -> dict[str, Any]:
        """Convert readable labels to Superset adhoc metric definitions."""
        if self.metric == "COUNT(*)":
            return {
                "expressionType": "SQL",
                "sqlExpression": "COUNT(*)",
                "label": self.metric,
            }
        match = re.fullmatch(r"(SUM|AVG|MIN|MAX|COUNT)\(([^()]+)\)", self.metric)
        if match is None:
            raise ValueError(f"Unsupported chart metric: {self.metric}")
        aggregate, column = match.groups()
        return {
            "expressionType": "SIMPLE",
            "column": {"column_name": column, "type": "NUMERIC"},
            "aggregate": aggregate,
            "label": self.metric,
        }

    def validate_columns(self, columns: tuple[tuple[str, str], ...]) -> None:
        """Reject unknown temporal, grouping, or metric columns before approval."""
        available = {name: column_type.casefold() for name, column_type in columns}
        if self.time_column not in available:
            raise ValueError(f"Chart time_column does not exist: {self.time_column}")
        missing_groups = [name for name in self.group_by if name not in available]
        if missing_groups:
            raise ValueError(
                f"Chart group_by column does not exist: {missing_groups[0]}"
            )
        match = re.fullmatch(r"(?:SUM|AVG|MIN|MAX|COUNT)\(([^()]+)\)", self.metric)
        if match and match.group(1) != "*":
            column = match.group(1)
            if column not in available:
                raise ValueError(f"Chart metric column does not exist: {column}")
            if not any(
                token in available[column]
                for token in ("int", "float", "double", "decimal", "numeric")
            ):
                raise ValueError(f"Chart metric column is not numeric: {column}")
