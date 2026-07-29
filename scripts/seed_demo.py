import os
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from app.db.session import SessionLocal  # noqa: E402
from app.services.demo import seed_demo  # noqa: E402


def main() -> None:
    with SessionLocal() as db:
        goal = seed_demo(db)
        print(f"Demo 数据已就绪：goal_id={goal.id}, title={goal.title}")


if __name__ == "__main__":
    main()
