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
"""Tests for safe analytics discovery helpers."""

from superset.ai.discovery import classify_columns, rank_resources


def test_rank_resources_prefers_exact_and_partial_topic_matches() -> None:
    resources = [
        {"name": "inventory"},
        {"name": "international_sales"},
        {"name": "sales_summary"},
    ]

    assert [item["name"] for item in rank_resources(resources, "international sales")] == [
        "international_sales",
        "sales_summary",
        "inventory",
    ]


def test_classify_columns_identifies_chart_candidates() -> None:
    result = classify_columns(
        [
            {"name": "order_date", "type": "DATE"},
            {"name": "sale_id", "type": "INTEGER"},
            {"name": "amount", "type": "NUMERIC"},
            {"name": "country", "type": "VARCHAR"},
        ]
    )

    assert result["temporal"] == ["order_date"]
    assert result["identifiers"] == ["sale_id"]
    assert result["measures"] == ["amount"]
    assert result["dimensions"] == ["country"]
