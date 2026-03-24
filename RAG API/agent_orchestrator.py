"""
Multi-Agent Orchestrator for RAG Collaboration Workspace.

Implements a structured prompt chain with 5 agents:
  Planner -> Analyst -> Researcher -> Executor -> Synthesizer

No external agent frameworks. Each agent is a Bedrock LLM call with a
distinct system prompt plus optional tool access (Athena SQL or RAG retrieval).
"""
from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Generator

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from provider_factory import get_analytics_store, get_bedrock_client

LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Agent definitions
# ---------------------------------------------------------------------------

AGENTS: dict[str, dict] = {
    "planner": {
        "name": "Planner",
        "icon": "clipboard-list",
        "color": "gray",
        "system_prompt": (
            "You are a task planner for an ITSM analytics team. "
            "Given a user goal and available agents (analyst, researcher, executor), "
            "produce a JSON array of 3-5 steps. Each step: {\"agent\": <analyst|researcher|executor>, \"task\": <string>}. "
            "Return ONLY valid JSON array, nothing else."
        ),
        "tools": [],
    },
    "analyst": {
        "name": "Analyst Agent",
        "icon": "chart-bar",
        "color": "teal",
        "system_prompt": (
            "You are a data analyst specializing in ITSM/ServiceNow ticket data. "
            "You analyze incident data using SQL. "
            "Given a task, write a single SQL query to answer it, then summarize the findings with exact numbers. "
            "Always cite exact counts from the data. Never estimate or hallucinate numbers. "
            "When writing SQL, wrap column names in double-quotes. Use the table name provided. "
            "Format: first output the SQL query in a ```sql block, then your analysis."
        ),
        "tools": ["athena_sql"],
    },
    "researcher": {
        "name": "Researcher Agent",
        "icon": "search",
        "color": "blue",
        "system_prompt": (
            "You are a research analyst for an ITSM team. "
            "You search through incident records, resolution notes, and policy documents to find patterns, "
            "root causes, and resolution approaches. "
            "Cite specific ticket IDs, document names, and resolution patterns when available. "
            "Be specific and evidence-based in your findings."
        ),
        "tools": ["rag_retrieval"],
    },
    "executor": {
        "name": "Executor Agent",
        "icon": "lightning-bolt",
        "color": "amber",
        "system_prompt": (
            "You are an ITSM execution specialist. "
            "Given data analysis and research findings from other agents, propose concrete action items: "
            "preventive measures, process changes, ticket templates for recurring issues, "
            "and escalation recommendations. "
            "Be specific and actionable. Number your recommendations. "
            "Reference specific findings from the Analyst and Researcher agents."
        ),
        "tools": [],
    },
    "synthesizer": {
        "name": "Synthesizer",
        "icon": "sparkles",
        "color": "purple",
        "system_prompt": (
            "You are a report synthesizer. "
            "Combine findings from multiple agent outputs into a clear, structured final report. "
            "Use markdown with sections: ## Overview, ## Key Findings, ## Data Insights, ## Recommendations. "
            "Include specific numbers, patterns, and action items from the agent outputs. "
            "Make the report suitable for management review."
        ),
        "tools": [],
    },
}

GOAL_PRESETS = [
    {
        "id": "q1_report",
        "title": "Q1 Incident Report",
        "goal": "Prepare a comprehensive Q1 incident report covering ticket volumes by category, top recurring issues, SLA compliance, and recommended fixes.",
        "icon": "document-report",
    },
    {
        "id": "identity_deep_dive",
        "title": "Identity Incident Deep Dive",
        "goal": "Deep dive into all identity-category incidents: analyze volumes, find common root causes from resolution notes, and draft a prevention plan.",
        "icon": "identification",
    },
    {
        "id": "sla_breach_analysis",
        "title": "SLA Breach Root Cause",
        "goal": "Analyze all SLA-breached tickets, identify patterns by category and priority, find root causes, and propose process improvements to reduce breaches.",
        "icon": "exclamation-circle",
    },
    {
        "id": "top5_recurring",
        "title": "Top 5 Recurring Issues",
        "goal": "Find the top 5 most frequently recurring incident types, research their common resolutions, and draft a preventive action plan for each.",
        "icon": "refresh",
    },
    {
        "id": "network_outage_review",
        "title": "Network Outage Review",
        "goal": "Review all network-category incidents: volume trends, affected systems, common root causes from resolution notes, and recommendations to reduce recurrence.",
        "icon": "wifi",
    },
]


