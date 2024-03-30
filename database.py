import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv
import os

# Load the .env file
load_dotenv()

class MySQLDatabase:
    def __init__(self):
        """Initialize the database connection."""
        self.connection = None
        try:
            self.connection = mysql.connector.connect(
                host=os.environ.get("DB_HOST"),
                database=os.environ.get("DB_NAME"),
                user=os.environ.get("DB_USER"),
                password=os.environ.get("DB_PASS")
            )
            if self.connection.is_connected():
                print("MySQL Database connection successful")
        except Error as e:
            print(f"Error while connecting to MySQL: {e}")

    def execute_query(self, query, params=None):
        """Execute a query (insert, update, delete)."""
        cursor = self.connection.cursor(dictionary=True)
        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            self.connection.commit()
            print("Query executed successfully")
        except Error as e:
            print(f"Failed to execute query: {e}")
        finally:
            cursor.close()

    def execute_select_query(self, query, params=None):
        """Execute a select query."""
        cursor = self.connection.cursor(dictionary=True)
        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            result = cursor.fetchall()
            return result
        except Error as e:
            print(f"Failed to execute query: {e}")
        finally:
            cursor.close()

    def close(self):
        """Close the database connection."""
        if self.connection.is_connected():
            self.connection.close()
            print("MySQL connection is closed")