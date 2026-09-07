from sqlalchemy import text

from app.core.config import Settings
from app.db.session import build_engine


def main() -> None:
    engine = build_engine(Settings())
    try:
        with engine.connect() as connection:
            if connection.scalar(text("SELECT 1")) != 1:
                raise RuntimeError("Unexpected database probe result")
        print("PostgreSQL connection OK")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
