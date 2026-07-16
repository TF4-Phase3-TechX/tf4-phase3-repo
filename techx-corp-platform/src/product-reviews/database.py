#!/usr/bin/python

# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Python
import os
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

# Retrieve Postgres environment variables
db_connection_str = must_map_env('DB_CONNECTION_STRING')

# Initialize Threaded Connection Pool
db_pool = pool.ThreadedConnectionPool(minconn=1, maxconn=20, dsn=db_connection_str)

@contextmanager
def get_db_connection():
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
                # Define the SQL query
                query = "SELECT id, username, description, score FROM reviews.productreviews WHERE product_id= %s ORDER BY id"

                # Execute the query
                cursor.execute(query, (request_product_id, ))

                # Fetch all the rows from the query result
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

                # Execute the query
                cursor.execute(query, (request_product_id, ))

                # Fetch all the rows from the query result
                records = cursor.fetchall()

                # Extract the average score
                if records and records[0][0] is not None:
                    # records will be a list like [(average_score,)]
                    average_score = records[0][0]
                    # return the score as a string rounded to 1 decimal place
                    return f"{average_score:.1f}"
                else:
                    # Handle the case where no records are returned (e.g., no reviews for the product)
                    return None

    except Exception as e:
        raise e
