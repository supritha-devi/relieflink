import psycopg2

from db import get_connection


try:
    connection = get_connection()
    with connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            database_name = cursor.fetchone()[0]
    print(f"Connected to {database_name} successfully!")

except psycopg2.Error as error:
    print("Connection failed:")
    print(error)
    raise SystemExit(1) from error

finally:
    if "connection" in locals():
        connection.close()