"""Clears every table EXCEPT users and api_provider_configs, for a clean
end-to-end test slate without needing to re-create accounts or re-enter
the Winston API key. Deletes in child-to-parent order to respect foreign
keys. Also removes uploaded submission files on disk, since those become
orphaned once their DB rows are gone.

PRESERVED: users, api_provider_configs (your accounts + the Winston key)
CLEARED: everything else + uploaded files on disk.
"""
import shutil

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.admin import ApiUsageLog
from app.models.conferences import Conference, ConferenceCoAdmin, ConferenceReviewer, GateRule
from app.models.submissions import (
    AIReport,
    Decision,
    PDFAnnotation,
    Review,
    Submission,
    SubmissionReviewerAssignment,
    SubmissionVersion,
)


def main():
    db = SessionLocal()
    try:
        counts = {}
        for model in [
            PDFAnnotation,
            SubmissionReviewerAssignment,
            Decision,
            Review,
            AIReport,
            SubmissionVersion,
            Submission,
            GateRule,
            ConferenceReviewer,
            ConferenceCoAdmin,
            Conference,
            ApiUsageLog,
        ]:
            counts[model.__tablename__] = db.query(model).delete()
        db.commit()

        print("[ok] cleared:")
        for table, n in counts.items():
            print(f"     {table}: {n} row(s)")
        print("[ok] preserved: users, api_provider_configs (your accounts + stored API keys)")

        upload_dir = f"{settings.upload_root}/submissions"
        try:
            shutil.rmtree(upload_dir)
            print(f"[ok] removed uploaded submission files under {upload_dir}")
        except FileNotFoundError:
            print(f"[ok] no uploaded files directory found at {upload_dir} — nothing to remove")
    finally:
        db.close()


if __name__ == "__main__":
    main()
