class AIError(Exception):
    """Base class for every expected AI failure. AIManager falls back on these and nothing else."""
