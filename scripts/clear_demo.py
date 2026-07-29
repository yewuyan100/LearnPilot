import os
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from app.db.session import SessionLocal  # noqa: E402
from app.services.demo import clear_demo  # noqa: E402


def main() -> None:
    with SessionLocal() as db:
        count = clear_demo(db)
        print(f"已清理 {count} 个 Demo 学习目标及其关联数据")


if __name__ == "__main__":
    main()
