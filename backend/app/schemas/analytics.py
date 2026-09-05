from pydantic import BaseModel


class ConferenceAnalytics(BaseModel):
    conference_id: str
    total_submissions: int
    submissions_by_status: dict[str, int]
    total_reviews_submitted: int
    total_decisions_made: int
    average_reviews_per_submission: float
