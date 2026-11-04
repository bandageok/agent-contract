"""agent-contract: behavioural contracts for AI agents.

Mine what "correct" looked like from your own traces, then catch the moment a
model swap, a prompt edit or a dependency bump quietly changes it.
"""

__version__ = "0.1.0"

from .loader import LoadError, load_traces, normalize_record  # noqa: F401
from .miner import MineOptions, mine  # noqa: F401
from .model import (  # noqa: F401
    AMBER,
    GREEN,
    RED,
    Assertion,
    Contract,
    Finding,
    Report,
    Step,
    Trace,
)
from .runner import run_contract  # noqa: F401

__all__ = [
    "__version__",
    "AMBER",
    "GREEN",
    "RED",
    "Assertion",
    "Contract",
    "Finding",
    "Report",
    "Step",
    "Trace",
    "MineOptions",
    "mine",
    "run_contract",
    "load_traces",
    "normalize_record",
    "LoadError",
]