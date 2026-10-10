"""Offline orchestration with dependency-injected future provider interfaces."""

from collections.abc import Mapping, Sequence
import json
from pathlib import Path
from typing import Any, Protocol

from .fact_checker import FactChecker
from .research_pack import ClaimRecord, EvidenceLink, ResearchPack, SourceEvidence
from .source_ranker import SourceRanker


class SourceProvider(Protocol):
    """Extension point only; no search or crawling implementation is included."""

    def get_sources(self, topic: str) -> Sequence[SourceEvidence]: ...


class ClaimExtractor(Protocol):
    """Future Ollama/Qwen adapters can return proposals with unreviewed links."""

    def extract_claims(
        self, topic: str, sources: Sequence[SourceEvidence]
    ) -> Sequence[ClaimRecord]: ...


class ResearchAgent:
    def __init__(
        self,
        ranker: SourceRanker | None = None,
        checker: FactChecker | None = None,
        source_provider: SourceProvider | None = None,
        claim_extractor: ClaimExtractor | None = None,
    ) -> None:
        self.ranker = ranker if ranker is not None else SourceRanker()
        self.checker = checker if checker is not None else FactChecker()
        self.source_provider = source_provider
        self.claim_extractor = claim_extractor

    def research(
        self,
        topic: str,
        sources: Sequence[SourceEvidence] | None = None,
        claims: Sequence[ClaimRecord] | None = None,
    ) -> ResearchPack:
        if not topic.strip():
            raise ValueError("Topic is required")
        if sources is None:
            if self.source_provider is None:
                raise ValueError("Supply local sources or a source provider")
            sources = self.source_provider.get_sources(topic)
        if claims is None:
            if self.claim_extractor is None:
                raise ValueError("Supply local claims or a claim extractor")
            claims = self.claim_extractor.extract_claims(topic, sources)
            # Generated proposals cannot certify their own evidence relationships.
            from dataclasses import replace

            claims = [
                replace(
                    claim,
                    evidence=tuple(
                        replace(link, reviewed=False) for link in claim.evidence
                    ),
                )
                for claim in claims
            ]
        # Validate IDs and references before classification; ignore input verdicts.
        pack = ResearchPack(topic=topic, sources=list(sources), claims=list(claims))
        pack.sources = self.ranker.rank(pack.sources)
        pack.claims = self.checker.check_claims(pack.claims, pack.sources)
        return pack

    def from_dict(self, data: Mapping[str, Any]) -> ResearchPack:
        sources = [SourceEvidence(**source) for source in data.get("sources", [])]
        claims = [
            ClaimRecord(
                **{
                    **claim,
                    "evidence": tuple(
                        EvidenceLink(**link) for link in claim.get("evidence", [])
                    ),
                }
            )
            for claim in data.get("claims", [])
        ]
        return self.research(topic=data["topic"], sources=sources, claims=claims)

    def from_json(self, path: str | Path) -> ResearchPack:
        with Path(path).open(encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("Research input must be a JSON object")
        return self.from_dict(data)
