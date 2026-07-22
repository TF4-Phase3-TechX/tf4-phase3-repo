#!/usr/bin/python

# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Python
import os
import time
import logging
import simplejson as json

# Postgres
import psycopg2
from psycopg2 import pool
from contextlib import contextmanager

def must_map_env(key: str):
    value = os.environ.get(key)
    if value is None:
        raise Exception(f'{key} environment variable must be set')
    return value

db_connection_str = must_map_env('DB_CONNECTION_STRING')
db_max_conn = int(os.getenv("DB_MAX_CONN", "20"))

_db_pool = None

def get_pool():
    global _db_pool
    if _db_pool is None:
        try:
            _db_pool = pool.ThreadedConnectionPool(
                minconn=0, 
                maxconn=db_max_conn, 
                dsn=db_connection_str
            )
            logging.info(f"Database connection pool initialized (maxconn={db_max_conn}).")
        except Exception as e:
            logging.error(f"Failed to initialize connection pool: {e}")
            raise
    return _db_pool


@contextmanager
def get_db_connection():
    """Context manager để mượn và trả kết nối tự động từ Pool."""
    conn = None
    retries = 3
    for _ in range(retries):
        try:
            conn = get_pool().getconn()
            break
        except pool.PoolError:
            logging.warning("Hết kết nối trong Pool, chờ 1.5 giây để thử lại...")
            time.sleep(1.5)
            
    if not conn:
        raise pool.PoolError("Không thể lấy kết nối từ Database sau nhiều lần thử.")

    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        get_pool().putconn(conn)


def fetch_product_reviews(product_id):
    try:
        return json.dumps(fetch_product_reviews_from_db(product_id), use_decimal=True)
    except Exception as e:
        return json.dumps({"error": str(e)})


def fetch_product_reviews_from_db(request_product_id):
    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                query = "SELECT id, username, description, score FROM reviews.productreviews WHERE product_id= %s ORDER BY id"
                cursor.execute(query, (request_product_id, ))
                records = cursor.fetchall()
                return records
    except Exception as e:
        raise e


def fetch_avg_product_review_score_from_db(request_product_id):
    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                # Define the SQL query
                query = "SELECT AVG(score) FROM reviews.productreviews WHERE product_id= %s"
                cursor.execute(query, (request_product_id, ))
                records = cursor.fetchall()

                # Extract the average score
                if records and records[0][0] is not None:
                    average_score = records[0][0]
                else:
                    average_score = None

                # return the score as a string rounded to 1 decimal place
                if average_score is not None:
                    return f"{average_score:.1f}"
                return None
    except Exception as e:
        raise e
