from dateutil import tz

# User preferences for scheduling
min_work_duration = "00:30" 
max_work_duration = "05:00"
timezone_str = "America/Vancouver"
timezone = tz.gettz(timezone_str)
start_time = "07:00"
end_time = "20:00"
notification_methods = ["popup", "email"]