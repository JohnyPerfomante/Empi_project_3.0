from dataclasses import dataclass, field, replace

import numpy as np

from app.models import Category
from app.nlp.methodology import (
    ALGORITHM_VERSION,  # noqa: F401 — stable public import for callers
    GENERIC_CONTENT_TERMS,
    RELEVANCE_POLICY,
)
from app.nlp.provider import Document, Provider
from app.nlp.text import NEGATIONS, surface_tokens
from app.schemas.analysis import AnalysisSettings
from app.schemas.catalog import ConceptIn, ConflictRule

LEXICAL_EXCLUDED_POS = {"PUNCT", "SYM", "ADP", "AUX", "CCONJ", "SCONJ", "DET", "PRON", "PART"}


@dataclass(frozen=True)
class Candidate:
    reference_id: int
    reference_text: str
    text: str
    concepts: list[ConceptIn]
    rules: list[ConflictRule]
    variation_id: int | None = None


@dataclass(frozen=True)
class Score:
    candidate: Candidate
    semantic_similarity: float
    lexical_similarity: float
    concept_coverage: float | None
    final_similarity: float
    category: Category
    explanation: str
    warnings: list[dict]
    matches: list[str]
    missing: list[str]
    comparisons: list[dict] = field(default_factory=list)
    raw_similarity: float = 0.0
    relevance: dict = field(default_factory=dict)


def lexical_sentences(doc: Document, *, surface=False) -> list[tuple[str, ...]]:
    if surface:
        return [tuple(word for token in sentence for word in surface_tokens(token.text)) for sentence in doc]
    return [
        tuple(
            token.text if surface else token.lemma for token in sentence if token.pos not in {"PUNCT", "SYM"}
        )
        for sentence in doc
    ]


def lexical_set(doc: Document) -> set[str]:
    return {
        token.lemma
        for sentence in doc
        for token in sentence
        if token.pos not in LEXICAL_EXCLUDED_POS or token.lemma in NEGATIONS
    }


def cosine(left, right) -> float:
    norm = np.linalg.norm(left) * np.linalg.norm(right)
    return float(np.clip(np.dot(left, right) / norm, 0, 1)) if norm else 0.0


def phrase_in(needle: tuple[str, ...], haystack: list[tuple[str, ...]]) -> bool:
    if not needle:
        return False
    return any(
        sentence[index : index + len(needle)] == needle
        for sentence in haystack
        for index in range(len(sentence) - len(needle) + 1)
    )


def phrase(provider: Provider, text: str) -> tuple[str, ...]:
    return tuple(word for sentence in lexical_sentences(provider.morphology(text)) for word in sentence)


def matches_phrase(provider, text, sentences, surface_sentences):
    doc = provider.morphology(text)
    lemmas = tuple(word for sentence in lexical_sentences(doc) for word in sentence)
    surface = tuple(word for sentence in lexical_sentences(doc, surface=True) for word in sentence)
    return phrase_in(lemmas, sentences) or phrase_in(surface, surface_sentences)


def negation_signals(doc: Document) -> set[tuple[str, str]]:
    signals = set()
    for sentence in doc:
        for index, token in enumerate(sentence):
            negation = token.lemma if token.lemma in NEGATIONS else token.text
            has_negative_feature = "Polarity=Neg" in token.features
            if negation not in NEGATIONS and not has_negative_feature:
                continue
            following = sentence[index + 1 : index + 5]
            if negation == "не" and following and following[0].lemma in {"тільки", "лише"}:
                continue
            content = next(
                (word.lemma for word in following if word.pos in {"VERB", "AUX", "NOUN", "ADJ", "ADV", ""}),
                "",
            )
            signals.add((negation if negation in NEGATIONS else token.lemma, content))
    return signals


def classify(
    score: float, configuration: AnalysisSettings, *, missing_required: bool, critical: bool, negation: bool
) -> Category:
    if critical or score < configuration.low_threshold:
        return Category.LOW_MATCH
    if missing_required or negation or score < configuration.high_threshold:
        return Category.NEEDS_REVIEW
    return Category.HIGH_MATCH


