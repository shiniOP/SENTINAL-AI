# app.py

import uuid
import json

import streamlit as st

from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver

from graph.workflow import build_workflow



# ============================================================
# AGENT EVALUATION / OBSERVABILITY HELPERS
# ============================================================

def _trace_entries(result, agent=None):
    trace = result.get("trace", []) if isinstance(result, dict) else []
    if agent is None:
        return trace
    return [
        entry for entry in trace
        if str(entry.get("agent", "")).lower() == agent
    ]


def _successful_entries(entries):
    success_states = {
        "success",
        "successful",
        "completed",
        "executed",
        "verified",
        "accepted",
        "approved",
        "created",
    }
    return [
        entry for entry in entries
        if str(entry.get("status", "")).lower() in success_states
    ]


def evaluate_agent(result, agent):
    """
    Produce auditable, rule-based evaluation signals.

    These are NOT fabricated accuracy scores. Each score is the
    number of observable checks passed by the agent.
    """
    plan = result.get("plan", []) or []
    completed = set(result.get("completed_tasks", []) or [])
    evidence = result.get("retrieved_context", []) or []
    tool_results = result.get("tool_results", []) or []
    proposed = result.get("proposed_action", {}) or {}
    policy = result.get("policy_result", "") or result.get(
        "validation_result", ""
    )
    critic_decision = str(
        result.get("critic_decision", "")
    ).upper()
    critic_feedback = result.get("critic_feedback", "")
    approved = bool(result.get("approved", False))
    verification = result.get("verification_result", "")
    trace = result.get("trace", []) or []

    checks = []

    if agent == "planner":
        valid_agents = {
            "investigator",
            "executor",
            "policy",
            "critic",
        }
        checks.append((
            "Plan generated",
            bool(plan),
        ))
        checks.append((
            "Specialised agents valid",
            bool(plan) and all(
                task.get("agent") in valid_agents
                for task in plan
            ),
        ))
        checks.append((
            "Task dependencies valid",
            bool(plan) and all(
                all(
                    dep in {
                        task.get("id")
                        for task in plan
                    }
                    for dep in task.get("depends_on", [])
                )
                for task in plan
            ),
        ))
        checks.append((
            "Delegation rationale present",
            bool(plan) and all(
                bool(task.get("reason"))
                for task in plan
            ),
        ))

    elif agent == "investigator":
        inv_entries = _trace_entries(result, "investigator")
        successful_tool = any(
            isinstance(item, dict) and item.get("success") is True
            for item in tool_results
        )
        checks.append((
            "Investigation trace recorded",
            bool(inv_entries),
        ))
        checks.append((
            "Evidence collected",
            bool(evidence),
        ))
        checks.append((
            "External tool response validated",
            successful_tool or not tool_results,
        ))
        checks.append((
            "Investigation task completed",
            any(
                entry.get("action") in {
                    "get_recent_commits",
                    "analyze_existing_evidence",
                }
                and str(entry.get("status", "")).lower()
                in {"success", "completed"}
                for entry in inv_entries
            ) or bool(evidence),
        ))
        checks.append((
            "No fabricated evidence signal",
            not any(
                "fabricat" in str(entry).lower()
                for entry in inv_entries
            ),
        ))

    elif agent == "executor":
        executor_entries = _trace_entries(result, "executor")
        checks.append((
            "Remediation proposal generated",
            bool(proposed.get("proposal")),
        ))
        checks.append((
            "Human approval required",
            proposed.get("requires_human_approval") is True,
        ))
        checks.append((
            "Execution not claimed during proposal",
            proposed.get("executed") is not True,
        ))
        checks.append((
            "Executor trace recorded",
            bool(executor_entries),
        ))
        checks.append((
            "Proposal task completed",
            any(
                entry.get("action") == "prepare_remediation"
                and str(entry.get("status", "")).lower()
                in {"success", "completed"}
                for entry in executor_entries
            ) or bool(proposed),
        ))

    elif agent == "policy":
        policy_entries = _trace_entries(result, "policy")
        policy_text = str(policy)
        checks.append((
            "Policy evaluation generated",
            bool(policy_text.strip()),
        ))
        checks.append((
            "Policy agent trace recorded",
            bool(policy_entries),
        ))
        checks.append((
            "Remediation was available for review",
            bool(proposed),
        ))
        checks.append((
            "Policy decision present",
            any(
                marker in policy_text.upper()
                for marker in (
                    "POLICY_DECISION:",
                    "APPROVE",
                    "REJECT",
                    "CONDITIONAL",
                )
            ),
        ))

    elif agent == "critic":
        critic_entries = _trace_entries(result, "critic")
        checks.append((
            "Critic trace recorded",
            bool(critic_entries),
        ))
        checks.append((
            "Explicit decision produced",
            critic_decision in {"ACCEPT", "REJECT"},
        ))
        checks.append((
            "Feedback provided",
            bool(str(critic_feedback).strip()),
        ))
        checks.append((
            "Proposal reviewed",
            bool(proposed),
        ))

    elif agent == "human":
        checks.append((
            "Approval checkpoint reached",
            bool(
                result.get("requires_human_approval")
                or result.get("approval_status")
                or result.get("__interrupt__")
            ),
        ))
        checks.append((
            "Human decision recorded",
            bool(result.get("approval_status")),
        ))
        checks.append((
            "Decision is explicit",
            result.get("approved") in {True, False},
        ))

    elif agent == "verification":
        checks.append((
            "Verification result generated",
            bool(str(verification).strip()),
        ))
        checks.append((
            "Verification trace recorded",
            bool(_trace_entries(result, "verification")),
        ))

    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)

    return {
        "passed": passed,
        "total": total,
        "checks": checks,
    }


