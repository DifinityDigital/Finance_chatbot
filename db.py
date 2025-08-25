
# from sqlalchemy import create_engine, inspect

# # Connect to DB
# engine = create_engine("sqlite:///finance.db")

# # Get inspector
# inspector = inspect(engine)

# # List tables
# tables = inspector.get_table_names()
# print("📊 Tables in DB:", tables)


# --------------------------------------------------------------------------------------------------------

# from sqlalchemy import inspect
# from sqlalchemy import create_engine, inspect

# engine = create_engine("sqlite:///finance.db")

# inspector = inspect(engine)
# columns = inspector.get_columns("actual_timesheet_data")
# print("📋 Columns in actual_timesheet_data:")
# for col in columns:
#     print(col['name'])


# ---------------------------------------------------------------------------------------------------------

import pandas as pd
from sqlalchemy import create_engine, inspect

# Connect to SQLite DB
engine = create_engine("sqlite:///finance.db")

engine = create_engine("sqlite:///memory.db")
inspector = inspect(engine)

# Get all table names
tables = inspector.get_table_names()
print("📊 Tables in DB:", tables)

# df = pd.read_sql("SELECT amount, amount_in_transaction_currency FROM actual_TB_data", con=engine)

# # Calculate sum of each column
# totals = df.sum()

# # Add totals as a new row with label 'Total'
# df.loc['Total'] = totals


# print(df)
# Show first 5 rows of each table
for table in tables:
    print(f"\n🔹 Preview of table: {table}")
    try:
        df = pd.read_sql(f"SELECT * FROM {table} ", con=engine)
        print(df)
    except Exception as e:
        print(f"❌ Error reading table {table}: {e}")

