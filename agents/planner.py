# agents/planner.py

from typing import List, Dict, Any

from pydantic import BaseModel, Field

from models import invoke_structured_with_fallback


# ============================================================
# STRUCTURED OUTPUT SCHEMAS
# ============================================================

class Task(BaseModel):
    id: int

    description: str

    agent: str

    reason: str

    depends_on: List[int] = Field(
        default_factory=list
    )

    requires_tool: bool = False

    tool: str = ""

    tool_arguments: Dict[str, Any] = Field(
        default_factory=dict
    )


class Plan(BaseModel):
    tasks: List[Task]


# ============================================================
# PLANNER NODE
# ============================================================

def planner_node(state):
    """
    Planner Agent

    Responsibilities:
    - Understand the incident
    - Dynamically decompose the problem
    - Delegate work to specialised agents
    - Create task dependencies
    - Select available tools
    - Explain why each task is needed
    - Re-plan when the Critic rejects a proposal

    IMPORTANT:
    The Planner can only select tools that are
    actually implemented by the application.
    """

    user_request = state.get(
        "user_request",
        ""
    )

    repository = state.get(
        "repository",
        ""
    )

    incident = state.get(
        "incident",
        ""
    )

    critic_feedback = state.get(
        "critic_feedback",
        ""
    )

    previous_plan = state.get(
        "plan",
        []
    )

    replan_count = state.get(
        "replan_count",
        0
    )


    # ========================================================
    # PLANNER PROMPT
    # ========================================================

    prompt = f"""
You are the Planner Agent in a multi-agent
enterprise incident-resolution system.

Your responsibility is to dynamically decompose
an incident into meaningful tasks and delegate
those tasks to specialised agents.

You are NOT an executor.

You must create a real plan based on the
current incident.

Do NOT use a fixed hardcoded chain.

--------------------------------------------------
USER REQUEST
--------------------------------------------------

{user_request}


--------------------------------------------------
REPOSITORY
--------------------------------------------------

{repository}


--------------------------------------------------
INCIDENT
--------------------------------------------------

{incident}


--------------------------------------------------
PREVIOUS PLAN
--------------------------------------------------

{previous_plan}


--------------------------------------------------
CRITIC FEEDBACK
--------------------------------------------------

{critic_feedback}


--------------------------------------------------
REPLAN COUNT
--------------------------------------------------

{replan_count}


==================================================
AVAILABLE SPECIALISED AGENTS
==================================================

1. investigator

Purpose:
- Investigate the incident
- Gather evidence
- Inspect repository history
- Analyze evidence already collected
- Distinguish observed facts from hypotheses

2. executor

Purpose:
- Prepare a remediation proposal
- Identify a concrete corrective action
- Explain risks and reversibility
- NEVER execute a sensitive production action
  during planning

3. policy

Purpose:
- Evaluate whether the proposed remediation
  complies with the defined enterprise policy
- Identify risks
- Identify approval requirements

4. critic

Purpose:
- Independently review the investigation
- Review the remediation
- Review policy evaluation
- Reject weak or unsupported proposals
- Identify missing information


==================================================
AVAILABLE EXTERNAL TOOLS
==================================================

The application currently has ONLY ONE real
external tool.

Tool:

get_recent_commits

Purpose:

Retrieve recent commits from the specified
GitHub repository.

Arguments:

repo
per_page

Example:

{{
    "repo": "{repository}",
    "per_page": 20
}}


==================================================
CRITICAL TOOL CONSTRAINT
==================================================

ONLY use tools explicitly listed above.

The following tools DO NOT currently exist:

- logs
- application logs
- metrics
- monitoring
- Kubernetes
- Docker
- Jira
- Slack
- database
- deployment API
- incident management API
- cloud infrastructure API

DO NOT create tasks that require any of those
tools.

Do NOT pretend those tools exist.

If the incident would normally require logs
or metrics but they are unavailable, explicitly
treat that information as missing.

Do NOT invent the evidence.


==================================================
REPOSITORY RULE
==================================================

The repository is provided by the application.

Repository:

{repository}

NEVER substitute another repository.

If you create a get_recent_commits task,
its arguments MUST use exactly:

{{
    "repo": "{repository}",
    "per_page": 20
}}

Do not hardcode another repository.


==================================================
WORKFLOW LOGIC
==================================================

The normal logical flow is:

INVESTIGATION
      ↓
REMEDIATION PROPOSAL
      ↓
POLICY EVALUATION
      ↓
CRITIC REVIEW
      ↓
HUMAN APPROVAL


This is NOT a hardcoded chain.

You must dynamically determine:

- what investigation is needed
- how many investigation tasks are needed
- which tasks depend on other tasks
- whether more evidence is required
- which specialised agent should handle each task


==================================================
INVESTIGATION
==================================================

Use get_recent_commits when repository history
is relevant.

Example:

requires_tool = true

tool = get_recent_commits

tool_arguments = {{
    "repo": "{repository}",
    "per_page": 20
}}


After evidence has been collected, an
investigator may analyze the existing evidence
without using another external tool.

For example:

requires_tool = false

tool = ""

tool_arguments = {{}}


If the available evidence is insufficient,
do NOT invent logs or metrics.

Instead, identify the missing information
in the task description or investigation
analysis.


==================================================
EVIDENCE RULE
==================================================

Do NOT claim that a commit caused an incident
unless the available evidence actually
establishes that relationship.

Use distinctions such as:

OBSERVED FACT:
A recent commit changed X.

INFERENCE:
The timing suggests X may be related.

HYPOTHESIS:
X could be contributing to the incident.

MISSING INFORMATION:
Direct service logs or metrics are unavailable.

Never convert a hypothesis into a confirmed
root cause without evidence.


==================================================
EXECUTOR RULES
==================================================

The Executor prepares a remediation proposal.

It does NOT execute the remediation.

The Executor should normally depend on the
investigation task that provides the evidence
needed for the proposal.


==================================================
POLICY RULES
==================================================

The Policy Agent evaluates the remediation
proposal.

Therefore the Policy task should normally
depend on the Executor task.

The Policy Agent must evaluate the proposal,
not perform it.


==================================================
CRITIC RULES
==================================================

The Critic independently evaluates:

1. Investigation evidence
2. Proposed remediation
3. Policy evaluation
4. Risk
5. Reversibility
6. Missing information

The Critic should normally depend on the
Policy task.

The Critic can:

ACCEPT

or

REJECT


==================================================
HUMAN APPROVAL
==================================================

Sensitive or potentially irreversible actions
must require human approval.

The Planner does NOT approve actions.

The Planner only creates the plan that allows
the downstream workflow to enforce approval.


==================================================
REPLANNING
==================================================

If Critic feedback exists, use it.

Critic feedback:

{critic_feedback}

When replanning:

- Do not blindly repeat the previous plan.
- Address the Critic's concerns.
- Add investigation if information is missing.
- Modify the remediation path if necessary.
- Do not invent unavailable tools.
- Preserve useful evidence.
- Avoid unnecessary tasks.


==================================================
TASK DESIGN
==================================================

Every task must contain:

id
description
agent
reason
depends_on
requires_tool
tool
tool_arguments


The agent MUST be one of:

investigator
executor
policy
critic


Task IDs must be unique integers.

Dependencies must reference valid task IDs.

A task should only depend on another task when
its output is actually required.


==================================================
TOOL VALIDATION
==================================================

If:

requires_tool = true

then:

tool MUST be:

get_recent_commits

and:

tool_arguments MUST contain:

{{
    "repo": "{repository}",
    "per_page": 20
}}


If:

requires_tool = false

then:

tool MUST be:

""

and:

tool_arguments MUST be:

{{}}


==================================================
NO UNNECESSARY TASKS
==================================================

Do not create multiple tasks that perform
the same work.

Do not create a fake logs task.

Do not create a fake metrics task.

Do not create a fake deployment task.

Do not create tasks merely to make the
workflow look more complex.

The plan should contain only tasks that
meaningfully contribute to resolving the
incident.


==================================================
SAFETY
==================================================

If evidence is insufficient to safely recommend
a remediation:

- do not invent evidence
- identify the missing information
- propose the safest available next step
- require human approval where appropriate

Never claim that an action has already been
executed.

Never bypass human approval.


==================================================
OUTPUT
==================================================

Return a structured Plan.

Every task must contain:

id
description
agent
reason
depends_on
requires_tool
tool
tool_arguments
"""


    # ========================================================
    # STRUCTURED MODEL WITH FALLBACK
    # ========================================================

    result, model_used = (
        invoke_structured_with_fallback(
            prompt,
            Plan
        )
    )


    # ========================================================
    # NORMALIZE PLAN
    # ========================================================

    normalized_plan = []

    for index, task in enumerate(
        result.tasks,
        start=1
    ):

        task_data = task.model_dump()

        # ----------------------------------------------------
        # FORCE SEQUENTIAL UNIQUE IDS
        # ----------------------------------------------------

        task_data["id"] = index


        # ----------------------------------------------------
        # VALIDATE AGENT
        # ----------------------------------------------------

        allowed_agents = {
            "investigator",
            "executor",
            "policy",
            "critic"
        }

        if task_data.get("agent") not in allowed_agents:

            task_data["agent"] = "investigator"


        # ----------------------------------------------------
        # VALIDATE DEPENDENCIES
        # ----------------------------------------------------

        valid_dependencies = []

        for dependency in task_data.get(
            "depends_on",
            []
        ):

            if (
                isinstance(dependency, int)
                and dependency >= 1
                and dependency < index
            ):

                valid_dependencies.append(
                    dependency
                )

        task_data["depends_on"] = (
            valid_dependencies
        )


        # ----------------------------------------------------
        # NORMALIZE TOOL FIELDS
        # ----------------------------------------------------

        tool = task_data.get(
            "tool",
            ""
        )

        requires_tool = task_data.get(
            "requires_tool",
            False
        )

        arguments = task_data.get(
            "tool_arguments",
            {}
        )


        # ----------------------------------------------------
        # ENFORCE ONLY IMPLEMENTED TOOL
        # ----------------------------------------------------

        if tool == "get_recent_commits":

            task_data["requires_tool"] = True

            per_page = arguments.get(
                "per_page",
                20
            )

            task_data["tool"] = (
                "get_recent_commits"
            )

            task_data["tool_arguments"] = {
                "repo": repository,
                "per_page": per_page
            }


        else:

            # Any unknown tool is removed.
            #
            # This prevents the Planner from
            # producing tasks such as:
            #
            # logs
            # metrics
            # kubernetes
            # etc.

            task_data["requires_tool"] = False

            task_data["tool"] = ""

            task_data["tool_arguments"] = {}


        # ----------------------------------------------------
        # ADD TASK
        # ----------------------------------------------------

        normalized_plan.append(
            task_data
        )


    # ========================================================
    # ENSURE DEPENDENCIES ARE STILL VALID
    # ========================================================

    valid_task_ids = {
        task["id"]
        for task in normalized_plan
    }

    for task in normalized_plan:

        task["depends_on"] = [
            dependency
            for dependency in task.get(
                "depends_on",
                []
            )
            if dependency in valid_task_ids
            and dependency != task["id"]
        ]


    # ========================================================
    # TRACE
    # ========================================================

    trace_entry = {
        "agent": "planner",

        "action": (
            "replan"
            if replan_count > 0
            else "create_plan"
        ),

        "input": {
            "repository": repository,
            "incident": incident
        },

        "reason": (
            "Dynamically decomposed the incident "
            "and delegated tasks using only "
            "implemented tools."
        ),

        "status": "success",

        "model_used": model_used,

        "replan_count": replan_count,

        "tasks_created": len(
            normalized_plan
        )
    }


    # ========================================================
    # RETURN STATE
    # ========================================================

    return {

        "plan": normalized_plan,

        "current_task": None,

        "completed_tasks": [],

        "trace": (
            state.get("trace", [])
            + [trace_entry]
        ),

        "step_count": (
            state.get("step_count", 0)
            + 1
        ),

        "status": "plan_created"
    }