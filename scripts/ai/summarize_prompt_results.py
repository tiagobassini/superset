#!/usr/bin/env python3
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

"""Summarize AI prompt test results from JSONL output.

Reads detailed JSONL records from run_example_prompt_suite.py and generates
a human-readable + machine-parseable summary with:
- Overall pass/fail statistics
- Detailed failure analysis with root cause categorization
- Actionable groupings for debugging and system improvements
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class FailureAnalysis:
    """Categorized failure information for a single test case."""

    case_id: str
    prompt: str
    status: str
    passed: bool
    failure_reasons: list[str]
    failure_categories: list[str]
    terminal_state: str
    latency_ms: int | None = None
    response_preview: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return asdict(self)


@dataclass
class SummaryStats:
    """Aggregate statistics for all test results."""

    total_cases: int = 0
    passed_count: int = 0
    failed_count: int = 0
    awaiting_confirmation: int = 0
    awaiting_user_input: int = 0
    completed_failed: int = 0
    other_status: int = 0
    total_latency_ms: int = 0
    average_latency_ms: float = 0.0
    failure_categories_count: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def compute(self) -> None:
        """Compute derived statistics."""
        if self.total_cases > 0:
            self.average_latency_ms = self.total_latency_ms / self.total_cases


def infer_failure_category(failure_reasons: list[str]) -> list[str]:
    """Map failure reason strings to root cause categories."""
    categories = set()

    for reason in failure_reasons:
        reason_lower = reason.lower()

        if "expected one confirmed execution plan" in reason_lower or "missing plan" in reason_lower:
            categories.add("planning_failure")
        elif "missing expected resource" in reason_lower or "ai_test" in reason_lower:
            categories.add("resource_not_created")
        elif "missing expected" in reason_lower and "column" in reason_lower:
            categories.add("missing_column")
        elif "missing expected" in reason_lower and "source" in reason_lower:
            categories.add("missing_source")
        elif "execution failed" in reason_lower or "error" in reason_lower:
            categories.add("execution_error")
        elif "awaiting confirmation" in reason_lower:
            categories.add("pending_confirmation")
        elif "awaiting input" in reason_lower:
            categories.add("pending_user_input")
        elif "timeout" in reason_lower:
            categories.add("timeout")
        else:
            categories.add("other_failure")

    return sorted(list(categories)) if categories else ["unknown"]


def extract_partial_response(response: str | None, max_chars: int = 150) -> str | None:
    """Extract a preview of the AI response for context."""
    if not response:
        return None
    truncated = response[:max_chars].strip()
    if len(response) > max_chars:
        truncated += "…"
    return truncated


def process_results(input_file: Path) -> tuple[SummaryStats, list[FailureAnalysis]]:
    """Read JSONL results and compute summary statistics and failure details."""
    stats = SummaryStats()
    failures: list[FailureAnalysis] = []

    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    with input_file.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            try:
                record = json.loads(line.strip())
            except json.JSONDecodeError as e:
                print(f"WARNING: Invalid JSON at line {line_num}: {e}", file=sys.stderr)
                continue

            case_id = record.get("id", "UNKNOWN")
            passed = record.get("passed", False)
            status = record.get("status", "unknown")
            terminal_state = record.get("metrics", {}).get("terminal_state", "unknown")
            latency_ms = record.get("metrics", {}).get("latency_ms")
            failure_reasons = record.get("failures", [])
            response = record.get("response", "")
            prompt = record.get("prompt", "")

            stats.total_cases += 1
            if latency_ms:
                stats.total_latency_ms += latency_ms

            if passed:
                stats.passed_count += 1
            else:
                stats.failed_count += 1

                # Categorize terminal state
                if terminal_state == "awaiting_confirmation":
                    stats.awaiting_confirmation += 1
                elif terminal_state == "awaiting_user_input":
                    stats.awaiting_user_input += 1
                elif terminal_state == "completed":
                    stats.completed_failed += 1
                else:
                    stats.other_status += 1

                # Infer failure categories
                failure_categories = infer_failure_category(failure_reasons)
                for cat in failure_categories:
                    stats.failure_categories_count[cat] += 1

                # Create failure record
                failure = FailureAnalysis(
                    case_id=case_id,
                    prompt=prompt,
                    status=status,
                    passed=False,
                    failure_reasons=failure_reasons,
                    failure_categories=failure_categories,
                    terminal_state=terminal_state,
                    latency_ms=latency_ms,
                    response_preview=extract_partial_response(response),
                )
                failures.append(failure)

    stats.compute()
    return stats, failures


def generate_summary_report(stats: SummaryStats, failures: list[FailureAnalysis]) -> dict[str, Any]:
    """Generate a complete summary report structured for humans and machines."""
    return {
        "summary": {
            "total_cases": stats.total_cases,
            "passed_count": stats.passed_count,
            "failed_count": stats.failed_count,
            "pass_rate_percent": round(100 * stats.passed_count / stats.total_cases, 1) if stats.total_cases > 0 else 0,
            "average_latency_ms": round(stats.average_latency_ms, 1),
        },
        "failure_breakdown": {
            "awaiting_confirmation": stats.awaiting_confirmation,
            "awaiting_user_input": stats.awaiting_user_input,
            "completed_but_failed": stats.completed_failed,
            "other_status": stats.other_status,
        },
        "failure_root_causes": dict(stats.failure_categories_count),
        "failures_detail": [failure.to_dict() for failure in failures],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Summarize AI prompt suite test results from JSONL output."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("/tmp/ai_prompt_suite.jsonl"),
        help="Path to input JSONL file (default: /tmp/ai_prompt_suite.jsonl)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/ai_prompt_suite_resume.jsonl"),
        help="Path to output summary JSON file (default: /tmp/ai_prompt_suite_resume.jsonl)",
    )
    args = parser.parse_args()

    try:
        stats, failures = process_results(args.input)
        report = generate_summary_report(stats, failures)

        # Write output file
        with args.output.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        # Print human-readable summary to stdout
        print("\n" + "=" * 70)
        print("AI PROMPT SUITE TEST SUMMARY")
        print("=" * 70)
        print(f"\nTotal Cases:      {stats.total_cases}")
        print(f"Passed:           {stats.passed_count} ({report['summary']['pass_rate_percent']}%)")
        print(f"Failed:           {stats.failed_count}")
        print(f"Average Latency:  {stats.average_latency_ms:.0f}ms\n")

        print("FAILURE BREAKDOWN:")
        print(f"  Awaiting confirmation:    {stats.awaiting_confirmation}")
        print(f"  Awaiting user input:      {stats.awaiting_user_input}")
        print(f"  Completed but failed:     {stats.completed_failed}")
        print(f"  Other status:             {stats.other_status}\n")

        print("ROOT CAUSE ANALYSIS:")
        for category, count in sorted(stats.failure_categories_count.items(), key=lambda x: -x[1]):
            print(f"  {category:30s}: {count:3d} cases")

        print(f"\n✓ Summary report written to: {args.output}")
        print("=" * 70 + "\n")

        return 0 if stats.failed_count == 0 else 1

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