# ---------------------------------------------------------------------------
# SQL extraction helper
# ---------------------------------------------------------------------------

def _extract_sql_from_text(text: str) -> str | None:
    """Extract SQL from ```sql ... ``` block or first SELECT statement."""
    import re
    # Try fenced code block first
    match = re.search(r"```sql\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # Try bare SELECT
    match = re.search(r"(SELECT\s+.+?)(;|$)", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


# ---------------------------------------------------------------------------
# RAG retrieval helper
# ---------------------------------------------------------------------------

def _rag_retrieve(query: str, index_name: str) -> str:
    """Retrieve relevant documents from RAG for the given query."""
    try:
        from vectordb_utils import get_vectorstore
        from customretriever import create_retriever

        vectorstore = get_vectorstore(index_name)
        retriever = create_retriever(vectorstore)
        if hasattr(retriever, "invoke"):
            docs = retriever.invoke(query)
        else:
            docs = retriever.get_relevant_documents(query)

        if not docs:
            return "No relevant documents found."

        snippets = []
        for doc in docs[:4]:
            content = (doc.page_content or "").strip()[:800]
            source = doc.metadata.get("source", doc.metadata.get("filename", "unknown"))
            snippets.append(f"[Source: {source}]\n{content}")
        return "\n\n---\n\n".join(snippets)
    except Exception as exc:
        LOGGER.warning("RAG retrieval failed: %s", exc)
        return f"RAG retrieval unavailable: {exc}"


# ---------------------------------------------------------------------------
# AgentRun
# ---------------------------------------------------------------------------

class AgentRun:
    """Manages a single multi-agent execution run."""

    def __init__(
        self,
        goal: str,
        dataset_id: str | None = None,
        index_name: str | None = None,
        workspace_id: str = "demo-shared",
    ) -> None:
        self.goal = goal
        self.dataset_id = dataset_id
        self.index_name = index_name
        self.workspace_id = workspace_id
        self.run_id = uuid.uuid4().hex
        self.messages: list[dict[str, Any]] = []
        self.created_at = int(time.time())
        self._bedrock = get_bedrock_client()
        self._analytics = get_analytics_store() if dataset_id else None
        self._analytics_snapshot: str | None = None  # loaded lazily

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    def plan(self) -> list[dict]:
        """Orchestrator decomposes goal into agent steps."""
        agent_info = (
            "Available agents:\n"
            "- analyst: queries structured ticket data with SQL via Athena\n"
            "- researcher: searches documents and resolution notes via RAG\n"
            "- executor: proposes concrete action plans and recommendations\n"
        )
        prompt = (
            f"User goal: {self.goal}\n\n"
            f"{agent_info}\n"
            "Return a JSON array of 3-5 steps. Example: "
            '[{"agent": "analyst", "task": "Count tickets by category"}, '
            '{"agent": "researcher", "task": "Find resolution patterns for network issues"}, '
            '{"agent": "executor", "task": "Draft preventive action plan"}]'
        )
        response = self._bedrock.generate_text(
            prompt=prompt,
            system_prompt=AGENTS["planner"]["system_prompt"],
            max_tokens=512,
            temperature=0.1,
        )
        try:
            import re
            # Strip any markdown fences
            cleaned = re.sub(r"```[a-z]*", "", response).strip().strip("`")
            steps = json.loads(cleaned)
            if isinstance(steps, list):
                valid = [s for s in steps if isinstance(s, dict) and "agent" in s and "task" in s]
                if valid:
                    return valid
        except Exception as exc:
            LOGGER.warning("Planner JSON parse failed (%s), using default plan", exc)

        # Fallback default plan
        return [
            {"agent": "analyst", "task": f"Analyze ticket data relevant to: {self.goal}"},
            {"agent": "researcher", "task": f"Search documents for patterns related to: {self.goal}"},
            {"agent": "executor", "task": f"Propose action items based on findings for: {self.goal}"},
        ]

    # ------------------------------------------------------------------
    # Step execution
    # ------------------------------------------------------------------

    def execute_step(self, step: dict) -> dict:
        """Run one agent step with its tools."""
        agent_key = step.get("agent", "executor")
        if agent_key not in AGENTS:
            agent_key = "executor"
        agent = AGENTS[agent_key]
        task = step.get("task", "")

        # Build context from prior messages
        prior_context = self._build_prior_context()

        # Agent thinks (first LLM call)
        think_prompt = (
            f"Goal: {self.goal}\n"
            f"Your task: {task}\n"
            + (f"\nContext from prior steps:\n{prior_context}\n" if prior_context else "")
            + (f"\nDataset ID for SQL queries: {self.dataset_id}\n" if self.dataset_id and agent_key == "analyst" else "")
            + (f"\nTable name to use in SQL: dataset_{self.dataset_id}\n" if self.dataset_id and agent_key == "analyst" else "")
        )

        thought = self._bedrock.generate_text(
            prompt=think_prompt,
            system_prompt=agent["system_prompt"],
            max_tokens=800,
            temperature=0.1,
        )

        # Execute tools
        tool_used = None
        tool_result = None
        output = thought

        if "athena_sql" in agent["tools"] and self._analytics and self.dataset_id:
            sql = _extract_sql_from_text(thought)
            if sql:
                tool_used = "athena_sql"
                try:
                    result = self._analytics.execute_query(
                        dataset_id=self.dataset_id,
                        sql=sql,
                    )
                    rows = result.get("rows", [])
                    columns = result.get("columns", [])
                    # Format as readable table
                    if rows:
                        table_lines = [" | ".join(str(r.get(c, "")) for c in columns) for r in rows[:20]]
                        tool_result = f"Columns: {columns}\nRows ({len(rows)} returned):\n" + "\n".join(table_lines)
                    else:
                        tool_result = "Query returned 0 rows."

                    # Second LLM call: summarize with actual data
                    summary_prompt = (
                        f"Goal: {self.goal}\n"
                        f"Your task: {task}\n"
                        f"SQL executed:\n```sql\n{sql}\n```\n"
                        f"Query results:\n{tool_result}\n\n"
                        "Summarize the findings in 2-4 sentences with exact numbers."
                    )
                    output = self._bedrock.generate_text(
                        prompt=summary_prompt,
                        system_prompt=agent["system_prompt"],
                        max_tokens=512,
                        temperature=0.1,
                    )
                except Exception as exc:
                    LOGGER.warning("Athena query failed: %s", exc)
                    tool_result = f"SQL execution failed: {exc}"
                    # Fall back to LLM-only analysis
                    output = thought + f"\n\n[Note: SQL execution failed — {exc}]"

        elif "rag_retrieval" in agent["tools"] and self.index_name:
            tool_used = "rag_retrieval"
            tool_result = _rag_retrieve(task, self.index_name)

            # Second LLM call: summarize with retrieved docs
            summary_prompt = (
                f"Goal: {self.goal}\n"
                f"Your task: {task}\n"
                f"Retrieved documents:\n{tool_result}\n\n"
                "Based on the retrieved documents, provide your analysis and findings."
            )
            output = self._bedrock.generate_text(
                prompt=summary_prompt,
                system_prompt=agent["system_prompt"],
                max_tokens=800,
                temperature=0.1,
            )

        message = {
            "type": "agent_message",
            "agent": agent_key,
            "agent_name": agent["name"],
            "icon": agent["icon"],
            "color": agent["color"],
            "task": task,
            "thought": thought,
            "tool_used": tool_used,
            "tool_result": tool_result,
            "output": output,
            "timestamp": time.time(),
        }
        self.messages.append(message)
        return message

    # ------------------------------------------------------------------
    # Analytics snapshot (from existing Analytics tab data)
    # ------------------------------------------------------------------

    @staticmethod
    def _format_analytics_value(value: Any) -> str:
        if value in (None, ""):
            return "No data"
        if isinstance(value, (int, float)):
            return f"{value:,}"
        return str(value)

    def _load_metric_preview(self, metric: dict[str, Any]) -> dict[str, Any] | None:
        if not self._analytics or not self.dataset_id:
            return None
        metric_id = str(metric.get("metric_id", ""))
        cached_result = self._analytics.load_metric_result(self.dataset_id, metric_id) if metric_id else None
        if cached_result:
            return cached_result

        sql = metric.get("sql")
        if not isinstance(sql, str) or not sql.strip():
            return None

        result = self._analytics.execute_query(dataset_id=self.dataset_id, sql=sql)
        preview_payload = {
            "dataset_id": self.dataset_id,
            "metric_id": metric_id,
            "sql": sql,
            "result": result,
            "chart_type": metric.get("chart_type", "table"),
            "source": "athena",
        }
        if metric_id:
            self._analytics.cache_metric_result(self.dataset_id, metric_id, preview_payload)
        return preview_payload

    def _metric_preview_lines(self, metric: dict[str, Any], preview: dict[str, Any]) -> list[str]:
        result = preview.get("result", {}) if isinstance(preview, dict) else {}
        rows = result.get("rows", []) if isinstance(result, dict) else []
        columns = result.get("columns", []) if isinstance(result, dict) else []
        if not rows or not columns:
            return [f"- {metric.get('title', 'Metric')}: No rows returned."]

        lines = [f"### {metric.get('title', 'Metric')}"]
        description = str(metric.get("description", "")).strip()
        if description:
            lines.append(f"- Description: {description}")

        first_row = rows[0]
        if len(rows) == 1 and len(columns) == 1:
            lines.append(
                f"- KPI value: {self._format_analytics_value(first_row.get(columns[0]))}"
            )
            return lines

        lines.append("| " + " | ".join(columns) + " |")
        lines.append("| " + " | ".join("---" for _ in columns) + " |")
        for row in rows[:5]:
            lines.append("| " + " | ".join(self._format_analytics_value(row.get(column)) for column in columns) + " |")
        if len(rows) > 5:
            lines.append(f"- Additional rows available: {len(rows) - 5}")
        return lines

    def _load_analytics_snapshot(self) -> str | None:
        """
        Pull the pre-computed analytics summary + top metrics for the dataset
        from the existing S3 cache (same data shown in the Analytics tab).
        Returns a markdown-formatted string or None if unavailable.
        """
        if not self._analytics or not self.dataset_id:
            return None
        try:
            cached = self._analytics.load_metrics_cache(self.dataset_id)
            if not cached:
                rows = self._analytics.load_dataset_rows(self.dataset_id)
                if not rows:
                    return None
                schema = self._analytics.get_schema(self.dataset_id) or self._analytics.profile_schema(rows)
                summary = self._analytics.build_summary_metrics(rows, schema)
                cached = {"summary": summary, "metrics": []}

            summary = cached.get("summary", {})
            metrics = cached.get("metrics", [])

            lines = ["## Analytics KPIs"]
            lines.append(f"- Dataset: `{self.dataset_id}`")
            lines.append(f"- Total rows: {self._format_analytics_value(summary.get('total_rows', 'unknown'))}")

            for key, val in summary.items():
                if key == "total_rows" or not isinstance(val, dict):
                    continue
                col = key.replace("top_", "").replace("_", " ")
                label = val.get("label", "-")
                count = val.get("count", "-")
                lines.append(
                    f"- Top {col}: {self._format_analytics_value(label)} ({self._format_analytics_value(count)})"
                )

            if metrics:
                lines.append("")
                lines.append("## Supporting Metrics")
                previewable_metrics = [metric for metric in metrics if metric.get("type") != "summary"][:3]
                if previewable_metrics:
                    for metric in previewable_metrics:
                        try:
                            preview = self._load_metric_preview(metric)
                            if preview:
                                lines.extend(self._metric_preview_lines(metric, preview))
                                lines.append("")
                        except Exception as metric_exc:
                            LOGGER.warning(
                                "Failed to load analytics metric preview for dataset=%s metric=%s: %s",
                                self.dataset_id,
                                metric.get("metric_id"),
                                metric_exc,
                            )
                else:
                    lines.append("- No supporting metrics were generated for this dataset.")

                lines.append("### Available Metrics")
                lines.append("| Metric | Type | Description |")
                lines.append("| --- | --- | --- |")
                for metric in metrics[:6]:
                    lines.append(
                        f"| {metric.get('title', '')} | {metric.get('type', '')} | {metric.get('description', '')} |"
                    )

            return "\n".join(lines)
        except Exception as exc:
            LOGGER.warning("Failed to load analytics snapshot: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    def synthesize(self) -> dict:
        """Final synthesis of all agent outputs, enriched with Analytics tab data."""
        all_outputs = "\n\n".join(
            f"**[{m['agent_name']}]** — {m['task']}\n{m['output']}"
            for m in self.messages
        )

        # Load analytics snapshot (same data shown in Analytics tab)
        if self._analytics_snapshot is None:
            self._analytics_snapshot = self._load_analytics_snapshot()

        analytics_section = (
            f"\n\nAnalytics Dashboard data (from structured dataset):\n{self._analytics_snapshot}"
            if self._analytics_snapshot
            else ""
        )

        prompt = (
            f"Goal: {self.goal}\n\n"
            f"Agent outputs:\n{all_outputs}"
            f"{analytics_section}\n\n"
            "Synthesize all findings into a complete, well-structured deliverable. "
            "If Analytics Dashboard data is provided, include dedicated sections named "
            "'## Analytics KPIs' and '## Supporting Metrics' using the exact structured metrics."
        )
        final = self._bedrock.generate_text(
            prompt=prompt,
            system_prompt=AGENTS["synthesizer"]["system_prompt"],
            max_tokens=1500,
            temperature=0.1,
        )
        if self._analytics_snapshot and "## Analytics KPIs" not in final:
            final = f"{final.rstrip()}\n\n{self._analytics_snapshot}"
        message = {
            "type": "synthesis",
            "agent": "synthesizer",
            "agent_name": AGENTS["synthesizer"]["name"],
            "icon": AGENTS["synthesizer"]["icon"],
            "color": AGENTS["synthesizer"]["color"],
            "task": "Synthesize all findings",
            "thought": None,
            "tool_used": None,
            "tool_result": None,
            "output": final,
            "timestamp": time.time(),
        }
        self.messages.append(message)
        return message

    # ------------------------------------------------------------------
    # Streaming runner
    # ------------------------------------------------------------------

    def run_streaming(self) -> Generator[str, None, None]:
        """
        Execute the full multi-agent run and yield SSE-formatted strings.

        Events emitted:
          event: plan      data: {steps: [...]}
          event: agent_message  data: {agent message dict}
          event: synthesis data: {synthesis message dict}
          event: done      data: {run_id, total_steps, created_at}
        """

        def sse(event: str, data: Any) -> str:
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        # 1. Plan
        try:
            steps = self.plan()
        except Exception as exc:
            LOGGER.exception("Planner failed: %s", exc)
            steps = [
                {"agent": "analyst", "task": "Analyze the available ticket data"},
                {"agent": "researcher", "task": "Search documents for relevant patterns"},
                {"agent": "executor", "task": "Propose action items"},
            ]

        yield sse("plan", {
            "run_id": self.run_id,
            "goal": self.goal,
            "steps": steps,
            "agent_name": AGENTS["planner"]["name"],
            "agent": "planner",
            "icon": AGENTS["planner"]["icon"],
            "color": AGENTS["planner"]["color"],
            "timestamp": time.time(),
        })

        # 1b. Pre-load analytics snapshot and stream it as context
        self._analytics_snapshot = self._load_analytics_snapshot()
        if self._analytics_snapshot:
            yield sse("analytics_snapshot", {
                "agent": "analyst",
                "agent_name": "Analytics Dashboard",
                "icon": "chart-bar",
                "color": "teal",
                "dataset_id": self.dataset_id,
                "snapshot": self._analytics_snapshot,
                "timestamp": time.time(),
            })

        # 2. Execute steps
        for step in steps:
            try:
                message = self.execute_step(step)
                yield sse("agent_message", message)
            except Exception as exc:
                LOGGER.exception("Agent step failed agent=%s: %s", step.get("agent"), exc)
                yield sse("agent_message", {
                    "type": "agent_message",
                    "agent": step.get("agent", "executor"),
                    "agent_name": AGENTS.get(step.get("agent", "executor"), AGENTS["executor"])["name"],
                    "icon": "exclamation",
                    "color": "red",
                    "task": step.get("task", ""),
                    "thought": None,
                    "tool_used": None,
                    "tool_result": None,
                    "output": f"Step failed: {exc}",
                    "timestamp": time.time(),
                })

        # 3. Synthesize
        try:
            synthesis = self.synthesize()
            yield sse("synthesis", synthesis)
        except Exception as exc:
            LOGGER.exception("Synthesis failed: %s", exc)
            yield sse("synthesis", {
                "type": "synthesis",
                "agent": "synthesizer",
                "agent_name": "Synthesizer",
                "output": "Synthesis failed. Please review individual agent outputs above.",
                "timestamp": time.time(),
            })

        # 4. Done
        yield sse("done", {
            "run_id": self.run_id,
            "total_steps": len(steps),
            "created_at": self.created_at,
            "workspace_id": self.workspace_id,
        })

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_prior_context(self) -> str:
        if not self.messages:
            return ""
        return "\n\n".join(
            f"[{m['agent_name']} — {m['task']}]:\n{m['output']}"
            for m in self.messages[-3:]
        )

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "goal": self.goal,
            "dataset_id": self.dataset_id,
            "index_name": self.index_name,
            "workspace_id": self.workspace_id,
            "created_at": self.created_at,
            "messages": self.messages,
            "status": "completed",
        }


# ---------------------------------------------------------------------------
# Run persistence (S3-based, no new DynamoDB table)
# ---------------------------------------------------------------------------

def save_run_to_s3(run: AgentRun) -> None:
    """Save completed run to S3 analytics bucket."""
    try:
        analytics = get_analytics_store()
        key = f"agent-runs/{run.workspace_id}/{run.run_id}.json"
        payload = json.dumps(run.to_dict(), indent=2).encode("utf-8")
        analytics.s3.put_object(
            Bucket=analytics.bucket_name,
            Key=key,
            Body=payload,
            ContentType="application/json",
        )
        LOGGER.info("Agent run saved run_id=%s key=%s", run.run_id, key)
    except Exception as exc:
        LOGGER.warning("Failed to save agent run: %s", exc)


def list_runs_from_s3(workspace_id: str) -> list[dict]:
    """List recent agent runs for a workspace from S3."""
    try:
        analytics = get_analytics_store()
        prefix = f"agent-runs/{workspace_id}/"
        response = analytics.s3.list_objects_v2(
            Bucket=analytics.bucket_name,
            Prefix=prefix,
        )
        runs = []
        for obj in response.get("Contents", []):
            run_data = json.loads(
                analytics.s3.get_object(
                    Bucket=analytics.bucket_name, Key=obj["Key"]
                )["Body"].read().decode("utf-8")
            )
            runs.append({
                "run_id": run_data.get("run_id"),
                "goal": run_data.get("goal"),
                "workspace_id": run_data.get("workspace_id"),
                "created_at": run_data.get("created_at"),
                "status": run_data.get("status", "completed"),
                "step_count": len(run_data.get("messages", [])),
            })
        return sorted(runs, key=lambda r: r.get("created_at", 0), reverse=True)[:20]
    except Exception as exc:
        LOGGER.warning("Failed to list agent runs: %s", exc)
        return []


def get_run_from_s3(workspace_id: str, run_id: str) -> dict | None:
    """Get full run data from S3."""
    try:
        analytics = get_analytics_store()
        key = f"agent-runs/{workspace_id}/{run_id}.json"
        response = analytics.s3.get_object(Bucket=analytics.bucket_name, Key=key)
        return json.loads(response["Body"].read().decode("utf-8"))
    except Exception as exc:
        LOGGER.warning("Failed to load agent run %s: %s", run_id, exc)
        return None
