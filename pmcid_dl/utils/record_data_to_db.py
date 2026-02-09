import json


# Create empty table
def create_tables(
    conn,
    table_sections,
    table_status,
    table_metadata,
):
    c = conn.cursor()

    c.execute(
        f"""CREATE TABLE IF NOT EXISTS "{table_sections}" (
	            "pmcid"	TEXT NOT NULL,
                PRIMARY KEY("pmcid")
            )"""
    )
    conn.commit()
    c.execute(
        f"""CREATE TABLE IF NOT EXISTS "{table_metadata}" (
                "pmcid"	TEXT,
	            FOREIGN KEY("pmcid") REFERENCES "{table_sections}"("pmcid")
            )"""
    )
    conn.commit()
    c.execute(
        f"""CREATE TABLE IF NOT EXISTS "{table_status}" (
            "pmcid" TEXT NOT NULL,
            FOREIGN KEY("pmcid") REFERENCES "{table_sections}"("pmcid")
            )"""
    )
    conn.commit()


def ensure_column_exists(conn, table, column_name):
    c = conn.cursor()
    c.execute(f"PRAGMA table_info({table})")
    existing_columns = [column[1] for column in c.fetchall()]

    if column_name not in existing_columns:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column_name} TEXT")
        conn.commit()


def flatten_dict(d, parent_key="", sep="_"):
    return_dict = {}
    for k in d:
        if parent_key:
            new_key = f"{parent_key}{sep}{k}"
        else:
            new_key = k
        if isinstance(d[k], dict):
            return_dict.update(flatten_dict(d[k], new_key, sep=sep))
        else:
            return_dict[k] = d[k]
    return return_dict


def commit_to_database(conn, pmcid, table, results):
    # Ensure all the dict are flatten to work with SQL
    results = flatten_dict(results)
    results["pmcid"] = pmcid
    # Ensure the table has the necessary columns
    for key in results:
        # Check if it is a list:
        if isinstance(results[key], list):
            results[key] = json.dumps(results[key])
        ensure_column_exists(conn, table, key)
    sql_query = f"""
    INSERT OR REPLACE INTO {table} ({', '.join([k for k in results])}) VALUES ({', '.join(['?' for _ in results])})
    """
    c = conn.cursor()
    c.execute(sql_query, tuple(results.values()))
    conn.commit()


def analyze_database(conn, table):
    # Get the list of columns from the status table
    c = conn.cursor()
    c.execute(f"PRAGMA table_info({table});")
    columns_info = c.fetchall()

    # Extract the column names excluding 'pmcid' and 'api_response'
    columns_to_analyze = [
        column[1]
        for column in columns_info
        if column[1] not in ("pmcid", "api_response")
    ]

    results = {}

    # Analyze each column
    for column in columns_to_analyze:
        # Query the counts of 1, 0, and NULL for the column
        query = f"""
            SELECT
                SUM(CASE WHEN "{column}" = 1 THEN 1 ELSE 0 END) as ones,
                SUM(CASE WHEN "{column}" = 0 THEN 1 ELSE 0 END) as zeros,
                SUM(CASE WHEN "{column}" IS NULL THEN 1 ELSE 0 END) as nulls
            FROM status;
        """
        c.execute(query)
        row = c.fetchone()
        ones, zeros, nulls = row
        try:
            proportion = round(ones/(ones+zeros+nulls), 2)
        except ZeroDivisionError:
            proportion = 0
        results[column] = {"recorded": ones, "not recorded": zeros, "NULLs": nulls, 'proportion': proportion}

    # Count distinct api_response values
    c.execute("SELECT api_response, COUNT(api_response) FROM status GROUP BY api_response;")
    distinct_api_response_count = c.fetchall()
    # for code in distinct_api_response_count:
    #     print(code)
    distinct_api_response_counts = {code: count for code, count in distinct_api_response_count}
    results["distinct_api_response"] = distinct_api_response_counts

    # Close the database connection
    conn.close()

    return results
