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
    time_grain: str = "P1Y"
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
            raise ValueError(f"Missing chart specification fields: {', '.join(missing)}")
        datasource_id = value["datasource_id"]
        if not isinstance(datasource_id, int) or isinstance(datasource_id, bool):
            raise ValueError("Chart datasource_id must be an integer")
        group_by = value.get("group_by", [])
        if not isinstance(group_by, list) or not all(isinstance(item, str) for item in group_by):
            raise ValueError("Chart group_by must be a list of column names")
        return cls(
            datasource_id=datasource_id,
            datasource_type=str(value["datasource_type"]),
            chart_title=str(value["chart_title"]).strip(),
            viz_type=str(value["viz_type"]),
            time_column=str(value["time_column"]),
            metric=str(value["metric"]),
            time_grain=str(value.get("time_grain", "P1Y")),
            group_by=tuple(group_by),
        )

    def to_chart_payload(self) -> dict[str, Any]:
        """Build the validated CreateChartCommand payload expected by Superset."""
        return {
            "datasource_id": self.datasource_id,
            "datasource_type": self.datasource_type,
            "slice_name": self.chart_title,
            "viz_type": self.viz_type,
            "params": json.dumps(
                {
                    "granularity_sqla": self.time_column,
                    "time_grain_sqla": self.time_grain,
                    "metrics": [self.metric],
                    "groupby": list(self.group_by),
                }
            ),
        }
