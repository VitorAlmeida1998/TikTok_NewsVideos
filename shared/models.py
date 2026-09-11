"""Modelos de dados compartilhados entre os módulos do pipeline."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class NewsItem:
    """Representação normalizada de uma notícia coletada de um feed RSS."""

    title: str
    source: str
    url: str
    published_at: datetime | None
    summary: str
    collected_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def content_hash(self) -> str:
        """Hash estável usado para dedupe (baseado em título normalizado + URL)."""
        basis = f"{self.title.strip().lower()}|{self.url.strip().lower()}"
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "published_at": self.published_at.isoformat()
            if self.published_at
            else None,
            "summary": self.summary,
            "collected_at": self.collected_at.isoformat(),
            "content_hash": self.content_hash,
        }
