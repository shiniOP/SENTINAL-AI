# graph/workflow.py

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt

from graph.state import AgentState

from agents.planner import planner_node
from agents.investigator import investigator_node
from agents.executor import executor_node
from agents.policy import policy_node
from agents.critic import critic_node

from graph.router import task_router_node


# ============================================================
# SAFETY LIMITS
# ============================================================

MAX_STEPS = 40
MAX_REPLANS = 2
MAX_RETRIES = 2


# ============================================================
# SAFE STOP
# ============================================================

def safe_stop_node(state):

    trace_entry = {
        "agent": "system",
        "action": "safe_stop",
        "reason": (
            "Workflow exceeded the maximum allowed "
            "number of execution steps, retries, or replans."
        ),
        "status": "safe_stopped",
    }

    return {
        "trace": (
            state.get("trace", [])
            + [trace_entry]
        ),
        "status": "safe_stopped",
        "step_count": (
            state.get("step_count", 0) + 1
        ),
    }


# ============================================================
# REPLAN
# ============================================================

def replan_node(state):

    new_replan_count = (
        state.get("replan_count", 0) + 1
    )

    trace_entry = {
        "agent": "system",
        "action": "replan",
        "reason": state.get(
            "critic_feedback",
            "Critic requested replanning."
        ),
        "status": "replanning",
        "replan_count": new_replan_count,
    }

    return {
        "replan_count": new_replan_count,

        "trace": (
            state.get("trace", [])
            + [trace_entry]
        ),

        "status": "replanning",

        "step_count": (
            state.get("step_count", 0) + 1
        ),
    }


# ============================================================
# RETRY
# ============================================================

def retry_node(state):

    new_retry_count = (
        state.get("retry_count", 0) + 1
    )

    current_task = state.get(
        "current_task",
        "unknown"
    )

    trace_entry = {
        "agent": "system",
        "action": "retry",
        "input": {
            "task_id": current_task,
            "retry_number": new_retry_count,
        },
        "reason": (
            "The previous specialized-agent execution "
            "failed, so the workflow is retrying the task."
        ),
        "status": "retrying",
        "retry_count": new_retry_count,
    }

    return {
        "retry_count": new_retry_count,

        "trace": (
            state.get("trace", [])
            + [trace_entry]
        ),

        "status": "retrying",

        "step_count": (
            state.get("step_count", 0) + 1
        ),
    }


# ============================================================
# HUMAN APPROVAL
# ============================================================