def system_evaluation(result):
    trace = result.get("trace", []) or []
    tool_results = result.get("tool_results", []) or []
    evidence = result.get("retrieved_context", []) or []

    tool_attempts = len(tool_results)
    tool_successes = sum(
        1 for item in tool_results
        if isinstance(item, dict) and item.get("success") is True
    )

    failed_trace = sum(
        1 for entry in trace
        if str(entry.get("status", "")).lower()
        in {
            "failed",
            "failure",
            "error",
            "blocked",
        }
    )

    execution_without_approval = any(
        entry.get("action") == "execute_remediation"
        and not bool(result.get("approved", False))
        for entry in trace
    )

    return {
        "agent_actions": len(trace),
        "successful_actions": len(_successful_entries(trace)),
        "failed_actions": failed_trace,
        "tool_attempts": tool_attempts,
        "tool_success_rate": (
            f"{(tool_successes / tool_attempts) * 100:.0f}%"
            if tool_attempts
            else "N/A"
        ),
        "evidence_items": len(evidence),
        "completed_tasks": len(
            result.get("completed_tasks", []) or []
        ),
        "total_tasks": len(result.get("plan", []) or []),
        "retries": result.get("retry_count", 0),
        "replans": result.get("replan_count", 0),
        "steps": result.get("step_count", 0),
        "max_steps": result.get("max_steps", 40),
        "safety_violations": int(execution_without_approval),
    }


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Sentinel AI",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================
# CUSTOM CSS / HTML
# ============================================================

st.html(
    """
    <style>

    /* =========================
       GLOBAL
       ========================= */

    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
        max-width: 1450px;
    }

    /* =========================
       HERO
       ========================= */

    .sentinel-hero {
        padding: 28px 32px;
        border-radius: 20px;
        margin-bottom: 22px;
        background:
            linear-gradient(
                135deg,
                rgba(15, 23, 42, 0.98),
                rgba(30, 41, 59, 0.96)
            );
        border: 1px solid rgba(148, 163, 184, 0.22);
        box-shadow:
            0 15px 40px rgba(0, 0, 0, 0.18);
    }

    .sentinel-title {
        font-size: 38px;
        font-weight: 800;
        letter-spacing: -1px;
        color: white;
        margin-bottom: 6px;
    }

    .sentinel-subtitle {
        color: #cbd5e1;
        font-size: 16px;
        line-height: 1.6;
        max-width: 850px;
    }

    .sentinel-badge {
        display: inline-block;
        margin-top: 15px;
        padding: 6px 12px;
        border-radius: 999px;
        background: rgba(34, 197, 94, 0.12);
        border: 1px solid rgba(34, 197, 94, 0.35);
        color: #86efac;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.5px;
    }

    /* =========================
       PIPELINE
       ========================= */

    .pipeline {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        align-items: center;
        margin: 10px 0 25px 0;
    }

    .pipeline-item {
        padding: 8px 13px;
        border-radius: 10px;
        background: rgba(51, 65, 85, 0.75);
        border: 1px solid rgba(148, 163, 184, 0.2);
        color: #e2e8f0;
        font-size: 13px;
        font-weight: 600;
    }

    .pipeline-arrow {
        color: #64748b;
        font-size: 16px;
    }

    /* =========================
       SECTION CARDS
       ========================= */

    .section-label {
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #64748b;
        font-weight: 700;
        margin-bottom: 5px;
    }

    .section-title {
        font-size: 24px;
        font-weight: 750;
        margin-bottom: 12px;
    }

    /* =========================
       METRIC CARDS
       ========================= */

    .metric-card {
        padding: 17px;
        border-radius: 14px;
        border: 1px solid rgba(148, 163, 184, 0.20);
        background: rgba(15, 23, 42, 0.035);
    }

    .metric-title {
        font-size: 12px;
        color: #64748b;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.7px;
    }

    .metric-value {
        font-size: 27px;
        font-weight: 800;
        margin-top: 4px;
    }

    /* =========================
       TRACE
       ========================= */

    .trace-card {
        padding: 14px 16px;
        margin-bottom: 9px;
        border-radius: 12px;
        border: 1px solid rgba(148, 163, 184, 0.18);
        background: rgba(248, 250, 252, 0.7);
    }

    .trace-agent {
        font-weight: 800;
        font-size: 14px;
    }

    .trace-action {
        color: #475569;
        font-size: 13px;
        margin-top: 3px;
    }

    .trace-reason {
        color: #64748b;
        font-size: 12px;
        margin-top: 7px;
        line-height: 1.5;
    }

    /* =========================
       AGENT EVALUATION
       ========================= */

    .eval-card {
        padding: 15px 16px;
        border-radius: 14px;
        border: 1px solid rgba(148, 163, 184, 0.20);
        background: rgba(15, 23, 42, 0.035);
        margin-bottom: 8px;
    }

    .eval-agent {
        font-size: 15px;
        font-weight: 800;
    }

    .eval-score {
        color: #16a34a;
        font-weight: 800;
        font-size: 13px;
    }

    .eval-muted {
        color: #64748b;
        font-size: 12px;
    }

    .eval-check {
        padding: 5px 0;
        font-size: 13px;
    }

    /* =========================
       APPROVAL
       ========================= */

    .approval-card {
        padding: 22px;
        border-radius: 16px;
        border: 1px solid rgba(245, 158, 11, 0.45);
        background: rgba(245, 158, 11, 0.08);
        margin: 15px 0;
    }

    .approval-title {
        font-size: 20px;
        font-weight: 800;
        margin-bottom: 7px;
    }

    .approval-text {
        color: #92400e;
        line-height: 1.5;
    }

    /* =========================
       SIDEBAR
       ========================= */

    [data-testid="stSidebar"] {
        border-right: 1px solid rgba(148, 163, 184, 0.18);
    }

    </style>
    """
)


