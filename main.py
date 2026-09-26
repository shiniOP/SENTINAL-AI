# main.py

from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver

from graph.workflow import build_workflow


# ============================================================
# INITIAL INCIDENT STATE
# ============================================================

initial_state = {
    # --------------------------------------------------------
    # User request / incident context
    # --------------------------------------------------------
    "user_request": (
        "Our payment service started experiencing failures "
        "after a recent deployment. Investigate what changed, "
        "determine the likely cause, prepare a remediation action, "
        "check whether the proposed remediation complies with "
        "company policy, validate the remediation before execution, "
        "and do not perform any irreversible action without human approval."
    ),

    "repository": "kubernetes/kubernetes",

    "incident": (
        "Payment service failures were reported after a recent deployment."
    ),

    # --------------------------------------------------------
    # Planning
    # --------------------------------------------------------
    "plan": [],
    "current_task": 0,
    "completed_tasks": [],

    # --------------------------------------------------------
    # Investigation / evidence
    # --------------------------------------------------------
    "retrieved_context": [],
    "sources": [],

    # --------------------------------------------------------
    # Tool usage
    # --------------------------------------------------------
    "tool_calls": [],
    "tool_results": [],

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------
    "validation_result": "",
    "validation_errors": [],

    "policy_result": "",
    "critic_decision": "",
    "critic_feedback": "",

    # --------------------------------------------------------
    # Recovery
    # --------------------------------------------------------
    "retry_count": 0,
    "replan_count": 0,

    # --------------------------------------------------------
    # Safety limits
    # --------------------------------------------------------
    "step_count": 0,
    "max_steps": 30,

    # --------------------------------------------------------
    # Proposed remediation
    # --------------------------------------------------------
    "proposed_action": {},

    # --------------------------------------------------------
    # Human approval
    # --------------------------------------------------------
    "requires_human_approval": False,
    "approved": False,
    "approval_status": "",
    "approval_reason": "",

    # --------------------------------------------------------
    # Execution / verification
    # --------------------------------------------------------
    "execution_result": "",
    "verification_result": "",

    # --------------------------------------------------------
    # Workflow
    # --------------------------------------------------------
    "status": "starting",
    "final_response": "",

    # --------------------------------------------------------
    # Human-auditable trace
    # --------------------------------------------------------
    "trace": [],
}


# ============================================================
# DISPLAY HELPERS
# ============================================================

def print_separator(title=""):
    print("\n" + "=" * 80)

    if title:
        print(f" {title}")

    print("=" * 80)


def print_trace(trace):
    print_separator("AUDIT TRACE")

    if not trace:
        print("No trace entries.")
        return

    for index, entry in enumerate(trace, start=1):

        agent = entry.get("agent", "unknown")
        action = entry.get("action", "unknown")
        status = entry.get("status", "")
        reason = entry.get("reason", "")

        print(f"\n[{index}] {agent}")
        print(f"    Action : {action}")

        if status:
            print(f"    Status : {status}")

        if reason:
            print(f"    Why    : {reason}")

        if "input" in entry:
            print(f"    Input  : {entry['input']}")

        if "output" in entry:
            print(f"    Output : {entry['output']}")


def print_plan(plan):
    print_separator("EXECUTION PLAN")

    if not plan:
        print("No plan generated.")
        return

    for task in plan:

        task_id = task.get("id")
        agent = task.get("agent")
        description = task.get("description")
        depends_on = task.get("depends_on", [])
        tool = task.get("tool")

        print(f"\nTask {task_id}")
        print(f"  Agent       : {agent}")
        print(f"  Description : {description}")
        print(f"  Depends on  : {depends_on}")

        if tool:
            print(f"  Tool        : {tool}")


def print_evidence(state):
    print_separator("INVESTIGATION EVIDENCE")

    context = state.get("retrieved_context", [])

    if not context:
        print("No investigation context available.")
    else:
        for index, item in enumerate(context, start=1):
            print(f"\nEvidence {index}:")
            print(item)

    sources = state.get("sources", [])

    print("\nSources:")

    if not sources:
        print("  None")

    for source in sources:
        print(f"  - {source}")


def print_tool_results(state):
    print_separator("TOOL RESULTS")

    results = state.get("tool_results", [])

    if not results:
        print("No external tool results.")
        return

    for index, result in enumerate(results, start=1):

        print(f"\nTool Result {index}")

        if isinstance(result, dict):

            for key, value in result.items():
                print(f"  {key}: {value}")

        else:
            print(f"  {result}")


def print_policy(state):
    print_separator("POLICY REVIEW")

    policy = state.get("policy_result", "")

    if policy:
        print(policy)
    else:
        print("No policy result available.")


def print_proposal(state):
    print_separator("REMEDIATION PROPOSAL")

    proposal = state.get("proposed_action", {})

    if not proposal:
        print("No remediation proposal generated.")
        return

    for key, value in proposal.items():
        print(f"{key}: {value}")


def print_critic(state):
    print_separator("CRITIC REVIEW")

    decision = state.get("critic_decision", "")
    feedback = state.get("critic_feedback", "")

    print(f"Decision: {decision}")

    if feedback:
        print("\nFeedback:")
        print(feedback)


def print_approval(state):
    print_separator("HUMAN APPROVAL")

    status = state.get("approval_status", "")
    reason = state.get("approval_reason", "")
    approved = state.get("approved", False)

    print(f"Required : {state.get('requires_human_approval', False)}")
    print(f"Status   : {status}")
    print(f"Approved : {approved}")

    if reason:
        print(f"Reason   : {reason}")


