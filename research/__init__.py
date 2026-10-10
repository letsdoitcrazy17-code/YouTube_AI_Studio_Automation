"""Standalone, offline research layer for YouTube AI Studio."""

from .fact_checker import FactChecker, FactCheckingRules
from .research_agent import ClaimExtractor, ResearchAgent, SourceProvider
from .research_pack import (
    ClaimRecord,
    ClaimStatus,
    Confidence,
    EvidenceLink,
    EvidenceStance,
    ResearchPack,
    SourceEvidence,
)
from .source_ranker import RankingRules, SourceRanker

__all__ = [
    "ClaimExtractor",
    "ClaimRecord",
    "ClaimStatus",
    "Confidence",
    "EvidenceLink",
    "EvidenceStance",
    "FactChecker",
    "FactCheckingRules",
    "RankingRules",
    "ResearchAgent",
    "ResearchPack",
    "SourceEvidence",
    "SourceProvider",
    "SourceRanker",
]
