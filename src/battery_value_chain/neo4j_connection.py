"""Connection helpers for the Neo4j Aura database."""

import os

from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase


def create_driver() -> Driver:
    """Load local configuration and create an authenticated Neo4j driver."""
    load_dotenv()
    uri = os.getenv("NEO4J_URI")
    username = os.getenv("NEO4J_USERNAME")
    password = os.getenv("NEO4J_PASSWORD")
    missing = [
        name
        for name, value in (
            ("NEO4J_URI", uri),
            ("NEO4J_USERNAME", username),
            ("NEO4J_PASSWORD", password),
        )
        if not value or value == "replace-with-your-aura-password"
    ]
    if missing:
        raise RuntimeError(f"Missing Neo4j configuration: {', '.join(missing)}")
    return GraphDatabase.driver(uri, auth=(username, password))


def verify_connection() -> int:
    """Verify Aura connectivity and return the database response value."""
    driver = create_driver()
    try:
        driver.verify_connectivity()
        record = driver.execute_query("RETURN 1 AS ok").records[0]
        return record["ok"]
    finally:
        driver.close()


if __name__ == "__main__":
    result = verify_connection()
    print(f"Neo4j connection verified: RETURN 1 AS ok -> {result}")