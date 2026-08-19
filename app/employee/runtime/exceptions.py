"""
Shared exceptions for the AI Employee runtime.

Kept in a dedicated module to avoid circular imports between
executor.py and supervisor.py.
"""


class HumanInterventionRequired(Exception):
    """Raised when a task requires human intervention."""
    pass


class TaskCancelled(Exception):
    """Raised when a task is cancelled by the user."""
    pass


class SupervisorOutputError(Exception):
    """Supervisor LLM output could not be parsed into a valid decision.

    After one retry with error feedback, this error fails the task
    with error code `supervisor_invalid_output` (never silently continue).
    """
    pass
