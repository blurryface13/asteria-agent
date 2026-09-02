"""Public package surface.

Keep the top-level import lightweight so offline evaluation tools can import
trace/model modules without eagerly loading every research provider.
"""

__all__ = ["AsteriaResearcher"]


def __getattr__(name):
    if name == "AsteriaResearcher":
        from .agent import AsteriaResearcher
        return AsteriaResearcher
    raise AttributeError(name)
