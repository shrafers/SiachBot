import os, sys
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(os.environ["DATABASE_URL"])
conn.autocommit = True
cur = conn.cursor()

sql_file = sys.argv[1] if len(sys.argv) > 1 else None
sql = open(sql_file).read() if sql_file else sys.stdin.read()

cur.execute(sql)
print("✅ SQL executed successfully")
conn.close()