def human_approval_node(state):

    proposed_action = state.get(
        "proposed_action",
        {}
    )

    policy_result = state.get(
        "policy_result",
        "No policy evaluation available."
    )

    critic_feedback = state.get(
        "critic_feedback",
        ""
    )

    approval_payload = {

        "type": "human_approval_required",

        "message": (
            "The Critic accepted the remediation. "
            "Human approval is required before execution."
        ),

        "proposed_action": proposed_action,

        "policy_evaluation": policy_result,

        "critic_feedback": critic_feedback,

        "risks": proposed_action.get(
            "risks",
            "See remediation proposal."
        ),

        "reversible": proposed_action.get(
            "reversible",
            "Unknown"
        ),

        "requires_human_approval": True,
    }

    # --------------------------------------------------------
    # AUDIT TRACE
    # --------------------------------------------------------

    trace_entry = {
        "agent": "human",
        "action": "approval_required",
        "input": approval_payload,
        "reason": (
            "Critic accepted the remediation, "
            "but execution requires explicit "
            "human authorization."
        ),
        "status": "awaiting_approval",
    }

    # --------------------------------------------------------
    # INTERRUPT
    # --------------------------------------------------------
    #
    # LangGraph pauses execution here.
    #
    # The workflow is resumed from main.py using:
    #
    # Command(
    #     resume={
    #         "approved": True,
    #         "reason": "Approved by operator"
    #     }
    # )
    #
    # --------------------------------------------------------

    decision = interrupt(
        {
            **approval_payload,
            "trace_entry": trace_entry,
        }
    )

    # --------------------------------------------------------
    # VALIDATE HUMAN RESPONSE
    # --------------------------------------------------------

    if not isinstance(
        decision,
        dict
    ):

        decision = {
            "approved": False,
            "reason": (
                "Invalid human approval response."
            ),
        }

    approved = bool(
        decision.get(
            "approved",
            False
        )
    )

    reason = decision.get(
        "reason",
        "No reason provided."
    )

    # ========================================================
    # APPROVED
    # ========================================================

    if approved:

        approval_trace = {
            "agent": "human",
            "action": "approval_decision",
            "input": {
                "approved": True,
                "reason": reason,
            },
            "reason": (
                "Human explicitly approved "
                "the proposed remediation."
            ),
            "status": "approved",
        }

        return {
            "requires_human_approval": True,

            "approval_status": "approved",

            "approval_reason": reason,

            "approved": True,

            "trace": (
                state.get("trace", [])
                + [
                    trace_entry,
                    approval_trace,
                ]
            ),

            "status": "human_approved",

            "step_count": (
                state.get("step_count", 0) + 1
            ),
        }

    # ========================================================
    # REJECTED
    # ========================================================

    rejection_trace = {
        "agent": "human",
        "action": "approval_decision",
        "input": {
            "approved": False,
            "reason": reason,
        },
        "reason": (
            "Human rejected the proposed remediation."
        ),
        "status": "rejected",
    }

    return {
        "requires_human_approval": True,

        "approval_status": "rejected",

        "approval_reason": reason,

        "approved": False,

        "trace": (
            state.get("trace", [])
            + [
                trace_entry,
                rejection_trace,
            ]
        ),

        "status": "human_rejected",

        "step_count": (
            state.get("step_count", 0) + 1
        ),
    }


# ============================================================
# EXECUTE
# ============================================================

def execute_node(state):

    approved = state.get(
        "approved",
        False
    )

    # --------------------------------------------------------
    # NEVER EXECUTE WITHOUT APPROVAL
    # --------------------------------------------------------

    if not approved:

        trace_entry = {
            "agent": "executor",
            "action": "execution_blocked",
            "reason": (
                "Human approval was not provided."
            ),
            "status": "blocked",
        }

        return {
            "trace": (
                state.get("trace", [])
                + [trace_entry]
            ),

            "execution_result": (
                "Execution blocked because "
                "human approval was not provided."
            ),

            "status": "execution_blocked",

            "step_count": (
                state.get("step_count", 0) + 1
            ),
        }

    # --------------------------------------------------------
    # SAFE DEMO EXECUTION
    # --------------------------------------------------------
    #
    # IMPORTANT:
    #
    # We intentionally do NOT perform a real production
    # rollback, deployment, restart, deletion, or
    # infrastructure mutation.
    #
    # This is a hackathon-safe execution simulation.
    #

    remediation = state.get(
        "proposed_action",
        {}
    )

    execution_result = (
        "Remediation approved by human "
        "and executed in SAFE DEMO MODE.\n\n"
        "Proposal:\n"
        f"{remediation.get('proposal', 'N/A')}"
    )

    trace_entry = {
        "agent": "executor",
        "action": "execute_remediation",
        "input": remediation,
        "reason": (
            "Human explicitly approved the "
            "proposed remediation."
        ),
        "status": "executed",
        "execution_mode": "safe_demo",
    }

    return {
        "execution_result": execution_result,

        "trace": (
            state.get("trace", [])
            + [trace_entry]
        ),

        "status": "remediation_executed",

        "step_count": (
            state.get("step_count", 0) + 1
        ),
    }


# ============================================================
# VERIFY
# ============================================================

