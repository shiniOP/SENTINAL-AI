# agents/policy.py

from models import invoke_with_fallback


def policy_node(state):

    plan = state.get("plan", [])
    current_task_id = state.get("current_task")

    # ---------------------------------------------------------
    # FIND CURRENT POLICY TASK
    # ---------------------------------------------------------

    task = next(
        (
            task
            for task in plan
            if task.get("id") == current_task_id
            and task.get("agent") == "policy"
        ),
        None
    )

    # ---------------------------------------------------------
    # SAFETY: CURRENT TASK IS NOT FOR POLICY
    # ---------------------------------------------------------

    if task is None:

        trace_entry = {
            "agent": "policy",
            "action": "skip",
            "reason": (
                "Current task is not assigned "
                "to policy."
            ),
            "status": "skipped"
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
            "status": "task_skipped"
        }

    # ---------------------------------------------------------
    # GET CONTEXT
    # ---------------------------------------------------------

    proposed_action = state.get(
        "proposed_action",
        {}
    )

    evidence = state.get(
        "retrieved_context",
        []
    )

    # ---------------------------------------------------------
    # POLICY PROMPT
    # ---------------------------------------------------------

    prompt = f"""
You are the Policy Agent in an enterprise
incident-resolution multi-agent system.

Your responsibility is to evaluate whether the
proposed remediation is acceptable according to
enterprise safety and change-management rules.

You do NOT execute the remediation.

You do NOT modify production.

You only evaluate the proposal.

--------------------------------------------------
USER REQUEST
--------------------------------------------------

{state.get("user_request", "")}

--------------------------------------------------
INCIDENT
--------------------------------------------------

{state.get("incident", "")}

--------------------------------------------------
CURRENT POLICY TASK
--------------------------------------------------

{task.get("description", "")}

--------------------------------------------------
INVESTIGATION EVIDENCE
--------------------------------------------------

{evidence}

--------------------------------------------------
PROPOSED REMEDIATION
--------------------------------------------------

{proposed_action}


==================================================
POLICY RULES
==================================================

Evaluate the proposal using these principles:

1. The proposed action must be supported by
   available evidence.

2. Do not treat an unverified hypothesis as
   a confirmed root cause.

3. High-risk or production-changing actions
   require human approval.

4. Irreversible actions require explicit
   human approval.

5. The remediation should be as limited and
   reversible as reasonably possible.

6. The proposal must include a verification
   strategy.

7. If important information is missing,
   identify it explicitly.

8. Never claim that an action has already
   been executed.


==================================================
OUTPUT
==================================================

Return:

POLICY_DECISION:
APPROVE
or
REJECT
or
CONDITIONAL

REASON:
<reason>

RISKS:
<risks>

MISSING_INFORMATION:
<missing information or NONE>

HUMAN_APPROVAL_REQUIRED:
YES

RECOMMENDATION:
<recommendation>
"""

    # ---------------------------------------------------------
    # MODEL WITH FALLBACK
    # ---------------------------------------------------------

    try:

        response, model_used = (
            invoke_with_fallback(prompt)
        )

        policy_result = response.content

    except Exception as e:

        trace_entry = {
            "agent": "policy",
            "action": "policy_evaluation",
            "reason": (
                "All configured Gemini models "
                "failed during policy evaluation."
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
            "status": "policy_failed"
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
        "agent": "policy",
        "action": "evaluate_remediation",
        "input": {
            "task_id": task.get("id"),
            "proposed_action": proposed_action
        },
        "reason": task.get(
            "reason",
            "Evaluate remediation against policy."
        ),
        "status": "success",
        "model_used": model_used,
        "human_approval_required": True
    }

    # ---------------------------------------------------------
    # RETURN
    # ---------------------------------------------------------

    return {

        # IMPORTANT:
        # Keep Policy output separate from Critic output.
        "policy_result": policy_result,

        "validation_result": policy_result,

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

        "status": "policy_evaluated"
    }