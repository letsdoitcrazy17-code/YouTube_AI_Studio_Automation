"""Configurable metadata heuristics, not verification of source authenticity."""

from dataclasses import dataclass, field, replace
from urllib.parse import urlsplit

from .research_pack import SourceEvidence, validate_score


def source_host(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or parsed.username is not None:
            return ""
        return (parsed.hostname or "").lower().rstrip(".").removeprefix("www.")
    except ValueError:
        return ""


@dataclass
class RankingRules:
    type_scores: dict[str, float] = field(
        default_factory=lambda: {
            "government": 0.95,
            "heritage": 0.90,
            "unesco": 0.98,
            "museum": 0.90,
            "university": 0.90,
            "academic": 0.90,
            "historical_organization": 0.85,
            "news": 0.65,
            "book": 0.65,
            "unknown": 0.30,
            "blog": 0.25,
            "seo": 0.15,
            "anonymous": 0.10,
            "aggregator": 0.20,
        }
    )
    domain_scores: dict[str, float] = field(
        default_factory=lambda: {
            "unesco.org": 0.98,
            "asi.nic.in": 0.95,
            "britishmuseum.org": 0.95,
            "si.edu": 0.95,
        }
    )
    institutional_suffixes: tuple[str, ...] = (
        ".gov",
        ".gov.in",
        ".gov.uk",
        ".edu",
        ".ac.uk",
        ".ac.in",
    )
    institutional_score: float = 0.90
    anonymous_cap: float = 0.30
    missing_excerpt_cap: float = 0.40

    def __post_init__(self) -> None:
        for score in [
            *self.type_scores.values(),
            *self.domain_scores.values(),
            self.institutional_score,
            self.anonymous_cap,
            self.missing_excerpt_cap,
        ]:
            validate_score(score)


class SourceRanker:
    def __init__(self, rules: RankingRules | None = None) -> None:
        self.rules = rules if rules is not None else RankingRules()

    def score(self, source: SourceEvidence) -> float:
        rules = self.rules
        score = rules.type_scores.get(
            source.source_type.lower().strip(), rules.type_scores.get("unknown", 0.30)
        )
        host = source_host(source.url)
        for domain, value in rules.domain_scores.items():
            domain = domain.lower().strip().rstrip(".")
            if domain and (host == domain or host.endswith("." + domain)):
                score = max(score, value)
        if any(host.endswith(suffix) for suffix in rules.institutional_suffixes):
            score = max(score, rules.institutional_score)
        if not source.publisher.strip():
            score = min(score, rules.anonymous_cap)
        if not source.excerpt.strip():
            score = min(score, rules.missing_excerpt_cap)
        validate_score(score)
        return score

    def rank(self, sources: list[SourceEvidence]) -> list[SourceEvidence]:
        return sorted(
            (
                replace(source, credibility_score=self.score(source))
                for source in sources
            ),
            key=lambda source: (-source.credibility_score, source.source_id),
        )
