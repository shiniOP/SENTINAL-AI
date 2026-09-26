# agents/critic.py

import re

from models import invoke_with_fallback


# ============================================================
# HELPERS
# ============================================================

def extract_decision(text: str):
    """
    Extract ONLY the explicit DECISION field.

    Expected:
        DECISION: ACCEPT
        DECISION: REJECT

    This prevents words such as "reject", "rejection",
    or "policy rejection" elsewhere in the response
    from corrupting the actual decision.
    """

    if not isinstance(text, str):
        text = str(text)

    match = re.search(
        r"(?im)^\s*DECISION\s*:\s*(ACCEPT|REJECT)\b",
        text
    )

    if match:
        return match.group(1).upper()

    return None


def extract_policy_decision(policy_result: str):
    """
    Extract the explicit Policy Agent decision.

    Expected:
        POLICY_DECISION: APPROVE
        POLICY_DECISION: REJECT
        POLICY_DECISION: CONDITIONAL
    """

    if not isinstance(policy_result, str):
        policy_result = str(policy_result)

    match = re.search(
        r"(?im)^\s*POLICY_DECISION\s*:\s*"
        r"(APPROVE|REJECT|CONDITIONAL)\b",
        policy_result
    )

    if match:
        return match.group(1).upper()

    return None


# ============================================================
# CRITIC NODE
# ============================================================

