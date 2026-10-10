# Offline documentary research

This package is independent of MoneyPrinterTurbo. It uses only the Python 3.11
standard library and performs no network, publishing, or model calls.

`ResearchAgent` accepts a topic, a source catalog, and claims. It validates IDs,
ranks source metadata, classifies claims, and returns a `ResearchPack`.
`from_dict` and `from_json` accept the same structure as a saved pack. Existing
input scores and verdicts are recalculated. JSON dates are supplied as strings
(prefer ISO 8601); missing dates remain null rather than being invented.

```python
from research import ResearchAgent

pack = ResearchAgent().from_dict({
    "topic": "Darkest Truths of the Taj Mahal",
    "sources": [{
        "source_id": "archive-1",
        "title": "Locally reviewed document",
        "url": "",
        "publisher": "Example archive",
        "source_type": "academic",
        "excerpt": "Replace with the actual passage.",
        "date": None,
    }],
    "claims": [{
        "claim_id": "claim-1",
        "text": "Replace with a precise claim supported by the passage.",
        "evidence": [{
            "source_id": "archive-1", "stance": "SUPPORTS", "reviewed": True,
        }],
    }],
})
assert not pack.verified_claims()  # One source is insufficient for FACT.
pack.save_json("research_pack.json")
```

Evidence links default to unreviewed CONTEXT. A reviewer must check whether the
source excerpt SUPPORTS, CONTRADICTS, or identifies the claim as LEGEND. Use
separate source IDs for different excerpts. The checker does not understand prose
or authenticate local metadata: its output is conditional on correct review.

Default FACT classification needs two independent sources scoring at least 0.85,
with reviewed support and no reviewed credible contradiction or legend evidence.
Credible evidence starts at 0.75. Contradictions yield DISPUTED; documented legends
yield LEGEND, including when their literal interpretation is contradicted.
Other claims are UNVERIFIED. Confidence describes the evidence for the assigned
classification, not the probability that a legend is literally true.

Only FACT/HIGH claims and historically relevant, explicitly labeled legends are
usable in a script. `verified_claims()` returns only FACT/HIGH usable claims.
Legends carry attribution guidance; disputed claims require editorial review.

`RankingRules` configures source-type weights, trusted domain weights,
institutional suffixes, and missing-metadata caps. These are heuristics: an
institutional URL or user-supplied type does not prove authenticity. Missing
publisher or excerpt prevents strong evidence. Dates do not raise credibility.

Repeated publishers, shared domains, identical excerpts, and explicit
`independence_group` values are merged for corroboration. Domain grouping is
deliberately conservative without a public-suffix dependency. Annotate copied or
syndicated material and institutions sharing an owner with the same group; this
offline implementation cannot discover concealed dependencies.

`SourceProvider` and `ClaimExtractor` are injectable protocols for future search
and Ollama/Qwen adapters. No adapters are enabled or bundled. Extracted claims
are proposals: the agent resets their evidence links to unreviewed. Human-reviewed
local claims can then be supplied explicitly on a later run.

Run tests from the repository root:

```text
python -m unittest discover -s test -p test_research.py -v
```
