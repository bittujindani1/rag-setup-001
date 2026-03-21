import requests
from fastapi import FastAPI, HTTPException
import json
import logging
import os
from typing import List
from typing import Dict, Optional

from env_bootstrap import bootstrap_env

bootstrap_env()


SQL_SERVER = os.getenv("SQL_SERVER")
SQL_DATABASE = os.getenv("SQL_DATABASE")

CONNECTOR_SQL_USERNAME = os.getenv("CONNECTOR_SQL_USERNAME")
CONNECTOR_SQL_PASSWORD = os.getenv("CONNECTOR_SQL_PASSWORD")

CONNECTOR_SQL_READ = os.getenv("CONNECTOR_SQL_READ")
CONNECTOR_SQL_INSERT = os.getenv("CONNECTOR_SQL_INSERT")
CONNECTOR_SQL_DELETE = os.getenv("CONNECTOR_SQL_DELETE")
CONNECTOR_SQL_UPDATE = os.getenv("CONNECTOR_SQL_UPDATE")


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from column_list import COLUMNS_FOR_CONVERSATION
# Construct SQL Query
def construct_sql_query_for_fetchall(schema: str, TableName: str, column: str, value: str) -> str:
    return f"SELECT * FROM {schema}.{TableName} WHERE {column} = '{value}';"

# Define the query constructor for filtering and sorting
def construct_sql_query_for_conversation(schema: str, TableName: str, column: str, value: str, order_by_column: str, order: str = 'ASC') -> str:
    """
    Construct SQL query to select rows from a table where a column matches a specific value, ordered by another column.
    """
    columns_joined = ', '.join(COLUMNS_FOR_CONVERSATION)
    return f"SELECT {columns_joined} FROM {schema}.{TableName} WHERE {column} = '{value}' ORDER BY {order_by_column} {order};"


# Construct SQL Query
def construct_sql_query_for_dashboard(schema: str, TableName: str, columns: List[str], order_by_column: str, order: str = 'DESC') -> str:
    columns_joined = ', '.join(columns)
    return f"SELECT {columns_joined} FROM {schema}.{TableName} ORDER BY {order_by_column} {order};"


# Perform SQL read query
def perform_sql_query(server: str, charset: str, database: str, schema: str, TableName: str, user_query: str):
    endpoint = CONNECTOR_SQL_READ

    # Correct request payload for the read request
    request_body = {
        "server": server,
        "serverid": 0,
        "username": CONNECTOR_SQL_USERNAME,
        "password": CONNECTOR_SQL_PASSWORD,
        "charset": charset,
        "database": database,
        "schema": schema,
        "TableName": TableName,
        "user_query": user_query
    }

    try:
        logger.info(f"Sending read request to {endpoint} with query: {user_query}")
        response = requests.post(endpoint, json=request_body)
        response.raise_for_status()
        
        # Check if the response contains data
        if response.status_code == 200 and response.json():
            return response.json()  # Return the result JSON directly
        else:
            logger.warning(f"No data found for query: {user_query}")
            return None  # Return None if the result is empty

    except requests.exceptions.RequestException as e:
        logger.error(f"SQL read request failed: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error performing SQL read: {str(e)}")
    





# Insert data into SQL table
def perform_sql_insert(server: str, charset: str, database: str, schema_: str, TableName: str, data_to_insert: dict):
    endpoint = CONNECTOR_SQL_INSERT

    request_body = {
        "server": server,
        "username": CONNECTOR_SQL_USERNAME,
        "password": CONNECTOR_SQL_PASSWORD,
        "charset": charset,
        "database": database,
        "schema": schema_,
        "TableName": TableName,
        "data_to_insert": [data_to_insert]  # Inserted as a list
    }

    try:
        logger.info(f"Sending insert request to {endpoint} with data: {data_to_insert}")
        response = requests.post(endpoint, json=request_body)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"SQL insert request failed: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error performing SQL insert: {str(e)}")







# Helper function to perform a SQL DELETE based on table, column, and value
def perform_sql_delete_on_input(server: str, charset: str, database: str, schema: str, TableName: str, column: str, value: str):
    sql_request_body = {
        "server": server,
        "username": CONNECTOR_SQL_USERNAME,
        "password": CONNECTOR_SQL_PASSWORD,
        "charset": charset,
        "database": database,
        "schema": schema,
        "TableName": TableName,
        "conditions": {column: value}
    }

    try:
        response = requests.post(CONNECTOR_SQL_DELETE, json=sql_request_body)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error deleting from {TableName} where {column} = {value}: {e}")
        raise HTTPException(status_code=400, detail=str(e))





