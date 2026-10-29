"""Shared pipeline constants.

Stage order lives here so the worker, the API, and the tests all agree on
what "the next stage" means.
"""

# Ordered list of (job_status, stage_name) pairs.
PIPELINE_STAGES: list[tuple[str, str]] = [
    ("researching", "research"),
    ("outlining", "outline"),
    ("drafting", "draft"),
    ("verifying", "verify"),
    ("styling", "style"),
    ("formatting", "format"),
]

STAGE_ORDER: list[str] = [stage for _, stage in PIPELINE_STAGES]
STATUS_ORDER: list[str] = [status for status, _ in PIPELINE_STAGES]

# Job statuses that mean "this job is finished, one way or another".
TERMINAL_STATUSES = ("done", "failed")


def next_stage_index(completed_stage: str | None) -> int:
    """Return the index of the first stage that still needs to run."""
    if completed_stage is None:
        return 0
    try:
        return STAGE_ORDER.index(completed_stage) + 1
    except ValueError:
        return 0


def job_status_for_stage(stage_name: str) -> str:
    """Map a stage name to the job status shown to the user."""
    try:
        return STATUS_ORDER[STAGE_ORDER.index(stage_name)]
    except ValueError:
        return "failed"
