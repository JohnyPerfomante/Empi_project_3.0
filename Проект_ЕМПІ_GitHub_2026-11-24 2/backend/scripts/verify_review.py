"""Read-only diagnostic against the real cached model, with equal-length and unrelated answers."""

import json

from app.core.config import settings
from app.nlp.analyzer import Candidate, analyze, cosine
from app.nlp.provider import LocalProvider
from app.schemas.analysis import AnalysisSettings
from app.schemas.catalog import ConceptIn


def main(provider=None):
    config = settings()
    if config.nlp_provider != "local":
        raise SystemExit("This check requires the real local NLP provider.")
    provider = provider or LocalProvider(config)
    references = [
        "Операційна система керує апаратними ресурсами комп’ютера та надає користувачу засоби взаємодії.",
        "ОС розподіляє пам’ять, процесорний час і пристрої між програмами та забезпечує роботу користувача.",
    ]
    concepts = [ConceptIn(concept="ресурси", synonyms=["обладнання", "пам’ять", "пристрої"])]
    candidates = [Candidate(i, text, text, concepts, []) for i, text in enumerate(references, 1)]
    good = "ОС керує обладнанням комп’ютера та дозволяє користувачу працювати з ним."
    unrelated = ("Садівник вирощує квіти, дерева та поливає город улітку. " * 8)[: len(good)]
    cases = {
        "paraphrase": good,
        "same_length_unrelated": unrelated,
        "long_unrelated": "Дощ зволожує землю, а сонячне світло допомагає рослинам розвиватися. " * 15,
        "negation": "ОС не керує обладнанням комп’ютера та дозволяє користувачу працювати з ним.",
        "second_reference": references[1],
    }
    reference_vectors = provider.encode(references)
    result = {}
    for label, answer in cases.items():
        vector = provider.encode([answer])[0]
        outcome = analyze(
            provider,
            answer,
            candidates,
            [cosine(vector, ref) for ref in reference_vectors],
            AnalysisSettings(),
        )
        result[label] = {
            "characters": len(answer),
            "score": round(outcome.final_similarity, 6),
            "category": outcome.category.value,
            "selected_reference": outcome.candidate.reference_id,
            "warnings": [warning["code"] for warning in outcome.warnings],
            "raw_score": round(outcome.raw_similarity, 6),
            "relevance": outcome.relevance,
        }
    assert len(good) == len(unrelated)
    assert result["paraphrase"]["score"] > result["same_length_unrelated"]["score"] + 0.2
    assert result["paraphrase"]["score"] > result["long_unrelated"]["score"] + 0.2
    assert result["same_length_unrelated"]["category"] == "LOW_MATCH"
    assert result["long_unrelated"]["category"] == "LOW_MATCH"
    assert result["same_length_unrelated"]["score"] == 0
    assert result["long_unrelated"]["score"] == 0
    assert result["negation"]["category"] != "HIGH_MATCH"
    assert result["second_reference"]["selected_reference"] == 2
    print(
        json.dumps(
            {"provider": provider.name, "cases": result, "assertions": "passed"}, ensure_ascii=False, indent=2
        )
    )


if __name__ == "__main__":
    main()