# Update function
def perform_sql_update(server: str, charset: str, database: str, schema_: str, TableName: str, data_to_update: Dict, conditions: Dict):
    endpoint = CONNECTOR_SQL_UPDATE
    
    request_body = {
        "server": server,
        "username": CONNECTOR_SQL_USERNAME,
        "password": CONNECTOR_SQL_PASSWORD,
        "charset": charset,
        "database": database,
        "schema": schema_,
        "TableName": TableName,
        "data_to_update": data_to_update,
        "conditions": conditions
    }
    
    try:
        response = requests.post(endpoint, headers={'Content-Type': 'application/json'}, json=request_body)
        response.raise_for_status()  # Raise an HTTPError for bad responses
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=str(e))
    


# Define the query constructor for filtering and sorting for Assistant table
def construct_sql_query_for_assistant(schema: str, TableName: str, assistant_id_column: str, assistant_id_value: str, columns: list) -> str:
    """
    Construct SQL query to select a specific row from the Assistant table where assistant_id matches a specific value.
    """
    columns_joined = ', '.join(columns)
    return f"SELECT {columns_joined} FROM {schema}.{TableName} WHERE {assistant_id_column} = '{assistant_id_value}';"


# Define the query constructor for filtering and sorting for Chat table
def construct_sql_query_for_chat(schema: str, TableName: str, assistant_id_column: str, assistant_id_value: str, columns: list, order_by_column: str, order: str = 'ASC') -> str:
    """
    Construct SQL query to select rows from the Chat table where assistant_id matches a specific value, ordered by another column.
    """
    columns_joined = ', '.join(columns)
    return f"SELECT {columns_joined} FROM {schema}.{TableName} WHERE {assistant_id_column} = '{assistant_id_value}' ORDER BY {order_by_column} {order};"




# Dummy function placeholders for SQL query construction and execution
def construct_sql_query_with_filter(schema, TableName, column, value, columns, order_by_column=None, order=None):
    columns_str = ", ".join(columns)
    query = f"SELECT {columns_str} FROM {schema}.{TableName} WHERE {column} = '{value}'"
    if order_by_column and order:
        query += f" ORDER BY {order_by_column} {order}"
    return query

def construct_sql_query_for_pagination(schema, TableName, columns, order_by_column, order, offset, limit):
    columns_str = ", ".join(columns)
    query = f"SELECT {columns_str} FROM {schema}.{TableName} ORDER BY {order_by_column} {order} OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"
    return query




def update_assistant_project_id(server, charset, database, schema, old_project_id, new_project_id="007"):
    TableName = "assistant_config"
    data_to_update = {"project_id": new_project_id}
    conditions = {"project_id": old_project_id}

    logger.info(f"Attempting to update project_id from {old_project_id} to {new_project_id} in assistant_config table.")

    try:
        result = perform_sql_update(
            server=server,
            charset=charset,
            database=database,
            schema_=schema,
            TableName=TableName,
            data_to_update=data_to_update,
            conditions=conditions
        )
        logger.info(f"Successfully updated assistant_config for project_id {old_project_id} to {new_project_id}.")
        return result
    except HTTPException as e:
        logger.error(f"Failed to update assistant_config for project_id {old_project_id}. Error: {e.detail}")
        raise e

# Cascade delete function for Project type
def delete_project_with_cascade(server, charset, database, schema, project_id):
    placeholder_project_id = "007"  # Constant project ID to which orphaned assistants will be reassigned

    # Step 1: Update assistants to point to the placeholder project_id
    update_assistant_project_id(server, charset, database, schema, project_id, placeholder_project_id)

    # Step 2: Delete all files linked to this project_id
    perform_sql_delete_on_input(server, charset, database, schema, "files", "project_id", project_id)

    # Step 3: Delete the project from the project table
    perform_sql_delete_on_input(server, charset, database, schema, "project", "project_id", project_id)

    return {"status": "success", "message": f"Project {project_id} and related files have been deleted, and assistants have been reassigned."}


