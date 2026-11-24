"""Complete known demonstration questions without replacing any existing material or history."""

from sqlalchemy import func, select

from app.database.session import session
from app.models import Question, QuestionStatus, ReferenceAnswer
from app.nlp.text import reference_signature
from app.schemas.catalog import ReferenceIn
from app.services.audit import audit
from app.services.materials import save_reference
from scripts.seed_demo import main as seed_demo

QA_REFERENCE = "Операційна система керує апаратними ресурсами і запускає прикладні програми."
QA_ALTERNATIVE = (
    "ОС розподіляє процесорний час, пам’ять та пристрої між програмами й організовує "
    "їх виконання, забезпечуючи роботу користувача з комп’ютером."
)


def main():
    seed_demo()
    with session() as db, db.begin():
        query = select(Question).where(Question.status == QuestionStatus.PUBLISHED)
        unresolved = []
        for question in db.scalars(query):
            references = list(
                db.scalars(
                    select(ReferenceAnswer).where(
                        ReferenceAnswer.question_id == question.id,
                    )
                )
            )
            if len({reference_signature(item.text) for item in references}) >= 2:
                continue
            if question.text.startswith("Як операційна система керує ресурсами? QA ") and any(
                reference_signature(item.text) == reference_signature(QA_REFERENCE) for item in references
            ):
                view = save_reference(db, question.id, ReferenceIn(text=QA_ALTERNATIVE))
                audit(
                    db,
                    None,
                    "create",
                    "reference_answer",
                    view.id,
                    question_id=question.id,
                    reason="second_reference_for_existing_qa_example",
                )
            else:
                unresolved.append(question.id)
        if unresolved:
            raise ValueError(f"Add a second reviewed reference manually for questions: {unresolved}")
        count = db.scalar(select(func.count(Question.id)))
    print(f"Verified references for existing published questions; {count} total questions preserved.")


if __name__ == "__main__":
    main()