def critic_node(state):

    plan = state.get(
        "plan",
        []
    )

    current_task_id = state.get(
        "current_task"
    )

    # --------------------------------------------------------
    # FIND CURRENT CRITIC TASK
    # --------------------------------------------------------

    task = next(
        (
            task
            for task in plan
            if task.get("id") == current_task_id
            and task.get("agent") == "critic"
        ),
        None
    )

    if task is None:

        return {
            "critic_decision": "REJECT",

            "critic_feedback": (
                "CRITIC ERROR: Current critic task "
                "could not be found."
            ),

            "status": "critic_failed",

            "step_count": (
                state.get("step_count", 0) + 1
            ),

            "trace": (
                state.get("trace", [])
                + [
                    {
                        "agent": "critic",
                        "action": "validate_remediation",
                        "reason": (
                            "Unable to locate the current "
                            "critic task."
                        ),
                        "status": "failed"
                    }
                ]
            )
        }


    # --------------------------------------------------------
    # INPUTS
    # --------------------------------------------------------

    proposed_action = state.get(
        "proposed_action",
        {}
    )

    retrieved_context = state.get(
        "retrieved_context",
        []
    )

    policy_result = state.get(
        "policy_result",
        ""
    )

    if not policy_result:

        policy_result = state.get(
            "validation_result",
            ""
        )


    # --------------------------------------------------------
    # CRITIC PROMPT
    # --------------------------------------------------------

    prompt = f"""
You are the Critic Agent in a multi-agent
enterprise incident-resolution system.

Your job is to independently validate the
remediation proposal before human approval.

==================================================
INVESTIGATION EVIDENCE
==================================================

{retrieved_context}


==================================================
PROPOSED REMEDIATION
==================================================

{proposed_action}


==================================================
POLICY EVALUATION
==================================================

{policy_result}


==================================================
CRITIC TASK
==================================================

{task.get("description", "")}


==================================================
CRITIC RESPONSIBILITIES
==================================================

Evaluate:

1. Whether the evidence supports the proposal.
2. Whether assumptions are clearly identified.
3. Whether missing information is acknowledged.
4. Whether the remediation is safe.
5. Whether the remediation is reversible.
6. Whether risks are identified.
7. Whether verification is defined.
8. Whether human approval is required.
9. Whether the proposal follows the Policy Agent's decision.


==================================================
IMPORTANT POLICY RULE
==================================================

If the Policy Agent explicitly says:

POLICY_DECISION: REJECT

then you MUST output:

DECISION: REJECT


If the Policy Agent says:

POLICY_DECISION: CONDITIONAL

you may output:

DECISION: ACCEPT

ONLY if the proposal preserves the required
conditions from the Policy Agent.

For example, if the Policy requires:

- diagnostic verification first
- human approval before dependency changes
- PII filtering
- verification after remediation

then the proposal must explicitly preserve
those conditions.


==================================================
IMPORTANT SAFETY RULE
==================================================

Do not reject a proposal merely because it
contains missing information.

If the proposal correctly acknowledges missing
information and chooses a safe diagnostic-first
approach, it can still be accepted.

Do not invent logs, metrics, telemetry,
deployment information, or production state.


==================================================
DECISION FORMAT
==================================================

Your response MUST contain exactly one explicit
decision line near the beginning.

Use:

DECISION: ACCEPT

or:

DECISION: REJECT

Do NOT write another DECISION line later.

Then provide:

REASON:

MISSING_INFORMATION:

RISKS:

RECOMMENDATION:


==================================================
FINAL RULE
==================================================

ACCEPT means:

The remediation is sufficiently safe to proceed
to the human approval stage.

It does NOT mean the action should execute
automatically.

REJECT means:

The workflow should replan and address the
critic's concerns.
"""


    # ========================================================
    # MODEL INVOCATION
    # ========================================================

    try:

        response, model_used = invoke_with_fallback(
            prompt
        )

        content = response.content

        if not isinstance(content, str):
            content = str(content)


    except Exception as e:

        return {
            "critic_decision": "REJECT",

            "critic_feedback": (
                f"CRITIC MODEL FAILURE: {str(e)}"
            ),

            "status": "critic_failed",

            "step_count": (
                state.get("step_count", 0) + 1
            ),

            "trace": (
                state.get("trace", [])
                + [
                    {
                        "agent": "critic",
                        "action": "validate_remediation",
                        "reason": (
                            "Critic model invocation failed."
                        ),
                        "status": "failed",
                        "error": str(e)
                    }
                ]
            )
        }


    # ========================================================
    # PARSE EXPLICIT DECISION
    # ========================================================

    decision = extract_decision(
        content
    )

    policy_decision = extract_policy_decision(
        policy_result
    )


    # --------------------------------------------------------
    # SAFE DEFAULT
    # --------------------------------------------------------

    if decision is None:

        decision = "REJECT"


    # ========================================================
    # POLICY SAFETY OVERRIDE
    # ========================================================

    # Policy REJECT can never be overridden by Critic ACCEPT.

    if policy_decision == "REJECT":

        decision = "REJECT"


    # ========================================================
    # CONDITIONAL POLICY CHECK
    # ========================================================

    if policy_decision == "CONDITIONAL":

        lower_content = content.lower()

        condition_indicators = [
            "condition",
            "phase 1",
            "human approval",
            "approval",
            "before",
            "verification"
        ]

        conditions_acknowledged = any(
            indicator in lower_content
            for indicator in condition_indicators
        )

        if (
            decision == "ACCEPT"
            and not conditions_acknowledged
        ):

            decision = "REJECT"

            content += (
                "\n\nSYSTEM SAFETY OVERRIDE:\n"
                "Policy was CONDITIONAL, but the Critic "
                "did not explicitly acknowledge the "
                "required conditions."
            )


    # ========================================================
    # TRACE
    # ========================================================

    trace_entry = {

        "agent": "critic",

        "action": "validate_remediation",

        "input": {
            "task_id": current_task_id,
            "policy_decision": policy_decision,
            "proposed_action": proposed_action
        },

        "reason": (
            "Independently validate the investigation "
            "evidence, remediation proposal, policy "
            "evaluation, risks, missing information, "
            "and human-approval requirements."
        ),

        "status": "success",

        "decision": decision,

        "model_used": model_used,

        "policy_safety_check": (
            "passed"
            if not (
                policy_decision == "REJECT"
                and decision == "ACCEPT"
            )
            else "failed"
        )
    }


    # ========================================================
    # ACCEPT
    # ========================================================

    if decision == "ACCEPT":

        return {

            "critic_decision": "ACCEPT",

            "critic_feedback": content,

            "status": "critic_accepted",

            "step_count": (
                state.get("step_count", 0) + 1
            ),

            "trace": (
                state.get("trace", [])
                + [trace_entry]
            )
        }


    # ========================================================
    # REJECT
    # ========================================================

    return {

        "critic_decision": "REJECT",

        "critic_feedback": content,

        "status": "critic_rejected",

        "step_count": (
            state.get("step_count", 0) + 1
        ),

        "trace": (
            state.get("trace", [])
            + [trace_entry]
        )
    }