def verify_node(state):

    execution_result = state.get(
        "execution_result",
        ""
    )

    verification_result = (
        "SAFE DEMO verification completed. "
        "The execution path completed successfully. "
        "No real production infrastructure was modified."
    )

    trace_entry = {
        "agent": "verification",
        "action": "verify_remediation",
        "input": {
            "execution_result": execution_result,
        },
        "reason": (
            "Verify the result of the approved "
            "remediation."
        ),
        "status": "success",
        "verification_mode": "safe_demo",
    }

    return {
        "verification_result": verification_result,

        "trace": (
            state.get("trace", [])
            + [trace_entry]
        ),

        "status": "verified",

        "step_count": (
            state.get("step_count", 0) + 1
        ),
    }


# ============================================================
# ROUTE AFTER TASK ROUTER
# ============================================================

def route_specialized_agent(state):

    # --------------------------------------------------------
    # STEP LIMIT
    # --------------------------------------------------------

    if state.get(
        "step_count",
        0
    ) >= MAX_STEPS:

        return "safe_stop"

    # --------------------------------------------------------
    # NO EXECUTABLE TASK
    # --------------------------------------------------------

    if state.get(
        "status"
    ) == "no_executable_task":

        return "safe_stop"

    # --------------------------------------------------------
    # CURRENT TASK
    # --------------------------------------------------------

    current_task_id = state.get(
        "current_task"
    )

    plan = state.get(
        "plan",
        []
    )

    task = next(
        (
            task
            for task in plan
            if task.get("id") == current_task_id
        ),
        None
    )

    if task is None:
        return "safe_stop"

    # --------------------------------------------------------
    # SPECIALIZED AGENT
    # --------------------------------------------------------

    agent = task.get(
        "agent"
    )

    if agent == "investigator":
        return "investigator"

    if agent == "executor":
        return "executor"

    if agent == "policy":
        return "policy"

    if agent == "critic":
        return "critic"

    return "safe_stop"


# ============================================================
# ROUTE AFTER SPECIALIZED AGENT
# ============================================================

def route_after_agent(state):

    # --------------------------------------------------------
    # STEP LIMIT
    # --------------------------------------------------------

    if state.get(
        "step_count",
        0
    ) >= MAX_STEPS:

        return "safe_stop"

    status = state.get(
        "status",
        ""
    )

    # ========================================================
    # CRITIC ACCEPTED
    # ========================================================

    if status == "critic_accepted":

        return "human_approval"

    # ========================================================
    # CRITIC REJECTED
    # ========================================================

    if status == "critic_rejected":

        replan_count = state.get(
            "replan_count",
            0
        )

        if replan_count >= MAX_REPLANS:

            return "safe_stop"

        return "replan"

    # ========================================================
    # HUMAN REJECTION
    # ========================================================

    if status == "human_rejected":

        return "safe_stop"

    # ========================================================
    # AGENT FAILURE
    # ========================================================

    if status in {
        "investigation_failed",
        "executor_failed",
        "policy_failed",
        "critic_failed",
    }:

        retry_count = state.get(
            "retry_count",
            0
        )

        if retry_count < MAX_RETRIES:

            return "retry"

        return "safe_stop"

    # ========================================================
    # NORMAL TASK COMPLETION
    # ========================================================

    if status in {
        "investigation_complete",
        "investigation_degraded",
        "remediation_proposed",
        "policy_evaluated",
    }:

        return "task_router"

    # ========================================================
    # RETRY STATE
    # ========================================================

    if status == "retrying":

        return "retry"

    # ========================================================
    # UNKNOWN STATE
    # ========================================================

    return "safe_stop"


# ============================================================
# ROUTE AFTER RETRY
# ============================================================

def route_after_retry(state):

    if state.get(
        "step_count",
        0
    ) >= MAX_STEPS:

        return "safe_stop"

    current_task_id = state.get(
        "current_task"
    )

    plan = state.get(
        "plan",
        []
    )

    task = next(
        (
            task
            for task in plan
            if task.get("id") == current_task_id
        ),
        None
    )

    if task is None:
        return "safe_stop"

    agent = task.get(
        "agent"
    )

    if agent in {
        "investigator",
        "executor",
        "policy",
        "critic",
    }:

        return agent

    return "safe_stop"


