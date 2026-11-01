"""Create the configured local database if missing; never replace an existing one."""
import os
from pathlib import Path

import psycopg
from psycopg import sql
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")
with psycopg.connect(
    dbname="postgres", user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"], host=os.getenv("DB_HOST", "localhost"),
    port=os.getenv("DB_PORT", "5432"), connect_timeout=5, autocommit=True,
) as connection:
    name = os.environ["DB_NAME"]
    if connection.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone():
        print("Configured database already exists; left unchanged.")
    else:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        print("Created configured database.")