# ============================================================
# HERO
# ============================================================

st.html(
    """
    <div class="sentinel-hero">

        <div class="sentinel-title">
            🛡️ Sentinel AI
        </div>

        <div class="sentinel-subtitle">
            Multi-Agent Enterprise Incident Resolution System
            with dynamic planning, delegation, external tools,
            policy validation, critic-based recovery and
            human-in-the-loop execution.
        </div>

        <div class="sentinel-badge">
            ● SAFE DEMO MODE
        </div>

    </div>

    <div class="pipeline">

        <div class="pipeline-item">🧠 Planner</div>
        <div class="pipeline-arrow">→</div>

        <div class="pipeline-item">🔀 Router</div>
        <div class="pipeline-arrow">→</div>

        <div class="pipeline-item">🔎 Investigator</div>
        <div class="pipeline-arrow">→</div>

        <div class="pipeline-item">⚙️ Executor</div>
        <div class="pipeline-arrow">→</div>

        <div class="pipeline-item">🛡️ Policy</div>
        <div class="pipeline-arrow">→</div>

        <div class="pipeline-item">🧐 Critic</div>
        <div class="pipeline-arrow">→</div>

        <div class="pipeline-item">👤 Human Approval</div>
        <div class="pipeline-arrow">→</div>

        <div class="pipeline-item">✅ Verify</div>

    </div>
    """
)


# ============================================================
# DEFAULT VALUES
# ============================================================

DEFAULT_REPOSITORY = "kubernetes/kubernetes"

DEFAULT_INCIDENT = """
Our payment service started experiencing failures
after a recent deployment.

Investigate what changed, determine the likely cause,
prepare a remediation action, check whether the proposed
remediation complies with company policy, and validate
the remediation before execution.

Do not perform any irreversible action without human approval.
"""

DEFAULT_USER_REQUEST = """
Investigate the incident, determine the likely cause,
prepare a safe remediation proposal, validate it against
company policy, and require human approval before execution.
"""


# ============================================================
# COMPANY POLICY
# ============================================================

COMPANY_POLICY = """
COMPANY INCIDENT-RESPONSE POLICY

1. Production changes require explicit human approval.

2. Irreversible or potentially destructive actions must
   never execute automatically.

3. Remediation must be supported by available evidence.
   Agents must not invent logs, metrics, telemetry,
   deployment state, or root causes.

4. If evidence is insufficient, the system should prefer
   diagnostic or read-only actions.

5. Every remediation proposal should identify:
   - target component
   - proposed action
   - expected benefit
   - risks
   - reversibility
   - side effects
   - verification steps

6. Security-sensitive changes require human review.

7. Dependency changes affecting production require human
   approval before execution.

8. Proposed changes should preferably be reversible.

9. The Critic must reject proposals that conflict with
   Policy requirements.

10. Agents must never claim that a remediation was executed
    before the execution stage.

11. Execution happens only after:
    investigation → remediation proposal → policy evaluation
    → critic validation → human approval.

12. If required information is missing, the system should
    explicitly identify the missing information rather than
    fabricate it.
"""


