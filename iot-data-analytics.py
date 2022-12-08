import mysql.connector
from datetime import datetime
import pandas

# connect to sql database
db = mysql.connector.connect(
    db="jordandalby_iot",
    host="ysjcs.net",
    port=3306,
    user="redacted",
    password="redacted"
)

cursor = db.cursor()