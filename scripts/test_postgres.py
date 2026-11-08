import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"


def main() -> None:
    """验证Python应用能够连接ResearchFlow PostgreSQL。"""
    load_dotenv(
        dotenv_path=ENV_FILE,
        override=False,
    )

    postgres_uri = os.getenv("POSTGRES_URI")

    if not postgres_uri:
        raise RuntimeError(
            f"缺少POSTGRES_URI，请检查：{ENV_FILE}"
        )

    with psycopg.connect(postgres_uri) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    current_database(),
                    current_user,
                    current_setting('server_version');
                """
            )
            database, user, version = cursor.fetchone()

    print("PostgreSQL连接成功")
    print(f"数据库：{database}")
    print(f"用户：{user}")
    print(f"版本：{version}")


if __name__ == "__main__":
    main()