# ============================================================
# ROUTE AFTER HUMAN APPROVAL
# ============================================================

def route_after_approval(state):

    # --------------------------------------------------------
    # HUMAN APPROVED
    # --------------------------------------------------------

    if state.get(
        "approved",
        False
    ):

        return "execute"

    # --------------------------------------------------------
    # HUMAN REJECTED
    # --------------------------------------------------------

    return "safe_stop"


# ============================================================
# BUILD WORKFLOW
# ============================================================

def build_workflow(checkpointer=None):

    workflow = StateGraph(
        AgentState
    )

    # ========================================================
    # NODES
    # ========================================================

    workflow.add_node(
        "planner",
        planner_node
    )

    workflow.add_node(
        "replan",
        replan_node
    )

    workflow.add_node(
        "retry",
        retry_node
    )

    workflow.add_node(
        "task_router",
        task_router_node
    )

    workflow.add_node(
        "investigator",
        investigator_node
    )

    workflow.add_node(
        "executor",
        executor_node
    )

    workflow.add_node(
        "policy",
        policy_node
    )

    workflow.add_node(
        "critic",
        critic_node
    )

    workflow.add_node(
        "human_approval",
        human_approval_node
    )

    workflow.add_node(
        "execute",
        execute_node
    )

    workflow.add_node(
        "verify",
        verify_node
    )

    workflow.add_node(
        "safe_stop",
        safe_stop_node
    )

    # ========================================================
    # START
    # ========================================================

    workflow.add_edge(
        START,
        "planner"
    )

    # ========================================================
    # PLANNER → TASK ROUTER
    # ========================================================

    workflow.add_edge(
        "planner",
        "task_router"
    )

    # ========================================================
    # REPLAN → PLANNER
    # ========================================================

    workflow.add_edge(
        "replan",
        "planner"
    )

    # ========================================================
    # RETRY → SPECIALIZED AGENT
    # ========================================================

    workflow.add_conditional_edges(
        "retry",
        route_after_retry,
        {
            "investigator": "investigator",
            "executor": "executor",
            "policy": "policy",
            "critic": "critic",
            "safe_stop": "safe_stop",
        }
    )

    # ========================================================
    # TASK ROUTER → SPECIALIZED AGENT
    # ========================================================

    workflow.add_conditional_edges(
        "task_router",
        route_specialized_agent,
        {
            "investigator": "investigator",
            "executor": "executor",
            "policy": "policy",
            "critic": "critic",
            "safe_stop": "safe_stop",
        }
    )

    # ========================================================
    # SPECIALIZED AGENTS
    # ========================================================

    for agent_name in [
        "investigator",
        "executor",
        "policy",
        "critic",
    ]:

        workflow.add_conditional_edges(
            agent_name,
            route_after_agent,
            {
                "task_router": "task_router",

                "replan": "replan",

                "retry": "retry",

                "human_approval": "human_approval",

                "safe_stop": "safe_stop",
            }
        )

    # ========================================================
    # HUMAN APPROVAL
    # ========================================================

    workflow.add_conditional_edges(
        "human_approval",
        route_after_approval,
        {
            "execute": "execute",
            "safe_stop": "safe_stop",
        }
    )

    # ========================================================
    # EXECUTE → VERIFY
    # ========================================================

    workflow.add_edge(
        "execute",
        "verify"
    )

    # ========================================================
    # VERIFY → END
    # ========================================================

    workflow.add_edge(
        "verify",
        END
    )

    # ========================================================
    # SAFE STOP → END
    # ========================================================

    workflow.add_edge(
        "safe_stop",
        END
    )

    # ========================================================
    # COMPILE WITH CHECKPOINTER
    # ========================================================

    return workflow.compile(
        checkpointer=checkpointer
    )