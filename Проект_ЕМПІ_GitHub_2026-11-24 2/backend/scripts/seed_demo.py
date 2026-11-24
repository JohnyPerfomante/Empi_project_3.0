import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from app.core.config import ROOT, settings
from app.database.session import session
from app.models import (
    AnswerVariation,
    Course,
    CourseMembership,
    Question,
    QuestionStatus,
    ReferenceAnswer,
    ReferenceConcept,
    Role,
    Specialty,
    StudentGroup,
    Subject,
    Submission,
    TeacherCourse,
    User,
)
from app.nlp.text import reference_signature, text_digest
from app.schemas.catalog import ConceptIn, ReferenceIn
from app.security.auth import now, password_hasher
from app.services.audit import audit
from app.services.materials import save_reference

TOPICS = {
    "alg": "Алгоритми та структури даних",
    "oop": "Об’єктно-орієнтоване програмування",
    "db": "Бази даних",
    "os": "Операційні системи",
    "net": "Комп’ютерні мережі",
    "arch": "Архітектура комп’ютерів",
    "dev": "Технології розроблення ПЗ",
}
DEMO_DOMAIN = "demo.edu.ua"
YEAR = "2026/2027"
TEACHERS = {
    "alg": ("teacher.alg", "Ірина Кравченко"),
    "oop": ("teacher.oop", "Олег Савченко"),
    "db": ("teacher.db", "Наталія Романенко"),
    "os": ("teacher", "Олена Мельник"),
    "net": ("teacher.net", "Андрій Шевченко"),
    "arch": ("teacher.arch", "Марина Ткаченко"),
    "dev": ("teacher.dev", "Дмитро Мельничук"),
}


def alternative_references():
    return json.loads((ROOT / "database/seeds/reference_alternatives.json").read_text(encoding="utf-8"))


def ensure_reference(db, question_id, text, concepts):
    for reference in db.scalars(select(ReferenceAnswer).where(ReferenceAnswer.question_id == question_id)):
        if reference_signature(reference.text) == reference_signature(text):
            existing = {
                item.concept.casefold(): item
                for item in db.scalars(
                    select(ReferenceConcept).where(ReferenceConcept.reference_answer_id == reference.id)
                )
            }
            for concept in concepts:
                if row := existing.get(concept.concept.casefold()):
                    combined = list(dict.fromkeys([*row.synonyms, *concept.synonyms]))
                    if combined != row.synonyms:
                        row.synonyms = combined
                        reference.updated_at = now()
            return reference
    view = save_reference(db, question_id, ReferenceIn(text=text, concepts=concepts))
    return db.get(ReferenceAnswer, view.id)


@dataclass(frozen=True)
class Example:
    topic: str
    question: str
    reference: str
    concepts: list[ConceptIn]
    correct: str
    partial: str
    incorrect: str


def load_examples(path: Path = ROOT / "database" / "seeds" / "questions.tsv") -> list[Example]:
    records = []
    overrides = json.loads((ROOT / "database/seeds/concept_synonyms.json").read_text(encoding="utf-8"))
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        topic, question, reference, terms, correct, partial, incorrect = line.split("|")
        concepts = []
        for term in terms.split(";"):
            concept, *synonyms = term.split("~")
            extra = overrides.get(question, {}).get(concept, [])
            concepts.append(ConceptIn(concept=concept, synonyms=list(dict.fromkeys([*synonyms, *extra]))))
        records.append(Example(topic, question, reference, concepts, correct, partial, incorrect))
    return records


def get_or_create(db, model, values, **identity):
    record = db.scalar(select(model).filter_by(**identity))
    if record is None:
        record = model(**identity, **values)
        db.add(record)
        db.flush()
    return record


