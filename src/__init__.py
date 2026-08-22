"""
AutoRewarder: A Python package to automate Microsoft Rewards.
"""

__all__ = ["AutoRewarderAPI"]


def __getattr__(name):
    """Load the Selenium-bound API only when the application actually needs it.

    This keeps lightweight modules such as mobile task state and statistics
    importable for diagnostics/tests on a machine that has not installed the
    optional browser runtime yet; the normal CLI still imports ``src.api``
    explicitly and therefore keeps the same dependency requirements.
    """
    if name == "AutoRewarderAPI":
        from .api import AutoRewarderAPI

        return AutoRewarderAPI
    raise AttributeError(name)
