"""Queue outdated unreviewed answers once; preserve every analysis and teacher decision."""

import json

from sqlalchemy import or_, select

from app.database.session import session
from app.models import AnalysisResult, Submission, SubmissionStatus
from app.nlp.methodology import ALGORITHM_VERSION
from app.services.audit import audit
from app.services.submissions import with_status


def enqueue_unreviewed(db):
    query, latest, review = with_status(select(Submission))
    version = AnalysisResult.configuration_snapshot['algorithm_version'].as_string()
    query = (query.join(AnalysisResult, AnalysisResult.id == latest.c.id)
             .where(Submission.status == SubmissionStatus.ANALYZED, review.c.id.is_(None),
                    or_(version.is_(None), version != ALGORITHM_VERSION))
             .order_by(Submission.id).with_for_update(of=Submission, skip_locked=True))
    ids = []
    for record in db.scalars(query):
        record.status = SubmissionStatus.QUEUED
        record.lease_token = record.lease_until = None
        ids.append(record.id)
        audit(db, None, 'reanalyze_algorithm_upgrade', 'submission', record.id,
              algorithm_version=ALGORITHM_VERSION, reason='outdated_unreviewed_analysis')
    return ids


def main():
    with session() as db, db.begin():
        ids = enqueue_unreviewed(db)
    print(json.dumps({'algorithm': ALGORITHM_VERSION, 'queued': len(ids), 'submission_ids': ids}))


if __name__ == '__main__':
    main()
