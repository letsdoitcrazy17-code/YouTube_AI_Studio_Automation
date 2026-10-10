"""Serializable research records; importing this module has no side effects."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import json
import math
from pathlib import Path


class ClaimStatus(StrEnum):
    FACT = "FACT"
    DISPUTED = "DISPUTED"
    LEGEND = "LEGEND"
    UNVERIFIED = "UNVERIFIED"


class Confidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EvidenceStance(StrEnum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    LEGEND = "LEGEND"
    CONTEXT = "CONTEXT"


def validate_score(value: float) -> None:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError("Scores must be finite and between 0.0 and 1.0")


@dataclass(frozen=True)
class SourceEvidence:
    source_id: str
    title: str
    url: str = ""
    publisher: str = ""
    source_type: str = "unknown"
    excerpt: str = ""
    date: str | None = None
    credibility_score: float = 0.0
    # Shared origin for syndicated/copied material or related institutions.
    independence_group: str = ""

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.title.strip():
            raise ValueError("Source ID and title are required")
        validate_score(self.credibility_score)


@dataclass(frozen=True)
class EvidenceLink:
    """A reviewed relationship between a claim and a source's excerpt.

    Merely attaching a source is context, not evidence of truth. A future model
    may propose links, but must not automatically mark them reviewed.
    """

    source_id: str
    stance: EvidenceStance = EvidenceStance.CONTEXT
    reviewed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "stance", EvidenceStance(self.stance))
        if not isinstance(self.reviewed, bool):
            raise ValueError("reviewed must be a boolean")


@dataclass(frozen=True)
class ClaimRecord:
    claim_id: str
    text: str
    evidence: tuple[EvidenceLink, ...] = ()
    historically_relevant: bool = False
    status: ClaimStatus = ClaimStatus.UNVERIFIED
    confidence: Confidence = Confidence.LOW
    usable_in_script: bool = False
    rationale: str = "Not checked"
    script_guidance: str = "Do not present as established fact."

    def __post_init__(self) -> None:
        if not self.claim_id.strip() or not self.text.strip():
            raise ValueError("Claim ID and text are required")
        if not isinstance(self.historically_relevant, bool):
            raise ValueError("historically_relevant must be a boolean")
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "status", ClaimStatus(self.status))
        object.__setattr__(self, "confidence", Confidence(self.confidence))


@dataclass
class ResearchPack:
    topic: str
    sources: list[SourceEvidence] = field(default_factory=list)
    claims: list[ClaimRecord] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if not self.topic.strip():
            raise ValueError("Topic is required")
        if len({source.source_id for source in self.sources}) != len(self.sources):
            raise ValueError("Duplicate source ID")
        initial_claims = list(self.claims)
        self.claims = []
        for claim in initial_claims:
            self.add_claim(claim)

    def add_claim(self, claim: ClaimRecord) -> None:
        if any(existing.claim_id == claim.claim_id for existing in self.claims):
            raise ValueError(f"Duplicate claim ID: {claim.claim_id}")
        known = {source.source_id for source in self.sources}
        if any(link.source_id not in known for link in claim.evidence):
            raise ValueError(f"Unknown source referenced by {claim.claim_id}")
        self.claims.append(claim)

    def verified_claims(self) -> list[ClaimRecord]:
        return [
            claim
            for claim in self.claims
            if claim.status == ClaimStatus.FACT
            and claim.confidence == Confidence.HIGH
            and claim.usable_in_script
        ]

    def to_dict(self) -> dict[str, object]:
        # JSON round-trip converts string enums to plain strings as well.
        return json.loads(json.dumps(asdict(self), ensure_ascii=False))

    def save_json(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return destination