# ============================================================
# SESSION STATE
# ============================================================

if "workflow" not in st.session_state:

    checkpointer = MemorySaver()

    st.session_state.workflow = build_workflow(
        checkpointer=checkpointer
    )


if "run_result" not in st.session_state:
    st.session_state.run_result = None


if "approval_data" not in st.session_state:
    st.session_state.approval_data = None


if "thread_id" not in st.session_state:
    st.session_state.thread_id = None


if "running" not in st.session_state:
    st.session_state.running = False


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown("## ⚙️ Incident Configuration")

    st.caption(
        "Configure the incident and repository used by "
        "the multi-agent system."
    )

    repository = st.text_input(
        "GitHub Repository",
        value=DEFAULT_REPOSITORY,
        help=(
            "Accepts owner/repository or a GitHub repository URL."
        )
    )

    incident = st.text_area(
        "Incident",
        value=DEFAULT_INCIDENT.strip(),
        height=180
    )

    user_request = st.text_area(
        "User Request",
        value=DEFAULT_USER_REQUEST.strip(),
        height=150
    )

    st.divider()

    st.markdown("### 🛡️ Company Policy")

    st.caption(
        "These are the demo policies used by the Policy "
        "Agent's evaluation logic."
    )

    st.text_area(
        "Active Policy",
        value=COMPANY_POLICY.strip(),
        height=330,
        disabled=True
    )

    st.divider()

    st.markdown("### 🔒 Safety Controls")

    st.success("SAFE DEMO MODE")

    st.caption(
        "The Executor does not modify real production "
        "infrastructure."
    )

    st.caption(
        "Human approval is required before the execution stage."
    )

    st.divider()

    st.markdown("### 🤖 Agents")

    st.markdown(
        """
        **🧠 Planner**  
        Dynamically creates the task graph.

        **🔎 Investigator**  
        Uses GitHub as an external evidence source.

        **⚙️ Executor**  
        Prepares remediation but does not execute it.

        **🛡️ Policy**  
        Evaluates remediation against policy.

        **🧐 Critic**  
        Independently validates the proposal.

        **👤 Human**  
        Approves or rejects sensitive execution.
        """
    )


# ============================================================
# RUN SYSTEM
# ============================================================

st.markdown(
    '<div class="section-label">CONTROL CENTER</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="section-title">Incident Resolution</div>',
    unsafe_allow_html=True
)


run_col1, run_col2 = st.columns(
    [4, 1]
)


with run_col1:

    st.info(
        "The Planner will dynamically decompose the incident "
        "and delegate tasks to specialised agents."
    )


with run_col2:

    run_button = st.button(
        "🚀 Run System",
        type="primary",
        use_container_width=True
    )


# ============================================================
# RUN WORKFLOW
# ============================================================

if run_button:

    # --------------------------------------------------------
    # NEW THREAD
    # --------------------------------------------------------

    thread_id = (
        "incident-"
        + uuid.uuid4().hex[:12]
    )

    st.session_state.thread_id = thread_id

    st.session_state.approval_data = None

    st.session_state.run_result = None

    st.session_state.running = True


    # --------------------------------------------------------
    # INITIAL STATE
    # --------------------------------------------------------

    initial_state = {

        "user_request": user_request,

        "repository": repository,

        "incident": incident,

        "plan": [],

        "current_task": None,

        "completed_tasks": [],

        "retrieved_context": [],

        "sources": [],

        "tool_calls": [],

        "tool_results": [],

        "validation_result": "",

        "validation_errors": [],

        "policy_result": "",

        "critic_decision": "",

        "critic_feedback": "",

        "retry_count": 0,

        "replan_count": 0,

        "step_count": 0,

        "max_steps": 40,

        "proposed_action": {},

        "requires_human_approval": False,

        "approval_status": "",

        "approval_reason": "",

        "approved": False,

        "execution_result": "",

        "verification_result": "",

        "status": "starting",

        "final_response": "",

        "trace": []
    }


    config = {

        "configurable": {
            "thread_id": thread_id
        },

        "recursion_limit": 100
    }


    # --------------------------------------------------------
    # EXECUTE GRAPH
    # --------------------------------------------------------

    try:

        with st.status(
            "🚀 Running multi-agent system...",
            expanded=True
        ) as status:

            st.write(
                "🧠 Planner is creating the task graph..."
            )

            result = (
                st.session_state.workflow.invoke(
                    initial_state,
                    config=config
                )
            )

            # ----------------------------------------------
            # CHECK FOR LANGGRAPH INTERRUPT
            # ----------------------------------------------

            interrupts = result.get(
                "__interrupt__",
                []
            )

            if interrupts:

                interrupt_object = interrupts[0]

                if hasattr(
                    interrupt_object,
                    "value"
                ):
                    interrupt_value = (
                        interrupt_object.value
                    )

                else:
                    interrupt_value = (
                        interrupt_object
                    )


                st.session_state.approval_data = {
                    "thread_id": thread_id,
                    "payload": interrupt_value
                }


                st.session_state.run_result = result


                status.update(
                    label="⏸️ Waiting for human approval",
                    state="running",
                    expanded=True
                )

            else:

                st.session_state.run_result = result

                status.update(
                    label="✅ Workflow completed",
                    state="complete",
                    expanded=False
                )

    except Exception as error:

        st.session_state.running = False

        st.session_state.run_result = None

        st.error(
            f"❌ Workflow error: {error}"
        )