def analyze(
    provider: Provider,
    answer: str,
    candidates: list[Candidate],
    similarities: list[float],
    configuration: AnalysisSettings,
) -> Score:
    if not candidates or len(candidates) != len(similarities):
        raise ValueError("Candidate texts and similarities must correspond")
    answer_doc = provider.morphology(answer)
    sentences = lexical_sentences(answer_doc)
    surface_sentences = lexical_sentences(answer_doc, surface=True)
    answer_terms = lexical_set(answer_doc)
    shared_rules = list(
        {
            (rule.phrase, rule.kind, rule.message): rule
            for candidate in candidates
            for rule in candidate.rules
        }.values()
    )
    evaluated = []
    for candidate, semantic in zip(candidates, similarities, strict=True):
        evaluated.append(
            evaluate_candidate(
                provider,
                answer_doc,
                sentences,
                surface_sentences,
                answer_terms,
                candidate,
                semantic,
                configuration,
                shared_rules,
            )
        )
    best = max(
        evaluated,
        key=lambda item: (item.final_similarity, item.semantic_similarity, item.lexical_similarity),
    )
    comparisons = [
        {
            "reference_answer_id": item.candidate.reference_id,
            "variation_id": item.candidate.variation_id,
            "text": item.candidate.text,
            "semantic_similarity": item.semantic_similarity,
            "lexical_similarity": item.lexical_similarity,
            "concept_coverage": item.concept_coverage,
            "final_similarity": item.final_similarity,
            "raw_similarity": item.raw_similarity,
            "relevance": item.relevance,
            "category": item.category.value,
            "selected": item is best,
            "warnings": item.warnings,
            "matches": item.matches,
            "missing": item.missing,
            "concepts": [concept.model_dump() for concept in item.candidate.concepts],
            "conflict_rules": [rule.model_dump() for rule in shared_rules],
        }
        for item in evaluated
    ]
    return replace(best, comparisons=comparisons)


def evaluate_candidate(
    provider,
    answer_doc,
    sentences,
    surface_sentences,
    answer_terms,
    candidate,
    semantic,
    configuration,
    shared_rules,
):
    semantic = float(np.clip(semantic, 0, 1))
    candidate_doc = provider.morphology(candidate.text)
    terms = lexical_set(candidate_doc)
    union = answer_terms | terms
    lexical = len(answer_terms & terms) / len(union) if union else 0.0

    matches, missing, required_missing = [], [], []
    coverage_weight, total_weight = 0.0, 0.0
    for concept in candidate.concepts:
        total_weight += concept.importance_weight
        if any(
            matches_phrase(provider, form, sentences, surface_sentences)
            for form in (concept.concept, *concept.synonyms)
        ):
            coverage_weight += concept.importance_weight
            matches.append(concept.concept)
        else:
            missing.append(concept.concept)
            if concept.is_required:
                required_missing.append(concept.concept)
    coverage = coverage_weight / total_weight if total_weight else None

    warnings = [
        {"code": rule.kind, "message": rule.message, "evidence": rule.phrase, "critical": True}
        for rule in shared_rules
        if matches_phrase(provider, rule.phrase, sentences, surface_sentences)
    ]
    critical = bool(warnings)
    negation = configuration.detect_negation and bool(
        negation_signals(answer_doc) - negation_signals(candidate_doc)
    )
    if negation:
        warnings.append(
            {
                "code": "negation",
                "message": "Є заперечення, відмінне від формулювання з найвищою подібністю.",
                "critical": False,
            }
        )
    if required_missing:
        warnings.append(
            {
                "code": "required_concepts",
                "message": "У відповіді бракує обов’язкових понять.",
                "evidence": required_missing,
                "critical": False,
            }
        )

    score = semantic * configuration.semantic_weight + lexical * configuration.lexical_weight
    if coverage is None:
        score /= configuration.semantic_weight + configuration.lexical_weight
    else:
        score += coverage * configuration.concept_weight
    raw_similarity = min(1.0, max(0.0, score))
    shared_terms = sorted((answer_terms & terms) - GENERIC_CONTENT_TERMS - NEGATIONS)
    if critical:
        reason = "critical_conflict"
    elif semantic < RELEVANCE_POLICY["semantic_floor"]:
        reason = "insufficient_semantics"
    elif not (
        matches
        or len(shared_terms) >= RELEVANCE_POLICY["minimum_shared_terms"]
        or semantic >= RELEVANCE_POLICY["semantic_only_threshold"]
    ):
        reason = "no_content_evidence"
    else:
        reason = "supported"
    passed = reason == "supported"
    relevance = {"passed": passed, "reason": reason, "shared_terms": shared_terms}
    if not passed and not critical:
        warnings.append({
            "code": "off_topic",
            "message": "Не підтверджено змістового зв’язку з цим еталоном: випадкова подібність не додає балів.",
            "critical": False,
        })
    score = raw_similarity if passed else 0.0
    category = classify(
        score, configuration, missing_required=bool(required_missing), critical=critical, negation=negation
    ) if passed else Category.LOW_MATCH
    explanation = {
        Category.HIGH_MATCH: "Висока подібність до навчального еталона. Остаточне рішення ухвалює викладач.",
        Category.NEEDS_REVIEW: "Відповідь потребує ручної перевірки через подібність, повноту або змістові маркери.",
        Category.LOW_MATCH: "Зафіксовано низьку подібність або критичну змістову ознаку. Остаточне рішення ухвалює викладач.",
    }[category]
    if not passed:
        explanation = (
            "0%: виявлено критичну змістову суперечність із правилом перевірки. "
            if critical else "0%: змістового зв’язку відповіді з еталонами не підтверджено. "
        ) + "Випадкова векторна подібність не зараховується. Остаточне рішення ухвалює викладач."
    return Score(
        candidate, semantic, lexical, coverage, score, category, explanation, warnings, matches, missing,
        raw_similarity=raw_similarity, relevance=relevance,
    )
