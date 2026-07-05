"""Point d'entrée legacy — délègue à l'orchestrateur."""

from agent.orchestrator import AgentConfigurationError, AgentError, Orchestrator, agent_service, orchestrator

__all__ = [
    "AgentConfigurationError",
    "AgentError",
    "Orchestrator",
    "agent_service",
    "orchestrator",
]
