from fastapi import APIRouter

from app.nlp.methodology import ALGORITHM_VERSION, FORMULAS, RELEVANCE_POLICY, SOURCES
from app.security.auth import DB, Staff
from app.services.access import get_course
from app.services.configuration import analysis_config

router = APIRouter(tags=["Методика перевірки"])


@router.get("/analysis/methodology")
def methodology(db: DB, actor: Staff, course_id: int | None = None):
    course = get_course(db, actor, course_id) if course_id is not None else None
    config = analysis_config(db, course)
    example = {"semantic": 0.85, "lexical": 0.50, "coverage": 0.75}
    raw_score = round(
        example["semantic"] * config.semantic_weight
        + example["lexical"] * config.lexical_weight
        + example["coverage"] * config.concept_weight,
        6,
    )
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "minimum_references": 2,
        "formulas": FORMULAS,
        "sources": SOURCES,
        "configuration": config.model_dump(),
        "relevance_policy": RELEVANCE_POLICY,
        "steps": [
            "Нормалізувати український текст і порівняти його з кожним еталоном та затвердженою варіацією.",
            "Для кожного кандидата обчислити S, L, C та початкову зважену подібність B.",
            "Перевірити змістовий зв’язок G: загальних слів і слабкого косинуса недостатньо; критична суперечність обнуляє результат.",
            "Отримати F = G × B для кожного кандидата; вибрати найбільший F, а не додавати бали різних еталонів.",
            "За всіма F = 0 показати 0% і причину; за часткової відповідності або заперечення рекомендувати ручну перевірку.",
        ],
        "example": {
            **example,
            "raw_score": raw_score,
            "gate": 1,
            "score": raw_score,
        },
        "unrelated_example": {
            "answer": "Користувач вводить відповідь",
            "question": "Що таке REST API?",
            "semantic": 0.24,
            "lexical": 0,
            "coverage": 0,
            "raw_score": round(0.24 * config.semantic_weight, 6),
            "gate": 0,
            "score": 0,
            "note": "Ілюстративні числа пояснюють арифметику, а не відтворюють конкретний знімок моделі. "
            "Поняття та спільні предметні терміни відсутні, семантика слабка, тому жоден еталон не дає балів.",
        },
        "interpretation": "Індекс відповідності не є ймовірністю правильності чи автоматичною оцінкою. "
        "Непідтверджений змістовий зв’язок або критична суперечність дає 0% і LOW_MATCH для цього кандидата. "
        "Сторонній текст не отримує балів за випадкову векторну подібність. "
        "Пропущені обов’язкові поняття або нове заперечення не дозволяють HIGH_MATCH. "
        "Нуль означає відсутність підтвердженої відповідності за правилами алгоритму; "
        "це не математичний доказ хибності будь-якого довільного тексту. Остаточне рішення ухвалює викладач.",
        "length_policy": "Довжина використовується лише для перевірки допустимого введення. "
        "Кількість символів не входить до жодної формули індексу відповідності.",
    }