def main():
    config = settings()
    password = config.demo_password.get_secret_value()
    if config.app_env != "development" or not 12 <= len(password) <= 128:
        raise SystemExit(
            "Demo seed requires APP_ENV=development and DEMO_PASSWORD of at least 12 characters."
        )
    hashed = password_hasher.hash(password)
    with session() as db, db.begin():
        users = {}
        for handle, name, role in (
            ("admin", "Олександр Коваль", Role.ADMIN),
            ("teacher", "Олена Мельник", Role.TEACHER),
            ("student", "Марія Бондар", Role.STUDENT),
            ("student2", "Андрій Лисенко", Role.STUDENT),
            *((handle, name, Role.TEACHER) for handle, name in TEACHERS.values() if handle != "teacher"),
        ):
            users[handle] = get_or_create(
                db,
                User,
                dict(full_name=name, role=role, password_hash=hashed, demo=True),
                email=f"{handle}@{DEMO_DOMAIN}",
            )
            if not users[handle].demo:
                raise ValueError("Demo account address is already used by a regular account")
        engineering = get_or_create(db, Specialty, {"name": "Інженерія програмного забезпечення"}, code="ІПЗ")
        computers = get_or_create(db, Specialty, {"name": "Комп’ютерна інженерія"}, code="КН")
        courses = {}
        for topic, name in TOPICS.items():
            specialty = computers if topic in {"arch", "os", "net"} else engineering
            subject = get_or_create(
                db,
                Subject,
                {"description": "Демонстраційна навчальна дисципліна."},
                name=name,
                specialty_id=specialty.id,
            )
            course = get_or_create(
                db,
                Course,
                {"demo": True, "description": subject.description},
                name=name,
                subject_id=subject.id,
                academic_year=YEAR,
            )
            if not course.demo:
                raise ValueError("A regular course has the same identity as a demo course")
            group = get_or_create(
                db,
                StudentGroup,
                {},
                name=f"{specialty.code}-4",
                specialty_id=specialty.id,
                academic_year=YEAR,
            )
            teacher = users[TEACHERS[topic][0]]
            get_or_create(db, TeacherCourse, {}, teacher_id=teacher.id, course_id=course.id)
            if topic != "os":
                legacy = db.scalar(
                    select(TeacherCourse).where(
                        TeacherCourse.teacher_id == users["teacher"].id,
                        TeacherCourse.course_id == course.id,
                    )
                )
                if legacy and legacy.active:
                    legacy.active = False
                    audit(
                        db,
                        users["admin"].id,
                        "set_teacher_access",
                        "course",
                        course.id,
                        teacher_id=users["teacher"].id,
                        active=False,
                        reason="separate_subject_teachers",
                    )
            members = [
                get_or_create(
                    db,
                    CourseMembership,
                    {"group_id": group.id},
                    student_id=users[key].id,
                    course_id=course.id,
                )
                for key in ("student", "student2")
            ]
            courses[topic] = course, members, teacher
        examples = load_examples()
        alternatives = alternative_references()
        for index, example in enumerate(examples):
            course, members, teacher = courses[example.topic]
            question = get_or_create(
                db,
                Question,
                {"created_by": teacher.id, "demo": True, "status": QuestionStatus.PUBLISHED},
                course_id=course.id,
                text=example.question,
            )
            reference = ensure_reference(db, question.id, example.reference, example.concepts)
            ensure_reference(db, question.id, alternatives[example.question], example.concepts)
            get_or_create(
                db,
                AnswerVariation,
                {"text": example.correct, "created_by": teacher.id, "demo": True},
                reference_answer_id=reference.id,
                text_digest=text_digest(example.correct),
            )
            if index % 2 == 0:
                member = members[(index // 2) % 2]
                answer = (example.correct, example.partial, example.incorrect)[(index // 2) % 3]
                get_or_create(
                    db,
                    Submission,
                    {
                        "question_text": question.text,
                        "answer_text": answer,
                        "membership_id": member.id,
                        "group_id": member.group_id,
                        "created_at": now() - timedelta(days=(index * 3) % 27),
                    },
                    student_id=member.student_id,
                    question_id=question.id,
                    request_id=f"00000000-0000-4000-8000-{index:012d}",
                )
    print(f"DEMO: {len(examples)} questions with 2 references, {len(TOPICS)} subject teachers and courses.")


if __name__ == "__main__":
    main()
