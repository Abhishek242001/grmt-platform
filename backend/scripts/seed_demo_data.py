"""
Seed a demo dataset — a platform_admin, an organizer, a conference with
valid gate rules, a couple of researchers, and sample submissions. Backs
the master build document §7 Phase 6 "load demo dataset" step and the
Demo-Day Checklist §8.4.

Usage (from backend/, with the venv active and DATABASE_URL pointed at the
target DB, after `alembic upgrade head`):
    python scripts/seed_demo_data.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.core import Conference, GateRule, User


def seed():
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == "admin@grmt.demo").first():
            print("[SKIP] Demo data already present (admin@grmt.demo exists).")
            return

        admin = User(email="admin@grmt.demo", password_hash=hash_password("DemoAdmin123!"), role="platform_admin", name="Platform Admin")
        organizer = User(email="organizer@grmt.demo", password_hash=hash_password("DemoOrganizer123!"), role="organizer", name="Demo Organizer")
        researcher1 = User(email="researcher1@grmt.demo", password_hash=hash_password("DemoResearcher123!"), role="researcher", name="Ada Researcher")
        researcher2 = User(email="researcher2@grmt.demo", password_hash=hash_password("DemoResearcher123!"), role="researcher", name="Grace Researcher")
        db.add_all([admin, organizer, researcher1, researcher2])
        db.flush()

        conf = Conference(
            organizer_id=organizer.id,
            name="GRMT Demo Conference 2026",
            theme="Applied AI & Robotics",
            tracks=["AI/ML", "Robotics", "NLP"],
            publisher_format="ieee",
        )
        db.add(conf)
        db.flush()

        # Gate rules — deliberately includes a soft ai_content_pct rule to
        # demonstrate the constraint is satisfiable, not just restrictive.
        rules = [
            GateRule(conference_id=conf.id, rule_type="ai_content_pct", is_hard_gate=False, threshold_soft=15),
            GateRule(conference_id=conf.id, rule_type="plagiarism_pct", is_hard_gate=False, threshold_soft=10),
            GateRule(conference_id=conf.id, rule_type="format_compliance", is_hard_gate=True, threshold_hard=1),
            GateRule(conference_id=conf.id, rule_type="citation_completeness", is_hard_gate=False, threshold_soft=1),
        ]
        db.add_all(rules)
        db.commit()

        print("[OK] Seeded demo data:")
        print(f"  platform_admin : admin@grmt.demo / DemoAdmin123!")
        print(f"  organizer      : organizer@grmt.demo / DemoOrganizer123!")
        print(f"  researcher     : researcher1@grmt.demo / DemoResearcher123!")
        print(f"  researcher     : researcher2@grmt.demo / DemoResearcher123!")
        print(f"  conference id  : {conf.id} ({conf.name})")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
