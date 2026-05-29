"""Sub-agents specializzati. Ognuno: prompt sistema + tool subset.

Caricati lazy via load_agent(name).
"""
from .base import BaseAgent
from .email_agent import EmailAgent
from .travel_agent import TravelAgent
from .code_agent import CodeAgent
from .desktop_agent import DesktopAgent
from .generic_agent import GenericAgent

_REGISTRY = {
    "email": EmailAgent,
    "travel": TravelAgent,
    "code": CodeAgent,
    "desktop": DesktopAgent,
    "generic": GenericAgent,
}


def load_agent(name: str):
    cls = _REGISTRY.get(name, GenericAgent)
    return cls()


def list_agents():
    return list(_REGISTRY.keys())
