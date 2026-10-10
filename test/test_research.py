"""Offline research safeguards. Fixtures are synthetic, not historical evidence."""

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research import (
    ClaimRecord,
    ClaimStatus,
    Confidence,
    EvidenceLink,
    EvidenceStance,
    FactChecker,
    FactCheckingRules,
    RankingRules,
    ResearchAgent,
    ResearchPack,
    SourceEvidence,
    SourceRanker,
)


def source(source_id: str = "a", **changes: object) -> SourceEvidence:
    values = dict(
        source_id=source_id,
        title=f"Archive {source_id}",
        url=f"https://{source_id}.example.org/document",
        publisher=f"Institution {source_id}",
        source_type="academic",
        excerpt=f"Independent documentary evidence {source_id}.",
    )
    values.update(changes)
    return SourceEvidence(**values)


def claim(
    *ids: str,
    stance: EvidenceStance = EvidenceStance.SUPPORTS,
    reviewed: bool = True,
    **changes: object,
) -> ClaimRecord:
    values = dict(
        claim_id="c1",
        text="Synthetic historical claim",
        evidence=tuple(EvidenceLink(sid, stance, reviewed) for sid in ids),
    )
    values.update(changes)
    return ClaimRecord(**values)


class TestResearch(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = ResearchAgent()
        # Different registered domains and publishers represent separate origins.
        self.sources = [
            source("a", url="https://archive-a.org/doc"),
            source("b", url="https://archive-b.org/doc"),
        ]

    def check(
        self, candidate: ClaimRecord, sources: list[SourceEvidence] | None = None
    ) -> ClaimRecord:
        return self.agent.research(
            "Documentary", self.sources if sources is None else sources, [candidate]
        ).claims[0]

    def test_independent_corroboration_is_fact(self) -> None:
        result = self.check(claim("a", "b"))
        self.assertEqual(result.status, ClaimStatus.FACT)
        self.assertEqual(result.confidence, Confidence.HIGH)
        self.assertTrue(result.usable_in_script)

    def test_unsupported_or_unreviewed_never_becomes_fact(self) -> None:
        for candidate in [
            claim(),
            claim("a"),
            claim("a", "b", reviewed=False),
            claim("a", "b", stance=EvidenceStance.CONTEXT),
            claim(
                status=ClaimStatus.FACT,
                confidence=Confidence.HIGH,
                usable_in_script=True,
            ),
        ]:
            with self.subTest(candidate=candidate):
                result = self.check(candidate)
                self.assertEqual(result.status, ClaimStatus.UNVERIFIED)
                self.assertFalse(result.usable_in_script)

    def test_weak_blank_and_anonymous_evidence_is_insufficient(self) -> None:
        for changes in [
            dict(source_type="blog"),
            dict(excerpt=" "),
            dict(publisher=""),
        ]:
            with self.subTest(changes=changes):
                sources = [replace(s, **changes) for s in self.sources]
                self.assertEqual(
                    self.check(claim("a", "b"), sources).status, ClaimStatus.UNVERIFIED
                )

    def test_duplicates_and_related_origins_do_not_corroborate(self) -> None:
        variants = [
            [self.sources[0], replace(self.sources[1], publisher=" Institution A ")],
            [source("a"), source("b")],  # subdomains of one domain
            [replace(s, independence_group="Shared archive") for s in self.sources],
            [replace(s, excerpt="Identical copied excerpt") for s in self.sources],
        ]
        for sources in variants:
            with self.subTest(sources=sources):
                self.assertEqual(
                    self.check(claim("a", "b"), sources).status, ClaimStatus.UNVERIFIED
                )
        self.assertEqual(self.check(claim("a", "a")).status, ClaimStatus.UNVERIFIED)

    def test_credible_contradiction_blocks_fact(self) -> None:
        candidate = claim("a", "b")
        candidate = replace(
            candidate,
            evidence=candidate.evidence
            + (EvidenceLink("c", EvidenceStance.CONTRADICTS, True),),
        )
        result = self.check(candidate, self.sources + [source("c")])
        self.assertEqual(result.status, ClaimStatus.DISPUTED)
        self.assertFalse(result.usable_in_script)

    def test_low_quality_contradiction_does_not_override_fact(self) -> None:
        candidate = replace(
            claim("a", "b"),
            evidence=claim("a", "b").evidence
            + (EvidenceLink("c", EvidenceStance.CONTRADICTS, True),),
        )
        self.assertEqual(
            self.check(
                candidate, self.sources + [source("c", source_type="blog")]
            ).status,
            ClaimStatus.FACT,
        )

    def test_legend_requires_label_and_relevance(self) -> None:
        for relevant in [True, False]:
            result = self.check(
                claim("a", stance=EvidenceStance.LEGEND, historically_relevant=relevant)
            )
            self.assertEqual(result.status, ClaimStatus.LEGEND)
            self.assertEqual(result.usable_in_script, relevant)
            self.assertIn("legend", result.script_guidance)
        candidate = replace(
            claim("a", "b"),
            evidence=claim("a", "b").evidence
            + (EvidenceLink("c", EvidenceStance.LEGEND, True),),
        )
        self.assertEqual(
            self.check(candidate, self.sources + [source("c")]).status,
            ClaimStatus.LEGEND,
        )

    def test_unreviewed_legend_is_unverified(self) -> None:
        self.assertEqual(
            self.check(claim("a", stance=EvidenceStance.LEGEND, reviewed=False)).status,
            ClaimStatus.UNVERIFIED,
        )

    def test_ranking_preferences_and_domain_boundaries(self) -> None:
        ranker = SourceRanker()
        official = source(url="https://whc.unesco.org/list", source_type="unknown")
        spoof = replace(official, url="https://unesco.org.evil.example/list")
        credentials = replace(official, url="https://unesco.org@evil.example/list")
        self.assertEqual(ranker.score(official), 0.98)
        self.assertEqual(ranker.score(spoof), 0.30)
        self.assertEqual(ranker.score(credentials), 0.30)
        for kind in [
            "government",
            "heritage",
            "museum",
            "university",
            "academic",
            "historical_organization",
        ]:
            self.assertGreaterEqual(ranker.score(source(source_type=kind)), 0.85)
        for kind in ["blog", "seo", "anonymous", "aggregator"]:
            self.assertLess(ranker.score(source(source_type=kind)), 0.5)
        self.assertEqual(
            ranker.score(
                source(url="https://culture.gov.in/doc", source_type="unknown")
            ),
            0.90,
        )

    def test_configurable_rules_and_input_immutability(self) -> None:
        ranker = SourceRanker(RankingRules(type_scores={"archive": 0.88}))
        original = source(source_type="archive")
        self.assertEqual(ranker.rank([original])[0].credibility_score, 0.88)
        self.assertEqual(original.credibility_score, 0.0)
        checker = FactChecker(FactCheckingRules(minimum_fact_sources=3))
        result = ResearchAgent(checker=checker).research(
            "Topic", self.sources, [claim("a", "b")]
        )
        self.assertEqual(result.claims[0].status, ClaimStatus.UNVERIFIED)

    def test_invalid_scores_and_thresholds(self) -> None:
        for value in [-1, 1.1, float("nan"), float("inf")]:
            with self.assertRaises(ValueError):
                source(credibility_score=value)
            with self.assertRaises(ValueError):
                RankingRules(institutional_score=value)
        for kwargs in [
            dict(minimum_fact_sources=1),
            dict(minimum_fact_sources=2.5),
            dict(credible_threshold=0.95, fact_threshold=0.8),
        ]:
            with self.assertRaises(ValueError):
                FactCheckingRules(**kwargs)

    def test_missing_and_duplicate_ids_rejected(self) -> None:
        for sources, claims in [
            ([self.sources[0]] * 2, []),
            (self.sources, [claim(), claim()]),
            (self.sources, [claim("missing")]),
        ]:
            with self.assertRaises(ValueError):
                self.agent.research("Topic", sources, claims)
        with self.assertRaises(ValueError):
            FactChecker().check_claim(claim("missing"), self.sources)

    def test_pack_add_verified_and_json_round_trip(self) -> None:
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            pack = self.agent.research(
                "Taj Mahal — research", self.sources, [claim("a", "b")]
            )
            pack.add_claim(ClaimRecord("c2", "Unverified story"))
            self.assertEqual(len(pack.verified_claims()), 1)
            with TemporaryDirectory() as directory:
                path = pack.save_json(Path(directory) / "pack.json")
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(data["claims"][0]["status"], "FACT")
                self.assertEqual(data["topic"], pack.topic)
                restored = self.agent.from_json(path)
                self.assertEqual(
                    restored.claims, pack.claims[:1] + [self.check(pack.claims[1])]
                )
                self.assertEqual(restored.sources, pack.sources)

    def test_future_extractor_cannot_self_certify(self) -> None:
        sources = self.sources

        class LocalProvider:
            def get_sources(self, topic: str) -> list[SourceEvidence]:
                return sources

        class ProposalExtractor:
            def extract_claims(
                self, topic: str, sources: list[SourceEvidence]
            ) -> list[ClaimRecord]:
                return [claim("a", "b", reviewed=True)]

        pack = ResearchAgent(
            source_provider=LocalProvider(), claim_extractor=ProposalExtractor()
        ).research("Topic")
        self.assertEqual(pack.claims[0].status, ClaimStatus.UNVERIFIED)
        self.assertFalse(any(link.reviewed for link in pack.claims[0].evidence))

    def test_empty_input_and_missing_providers(self) -> None:
        self.assertEqual(self.agent.research("Topic", [], []).claims, [])
        for kwargs in [{}, {"sources": []}]:
            with self.assertRaises(ValueError):
                self.agent.research("Topic", **kwargs)
        with self.assertRaises(ValueError):
            ResearchPack(" ")

    def test_boolean_strings_are_not_trusted(self) -> None:
        with self.assertRaises(ValueError):
            EvidenceLink("a", reviewed="false")
        with self.assertRaises(ValueError):
            claim(historically_relevant="false")


if __name__ == "__main__":
    unittest.main()
