"""Visual verification constants."""

from typing import Literal

VISUAL_NEXT_ACTIONS_LIMIT = 5

VISUAL_VERDICT_STATUSES = ("pass", "revise", "fail")

VisualVerdictStatus = Literal["pass", "revise", "fail"]
