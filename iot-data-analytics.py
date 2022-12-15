import mysql.connector
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# connect to sql database
db = mysql.connector.connect(
    db="jordandalby_iot",
    host="ysjcs.net",
    port=3306,
    user="redacted",
    password="redacted"
)

cursor = db.cursor()

def create_attendance_graph(module_id):
    # find all timetable_entries for the module
    cursor.execute(f"SELECT * FROM timetable_entries WHERE module_id={module_id}")
    result = cursor.fetchall()

    dates = []

    present = []
    late = []

    for timetable_data in result:
        dates.append(timetable_data[2])
        timetable_id = timetable_data[0]

        cursor.execute(f"SELECT * FROM attendance WHERE timetable_entry_id={timetable_id}")
        attendance_result = cursor.fetchall()

        present_count = int(0)
        late_count = int(0)
        for attendance_data in attendance_result:
            if attendance_data[4] == "PRESENT":
                present_count += 1
            elif attendance_data[4] == "LATE":
                late_count += 1
        
        present.append(present_count)
        late.append(late_count)

    frame = pd.DataFrame({'On-time':present, 'Late':late}, index=dates)

    print(frame.dtypes)
    print(frame)
    
    plot = frame.plot.bar(rot=0, stacked=True)
    plt.show()

create_attendance_graph(1)