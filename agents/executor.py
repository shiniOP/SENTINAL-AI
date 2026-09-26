# agents/executor.py

from models import invoke_with_fallback


def executor_node(state):

    plan = state.get("plan", [])
    current_task_id = state.get("current_task")

    # ---------------------------------------------------------
    # FIND CURRENT EXECUTOR TASK
    # ---------------------------------------------------------

    task = next(
        (
            task
            for task in plan
            if task.get("id") == current_task_id
            and task.get("agent") == "executor"
        ),
        None
    )

    # ---------------------------------------------------------
    # SAFETY: CURRENT TASK IS NOT FOR EXECUTOR
    # ---------------------------------------------------------

    if task is None:

        trace_entry = {
            "agent": "executor",
            "action": "skip",
            "reason": (
                "Current task is not assigned "
                "to executor."
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
    # COLLECT CONTEXT
    # ---------------------------------------------------------

    context = state.get(
        "retrieved_context",
        []
    )

    policy_result = state.get(
        "policy_result",
        state.get(
            "validation_result",
            "No policy evaluation available."
        )
    )

    # ---------------------------------------------------------
    # EXECUTOR PROMPT
    # ---------------------------------------------------------

    prompt = f"""
You are the Executor Agent in an enterprise
incident-resolution multi-agent system.

Your responsibility is to PREPARE a remediation
proposal.

You must NOT actually execute a sensitive
production action at this stage.

The Critic Agent must review your proposal
before human approval.

The system must never claim that a remediation
has already been executed.

--------------------------------------------------
USER REQUEST
--------------------------------------------------

{state.get("user_request", "")}


--------------------------------------------------
INCIDENT
--------------------------------------------------

{state.get("incident", "")}


--------------------------------------------------
CURRENT TASK
--------------------------------------------------

{task.get("description", "")}


--------------------------------------------------
INVESTIGATION EVIDENCE
--------------------------------------------------

{context}


--------------------------------------------------
POLICY EVALUATION
--------------------------------------------------

{policy_result}


==================================================
REMEDIATION REQUIREMENTS
==================================================

Prepare a concrete remediation proposal.

The proposal must include:

1. Problem being addressed

2. Proposed remediation action

3. Target/component affected

4. Why this action addresses the
   likely cause

5. Evidence supporting the action

6. Whether the action is reversible

7. Risks

8. Potential side effects

9. Verification steps after execution

10. Whether human approval is required


==================================================
EVIDENCE SAFETY
==================================================

Do NOT invent:

- logs
- metrics
- deployment information
- service behavior
- infrastructure state
- database state
- monitoring results

Clearly distinguish:

OBSERVED FACTS

INFERENCES

HYPOTHESES

MISSING INFORMATION

If evidence is insufficient to confidently
identify the root cause, explicitly say so.

Do NOT convert a hypothesis into a confirmed
root cause.


==================================================
EXECUTION SAFETY
==================================================

You are preparing the remediation only.

DO NOT:

- execute commands
- modify production
- deploy code
- restart services
- delete resources
- change infrastructure
- claim that a rollback occurred
- claim that a fix was applied

The actual execution will happen only after
the Critic review and required human approval.

Return a clear remediation proposal.
"""

    # ---------------------------------------------------------
    # MODEL INVOCATION WITH FALLBACK
    # ---------------------------------------------------------

    try:

        result, model_used = (
            invoke_with_fallback(prompt)
        )

        response = result.content

    except Exception as e:

        trace_entry = {
            "agent": "executor",
            "action": "prepare_remediation",
            "input": task.get(
                "description",
                ""
            ),
            "reason": (
                "Executor model invocation failed "
                "after all configured model fallbacks."
            ),
            "status": "failed",
            "error": str(e)
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
            "status": "executor_failed"
        }

    # ---------------------------------------------------------
    # CREATE PROPOSED ACTION
    # ---------------------------------------------------------

    proposed_action = {
        "task_id": task.get("id"),
        "description": task.get(
            "description",
            ""
        ),
        "proposal": response,
        "requires_human_approval": True,
        "reversible": None,
        "executed": False
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
    # AUDIT TRACE
    # ---------------------------------------------------------

    trace_entry = {
        "agent": "executor",
        "action": "prepare_remediation",
        "input": {
            "task_id": task.get("id"),
            "description": task.get(
                "description",
                ""
            )
        },
        "reason": task.get(
            "reason",
            "Prepare a remediation proposal."
        ),
        "status": "proposal_ready",
        "human_approval_required": True,
        "model_used": model_used
    }

    # ---------------------------------------------------------
    # RETURN UPDATED STATE
    # ---------------------------------------------------------

    return {
        "proposed_action": proposed_action,

        "requires_human_approval": True,

        "completed_tasks": (
            updated_completed_tasks
        ),

        "trace": (
            state.get("trace", [])
            + [trace_entry]
        ),

        "step_count": (
            state.get("step_count", 0)
            + 1
        ),

        "status": "remediation_proposed"
    }