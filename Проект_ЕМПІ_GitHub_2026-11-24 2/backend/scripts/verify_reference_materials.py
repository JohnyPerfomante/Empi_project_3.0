"""Check that each supplied reference satisfies its own rubric using real Ukrainian morphology."""

import json

from app.core.config import settings
from app.nlp.analyzer import Candidate, analyze
from app.nlp.provider import LocalProvider
from app.schemas.analysis import AnalysisSettings
from scripts.seed_demo import alternative_references, load_examples


def main(provider=None):
    provider = provider or LocalProvider(settings())
    alternatives = alternative_references()
    issues = []
    checked = 0
    for example in load_examples():
        for kind, text in [("primary", example.reference), ("alternative", alternatives[example.question])]:
            candidate = Candidate(1, text, text, example.concepts, [])
            # Self-similarity is 1; this check isolates rubric/tokenisation consistency.
            outcome = analyze(provider, text, [candidate], [1.0], AnalysisSettings())
            checked += 1
            if outcome.category.value != "HIGH_MATCH" or outcome.concept_coverage != 1:
                issues.append({"question": example.question, "kind": kind, "missing": outcome.missing})
    print(json.dumps({"checked": checked, "issues": issues}, ensure_ascii=False, indent=2))
    if issues:
        raise SystemExit("Some reference answers do not satisfy their own rubric.")


if __name__ == "__main__":
    main()
