# graph/state.py

from typing import TypedDict, List, Dict, Any


class AgentState(TypedDict, total=False):

    # ========================================================
    # INCIDENT INPUT
    # ========================================================

    user_request: str
    repository: str
    incident: str

    # ========================================================
    # PLANNING
    # ========================================================

    plan: List[Dict[str, Any]]

    current_task: int

    completed_tasks: List[int]

    # ========================================================
    # INVESTIGATION
    # ========================================================

    retrieved_context: List[str]

    sources: List[str]

    # ========================================================
    # TOOLS
    # ========================================================

    tool_calls: List[Dict[str, Any]]

    tool_results: List[Dict[str, Any]]

    # ========================================================
    # VALIDATION / POLICY
    # ========================================================

    validation_result: str

    validation_errors: List[str]

    policy_result: str

    # ========================================================
    # CRITIC
    # ========================================================

    critic_decision: str

    critic_feedback: str

    # ========================================================
    # RECOVERY
    # ========================================================

    retry_count: int

    replan_count: int

    # ========================================================
    # SAFETY LIMITS
    # ========================================================

    step_count: int

    max_steps: int

    # ========================================================
    # REMEDIATION
    # ========================================================

    proposed_action: Dict[str, Any]

    requires_human_approval: bool

    # ========================================================
    # HUMAN APPROVAL
    # ========================================================

    approval_status: str

    approval_reason: str

    approved: bool

    # ========================================================
    # EXECUTION
    # ========================================================

    execution_result: str

    verification_result: str

    # ========================================================
    # WORKFLOW
    # ========================================================

    status: str

    final_response: str

    # ========================================================
    # AUDIT TRACE
    # ========================================================

    trace: List[Dict[str, Any]]