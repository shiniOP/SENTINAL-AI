# agents/investigator.py

from models import invoke_with_fallback
from tools.github_tools import get_recent_commits


def investigator_node(state):

    plan = state.get("plan", [])
    current_task_id = state.get("current_task")

    # ---------------------------------------------------------
    # FIND CURRENT INVESTIGATOR TASK
    # ---------------------------------------------------------

    task = next(
        (
            task
            for task in plan
            if task.get("id") == current_task_id
            and task.get("agent") == "investigator"
        ),
        None
    )

    # ---------------------------------------------------------
    # SAFETY: CURRENT TASK IS NOT FOR INVESTIGATOR
    # ---------------------------------------------------------

    if task is None:

        trace_entry = {
            "agent": "investigator",
            "action": "skip",
            "reason": (
                "Current task is not assigned "
                "to investigator."
            ),
            "status": "skipped"
        }

        return {
            "trace": (
                state.get("trace", [])
                + [trace_entry]
            ),
            "step_count": (
                state.get("step_count", 0)
                + 1
            ),
            "status": "task_skipped"
        }

    # ---------------------------------------------------------
    # TOOL INFORMATION
    # ---------------------------------------------------------

    tool_name = task.get(
        "tool",
        ""
    )

    tool_arguments = task.get(
        "tool_arguments",
        {}
    )

    # ---------------------------------------------------------
    # GITHUB TOOL
    # ---------------------------------------------------------

    if tool_name == "get_recent_commits":

        trace_entry = {
            "agent": "investigator",
            "action": "get_recent_commits",
            "reason": task.get(
                "reason",
                "Investigate repository history."
            ),
            "input": tool_arguments,
            "status": "running"
        }

        try:

            result = get_recent_commits(
                repo=tool_arguments.get(
                    "repo",
                    state.get(
                        "repository",
                        ""
                    )
                ),
                per_page=tool_arguments.get(
                    "per_page",
                    20
                )
            )

        except Exception as e:

            result = {
                "success": False,
                "error": str(e)
            }

        # -----------------------------------------------------
        # TOOL FAILURE
        # -----------------------------------------------------

        if not result.get(
            "success",
            False
        ):

            failure_trace = {
                **trace_entry,
                "status": "failed",
                "error": result.get(
                    "error",
                    "Unknown GitHub error."
                )
            }

            return {
                "tool_results": (
                    state.get(
                        "tool_results",
                        []
                    )
                    + [result]
                ),
                "trace": (
                    state.get(
                        "trace",
                        []
                    )
                    + [failure_trace]
                ),
                "step_count": (
                    state.get(
                        "step_count",
                        0
                    )
                    + 1
                ),
                "status": "investigation_failed"
            }

        # -----------------------------------------------------
        # FORMAT GITHUB EVIDENCE
        # -----------------------------------------------------

        commits = result.get(
            "commits",
            []
        )

        evidence_text = (
            "Recent GitHub commits for "
            f"{result.get('repository')}:\n"
        )

        for commit in commits:

            evidence_text += (
                f"\nSHA: {commit.get('sha')}"
                f"\nAuthor: {commit.get('author')}"
                f"\nDate: {commit.get('date')}"
                f"\nMessage: {commit.get('message')}"
                "\n"
            )

        # -----------------------------------------------------
        # MARK TASK COMPLETE
        # -----------------------------------------------------

        completed_tasks = state.get(
            "completed_tasks",
            []
        )

        if task["id"] not in completed_tasks:

            updated_completed_tasks = (
                completed_tasks
                + [task["id"]]
            )

        else:

            updated_completed_tasks = (
                completed_tasks
            )

        # -----------------------------------------------------
        # AUDIT TRACE
        # -----------------------------------------------------

        success_trace = {
            "agent": "investigator",
            "action": "get_recent_commits",
            "reason": task.get(
                "reason",
                "Investigate repository history."
            ),
            "input": tool_arguments,
            "status": "success"
        }

        # -----------------------------------------------------
        # RETURN
        # -----------------------------------------------------

        return {

            "retrieved_context": (
                state.get(
                    "retrieved_context",
                    []
                )
                + [evidence_text]
            ),

            "sources": (
                state.get(
                    "sources",
                    []
                )
                + [
                    f"https://github.com/"
                    f"{result.get('repository')}"
                ]
            ),

            "tool_calls": (
                state.get(
                    "tool_calls",
                    []
                )
                + [
                    {
                        "tool": "get_recent_commits",
                        "arguments": tool_arguments
                    }
                ]
            ),

            "tool_results": (
                state.get(
                    "tool_results",
                    []
                )
                + [result]
            ),

            "completed_tasks": (
                updated_completed_tasks
            ),

            "trace": (
                state.get(
                    "trace",
                    []
                )
                + [success_trace]
            ),

            "step_count": (
                state.get(
                    "step_count",
                    0
                )
                + 1
            ),

            "status": "investigation_complete"
        }

    # ---------------------------------------------------------
    # UNKNOWN TOOL
    # ---------------------------------------------------------

    if tool_name:

        trace_entry = {
            "agent": "investigator",
            "action": "tool_selection_failed",
            "reason": (
                f"Unknown tool: {tool_name}"
            ),
            "input": {
                "tool": tool_name
            },
            "status": "failed"
        }

        return {
            "trace": (
                state.get(
                    "trace",
                    []
                )
                + [trace_entry]
            ),
            "step_count": (
                state.get(
                    "step_count",
                    0
                )
                + 1
            ),
            "status": "investigation_failed"
        }

    # ---------------------------------------------------------
    # ANALYZE EXISTING EVIDENCE
    # ---------------------------------------------------------

    existing_evidence = state.get(
        "retrieved_context",
        []
    )

    if not existing_evidence:

        completed_tasks = state.get(
            "completed_tasks",
            []
        )

        if task["id"] not in completed_tasks:

            completed_tasks = (
                completed_tasks
                + [task["id"]]
            )

        trace_entry = {
            "agent": "investigator",
            "action": "investigation_degraded",
            "reason": (
                "No external tool was specified "
                "and no existing evidence is available."
            ),
            "status": "degraded"
        }

        return {

            "completed_tasks": (
                completed_tasks
            ),

            "trace": (
                state.get(
                    "trace",
                    []
                )
                + [trace_entry]
            ),

            "step_count": (
                state.get(
                    "step_count",
                    0
                )
                + 1
            ),

            "status": "investigation_degraded"
        }

    # ---------------------------------------------------------
    # INVESTIGATION ANALYSIS PROMPT
    # ---------------------------------------------------------

    prompt = f"""
You are the Investigator Agent in an enterprise
incident-resolution multi-agent system.

Analyze the evidence already collected.

Your job is to help the system understand what
is known about the incident.

IMPORTANT:

Do NOT invent:

- logs
- metrics
- deployments
- infrastructure state
- database state
- service behavior
- monitoring results

Only use the evidence provided below.

Clearly distinguish:

1. OBSERVED FACTS
2. INFERENCES
3. HYPOTHESES
4. MISSING INFORMATION

Never present a hypothesis as a confirmed
root cause.

--------------------------------------------------
INCIDENT
--------------------------------------------------

{state.get("incident", "")}

--------------------------------------------------
USER REQUEST
--------------------------------------------------

{state.get("user_request", "")}

--------------------------------------------------
CURRENT TASK
--------------------------------------------------

{task.get("description", "")}

--------------------------------------------------
EXISTING EVIDENCE
--------------------------------------------------

{existing_evidence}

Provide a concise investigation analysis.
"""

    # ---------------------------------------------------------
    # MODEL WITH FALLBACK
    # ---------------------------------------------------------

    try:

        response, model_used = (
            invoke_with_fallback(prompt)
        )

        analysis = response.content

    except Exception as e:

        trace_entry = {
            "agent": "investigator",
            "action": "analysis_failed",
            "reason": (
                "All configured Gemini models "
                "failed during investigation."
            ),
            "status": "failed",
            "error": str(e)
        }

        return {
            "trace": (
                state.get(
                    "trace",
                    []
                )
                + [trace_entry]
            ),
            "step_count": (
                state.get(
                    "step_count",
                    0
                )
                + 1
            ),
            "status": "investigation_failed"
        }

    # ---------------------------------------------------------
    # MARK TASK COMPLETE
    # ---------------------------------------------------------

    completed_tasks = state.get(
        "completed_tasks",
        []
    )

    if task["id"] not in completed_tasks:

        updated_completed_tasks = (
            completed_tasks
            + [task["id"]]
        )

    else:

        updated_completed_tasks = (
            completed_tasks
        )

    # ---------------------------------------------------------
    # TRACE
    # ---------------------------------------------------------

    trace_entry = {
        "agent": "investigator",
        "action": "analyze_existing_evidence",
        "input": task.get(
            "description",
            ""
        ),
        "reason": task.get(
            "reason",
            ""
        ),
        "status": "success",
        "model_used": model_used
    }

    # ---------------------------------------------------------
    # RETURN
    # ---------------------------------------------------------

    return {

        "retrieved_context": (
            state.get(
                "retrieved_context",
                []
            )
            + [analysis]
        ),

        "completed_tasks": (
            updated_completed_tasks
        ),

        "trace": (
            state.get(
                "trace",
                []
            )
            + [trace_entry]
        ),

        "step_count": (
            state.get(
                "step_count",
                0
            )
            + 1
        ),

        "status": "investigation_complete"
    }