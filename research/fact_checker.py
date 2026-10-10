"""Conservative classification of explicitly reviewed, claim-specific evidence."""

from dataclasses import dataclass, replace
from collections.abc import Iterable

from .research_pack import (
    ClaimRecord,
    ClaimStatus,
    Confidence,
    EvidenceStance,
    SourceEvidence,
    validate_score,
)
from .source_ranker import source_host


@dataclass(frozen=True)
class FactCheckingRules:
    credible_threshold: float = 0.75
    fact_threshold: float = 0.85
    minimum_fact_sources: int = 2

    def __post_init__(self) -> None:
        validate_score(self.credible_threshold)
        validate_score(self.fact_threshold)
        if not 0 < self.credible_threshold <= self.fact_threshold:
            raise ValueError("Require 0 < credible_threshold <= fact_threshold")
        if type(self.minimum_fact_sources) is not int or self.minimum_fact_sources < 2:
            raise ValueError("FACT requires at least two independent sources")


def _independent_count(sources: list[SourceEvidence]) -> int:
    """Merge overlapping origins transitively; repeated pages aren't corroboration.

    Publisher metadata and explicit groups are locally supplied, not authenticated.
    Sites with different hosts may still share an owner; annotate their group.
    """
    groups: list[set[str]] = []
    for source in sources:
        keys = {"publisher:" + " ".join(source.publisher.casefold().split())}
        host = source_host(source.url)
        if host:
            # Conservative grouping includes parent domains (including ccTLDs).
            labels = host.split(".")
            keys.update(
                "host:" + ".".join(labels[i:]) for i in range(max(1, len(labels) - 1))
            )
        if source.independence_group.strip():
            keys.add("group:" + source.independence_group.strip().casefold())
        if source.excerpt.strip():
            keys.add("excerpt:" + " ".join(source.excerpt.casefold().split()))
        overlapping = [group for group in groups if group & keys]
        for group in overlapping:
            keys.update(group)
            groups.remove(group)
        groups.append(keys)
    return len(groups)


class FactChecker:
    def __init__(self, rules: FactCheckingRules | None = None) -> None:
        self.rules = rules if rules is not None else FactCheckingRules()

    def check_claim(
        self, claim: ClaimRecord, sources: Iterable[SourceEvidence]
    ) -> ClaimRecord:
        catalog: dict[str, SourceEvidence] = {}
        for source in sources:
            if source.source_id in catalog:
                raise ValueError(f"Duplicate source ID: {source.source_id}")
            catalog[source.source_id] = source
        evidence: dict[EvidenceStance, list[SourceEvidence]] = {
            stance: [] for stance in EvidenceStance
        }
        for link in claim.evidence:
            if link.source_id not in catalog:
                raise ValueError(f"Unknown source: {link.source_id}")
            source = catalog[link.source_id]
            if (
                link.reviewed
                and source.excerpt.strip()
                and source.publisher.strip()
                and source.credibility_score >= self.rules.credible_threshold
            ):
                evidence[link.stance].append(source)

        support = evidence[EvidenceStance.SUPPORTS]
        contradictions = evidence[EvidenceStance.CONTRADICTS]
        legends = evidence[EvidenceStance.LEGEND]
        strong = [
            source
            for source in support
            if source.credibility_score >= self.rules.fact_threshold
        ]
        count = _independent_count(strong)
        status, confidence, usable = ClaimStatus.UNVERIFIED, Confidence.LOW, False
        rationale = (
            "Insufficient reviewed, independent evidence to establish this claim."
        )
        guidance = "Do not present as established fact."
        # Legend evidence blocks promotion of the legend's literal content to FACT.
        if legends:
            status = ClaimStatus.LEGEND
            confidence = Confidence.MEDIUM
            usable = claim.historically_relevant
            rationale = "Credible evidence identifies this account as a legend, not literal fact."
            guidance = "Explicitly introduce as a legend or tradition and attribute its source."
            if contradictions:
                rationale += (
                    " Credible evidence also contradicts its literal interpretation."
                )
        elif contradictions:
            status = ClaimStatus.DISPUTED
            confidence = Confidence.MEDIUM
            rationale = "Credible evidence challenges this claim; it must not be stated as fact."
            guidance = "Requires editorial review and explicit attribution of the disagreement."
        elif count >= self.rules.minimum_fact_sources:
            status, confidence, usable = ClaimStatus.FACT, Confidence.HIGH, True
            rationale = f"Supported by {count} independent strong sources with no credible contradiction."
            guidance = "May be used as a fact with source attribution."
        return replace(
            claim,
            status=status,
            confidence=confidence,
            usable_in_script=usable,
            rationale=rationale,
            script_guidance=guidance,
        )

    def check_claims(
        self, claims: Iterable[ClaimRecord], sources: Iterable[SourceEvidence]
    ) -> list[ClaimRecord]:
        catalog = list(sources)
        return [self.check_claim(claim, catalog) for claim in claims]
