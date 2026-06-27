from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FileContext:
    """Contexte structuré extrait d'un fichier — jamais envoyé en binaire au LLM."""

    file_name: str
    file_type: str
    extracted_text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_name": self.file_name,
            "file_type": self.file_type,
            "extracted_text": self.extracted_text,
            "metadata": self.metadata,
            "warnings": self.warnings,
        }
