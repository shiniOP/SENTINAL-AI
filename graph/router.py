# graph/router.py


def task_router_node(state):
    """
    Select the next executable task from the Planner's plan.

    The Router does NOT simply choose the first unfinished task.

    It checks:
    1. Is the task already completed?
    2. Are its dependencies satisfied?
    3. Which specialised agent is responsible?
    """

    plan = state.get("plan", [])

    completed_tasks = state.get(
        "completed_tasks",
        []
    )

    # --------------------------------------------------------
    # Find executable task
    # --------------------------------------------------------

    next_task = None

    for task in plan:

        task_id = task.get("id")

        # Already completed
        if task_id in completed_tasks:
            continue

        # ----------------------------------------------------
        # Task dependencies
        # ----------------------------------------------------

        dependencies = task.get(
            "depends_on",
            []
        )

        # Check whether every dependency is completed
        dependencies_satisfied = all(
            dependency in completed_tasks
            for dependency in dependencies
        )

        if not dependencies_satisfied:
            continue

        # This task is executable
        next_task = task
        break

    # --------------------------------------------------------
    # No executable tasks
    # --------------------------------------------------------

    if next_task is None:

        trace_entry = {
            "agent": "task_router",
            "action": "no_executable_task",
            "reason": (
                "No unfinished task currently has "
                "all required dependencies satisfied."
            ),
            "status": "waiting"
        }

        return {
            "trace":
                state.get("trace", []) +
                [trace_entry],

            "step_count":
                state.get("step_count", 0) + 1,

            "status":
                "no_executable_task"
        }

    # --------------------------------------------------------
    # Select task
    # --------------------------------------------------------

    task_id = next_task.get("id")

    agent = next_task.get(
        "agent",
        "unknown"
    )

    trace_entry = {
        "agent": "task_router",
        "action": "route_task",

        "input": {
            "task_id": task_id,
            "agent": agent,
            "description":
                next_task.get(
                    "description",
                    ""
                ),
            "depends_on":
                next_task.get(
                    "depends_on",
                    []
                )
        },

        "reason": (
            "Selected the next unfinished task "
            "whose dependencies are satisfied."
        ),

        "status": "success"
    }

    # --------------------------------------------------------
    # Return updated state
    # --------------------------------------------------------

    return {

        "current_task":
            task_id,

        "trace":
            state.get("trace", []) +
            [trace_entry],

        "step_count":
            state.get("step_count", 0) + 1,

        "status":
            "task_routed"
    }