def print_execution(state):
    print_separator("EXECUTION")

    execution = state.get("execution_result", "")

    if execution:
        print(execution)
    else:
        print("No execution result.")


def print_verification(state):
    print_separator("VERIFICATION")

    verification = state.get("verification_result", "")

    if verification:
        print(verification)
    else:
        print("No verification result.")


def print_metrics(state):
    print_separator("SAFETY / WORKFLOW METRICS")

    print(f"Workflow status : {state.get('status')}")
    print(f"Workflow steps  : {state.get('step_count', 0)}")
    print(f"Max steps       : {state.get('max_steps', 30)}")
    print(f"Retries         : {state.get('retry_count', 0)}")
    print(f"Replans         : {state.get('replan_count', 0)}")


def print_summary(state):
    print_separator("FINAL SUMMARY")

    final_response = state.get("final_response", "")

    if final_response:
        print(final_response)
        return

    status = state.get("status", "unknown")

    print(f"Final workflow status: {status}")

    critic_decision = state.get("critic_decision")

    if critic_decision:
        print(f"Critic decision: {critic_decision}")

    approval_status = state.get("approval_status")

    if approval_status:
        print(f"Human approval: {approval_status}")

    execution_result = state.get("execution_result")

    if execution_result:
        print(f"Execution: {execution_result}")

    verification_result = state.get("verification_result")

    if verification_result:
        print(f"Verification: {verification_result}")


# ============================================================
# HUMAN APPROVAL
# ============================================================

def handle_interrupt(interrupt_data):
    """
    Display the human approval request generated by LangGraph.
    """

    print_separator("⚠ HUMAN APPROVAL REQUIRED")

    print("The system has prepared a potentially sensitive action.")
    print("The action has NOT been executed.")

    if isinstance(interrupt_data, dict):

        approval_payload = interrupt_data.get(
            "approval_payload",
            interrupt_data
        )

        print("\nApproval request:")

        if isinstance(approval_payload, dict):

            for key, value in approval_payload.items():
                print(f"\n{key}:")
                print(value)

        else:
            print(approval_payload)

        trace_entry = interrupt_data.get("trace_entry")

        if trace_entry:
            print("\nAudit information:")
            print(f"Agent  : {trace_entry.get('agent')}")
            print(f"Action : {trace_entry.get('action')}")
            print(f"Why    : {trace_entry.get('reason')}")

    else:
        print(interrupt_data)

    print("\n" + "-" * 80)

    while True:

        choice = input(
            "\nApprove this action? [y/n]: "
        ).strip().lower()

        if choice in ("y", "yes"):

            reason = input(
                "Approval reason (optional): "
            ).strip()

            return {
                "approved": True,
                "reason": reason or "Human approved the proposed action."
            }

        if choice in ("n", "no"):

            reason = input(
                "Rejection reason (optional): "
            ).strip()

            return {
                "approved": False,
                "reason": reason or "Human rejected the proposed action."
            }

        print("Please enter y or n.")


# ============================================================
# MAIN WORKFLOW
# ============================================================

def main():

    print_separator("AI INCIDENT RESOLUTION MULTI-AGENT SYSTEM")

    print("\nStarting workflow...")
    print("Mode: SAFE DEMO")
    print("External tool: GitHub API")
    print("Human approval: ENABLED")

    # --------------------------------------------------------
    # MemorySaver gives LangGraph a checkpoint for the
    # interrupt/resume cycle.
    # --------------------------------------------------------

    checkpointer = MemorySaver()

    # --------------------------------------------------------
    # Build workflow
    # --------------------------------------------------------

    graph = build_workflow(
        checkpointer=checkpointer
    )

    # --------------------------------------------------------
    # LangGraph thread configuration
    # --------------------------------------------------------

    config = {
        "configurable": {
            "thread_id": "incident-demo-001"
        },

        # Prevent runaway graph execution.
        "recursion_limit": 100,
    }

    # --------------------------------------------------------
    # First execution
    # --------------------------------------------------------

    print_separator("WORKFLOW START")

    result = graph.invoke(
        initial_state,
        config=config
    )

    # --------------------------------------------------------
    # Interrupt / Resume loop
    #
    # LangGraph returns "__interrupt__" when the workflow
    # reaches the human approval node.
    # --------------------------------------------------------

    while "__interrupt__" in result:

        interrupts = result.get(
            "__interrupt__",
            []
        )

        if not interrupts:
            break

        # Usually there will be one interrupt.
        interrupt_object = interrupts[0]

        # LangGraph interrupt objects normally expose the
        # payload through `.value`.
        if hasattr(interrupt_object, "value"):
            interrupt_data = interrupt_object.value
        else:
            interrupt_data = interrupt_object

        # Ask the human.
        resume_value = handle_interrupt(
            interrupt_data
        )

        print_separator("RESUMING WORKFLOW")

        # Resume the exact same thread/checkpoint.
        result = graph.invoke(
            Command(
                resume=resume_value
            ),
            config=config
        )

    # --------------------------------------------------------
    # Final workflow state
    # --------------------------------------------------------

    state = result

    # --------------------------------------------------------
    # Print complete human-auditable output
    # --------------------------------------------------------

    print_metrics(state)

    print_plan(
        state.get("plan", [])
    )

    print_evidence(state)

    print_tool_results(state)

    print_policy(state)

    print_proposal(state)

    print_critic(state)

    print_approval(state)

    print_execution(state)

    print_verification(state)

    print_trace(
        state.get("trace", [])
    )

    print_summary(state)

    print_separator("WORKFLOW COMPLETE")


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()