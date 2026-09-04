"""Reserved plugin boundary for the Notion/custom task adapter.

The intake adapter is intentionally external to a worker agent in phase one.
This module keeps a stable plugin name while task transport evolves.
"""


def register(ctx) -> None:
    return None
