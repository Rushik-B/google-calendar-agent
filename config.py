from dateutil import tz

# User preferences for scheduling
min_work_duration = "00:30" 
max_work_duration = "05:00"
timezone_str = "America/Vancouver"
timezone = tz.gettz(timezone_str)
start_time = "07:00"
end_time = "20:00"
notification_methods = ["popup", "email"]

# Standardized time period definitions
# Time ranges for different parts of the day (start_time, end_time)
time_periods = {
    "morning": {
        "start": "06:00",
        "end": "12:00",
        "default_time": "09:00"  # Default time to use when "morning" is mentioned
    },
    "afternoon": {
        "start": "12:00",
        "end": "18:00",
        "default_time": "14:00"  # Default time to use when "afternoon" is mentioned
    },
    "evening": {
        "start": "18:00",
        "end": "23:59",
        "default_time": "18:00"  # Default time to use when "evening" is mentioned
    },
    "night": {
        "start": "20:00",
        "end": "23:59",
        "default_time": "20:00"  # Default time to use when "night" is mentioned
    }
}

# Time thresholds for deadline constraints
# These define when a period ends for deadline purposes
deadline_thresholds = {
    'morning': (0, 0),   # Morning ends at midnight (start of day)
    'afternoon': (12, 0), # Afternoon ends at noon
    'evening': (18, 0),   # Evening ends at 6 PM
    'night': (22, 0)      # Night ends at 10 PM
}