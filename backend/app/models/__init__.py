"""
Import every model module here so Base.metadata.create_all() / Alembic
autogenerate sees the full schema regardless of which module first imports
`app.models`.
"""
from app.models.core import Conference, ConferenceCoadmin, ConferenceReviewer, GateRule, User  # noqa: F401
from app.models.submissions import (  # noqa: F401
    AIReport,
    CrossConferenceLink,
    Notification,
    PlagiarismMatch,
    Review,
    ReviewerAssignment,
    Submission,
    SubmissionVersion,
)
from app.models.platform import (  # noqa: F401
    AuditLog,
    FlagFeedback,
    ModelUsageLog,
    PDFAnnotation,
    PublisherFormatRule,
    ReferenceCorpusPaper,
    SystemSetting,
    TestRun,
)
