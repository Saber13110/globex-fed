"""Package backends — abstraction d'exécution multi-environnement pour Jarvis."""

from __future__ import annotations

from jarvis.engine.mission.backends.base import BackendResult, ExecutionBackend
from jarvis.engine.mission.backends.docker import DockerBackend
from jarvis.engine.mission.backends.local import LocalBackend
from jarvis.engine.mission.backends.remote import RemoteBackend
from jarvis.engine.mission.backends.rpc import RPC_ALLOWED_TOOLS, ScriptRPCRunner
from jarvis.engine.mission.backends.ssh import SSHBackend

__all__ = [
    "BackendResult",
    "DockerBackend",
    "ExecutionBackend",
    "LocalBackend",
    "RemoteBackend",
    "RPC_ALLOWED_TOOLS",
    "ScriptRPCRunner",
    "SSHBackend",
]