# ============================================================
# CURRENT RESULT
# ============================================================

result = st.session_state.get(
    "run_result"
)


if result:

    st.divider()

    # ========================================================
    # METRICS
    # ========================================================

    st.markdown(
        '<div class="section-label">SYSTEM METRICS</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="section-title">Recovery & Execution Metrics</div>',
        unsafe_allow_html=True
    )


    metric1, metric2, metric3, metric4, metric5 = st.columns(5)


    with metric1:

        st.metric(
            "Workflow Steps",
            result.get(
                "step_count",
                0
            )
        )


    with metric2:

        st.metric(
            "Retries",
            result.get(
                "retry_count",
                0
            )
        )


    with metric3:

        st.metric(
            "Replans",
            result.get(
                "replan_count",
                0
            )
        )


    with metric4:

        st.metric(
            "Tasks",
            len(
                result.get(
                    "plan",
                    []
                )
            )
        )


    with metric5:

        st.metric(
            "Completed",
            len(
                result.get(
                    "completed_tasks",
                    []
                )
            )
        )


    # ========================================================
    # STATUS
    # ========================================================

    status = result.get(
        "status",
        "unknown"
    )


    st.markdown("### Current Status")

    if status in {
        "verified",
        "remediation_executed"
    }:

        st.success(
            f"✅ {status}"
        )

    elif status in {
        "awaiting_human_approval",
        "human_approval_required"
    }:

        st.warning(
            f"⏸️ {status}"
        )

    elif status in {
        "safe_stopped",
        "critic_rejected"
    }:

        st.error(
            f"🛑 {status}"
        )

    else:

        st.info(
            f"ℹ️ {status}"
        )


    # ========================================================
    # HUMAN APPROVAL
    # ========================================================

    approval_data = (
        st.session_state.get(
            "approval_data"
        )
    )


    if approval_data:

        st.divider()

        st.html(
            """
            <div class="approval-card">

                <div class="approval-title">
                    👤 Human Approval Required
                </div>

                <div class="approval-text">
                    The Critic accepted the proposed remediation.
                    Execution is paused until a human explicitly
                    approves or rejects the action.
                </div>

            </div>
            """
        )


        payload = approval_data.get(
            "payload",
            {}
        )


        # ----------------------------------------------------
        # APPROVAL INFORMATION
        # ----------------------------------------------------

        if isinstance(
            payload,
            dict
        ):

            proposed_action = payload.get(
                "proposed_action",
                {}
            )

            policy_evaluation = payload.get(
                "policy_evaluation",
                ""
            )

            critic_feedback = payload.get(
                "critic_feedback",
                ""
            )

            risks = payload.get(
                "risks",
                "Not specified."
            )

            reversible = payload.get(
                "reversible",
                "Unknown"
            )


            with st.expander(
                "🔎 Review Proposed Remediation",
                expanded=True
            ):

                st.markdown(
                    "#### Proposed Action"
                )

                if proposed_action:

                    proposal_text = (
                        proposed_action.get(
                            "proposal",
                            "No proposal available."
                        )
                    )

                    st.write(
                        proposal_text
                    )

                else:

                    st.write(
                        "No proposed action available."
                    )


                st.markdown(
                    "#### Policy Evaluation"
                )

                st.write(
                    policy_evaluation
                )


                st.markdown(
                    "#### Critic Validation"
                )

                st.write(
                    critic_feedback
                )


                st.markdown(
                    "#### Risks"
                )

                st.write(
                    risks
                )


                st.markdown(
                    "#### Reversible"
                )

                st.write(
                    str(reversible)
                )


        # ----------------------------------------------------
        # APPROVAL BUTTONS
        # ----------------------------------------------------

        st.markdown(
            "### Decision"
        )

        approve_col, reject_col = st.columns(
            2
        )


        with approve_col:

            approve_button = st.button(
                "✅ Approve & Continue",
                type="primary",
                use_container_width=True
            )


        with reject_col:

            reject_button = st.button(
                "❌ Reject & Stop",
                use_container_width=True
            )


        # ----------------------------------------------------
        # APPROVE
        # ----------------------------------------------------

        if approve_button:

            thread_id = (
                approval_data[
                    "thread_id"
                ]
            )


            config = {

                "configurable": {
                    "thread_id": thread_id
                },

                "recursion_limit": 100
            }


            resume_payload = {

                "approved": True,

                "reason": (
                    "Approved by human operator."
                )
            }


            try:

                with st.status(
                    "▶️ Resuming approved workflow...",
                    expanded=True
                ):

                    resumed_result = (
                        st.session_state.workflow.invoke(
                            Command(
                                resume=resume_payload
                            ),
                            config=config
                        )
                    )


                st.session_state.run_result = (
                    resumed_result
                )

                st.session_state.approval_data = None

                st.success(
                    "✅ Human approval recorded. "
                    "Workflow resumed."
                )

                st.rerun()


            except Exception as error:

                st.error(
                    f"❌ Could not resume workflow: {error}"
                )


        # ----------------------------------------------------
        # REJECT
        # ----------------------------------------------------

        if reject_button:

            thread_id = (
                approval_data[
                    "thread_id"
                ]
            )


            config = {

                "configurable": {
                    "thread_id": thread_id
                },

                "recursion_limit": 100
            }


            resume_payload = {

                "approved": False,

                "reason": (
                    "Rejected by human operator."
                )
            }


            try:

                with st.status(
                    "🛑 Rejecting remediation...",
                    expanded=True
                ):

                    resumed_result = (
                        st.session_state.workflow.invoke(
                            Command(
                                resume=resume_payload
                            ),
                            config=config
                        )
                    )


                st.session_state.run_result = (
                    resumed_result
                )

                st.session_state.approval_data = None

                st.warning(
                    "🛑 Remediation rejected. "
                    "Workflow stopped safely."
                )

                st.rerun()


            except Exception as error:

                st.error(
                    f"❌ Could not reject workflow: {error}"
                )


    # ========================================================
    # GENERATED PLAN
    # ========================================================

    st.divider()

    st.markdown(
        '<div class="section-label">PLANNING</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="section-title">🧠 Dynamic Execution Plan</div>',
        unsafe_allow_html=True
    )


    plan = result.get(
        "plan",
        []
    )


    if not plan:

        st.info(
            "No plan generated."
        )

    else:

        for task in plan:

            task_id = task.get(
                "id",
                "?"
            )

            agent = task.get(
                "agent",
                "unknown"
            )

            description = task.get(
                "description",
                ""
            )

            reason = task.get(
                "reason",
                ""
            )

            dependencies = task.get(
                "depends_on",
                []
            )

            tool = task.get(
                "tool",
                ""
            )

            requires_tool = task.get(
                "requires_tool",
                False
            )


            with st.expander(
                f"Task {task_id} · {agent.upper()}",
                expanded=False
            ):

                st.write(
                    f"**Description:** {description}"
                )

                st.write(
                    f"**Why:** {reason}"
                )

                st.write(
                    f"**Dependencies:** {dependencies}"
                )

                st.write(
                    f"**Requires Tool:** {requires_tool}"
                )

                if requires_tool:

                    st.write(
                        f"**Tool:** `{tool}`"
                    )

                    st.json(
                        task.get(
                            "tool_arguments",
                            {}
                        )
                    )


    # ========================================================
    # INVESTIGATION
    # ========================================================

    st.divider()

    st.markdown(
        '<div class="section-label">EVIDENCE</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="section-title">🔎 Investigation Results</div>',
        unsafe_allow_html=True
    )


    evidence = result.get(
        "retrieved_context",
        []
    )


    if evidence:

        for index, item in enumerate(
            evidence,
            start=1
        ):

            with st.expander(
                f"Evidence {index}",
                expanded=False
            ):

                st.write(item)

    else:

        st.info(
            "No investigation evidence available."
        )


    # ========================================================
    # SOURCES
    # ========================================================

    sources = result.get(
        "sources",
        []
    )


    if sources:

        with st.expander(
            "📚 Sources"
        ):

            for source in sources:

                st.write(
                    f"- {source}"
                )


    # ========================================================
    # TOOL RESULTS
    # ========================================================

    st.markdown(
        "### 🔧 External Tool Results"
    )


    tool_results = result.get(
        "tool_results",
        []
    )


    if tool_results:

        for index, tool_result in enumerate(
            tool_results,
            start=1
        ):

            with st.expander(
                f"Tool Result {index}"
            ):

                st.json(
                    tool_result
                )

    else:

        st.info(
            "No external tool results."
        )


    # ========================================================
    # POLICY
    # ========================================================

    st.divider()

    st.markdown(
        '<div class="section-label">GOVERNANCE</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="section-title">🛡️ Policy Evaluation</div>',
        unsafe_allow_html=True
    )


    policy_result = result.get(
        "policy_result",
        ""
    )


    if not policy_result:

        policy_result = result.get(
            "validation_result",
            ""
        )


    if policy_result:

        st.write(
            policy_result
        )

    else:

        st.info(
            "No policy evaluation available."
        )


    # ========================================================
    # PROPOSED REMEDIATION
    # ========================================================

    st.divider()

    st.markdown(
        '<div class="section-label">REMEDIATION</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="section-title">⚙️ Proposed Remediation</div>',
        unsafe_allow_html=True
    )


    proposed_action = result.get(
        "proposed_action",
        {}
    )


    if proposed_action:

        st.write(
            proposed_action.get(
                "proposal",
                "No proposal."
            )
        )


        prop_col1, prop_col2, prop_col3 = st.columns(3)


        with prop_col1:

            st.metric(
                "Task",
                proposed_action.get(
                    "task_id",
                    "N/A"
                )
            )


        with prop_col2:

            st.metric(
                "Human Approval",
                str(
                    proposed_action.get(
                        "requires_human_approval",
                        True
                    )
                )
            )


        with prop_col3:

            st.metric(
                "Executed",
                str(
                    proposed_action.get(
                        "executed",
                        False
                    )
                )
            )


    else:

        st.info(
            "No remediation proposal available."
        )


    # ========================================================
    # CRITIC
    # ========================================================

    st.divider()

    st.markdown(
        '<div class="section-label">VALIDATION</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="section-title">🧐 Critic Validation</div>',
        unsafe_allow_html=True
    )


    critic_decision = result.get(
        "critic_decision",
        "N/A"
    )


    critic_feedback = result.get(
        "critic_feedback",
        "No critic feedback."
    )


    if critic_decision == "ACCEPT":

        st.success(
            "✅ Critic Decision: ACCEPT"
        )

    elif critic_decision == "REJECT":

        st.error(
            "❌ Critic Decision: REJECT"
        )

    else:

        st.info(
            f"Critic Decision: {critic_decision}"
        )


    st.write(
        critic_feedback
    )


    # ========================================================
    # EXECUTION
    # ========================================================

    st.divider()

    st.markdown(
        '<div class="section-label">EXECUTION</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="section-title">⚙️ Execution Result</div>',
        unsafe_allow_html=True
    )


    execution_result = result.get(
        "execution_result",
        ""
    )


    if execution_result:

        st.success(
            execution_result
        )

    else:

        st.info(
            "Execution has not occurred."
        )


    # ========================================================
    # VERIFICATION
    # ========================================================

    st.markdown(
        "### ✅ Verification"
    )


    verification_result = result.get(
        "verification_result",
        ""
    )


    if verification_result:

        st.success(
            verification_result
        )

    else:

        st.info(
            "Verification has not occurred."
        )



    # ========================================================
    # AGENT EVALUATION & OBSERVABILITY
    # ========================================================

    st.divider()

    st.markdown(
        '<div class="section-label">AGENT EVALUATION</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="section-title">📊 Agent Evaluation & System Quality</div>',
        unsafe_allow_html=True
    )

    st.caption(
        "Rule-based, auditable evaluation signals derived from the "
        "actual workflow state and trace. These are not fabricated "
        "accuracy percentages."
    )

    agent_definitions = [
        ("🧠 Planner", "planner"),
        ("🔎 Investigator", "investigator"),
        ("⚙️ Executor", "executor"),
        ("🛡️ Policy", "policy"),
        ("🧐 Critic", "critic"),
        ("👤 Human", "human"),
        ("✅ Verification", "verification"),
    ]

    eval_cols = st.columns(4)

    for index, (display_name, agent_key) in enumerate(agent_definitions):
        evaluation = evaluate_agent(result, agent_key)

        with eval_cols[index % 4]:
            passed = evaluation["passed"]
            total = evaluation["total"]

            st.markdown(
                f"""
                <div class="eval-card">
                    <div class="eval-agent">{display_name}</div>
                    <div class="eval-score">
                        {passed}/{total} checks passed
                    </div>
                    <div class="eval-muted">
                        Observable workflow checks
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            with st.expander(
                f"View {display_name.split(' ', 1)[-1]} evaluation",
                expanded=False
            ):
                for check_name, passed_check in evaluation["checks"]:
                    icon = "✅" if passed_check else "❌"
                    st.markdown(
                        f"{icon} **{check_name}**"
                    )

    st.markdown("### 🧮 System Quality")

    sys_eval = system_evaluation(result)

    q1, q2, q3, q4, q5 = st.columns(5)

    with q1:
        st.metric(
            "Agent Actions",
            sys_eval["agent_actions"]
        )

    with q2:
        st.metric(
            "Successful Actions",
            sys_eval["successful_actions"]
        )

    with q3:
        st.metric(
            "Tool Success",
            sys_eval["tool_success_rate"]
        )

    with q4:
        st.metric(
            "Evidence Items",
            sys_eval["evidence_items"]
        )

    with q5:
        st.metric(
            "Safety Violations",
            sys_eval["safety_violations"]
        )

    q6, q7, q8, q9, q10 = st.columns(5)

    with q6:
        st.metric(
            "Tasks Completed",
            f'{sys_eval["completed_tasks"]}/{sys_eval["total_tasks"]}'
        )

    with q7:
        st.metric(
            "Retries",
            sys_eval["retries"]
        )

    with q8:
        st.metric(
            "Replans",
            sys_eval["replans"]
        )

    with q9:
        st.metric(
            "Steps",
            f'{sys_eval["steps"]}/{sys_eval["max_steps"]}'
        )

    with q10:
        st.metric(
            "Failed Actions",
            sys_eval["failed_actions"]
        )

    with st.expander(
        "🔍 Evaluation Methodology",
        expanded=False
    ):
        st.markdown(
            """
            **Planner**
            - Plan exists
            - Specialised agents are valid
            - Dependencies are valid
            - Delegation rationale is present

            **Investigator**
            - Evidence was collected
            - External tool response was validated
            - Investigation trace exists
            - No fabricated-evidence signal was detected

            **Executor**
            - Remediation proposal exists
            - Human approval is required
            - Execution was not claimed during proposal
            - Executor trace exists

            **Policy**
            - Policy evaluation exists
            - Proposal was available for review
            - An explicit policy decision is present

            **Critic**
            - Independent critic trace exists
            - Explicit ACCEPT/REJECT decision exists
            - Feedback exists
            - Proposal was reviewed

            **Human / Verification**
            - Approval checkpoint and decision are tracked
            - Verification result and trace are tracked

            Scores represent **observable checks passed**, not model
            accuracy or benchmark performance.
            """
        )

    # ========================================================
    # AUDIT TRACE
    # ========================================================

    st.divider()

    st.markdown(
        '<div class="section-label">OBSERVABILITY</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="section-title">🧾 Human-Auditable Agent Trace</div>',
        unsafe_allow_html=True
    )


    trace = result.get(
        "trace",
        []
    )


    if not trace:

        st.info(
            "No trace available."
        )

    else:

        for index, entry in enumerate(
            trace,
            start=1
        ):

            agent = entry.get(
                "agent",
                "unknown"
            )

            action = entry.get(
                "action",
                ""
            )

            reason = entry.get(
                "reason",
                ""
            )

            status_value = entry.get(
                "status",
                ""
            )

            model_used = entry.get(
                "model_used"
            )


            with st.container(
                border=True
            ):

                trace_col1, trace_col2 = st.columns(
                    [1, 5]
                )


                with trace_col1:

                    st.markdown(
                        f"### #{index}"
                    )


                with trace_col2:

                    st.markdown(
                        f"**{agent.upper()}**"
                    )

                    st.caption(
                        f"Action: {action}"
                    )

                    if reason:

                        st.caption(
                            f"Why: {reason}"
                        )

                    if status_value:

                        st.caption(
                            f"Status: {status_value}"
                        )

                    if model_used:

                        st.caption(
                            f"Model: {model_used}"
                        )


                    if "decision" in entry:

                        st.caption(
                            "Decision: "
                            + str(
                                entry.get(
                                    "decision"
                                )
                            )
                        )


                    if "replan_count" in entry:

                        st.caption(
                            "Replans: "
                            + str(
                                entry.get(
                                    "replan_count"
                                )
                            )
                        )


                    if "retry_count" in entry:

                        st.caption(
                            "Retries: "
                            + str(
                                entry.get(
                                    "retry_count"
                                )
                            )
                        )


                    if "input" in entry:

                        with st.expander(
                            "View input"
                        ):

                            st.json(
                                entry.get(
                                    "input"
                                )
                            )


    # ========================================================
    # RAW STATE
    # ========================================================

    st.divider()

    with st.expander(
        "🧪 Developer Debug State"
    ):

        debug_result = dict(
            result
        )

        # Interrupt objects can be difficult to serialize.
        if "__interrupt__" in debug_result:

            debug_result[
                "__interrupt__"
            ] = str(
                debug_result[
                    "__interrupt__"
                ]
            )


        st.json(
            debug_result
        )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "Sentinel AI · Multi-Agent Incident Resolution · "
    "LangGraph · Gemini · GitHub API · Human-in-the-Loop"
)