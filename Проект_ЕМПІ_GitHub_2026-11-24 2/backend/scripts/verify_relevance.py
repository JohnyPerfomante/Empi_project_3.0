"""Read-only real-model regression across every demo question; not an independent accuracy benchmark."""

import json
from collections import Counter

from app.core.config import settings
from app.nlp.analyzer import Candidate, analyze, cosine
from app.nlp.methodology import ALGORITHM_VERSION, RELEVANCE_POLICY
from app.nlp.provider import LocalProvider
from app.schemas.analysis import AnalysisSettings
from scripts.seed_demo import alternative_references, load_examples

UNRELATED_ANSWERS = [
    "Користувач вводить відповідь",
    "Я не знаю відповіді на це запитання.",
    "Садівник вирощує квіти й поливає город.",
    "Сьогодні гарна погода, а завтра я поїду відпочивати.",
    "Це дуже важливе питання, яке має багато різних правильних відповідей.",
]


def main():
    config = settings()
    if config.nlp_provider != "local":
        raise SystemExit("This diagnostic requires NLP_PROVIDER=local.")
    provider = LocalProvider(config)
    examples, alternatives = load_examples(), alternative_references()
    texts = list(dict.fromkeys([
        *UNRELATED_ANSWERS,
        *(text for item in examples for text in [item.reference, alternatives[item.question], item.correct, item.partial]),
    ]))
    vectors = dict(zip(texts, provider.encode(texts), strict=True))
    counts, issues, rows = Counter(), [], []
    for item in examples:
        reference_texts = [item.reference, alternatives[item.question]]
        for with_rubric in [True, False]:
            candidates = [Candidate(i, text, text, item.concepts if with_rubric else [], [])
                          for i, text in enumerate(reference_texts, 1)]
            cases = [('unrelated', answer) for answer in UNRELATED_ANSWERS]
            if with_rubric:
                cases.extend([('paraphrase', item.correct), ('partial', item.partial)])
                cases.extend(('reference', text) for text in reference_texts)
            for kind, answer in cases:
                result = analyze(provider, answer, candidates,
                                 [cosine(vectors[answer], vectors[c.text]) for c in candidates], AnalysisSettings())
                counts[kind] += 1
                valid = (result.final_similarity == 0 if kind == 'unrelated'
                         else result.final_similarity > 0 if kind == 'paraphrase'
                         else result.final_similarity > .99 if kind == 'reference' else True)
                row = {'question': item.question, 'kind': kind, 'rubric': with_rubric,
                       'answer': answer, 'score': round(result.final_similarity, 6),
                       'raw_score': round(result.raw_similarity, 6),
                       'category': result.category.value, 'reason': result.relevance['reason']}
                rows.append(row)
                if not valid:
                    issues.append(row)
    print(json.dumps({'algorithm': ALGORITHM_VERSION, 'policy': RELEVANCE_POLICY,
                      'model': provider.name, 'questions': len(examples), 'counts': counts,
                      'issues': issues, 'rows': rows}, ensure_ascii=False, indent=2))
    if issues:
        raise SystemExit('Real-model relevance regression failed; see issues above.')


if __name__ == '__main__':
    main()
