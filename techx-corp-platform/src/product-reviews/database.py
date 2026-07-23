#!/usr/bin/python

# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Python
import os
import simplejson as json

# Postgres
import psycopg2
from psycopg2 import pool as pg_pool

def must_map_env(key: str):
    value = os.environ.get(key)
    if value is None:
        raise Exception(f'{key} environment variable must be set')
    return value

# Retrieve Postgres environment variables
db_connection_str = must_map_env('DB_CONNECTION_STRING')

# TC-02: Replace per-query psycopg2.connect() with a ThreadedConnectionPool.
# Previously, each query opened a new TCP+TLS connection to RDS — extremely expensive.
# At 75 users, RDS CPU spiked to ~100% just handling connection setup/teardown,
# pushing query latency from ~20ms to >1.5s and breaking SLO.
# Pool reuses existing connections, expected to drop query latency back to <20ms.
_db_pool = pg_pool.ThreadedConnectionPool(
    minconn=5,
    maxconn=50,  # matches gRPC max_workers=50 (TC-03) so no thread ever waits for a conn
    dsn=db_connection_str,
)

class DBConnection:
    """Context manager that safely borrows a connection from the pool.

    On exit it always rolls back any open transaction before returning the
    connection, preventing idle-in-transaction state from leaking into the pool.
    """
    def __enter__(self):
        self.conn = _db_pool.getconn()
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.conn.rollback()  # ensure clean transaction state before returning
        except Exception:
            pass
        _db_pool.putconn(self.conn)
        return False  # do not suppress exceptions

def fetch_product_reviews(product_id):
    try:
        return json.dumps(fetch_product_reviews_from_db(product_id), use_decimal=True)
    except Exception as e:
        return json.dumps({"error": str(e)})

def fetch_product_reviews_from_db(request_product_id):
    with DBConnection() as connection:
        with connection.cursor() as cursor:
            # Define the SQL query
            query = "SELECT id, username, description, score FROM reviews.productreviews WHERE product_id= %s ORDER BY id"

            # Execute the query
            cursor.execute(query, (request_product_id, ))

            # Fetch all the rows from the query result
            records = cursor.fetchall()
            return records

def fetch_avg_product_review_score_from_db(request_product_id):
    with DBConnection() as connection:
        with connection.cursor() as cursor:
            # Define the SQL query
            query = "SELECT AVG(score) FROM reviews.productreviews WHERE product_id= %s"

            # Execute the query
            cursor.execute(query, (request_product_id, ))

            # Fetch all the rows from the query result
            records = cursor.fetchall()

            # Extract the average score
            if records:
                # records will be a list like [(average_score,)]
                average_score = records[0][0]
            else:
                # Handle the case where no records are returned (e.g., no reviews for the product)
                average_score = None

            # return the score as a string rounded to 1 decimal place
            return f"{average_score:.1f}"
