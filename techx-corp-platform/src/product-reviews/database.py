#!/usr/bin/python

# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Python
import os
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


try:
    db_pool = pool.ThreadedConnectionPool(
        minconn=1, 
        maxconn=20, 
        dsn=db_connection_str
    )
    logging.info("Khởi tạo ThreadedConnectionPool thành công (maxconn=20).")
except Exception as e:
    logging.critical(f"Lỗi khởi tạo DB Pool: {e}")
    raise e


@contextmanager
def get_db_connection():
    """Context manager để mượn và trả kết nối tự động từ Pool."""
    conn = db_pool.getconn()
    try:
        yield conn
    finally:
        db_pool.putconn(conn)


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
