from flask import Flask, request, jsonify
from flask_cors import CORS
import datetime
import os.path
import json
import logging
from dateutil.parser import parse as dateutil_parse
from dateutil.relativedelta import relativedelta
from dateutil import tz
import google.generativeai as genai
from dotenv import load_dotenv

# Import calendar utility functions
from calendar_utils import (
    get_credentials,
    normalize_date_time,
    calculate_end_time,
    get_calendar_id,
    get_color_from_calendar_id,
    generate_humanized_view_response,
    set_user_preferred_calendars,
    fetch_events,
    extract_time_from_query
)

# Configure logging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Suppress Google API client logs
logging.getLogger('googleapiclient').setLevel(logging.ERROR)
logging.getLogger('google_auth_oauthlib').setLevel(logging.ERROR)
logging.getLogger('google.auth').setLevel(logging.ERROR)

# Global User Preferences
PREF_FILE = "preferences.json"
user_preferred_calendars = []

# Load preferences from file on startup
def load_preferences():
    global user_preferred_calendars
    if os.path.exists(PREF_FILE):
        try:
            with open(PREF_FILE, 'r') as f:
                user_preferred_calendars = json.load(f)
            logger.info(f"Loaded preferences from {PREF_FILE}: {user_preferred_calendars}")
            # Update the user_preferred_calendars in calendar_utils
            set_user_preferred_calendars(user_preferred_calendars)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading preferences from {PREF_FILE}: {e}")
            user_preferred_calendars = []

load_preferences()

# Import user preferences from config file
from config import min_work_duration, max_work_duration, timezone_str, timezone, start_time, end_time, notification_methods

# Load environment variables
load_dotenv()

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

app = Flask(__name__)
CORS(app)

# Import the necessary Google API libraries after the app is initialized
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# No need to redefine these functions since they're imported from calendar_utils:
# - get_credentials()
# - normalize_date_time()
# - calculate_end_time()
# - get_calendar_id()
# - get_color_from_calendar_id()
# - fetch_events()

def parse_and_validate_inputs(date_range, start_time, end_time):
    """Parse and validate the date range and time inputs."""
    if " to " in date_range:
        start_date_str, end_date_str = date_range.split(" to ")
    else:
        start_date_str = date_range
        end_date_str = date_range
    try:
        start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Invalid date format in date_range. Use 'YYYY-MM-DD' or 'YYYY-MM-DD to YYYY-MM-DD'")

    if start_date > end_date:
        raise ValueError("Start date cannot be after end date")

    try:
        start_time_obj = datetime.datetime.strptime(start_time, "%H:%M").time()
        end_time_obj = datetime.datetime.strptime(end_time, "%H:%M").time()
    except ValueError:
        raise ValueError("Invalid time format. Use 'HH:MM'")

    if start_time_obj >= end_time_obj:
        raise ValueError("start_time must be before end_time")

    return start_date, end_date, start_time_obj, end_time_obj

def calculate_free_slots_for_day(day, start_time, end_time, events, current_datetime, tz):
    """Calculate free time slots for a single day."""
    day_start = datetime.datetime.combine(day, start_time).replace(tzinfo=tz)
    day_end = datetime.datetime.combine(day, end_time).replace(tzinfo=tz)

    pointer = day_start
    if day == current_datetime.date():
        current_in_tz = current_datetime.astimezone(tz)
        if current_in_tz > day_start:
            pointer = current_in_tz
        if pointer >= day_end:
            return []  # No free slots if current time is after day_end

    busy_intervals = []
    for event in events:
        ev_start = dateutil_parse(event['start']['dateTime']).astimezone(tz)
        ev_end = dateutil_parse(event['end']['dateTime']).astimezone(tz)
        if ev_end <= day_start or ev_start >= day_end:
            continue
        busy_start = max(ev_start, day_start)
        busy_end = min(ev_end, day_end)
        busy_intervals.append((busy_start, busy_end))

    # Sort and merge overlapping busy intervals
    busy_intervals.sort(key=lambda x: x[0])
    merged_busy = []
    for interval in busy_intervals:
        if not merged_busy:
            merged_busy.append(interval)
        else:
            last_start, last_end = merged_busy[-1]
            if interval[0] <= last_end:
                merged_busy[-1] = (last_start, max(last_end, interval[1]))
            else:
                merged_busy.append(interval)

    free_slots = []
    for interval in merged_busy:
        busy_start, busy_end = interval
        if pointer < busy_start:
            free_slots.append((pointer, busy_start))
        pointer = max(pointer, busy_end)
    if pointer < day_end:
        free_slots.append((pointer, day_end))

    return free_slots

def format_free_slots(free_slots):
    """Format free slots into a list of dictionaries."""
    formatted = []
    for start, end in free_slots:
        duration_minutes = int((end - start).total_seconds() / 60)
        formatted.append({
            "start": start.isoformat(),
            "end": end.isoformat(),
            "duration_minutes": duration_minutes,
            "day": start.strftime("%Y-%m-%d"),
            "start_time": start.strftime("%H:%M"),
            "end_time": end.strftime("%H:%M")
        })
    return formatted

def find_time_helper(date_range, start_time="08:00", end_time="21:00", calendarIds=None):
    """Find all available free time slots in the given date range and daily time window."""
    try:
        creds = get_credentials()  # Using imported function
        service = build("calendar", "v3", credentials=creds)

        tz_obj = timezone
        current_datetime = datetime.datetime.now(tz_obj)

        start_date, end_date, start_time_obj, end_time_obj = parse_and_validate_inputs(date_range, start_time, end_time)

        # Create timezone-aware datetime objects
        time_min = datetime.datetime.combine(start_date, datetime.time(0, 0)).replace(tzinfo=tz_obj).isoformat()
        time_max = datetime.datetime.combine(end_date, datetime.time(23, 59, 59)).replace(tzinfo=tz_obj).isoformat()

        if calendarIds is None:
            calendarIds = [cal['id'] for cal in user_preferred_calendars] if user_preferred_calendars else ["primary"]

        all_events = fetch_events(service, calendarIds, time_min, time_max)  # Using imported function

        free_slots = []
        current_date = start_date
        while current_date <= end_date:
            daily_free_slots = calculate_free_slots_for_day(current_date, start_time_obj, end_time_obj, all_events, current_datetime, tz_obj)
            free_slots.extend(daily_free_slots)
            current_date += datetime.timedelta(days=1)

        formatted_free_slots = format_free_slots(free_slots)

        logger.info(f"Found {len(formatted_free_slots)} free time slots")
        return {
            "success": True,
            "free_slots": formatted_free_slots,
            "date_range": date_range,
            "daily_start_time": start_time,
            "daily_end_time": end_time,
            "total_free_slots": len(formatted_free_slots)
        }
    except Exception as e:
        logger.error(f"Error finding available time: {e}")
        return {
            "success": False,
            "message": f"Error finding available time: {str(e)}"
        }

def get_user_intent(natural_language):
    try:
        model = genai.GenerativeModel(model_name="gemini-2.0-flash")
        prompt = f"""
        Your job is to understand the user's intent from the text I am about to give you.
        The user is interacting with a calendar application which will allow the user to chat with their calendar, create events, delete events, 
        view their events, and find time in their calendar to schedule an event/ events.

        The possible intents are:
        1. Create event
        2. Delete event
        3. View events
        4. Find time to schedule event/ events
        
        return the intent as a string. The string should be one of the possible intents.
        
        Here is the text: "{natural_language}"  
        """


        logger.info(f"User's query: {natural_language}")

        
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Error getting user intent: {e}")
        return "Other"

def find_time(natural_language, start_time=start_time, end_time=end_time, work_duration=min_work_duration):
    try:
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        current_time = datetime.datetime.now().strftime("%H:%M")
        model = genai.GenerativeModel(model_name="gemini-2.0-flash")
        
        # Initialize variables
        busy_events = []
        
        # Extract total hours needed from request
        hours_extraction_prompt = f"""
        Extract ONLY the total hours or time needed from this text: "{natural_language}"
        
        Instructions:
        1. Look for phrases like "need X hours", "takes X hours", "around X hours", "X hours to finish", etc.
        2. Return just the number of hours as a float (e.g., "6" or "2.5")
        3. If no specific hours are mentioned, return "0"
        
        Return ONLY the number, nothing else.
        """
        
        hours_response = model.generate_content(hours_extraction_prompt)
        hours_text = hours_response.text.strip()
        
        try:
            requested_hours = float(hours_text)
            logger.info(f"Extracted requested hours: {requested_hours}")
        except ValueError:
            requested_hours = 0
            logger.warning(f"Could not parse requested hours from: {hours_text}")
            
        date_extraction_prompt = f"""
        Current date: {current_date}  
        Current time: {current_time}  

        Extract the relevant date or date range and time-of-day constraints from the following text: "{natural_language}".  

        ## Instructions:
        - The user is requesting time to work on a task with a deadline or time period.
        - IMPORTANT: When the user mentions a deadline or tasks "to be done by", "to be completed by", or "due by" a certain date, ALWAYS return a date range from today to that deadline.
        - The goal is to find available time slots to work on the task BEFORE the deadline.
        - If the user is asking about availability at a specific time (like "Am I free at 2 PM on Wednesday?"), return ONLY the DATE in YYYY-MM-DD format.

        ## Examples:
        1. **"Find me time to work on X on Monday."**  
        - Return: The date of the next Monday.  

        2. **"I have a project due on Friday and need to complete it by then."**  
        - Return: "{current_date} to [next Friday from {current_date}]"
        
        3. **"Am I free at 2 PM next Wednesday?"**
        - Return: The date of next Wednesday in YYYY-MM-DD format only

        ## Date Extraction Rules:
        - If the user is checking availability at a specific time, return ONLY the date without the time.
        - If the user mentions a task that needs to be **completed by**, **done by**, **finished by**, or **due by/on** a specific date, ALWAYS return a range from today to that date.
        - If the user mentions needing a certain number of hours to complete a task with a deadline, ALWAYS return a range from today to the deadline.
        - If the user specifies a **single date** without a deadline context (e.g., "Find me time on Monday"), return **that date only**.  
        - If a **date range** is explicitly given (e.g., "this week", "next month", "between Monday and Friday"), return the **start and end dates** of that period.  
        - If **no date is mentioned**, assume the task is for **this week**, starting today.  

        ## Deadline Detection:
        - Look for phrases like "to be done by", "due by", "due on", "finish by", "complete by", "by [date]"
        - When these phrases appear, it means the user needs time BEFORE that date, not ON that date only.
        - Always return a date range from today to the deadline date in these cases.

        ## Output Format:  
        - **Single date**: `"YYYY-MM-DD"`  
        - **Date range**: `"YYYY-MM-DD to YYYY-MM-DD"`  
        - **Specific time slot**: `"YYYY-MM-DD HH:MM to YYYY-MM-DD HH:MM"`  
        - **List of dates or times**: `["YYYY-MM-DD", "YYYY-MM-DD"]` or `["YYYY-MM-DD HH:MM to HH:MM", ...]`  
        - Return **only the date or time range string**, nothing else.  

        Extract and return the appropriate date or date range.  
        """
        
        date_response = model.generate_content(date_extraction_prompt)
        date_range = date_response.text.strip()
        
        logger.info(f"Date range extracted from find_time: {date_range}")
        logger.info(f"Date range: {date_range}")
        
        # Process date_range if it contains time information
        processed_date_range = date_range
        if ' to ' in date_range:
            parts = date_range.split(' to ')
            # Extract only the date portion if times are included
            if len(parts) == 2:
                start_parts = parts[0].split()
                end_parts = parts[1].split()
                # Check if we have date and time format
                if len(start_parts) > 1 and ':' in parts[0]:
                    start_date = start_parts[0]
                    end_date = end_parts[0] if len(end_parts) > 0 else start_date
                    processed_date_range = f"{start_date} to {end_date}"
        elif ' ' in date_range and ':' in date_range:
            # Handle single date with time
            processed_date_range = date_range.split()[0]
        
        # For queries about specific time availability, get the time
        if "am i free" in natural_language.lower() or "check if i'm free" in natural_language.lower():
            specific_time = extract_time_from_query(natural_language)
            if processed_date_range and specific_time:
                logger.info(f"Specific time query detected: {specific_time} on {processed_date_range}")
                # Adjust start_time and end_time to narrow the search window
                time_obj = datetime.datetime.strptime(specific_time, "%H:%M")
                # Create a 2-hour window centered around the requested time
                start_time_adj = (time_obj - datetime.timedelta(hours=1)).strftime("%H:%M")
                end_time_adj = (time_obj + datetime.timedelta(hours=1)).strftime("%H:%M")
                start_time = start_time_adj
                end_time = end_time_adj
                logger.info(f"Adjusted time window: {start_time} to {end_time}")
        
        logger.info(f"Processed date range for find_time_helper: {processed_date_range}")
        
        # Extract deadline time of day constraints
        deadline_extraction_prompt = f"""
        Analyze the following text and extract ONLY any time-of-day deadline constraints:
        "{natural_language}"
        
        Instructions:
        1. Look for phrases like "by Sunday morning", "before Friday evening", "due Wednesday night", etc.
        2. If such a phrase exists, return a JSON object with:
           - deadline_day: the day of the deadline (e.g., "Sunday", "Friday")
           - deadline_time: the time of day ("morning", "afternoon", "evening", "night")
        3. If no such phrase exists, return an empty JSON object: {{}}
        
        Return ONLY the JSON object, no additional text.
        """
        
        deadline_response = model.generate_content(deadline_extraction_prompt)
        deadline_text = deadline_response.text.strip()
        
        # Clean up the response
        if deadline_text.startswith("```json"):
            deadline_text = deadline_text[7:-3]
        elif deadline_text.startswith("```"):
            deadline_text = deadline_text[3:-3]
            
        try:
            deadline_info = json.loads(deadline_text)
            logger.info(f"Extracted deadline constraint: {deadline_info}")
        except json.JSONDecodeError:
            deadline_info = {}
            logger.warning(f"Could not parse deadline info from: {deadline_text}")
        
        # Get calendar IDs from user preferences
        calendar_ids = [cal['id'] for cal in user_preferred_calendars] if user_preferred_calendars else ["primary"]
        logger.info(f"Using calendars in find_time: {calendar_ids}")
        
        # Get all available time slots
        time_slots_result = find_time_helper(processed_date_range, start_time, end_time, calendar_ids)
        logger.info(f"Available time slots by the find_time_helper: {time_slots_result}")
        
        if not time_slots_result.get('success', False):
            logger.error(f"Failed to find available time slots: {time_slots_result['message']}")
            return json.dumps({"error": "Failed to find available time slots"})
        
        free_slots = time_slots_result.get('free_slots', [])
        if not free_slots:
            logger.warning("No free slots found in the specified date range")
            return json.dumps([])
        
        # Create a list of busy events for Gemini to be explicitly aware of
        busy_events = []
        if ' to ' in processed_date_range:
            start_date, end_date = processed_date_range.split(' to ')
        else:
            start_date = end_date = processed_date_range
        
        creds = get_credentials()
        service = build("calendar", "v3", credentials=creds)
        
        for calendar_id in calendar_ids:
            try:
                events_result = service.events().list(
                    calendarId=calendar_id,
                    timeMin=f"{start_date}T00:00:00-07:00",
                    timeMax=f"{end_date}T23:59:59-07:00",
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                
                for event in events_result.get('items', []):
                    if 'dateTime' in event.get('start', {}) and 'dateTime' in event.get('end', {}):
                        start = event['start']['dateTime']
                        end = event['end']['dateTime']
                        summary = event.get('summary', 'Busy')
                        busy_events.append({
                            "summary": summary,
                            "start": start,
                            "end": end,
                            "calendar": calendar_id
                        })
            except Exception as e:
                logger.error(f"Error fetching busy events from calendar {calendar_id}: {e}")
        
        slots_prompt = f"""
        Current date: {current_date}  
        Current time: {current_time}  

        You are a scheduling assistant. The user's request: "{natural_language}"

        ## Current Time Awareness
        - It is currently {current_date} at {current_time}
        - IMPORTANT: NEVER suggest time slots that are in the past
        - Today's time slots must start AFTER the current time

        ## Detected Time Constraints:
        - Date Range: {processed_date_range}

        ## Deadline Time-of-Day Detection (CRITICAL):
        - IMPORTANT: Carefully analyze if the user mentioned a deadline with a specific time of day
        - Look for phrases like "by Sunday morning", "before Friday evening", "due Thursday night"
        - When such phrases appear, DO NOT schedule ANY sessions on or after that time
        - Time of day definitions:
          * Morning: 00:00-11:59 AM
          * Afternoon: 12:00-5:59 PM
          * Evening: 6:00-9:59 PM
          * Night: 10:00 PM-11:59 PM
        - For a deadline like "by Sunday morning", this means:
          * All tasks MUST be scheduled to end BEFORE Sunday at 00:00 AM
          * NO tasks may be scheduled on Sunday at all

        ## Task Duration Analysis: (IMPORTANT)
        - First, analyze if the user mentioned a specific total duration for their task
        - If they mention needing "X hours" (e.g., "6 hours", "around 4 hours", "it'll take me 8 hours"), extract this value
        - Consider approximate language like "around 6 hours", "about 5 hours", etc. and extract the numeric value
        - If no specific duration is mentioned, default to scheduling 1-2 hour blocks   

        ## Available Free Time Slots you can schedule into (IMPORTANT):
        {json.dumps(free_slots, indent=2)}
        
        ##You can ONLY schedule into the free slots above. Do not suggest any other time slots.
        
        ##Time of day preferences:
        - If the user mentions a task is due by a specific time of day (e.g., "morning", "afternoon", "evening"), Do not schedule any sessions that are after that time.
        - Morning ends at 11:59 AM, Afternoon ends at 5:59 PM, Evening ends at 9:59 PM, and Night ends at 11:59 PM.
        - For example, if the user mentions that a task is due by "Sunday morning", do not schedule ANY sessions on Sunday.
        - If a task is "due by Friday evening", do not schedule sessions after 5:59 PM on Friday or on any day after Friday.

        ## Scheduling Constraints:  
        1. **Work session duration**: Each session **MUST** be between **{min_work_duration} and {max_work_duration} hours**. Sessions exceeding this range **are not allowed**.
        2. You can go close to the max and min work duration but do not exceed it thats it.
        3. Only under very tight constraints can you go over the max work duration.           
        4. **Breaks**: There must be **at least a 30-minute gap** between any two scheduled sessions.  
        5. **User preference**: If the user mentioned a specific time (e.g., "morning", "afternoon"), prioritize matching slots.  
        6. **Time rounding**: Round session start and end times to the **nearest 15 minutes**.  
        7. **Total hours**: If the user mentions a total number of hours needed (e.g., "I need 10 hours to finish my assignment"), schedule enough sessions to meet that total requirement while respecting the other constraints.
        8. **Past times**: NEVER suggest time slots that are in the past relative to the current time ({current_time} on {current_date}).
        9. **Strict enforcement**:  
        - **Do not exceed {max_work_duration} per session.**  
        - **Do not suggest sessions shorter than {min_work_duration}.**
        - **NEVER OVERLAP with any existing busy event**
        - **NEVER suggest slots that start in the past**
        - **NEVER suggest slots on or after the deadline day+time specified by the user**
        - **If no suitable slots exist within these constraints, return an empty JSON array.**  

        ## Planning Instructions:
        1. First, analyze the natural language request to determine:
           - Total hours required
           - Any time-of-day constraints (morning/afternoon/evening)
           - The deadline (including time of day)
        2. If there is a total hours requirement, calculate how many sessions you'll need
        3. For TODAY ({current_date}), only suggest time slots that start AFTER {current_time}
        4. Schedule sessions across multiple days if needed to fulfill the total hours
        5. Prioritize longer sessions (closer to {max_work_duration}) to minimize session switching
        6. NEVER schedule any sessions on or after the specific deadline time
        7. Double-check that NONE of your suggested slots are outside of the free slots provided.

        ## Expected Output Format:  
        Return **only** a JSON array with the suggested time slots, formatted as follows:  

        [
            {{
                "start": "2023-04-01T09:00:00-07:00",
                "end": "2023-04-01T11:00:00-07:00"
            }},
            {{
                "start": "2023-04-01T13:30:00-07:00",
                "end": "2023-04-01T15:30:00-07:00"
            }}
        ]
        """
        
        slots_response = model.generate_content(slots_prompt)
        processed_slots = slots_response.text.strip()
        
        if processed_slots.startswith("```json"):
            processed_slots = processed_slots[7:-3]
        elif processed_slots.startswith("```"):
            processed_slots = processed_slots[3:-3]
        
        logger.info(f"Processed slots: {processed_slots}")
        
        try:
            slots = json.loads(processed_slots)
            
            # Double-check for overlaps with busy events
            validated_slots = []
            current_datetime = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-7)))
            logger.info(f"Current time for validation: {current_datetime}")
            
            # Time-of-day deadline validation
            has_deadline_constraint = bool(deadline_info.get('deadline_day') and deadline_info.get('deadline_time'))
            deadline_day = deadline_info.get('deadline_day', '').lower() if has_deadline_constraint else None
            deadline_time = deadline_info.get('deadline_time', '').lower() if has_deadline_constraint else None
            
            # Convert day name to date if we have a deadline constraint
            deadline_date = None
            if has_deadline_constraint:
                # Parse the end date from the date range
                if ' to ' in processed_date_range:
                    _, end_date_str = processed_date_range.split(' to ')
                    end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
                    
                    # Map day names to dates
                    day_map = {
                        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                        'friday': 4, 'saturday': 5, 'sunday': 6
                    }
                    
                    if deadline_day in day_map:
                        # Calculate days until the deadline day
                        current_day = datetime.datetime.now().weekday()
                        days_until_deadline = (day_map[deadline_day] - current_day) % 7
                        if days_until_deadline == 0:  # Same day of week
                            days_until_deadline = 7  # Next week
                        
                        deadline_date = datetime.datetime.now().date() + datetime.timedelta(days=days_until_deadline)
                        logger.info(f"Calculated deadline date: {deadline_date}")
            
            for slot in slots:
                slot_start = dateutil_parse(slot['start'])
                slot_end = dateutil_parse(slot['end'])
                has_overlap = False
                
                # Check if the slot is in the past
                if slot_start <= current_datetime:
                    logger.warning(f"Skipping suggested slot {slot['start']}-{slot['end']} as it's in the past")
                    has_overlap = True
                
                # Check deadline constraint if we have one
                if has_deadline_constraint and deadline_date:
                    slot_date = slot_start.date()
                    
                    # Define time thresholds for time of day
                    time_thresholds = {
                        'morning': datetime.time(0, 0),  # Start of day
                        'afternoon': datetime.time(12, 0),
                        'evening': datetime.time(18, 0),
                        'night': datetime.time(22, 0)
                    }
                    
                    # If slot is on or after the deadline day
                    if slot_date >= deadline_date:
                        # For "morning" deadline, reject any slot on deadline day
                        if deadline_time == 'morning':
                            logger.warning(f"Skipping slot {slot['start']}-{slot['end']} due to morning deadline on {deadline_date}")
                            has_overlap = True
                        # For other deadlines, check if slot starts after the time threshold
                        elif deadline_time in time_thresholds:
                            threshold_time = time_thresholds[deadline_time]
                            slot_time = slot_start.time()
                            
                            if slot_date > deadline_date or (slot_date == deadline_date and slot_time >= threshold_time):
                                logger.warning(f"Skipping slot {slot['start']}-{slot['end']} due to {deadline_time} deadline on {deadline_date}")
                                has_overlap = True
                
                # Check for overlap with busy events
                for busy_event in busy_events:
                    busy_start = dateutil_parse(busy_event['start'])
                    busy_end = dateutil_parse(busy_event['end'])
                    
                    # Check for overlap
                    if (slot_start < busy_end and slot_end > busy_start):
                        has_overlap = True
                        logger.warning(f"Skipping suggested slot {slot['start']}-{slot['end']} due to overlap with {busy_event['summary']}")
                        break
                
                if not has_overlap:
                    validated_slots.append(slot)
                    
            if len(validated_slots) < len(slots):
                logger.warning(f"Removed {len(slots) - len(validated_slots)} suggested slots due to conflicts or deadline constraints")
            
            # Calculate total hours in validated slots
            total_minutes = 0
            for slot in validated_slots:
                slot_start = dateutil_parse(slot['start'])
                slot_end = dateutil_parse(slot['end'])
                duration_minutes = (slot_end - slot_start).total_seconds() / 60
                total_minutes += duration_minutes
            
            total_hours = total_minutes / 60
            logger.info(f"Total hours in validated slots: {total_hours:.2f}, Requested hours: {requested_hours}")
            
            # Check if we found enough time
            if requested_hours > 0 and total_hours < requested_hours:
                insufficient_time_message = {
                    "validatedSlots": validated_slots,
                    "requestedHours": requested_hours,
                    "foundHours": total_hours,
                    "insufficientTime": True,
                    "message": f"Could only find {total_hours:.2f} hours of the {requested_hours} hours you requested before the deadline."
                }
                logger.warning(f"Insufficient time found: {total_hours:.2f} hours of {requested_hours} hours requested")
                return json.dumps(insufficient_time_message)
            
            return json.dumps(validated_slots)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response: {processed_slots}, Error: {e}")
            return "[]"
        
    except Exception as e:
        logger.error(f"Error finding available time: {e}")
        return json.dumps({"error": str(e)})

def extract_event_details(natural_language):
    try:
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        current_time = datetime.datetime.now().strftime("%H:%M")
        model = genai.GenerativeModel(model_name="gemini-2.0-flash")
        
        if user_preferred_calendars:
            calendar_names = [cal['summary'] for cal in user_preferred_calendars]
        else:
            calendar_names = ["primary"]
        
        prompt = f"""
        Current date: {current_date}
        Current time: {current_time}
        
        Extract event details from this text: "{natural_language}"
        
        If multiple events are mentioned, return an array of event objects, each with these fields:

        1. summary: Event title or summary
        2. location: Where the event takes place (if mentioned)
        3. description: Any additional details
        4. date: The date of the event (YYYY-MM-DD)
        5. startTime: Start time (HH:MM)
        6. endTime: End time (HH:MM) 
        7. duration: Duration in hours and minutes (HH:MM)
        8. calendarName: Name of calendar this event needs to go in. Choose from the following: {', '.join(calendar_names)}
        9. recurrence: Frequency if event repeats (DAILY, WEEKLY, MONTHLY, every tuesday, every friday, etc.)
        10. recurrenceDays: For weekly events, which days (MO,TU,WE,TH,FR,SA,SU)
        11. recurrenceCount: Number of recurrences
        12. notifications: Array of notification times before the event (in minutes)
        13. notificationMethods: Array of notification methods ("email", "popup", or both)
        
        For dates and times:
        - If "today" is mentioned, use {current_date}
        - If "tomorrow" is mentioned, use the next day
        - If a day like "Friday" is mentioned, find the next occurrence from {current_date}
        - For vague times like "morning", use 09:00
        - For "afternoon", use 14:00
        - For "evening", use 18:00
        - For "night", use 22:00
        - Default duration to 01:00 (1 hour) if not specified
        
        For notifications:
        - If "remind me" or similar phrases are used, include notifications
        - For phrases like "10 minutes before", set notifications to [10]
        - For "an hour before", set notifications to [60]
        - For "a day before", set notifications to [1440]
        - Default notification method is "popup" unless "email" is mentioned

        For calendarName:
        - Use the calendar names provided in the list: {', '.join(calendar_names)}
        - If no calendar is specified, use "primary"
        - If the calendar is not found, use "primary"
        - If there is a mention of any calendar name in the user input, use that calendar, 
        regardless of the case or spelling.For example, if the user mentions "cs188" or "CS188" or "Cs188", 
        use the calendar with the name "CS 188".
        
        For a single event, return a single object. For multiple events, return an array of objects.
        Each object should follow the format described above.

        Important instructions for multiple events:
            - When multiple days are mentioned (e.g., "Saturday and Wednesday"), create SEPARATE events for EACH day
            - If events are requested for different days, ensure each event has its own unique date
            - Carefully distinguish between multiple events versus a single event with multiple attributes

        Provide only the JSON output without any explanation.
        """
        
        #initialize model
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        #handle json formatting
        if response_text.startswith("```json"):
            response_text = response_text[7:-3]
        elif response_text.startswith("```"):
            response_text = response_text[3:-3]
            
        logger.debug(f"Gemini response: {response_text}")
        
        #checking if all the calendar names are being pulled up
        logger.debug(f"The selected calendars: {calendar_names}")
        
        try:
            event_details = json.loads(response_text)
            
            if isinstance(event_details, list):
                standardized_events = []
                for event in event_details:
                    # Calculate end time if it's missing but we have start time and duration
                    if event.get('startTime') and not event.get('endTime') and event.get('duration'):
                        start_time_obj = datetime.datetime.strptime(event.get('startTime'), "%H:%M")
                        duration_parts = event.get('duration').split(':')
                        hours_to_add = int(duration_parts[0])
                        minutes_to_add = int(duration_parts[1])
                        end_time_obj = start_time_obj + datetime.timedelta(hours=hours_to_add, minutes=minutes_to_add)
                        event['endTime'] = end_time_obj.strftime("%H:%M")
                    
                    # If we still don't have an end time, default to 1 hour after start
                    if event.get('startTime') and not event.get('endTime'):
                        start_time_obj = datetime.datetime.strptime(event.get('startTime'), "%H:%M")
                        end_time_obj = start_time_obj + datetime.timedelta(hours=1)
                        event['endTime'] = end_time_obj.strftime("%H:%M")
                    
                    # Parse start and end times to check if end is before start (overnight event)
                    if event.get('startTime') and event.get('endTime'):
                        start_time = datetime.datetime.strptime(event.get('startTime'), "%H:%M")
                        end_time = datetime.datetime.strptime(event.get('endTime'), "%H:%M")
                        
                        # Get the event date
                        event_date = event.get('date')
                        end_date = event_date
                        
                        # If end time is earlier than start time, it's an overnight event
                        if end_time < start_time:
                            # Calculate the next day's date
                            date_obj = datetime.datetime.strptime(event_date, "%Y-%m-%d")
                            next_day = date_obj + datetime.timedelta(days=1)
                            end_date = next_day.strftime("%Y-%m-%d")
                            logger.info(f"Detected overnight event: {event.get('summary')} - adjusted end date to {end_date}")
                    
                    standardized_event = {
                        "summary": event.get("summary", "Untitled Event"),
                        "location": event.get("location", ""),
                        "description": event.get("description", ""),
                        "calendarId": get_calendar_id(event.get("calendarName", "primary")), 
                        "duration": event.get("duration", "01:00"),
                        "start": {
                            "dateTime": f"{event_date}T{event.get('startTime')}:00",
                            "timeZone": timezone_str
                        },
                        "end": {
                            "dateTime": f"{end_date}T{event.get('endTime')}:00",
                            "timeZone": timezone_str
                        }
                    }
                    
                    if event.get("notifications") or event.get("notificationMethods"):
                        notifications = event.get("notifications", [10])
                        methods = event.get("notificationMethods", ["popup"])
                        standardized_event["reminders"] = {
                            "useDefault": False,
                            "overrides": []
                        }
                        for minutes in notifications:
                            for method in methods:
                                standardized_event["reminders"]["overrides"].append({
                                    "method": method,
                                    "minutes": minutes
                                })
                    
                    if event.get("recurrence"):
                        rrule = f"RRULE:FREQ={event.get('recurrence')}"
                        if event.get("recurrenceCount"):
                            rrule += f";COUNT={event.get('recurrenceCount')}"
                        if event.get("recurrence") == "WEEKLY" and event.get("recurrenceDays"):
                            rrule += f";BYDAY={','.join(event.get('recurrenceDays'))}"
                        standardized_event["recurrence"] = [rrule]
                    
                    standardized_events.append(standardized_event)
                return standardized_events
            else:
                # Calculate end time if it's missing but we have start time and duration
                if event_details.get('startTime') and not event_details.get('endTime') and event_details.get('duration'):
                    start_time_obj = datetime.datetime.strptime(event_details.get('startTime'), "%H:%M")
                    duration_parts = event_details.get('duration').split(':')
                    hours_to_add = int(duration_parts[0])
                    minutes_to_add = int(duration_parts[1])
                    end_time_obj = start_time_obj + datetime.timedelta(hours=hours_to_add, minutes=minutes_to_add)
                    event_details['endTime'] = end_time_obj.strftime("%H:%M")
                
                # If we still don't have an end time, default to 1 hour after start
                if event_details.get('startTime') and not event_details.get('endTime'):
                    start_time_obj = datetime.datetime.strptime(event_details.get('startTime'), "%H:%M")
                    end_time_obj = start_time_obj + datetime.timedelta(hours=1)
                    event_details['endTime'] = end_time_obj.strftime("%H:%M")
                
                # Parse start and end times to check if end is before start (overnight event)
                if event_details.get('startTime') and event_details.get('endTime'):
                    start_time = datetime.datetime.strptime(event_details.get('startTime'), "%H:%M")
                    end_time = datetime.datetime.strptime(event_details.get('endTime'), "%H:%M")
                    
                    # Get the event date
                    event_date = event_details.get('date')
                    end_date = event_date
                    
                    # If end time is earlier than start time, it's an overnight event
                    if end_time < start_time:
                        # Calculate the next day's date
                        date_obj = datetime.datetime.strptime(event_date, "%Y-%m-%d")
                        next_day = date_obj + datetime.timedelta(days=1)
                        end_date = next_day.strftime("%Y-%m-%d")
                        logger.info(f"Detected overnight event: {event_details.get('summary')} - adjusted end date to {end_date}")
                
                standardized_event = {
                    "summary": event_details.get("summary", "Untitled Event"),
                    "location": event_details.get("location", ""),
                    "description": event_details.get("description", ""),
                    "calendarId": get_calendar_id(event_details.get("calendarName", "primary")),
                    "duration": event_details.get("duration", "01:00"),
                    "start": {
                        "dateTime": f"{event_date}T{event_details.get('startTime')}:00",
                        "timeZone": timezone_str
                    },
                    "end": {
                        "dateTime": f"{end_date}T{event_details.get('endTime')}:00",
                        "timeZone": timezone_str
                    }
                }
                
                if event_details.get("notifications") or event_details.get("notificationMethods"):
                    notifications = event_details.get("notifications", [10])
                    methods = event_details.get("notificationMethods", ["popup"])
                    standardized_event["reminders"] = {
                        "useDefault": False,
                        "overrides": []
                    }
                    for minutes in notifications:
                        for method in methods:
                            standardized_event["reminders"]["overrides"].append({
                                "method": method,
                                "minutes": minutes
                            })
                
                if event_details.get("recurrence"):
                    rrule = f"RRULE:FREQ={event_details.get('recurrence')}"
                    if event_details.get("recurrenceCount"):
                        rrule += f";COUNT={event_details.get('recurrenceCount')}"
                    if event.get("recurrence") == "WEEKLY" and event.get("recurrenceDays"):
                        rrule += f";BYDAY={','.join(event.get('recurrenceDays'))}"
                    standardized_event["recurrence"] = [rrule]
                
                return standardized_event
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {e} for response: {response_text}")
            raise ValueError(f"Failed to parse AI response as JSON: {str(e)}")
    except Exception as e:
        logger.error(f"Error extracting event details: {e}")
        raise

@app.route('/api/get-calendars', methods=['GET'])
def get_calendars():
    try:
        creds = get_credentials()
        service = build("calendar", "v3", credentials=creds)
        calendar_list = service.calendarList().list().execute()
        calendars = []
        for calendar in calendar_list.get('items', []):
            calendars.append({
                'id': calendar['id'],
                'summary': calendar['summary'],
                'primary': calendar.get('primary', False),
                'description': calendar.get('description', ''),
                'backgroundColor': calendar.get('backgroundColor', '#4285F4'),
                'colorId': calendar.get('colorId', '')
            })
        return jsonify({
            "success": True,
            "calendars": calendars
        })
    except Exception as e:
        logger.error(f"Error fetching calendars: {e}")
        return jsonify({
            "success": False,
            "message": f"Error fetching calendars: {str(e)}"
        }), 500


#API endpoint for setting preferred calendars 
@app.route('/api/set-preferred-calendars', methods=['POST'])
def set_preferred_calendars():
    global user_preferred_calendars
    data = request.json
    user_preferred_calendars = data.get('calendars', [])
    
    # Update the user_preferred_calendars in calendar_utils
    set_user_preferred_calendars(user_preferred_calendars)
    
    # Save to file
    try:
        with open(PREF_FILE, 'w') as f:
            json.dump(user_preferred_calendars, f, indent=2)
        logger.info(f"Saved preferences to {PREF_FILE}: {user_preferred_calendars}")
    except IOError as e:
        logger.error(f"Error saving preferences to {PREF_FILE}: {e}")
        return jsonify({
            "success": False,
            "message": f"Failed to save preferences: {str(e)}"
        }), 500
    return jsonify({
        "success": True,
        "message": "Preferred calendars set successfully"
    })

#Returns the current contents of user_preferred_calendars, which is loaded 
#from preferences.json on startup.
@app.route('/api/get-preferred-calendars', methods=['GET'])
def get_preferred_calendars():
    global user_preferred_calendars
    return jsonify({
        "success": True,
        "calendars": user_preferred_calendars
    })

@app.route('/api/create-event', methods=['POST'])
def create_event():
    try:
        data = request.json
        logger.info(f"Received event data: {data}")
        calendar_id = data.get("calendarId", "primary")
        start_data = data.get("start", {}).copy()
        end_data = data.get("end", {}).copy()
        
        if start_data.get("dateTime"):
            start_data["dateTime"] = normalize_date_time(start_data["dateTime"])
        
        if data.get("duration") and start_data.get("dateTime"):
            end_datetime = calculate_end_time(start_data["dateTime"], data["duration"])
            end_data = {
                "dateTime": end_datetime,
                "timeZone": start_data.get("timeZone", timezone_str)
            }
        elif end_data.get("dateTime"):
            end_data["dateTime"] = normalize_date_time(end_data["dateTime"])
        
        creds = get_credentials()
        service = build("calendar", "v3", credentials=creds)
        
        event = {
            "summary": data.get("summary", "Untitled Event"),
            "location": data.get("location", ""),
            "description": data.get("description", ""),
            "start": start_data,
            "end": end_data
        }
        
        if data.get("colorId"):
            event["colorId"] = data.get("colorId")
        if data.get("recurrence"):
            event["recurrence"] = data.get("recurrence")
        if data.get("reminders"):
            event["reminders"] = data.get("reminders")
        
        logger.info(f"Creating event with data: {event}")
        created_event = service.events().insert(calendarId=calendar_id, body=event).execute()
        
        return jsonify({
            "success": True,
            "message": "Event created successfully",
            "eventLink": created_event.get('htmlLink')
        })
    except Exception as e:
        logger.error(f"Error creating event: {e}")
        return jsonify({
            "success": False,
            "message": f"Error creating event: {str(e)}"
        }), 500

@app.route('/api/get-events', methods=['GET'])
def get_events():
    try:
        creds = get_credentials()
        service = build("calendar", "v3", credentials=creds)
        
        start_date = request.args.get('start', '')
        end_date = request.args.get('end', '')
        
        if not start_date or not end_date:
            today = datetime.datetime.now()
            start_date = today.strftime('%Y-%m-%d')
            end_of_week = today + datetime.timedelta(days=6)
            end_date = end_of_week.strftime('%Y-%m-%d')
        
        time_min = f"{start_date}T00:00:00-07:00"
        time_max = f"{end_date}T23:59:59-07:00"
        
        calendar_ids = []
        if user_preferred_calendars:
            calendar_ids = [cal['id'] for cal in user_preferred_calendars]
        else:
            calendar_ids = ["primary"]
        
        all_events = []
        for calendar_id in calendar_ids:
            events_result = service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            for event in events_result.get('items', []):
                # Skip events without start/end time
                if 'dateTime' not in event.get('start', {}) or 'dateTime' not in event.get('end', {}):
                    continue
                    
                event_data = {
                    'id': event.get('id'),
                    'title': event.get('summary', 'Untitled Event'),
                    'start': event.get('start').get('dateTime'),
                    'end': event.get('end').get('dateTime'),
                    'calendarId': calendar_id,
                    'backgroundColor': '#' + str(int(get_color_from_calendar_id(calendar_id)) * 123456 % 0xFFFFFF).zfill(6),
                    'existingEvent': True
                }
                all_events.append(event_data)
        
        return jsonify({
            "success": True,
            "events": all_events
        })
    except Exception as e:
        logger.error(f"Error fetching events: {e}")
        return jsonify({
            "success": False,
            "message": f"Error fetching events: {str(e)}"
        }), 500

@app.route('/api/natural-language-event', methods=['POST'])
def process_natural_language():
    try:
        creds = get_credentials()
        service = build("calendar", "v3", credentials=creds)
        data = request.json
        text = data.get('text', '')
        
        if not text:
            return jsonify({
                "success": False,
                "message": "No text provided"
            }), 400
        
        intent = get_user_intent(text)
        
        logger.info(f"Detected intent: {intent}")
        
        if intent == "Create event":
            event_details = extract_event_details(text)
            if isinstance(event_details, list):
                created_events = []
                for event in event_details:
                    created_event = service.events().insert(
                        calendarId=event.get("calendarId", "primary"), 
                        body=event
                    ).execute()
                    created_events.append(created_event)
                
                return jsonify({
                    "success": True,
                    "message": f"{len(created_events)} events created successfully",
                    "events": created_events,
                    "humanizedResponse": f"Added {len(created_events)} events to your calendar."
                })
            else:
                created_event = service.events().insert(
                    calendarId=event_details.get("calendarId", "primary"), 
                    body=event_details
                ).execute()
                return jsonify({
                    "success": True,
                    "message": "Event created successfully",
                    "eventLink": created_event.get('htmlLink'),
                    "event": created_event,
                    "humanizedResponse": f"Added '{event_details.get('summary', 'event')}' to your calendar."
                })
        
        elif intent == "Find time" or intent == "Find time to schedule event/ events":
            # Extract a summary using basic text processing instead of calling Gemini again
            try:
                # Some simple rules to extract a potential event title
                text_lower = text.lower()
                custom_summary = "Suggested Time"
                
                # Look for common patterns
                for pattern in ["time to work on", "time for", "schedule time for", "find time for", 
                               "time to finish", "time to complete", "time to prepare", 
                               "when can i", "need to work on", "need time for"]:
                    if pattern in text_lower:
                        # Get the text after the pattern
                        parts = text_lower.split(pattern, 1)
                        if len(parts) > 1:
                            # Extract the first few words after the pattern
                            words = parts[1].strip().split()
                            if words:
                                # Take at most 5 words
                                phrase = " ".join(words[:5])
                                # Remove any trailing punctuation
                                phrase = phrase.rstrip('.,:;!?')
                                # Capitalize words
                                custom_summary = " ".join(word.capitalize() for word in phrase.split())
                                break
                
                # Ensure the summary isn't too long
                if len(custom_summary) > 30:
                    custom_summary = custom_summary[:27] + "..."
            
                    
                logger.info(f"Extracted custom summary without AI: {custom_summary}")
            except Exception as e:
                logger.warning(f"Could not extract custom summary: {e}")
                custom_summary = "Suggested Time"
            
            # The user can also explicitly provide a summary in the request
            user_provided_summary = data.get('summary')
            if user_provided_summary:
                custom_summary = user_provided_summary
            
            # Find available time slots
            available_slots_json = find_time(text)
            
            try:
                available_slots = json.loads(available_slots_json)
                
                # Handle error response
                if isinstance(available_slots, dict) and available_slots.get("error"):
                    error_message = available_slots.get("error")
                    logger.error(f"Error finding available time: {error_message}")
                    return jsonify({
                        "success": False,
                        "intent": "find_time",
                        "message": error_message,
                        "humanizedResponse": f"I encountered a problem finding available time slots: {error_message}"
                    }), 400
                
                # Check for insufficient time message
                if isinstance(available_slots, dict) and available_slots.get("insufficientTime"):
                    # Format slots for calendar display even if insufficient
                    formatted_slots = []
                    for slot in available_slots.get("validatedSlots", []):
                        formatted_slots.append({
                            'id': f"suggested-{len(formatted_slots)}",
                            'title': custom_summary,
                            'start': slot['start'],
                            'end': slot['end'],
                            'backgroundColor': '#8bc34a',
                            'borderColor': '#689f38',
                            'textColor': '#000',
                            'suggestedSlot': True
                        })
                    
                    logger.info(f"Returning insufficient time message: {available_slots['message']}")
                    return jsonify({
                        "success": True,
                        "intent": "find_time",
                        "availableSlots": available_slots.get("validatedSlots", []),
                        "calendarEvents": formatted_slots,
                        "summary": custom_summary,
                        "insufficientTime": True,
                        "requestedHours": available_slots.get("requestedHours"),
                        "foundHours": available_slots.get("foundHours"),
                        "message": available_slots.get("message"),
                        "humanizedResponse": available_slots.get("message", "I found some time slots for you, but they may not be enough for what you need.")
                    })
                
                # Format slots for calendar display
                formatted_slots = []
                for slot in available_slots:
                    formatted_slots.append({
                        'id': f"suggested-{len(formatted_slots)}",
                        'title': custom_summary,
                        'start': slot['start'],
                        'end': slot['end'],
                        'backgroundColor': '#8bc34a',
                        'borderColor': '#689f38',
                        'textColor': '#000',
                        'suggestedSlot': True
                    })
                
                # Generate a human-readable response
                slots_count = len(formatted_slots)
                if slots_count == 0:
                    humanized_response = "I couldn't find any suitable time slots based on your request."
                elif slots_count == 1:
                    slot_start = dateutil_parse(formatted_slots[0]['start']).strftime("%A, %B %d at %I:%M %p")
                    humanized_response = f"I found one suitable time slot for {custom_summary} on {slot_start}."
                else:
                    humanized_response = f"I found {slots_count} suitable time slots for {custom_summary}. Please select one that works for you."
                
                logger.info(f"Formatted slots for calendar: {formatted_slots}")
                return jsonify({
                    "success": True,
                    "intent": "find_time",
                    "availableSlots": available_slots,
                    "calendarEvents": formatted_slots,
                    "summary": custom_summary,
                    "humanizedResponse": humanized_response
                })
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing find_time response: {e}, response was: {available_slots_json}")
                return jsonify({
                    "success": False,
                    "intent": "find_time",
                    "message": "Error parsing time slot data",
                    "humanizedResponse": "I had trouble finding available time slots. Could you try rephrasing your request?"
                }), 400
        
        elif intent == "View events":
            # Extract query parameters using Gemini
            model = genai.GenerativeModel(model_name="gemini-2.0-flash")
            
            extraction_prompt = f"""
            Current date: {datetime.datetime.now().strftime("%Y-%m-%d")}
            Current time: {datetime.datetime.now().strftime("%H:%M")}
            
            Extract calendar query parameters from this text: "{text}"
            
            Parse the following parameters:
            1. query_type: The type of calendar query (options: "list_events", "check_free_time", "event_duration", "event_details")
            2. date_range: The date or date range being queried (e.g., "today", "tomorrow", "this week", "2023-05-01", "2023-05-01 to 2023-05-07")
            3. filters: Any filters for events (e.g., "meetings", "work", "personal", etc.)
            4. event_name: If asking about a specific event, its name.
            5. calendar_name: If specifying a calendar, its name
            
            Return a JSON object with these fields. Normalize dates to YYYY-MM-DD format.
            For "today", use the current date. For "this week", use the current date to the end of the week.
            For "tomorrow", use tomorrow's date.
            
            Provide only the JSON output.
            """
            
            response = model.generate_content(extraction_prompt)
            response_text = response.text.strip()
            
            # Handle JSON formatting
            if response_text.startswith("```json"):
                response_text = response_text[7:-3]
            elif response_text.startswith("```"):
                response_text = response_text[3:-3]
            
            logger.info(f"Extracted query parameters for view events: {response_text}")
            
            try:
                query_params = json.loads(response_text)
                
                # Get calendar IDs based on preferences or specified calendar
                calendar_ids = []
                if query_params.get("calendar_name"):
                    calendar_id = get_calendar_id(query_params.get("calendar_name"))
                    calendar_ids = [calendar_id]
                elif user_preferred_calendars:
                    calendar_ids = [cal['id'] for cal in user_preferred_calendars]
                else:
                    calendar_ids = ["primary"]
                
                # Normalize date range
                date_range = query_params.get("date_range", "")
                if "to" in date_range:
                    start_date, end_date = date_range.split(" to ")
                else:
                    start_date = end_date = date_range
                
                time_min = f"{start_date}T00:00:00-07:00"
                time_max = f"{end_date}T23:59:59-07:00"
                
                # Process based on query type
                query_type = query_params.get("query_type", "list_events")
                
                if query_type == "list_events":
                    # Fetch events for the specified date range and calendars
                    all_events = []
                    for calendar_id in calendar_ids:
                        try:
                            events_result = service.events().list(
                                calendarId=calendar_id,
                                timeMin=time_min,
                                timeMax=time_max,
                                singleEvents=True,
                                orderBy='startTime'
                            ).execute()
                            
                            events = events_result.get('items', [])
                            
                            # Apply filters if specified
                            if query_params.get("filters"):
                                filtered_events = []
                                filters = [f.lower() for f in query_params.get("filters").split(",")]
                                
                                for event in events:
                                    event_summary = event.get('summary', '').lower()
                                    event_description = event.get('description', '').lower()
                                    
                                    if any(filter_term in event_summary or filter_term in event_description for filter_term in filters):
                                        filtered_events.append(event)
                                
                                events = filtered_events
                            
                            # Format events for display
                            for event in events:
                                formatted_event = {
                                    'id': event.get('id'),
                                    'summary': event.get('summary', 'Untitled Event'),
                                    'calendarId': calendar_id
                                }
                                
                                # Format start and end times
                                if 'dateTime' in event.get('start', {}):
                                    start_dt = dateutil_parse(event['start']['dateTime'])
                                    formatted_event['start'] = start_dt.strftime("%Y-%m-%d %H:%M")
                                    
                                    if 'dateTime' in event.get('end', {}):
                                        end_dt = dateutil_parse(event['end']['dateTime'])
                                        formatted_event['end'] = end_dt.strftime("%Y-%m-%d %H:%M")
                                        
                                        # Calculate duration
                                        duration_min = (end_dt - start_dt).total_seconds() / 60
                                        hours, minutes = divmod(duration_min, 60)
                                        formatted_event['duration'] = f"{int(hours)}h {int(minutes)}m"
                                
                                # Add location if available
                                if 'location' in event:
                                    formatted_event['location'] = event['location']
                                    
                                all_events.append(formatted_event)
                        except Exception as e:
                            logger.error(f"Error fetching events from calendar in view events: {calendar_id}: {e}")
                    
                    response_data = {
                        "success": True,
                        "intent": "view_events",
                        "query_type": "list_events",
                        "date_range": date_range,
                        "events": all_events,
                        "total_events": len(all_events)
                    }
                    
                    # Generate a humanized response
                    humanized_response = generate_humanized_view_response(response_data)
                    response_data["humanizedResponse"] = humanized_response
                    
                    return jsonify(response_data)
                    
                elif query_type == "check_free_time":
                    # Leverage existing find_time_helper function to get free slots
                    free_time_result = find_time_helper(
                        date_range=date_range,
                        calendarIds=calendar_ids
                    )
                    
                    response_data = {
                        "success": True,
                        "intent": "view_events",
                        "query_type": "check_free_time",
                        "date_range": date_range,
                        "free_slots": free_time_result.get("free_slots", []),
                        "total_free_slots": free_time_result.get("total_free_slots", 0)
                    }
                    
                    # Generate a humanized response
                    humanized_response = generate_humanized_view_response(response_data)
                    response_data["humanizedResponse"] = humanized_response
                    
                    return jsonify(response_data)
                    
                elif query_type == "event_duration" or query_type == "event_details":
                    # Fetch specific event details
                    event_name = query_params.get("event_name", "").lower()
                    
                    if not event_name:
                        return jsonify({
                            "success": False,
                            "message": "Event name not specified in the query",
                            "humanizedResponse": "I couldn't find the event you're looking for. Could you specify the event name?"
                        }), 400
                    
                    # Search for the specified event across calendars
                    matching_events = []
                    
                    for calendar_id in calendar_ids:
                        try:
                            events_result = service.events().list(
                                calendarId=calendar_id,
                                timeMin=time_min,
                                timeMax=time_max,
                                singleEvents=True,
                                orderBy='startTime'
                            ).execute()
                            
                            for event in events_result.get('items', []):
                                event_summary = event.get('summary', '').lower()
                                
                                # Check if event name matches or contains the query
                                if event_name in event_summary:
                                    # Calculate event duration
                                    if 'dateTime' in event.get('start', {}) and 'dateTime' in event.get('end', {}):
                                        start_dt = dateutil_parse(event['start']['dateTime'])
                                        end_dt = dateutil_parse(event['end']['dateTime'])
                                        
                                        duration_min = (end_dt - start_dt).total_seconds() / 60
                                        hours, minutes = divmod(duration_min, 60)
                                        
                                        matching_events.append({
                                            'id': event.get('id'),
                                            'summary': event.get('summary', 'Untitled Event'),
                                            'start': start_dt.strftime("%Y-%m-%d %H:%M"),
                                            'end': end_dt.strftime("%Y-%m-%d %H:%M"),
                                            'duration': f"{int(hours)}h {int(minutes)}m",
                                            'duration_minutes': int(duration_min),
                                            'location': event.get('location', ''),
                                            'description': event.get('description', ''),
                                            'calendarId': calendar_id
                                        })
                        except Exception as e:
                            logger.error(f"Error fetching events from calendar {calendar_id}: {e}")
                    
                    response_data = {
                        "success": True,
                        "intent": "view_events",
                        "query_type": query_type,
                        "event_name": query_params.get("event_name"),
                        "date_range": date_range,
                        "matching_events": matching_events,
                        "total_matching_events": len(matching_events)
                    }
                    
                    # Generate a humanized response
                    humanized_response = generate_humanized_view_response(response_data)
                    response_data["humanizedResponse"] = humanized_response
                    
                    return jsonify(response_data)
                
                else:
                    return jsonify({
                        "success": False,
                        "message": f"Unsupported query type: {query_type}",
                        "humanizedResponse": "I don't understand what calendar information you're looking for. Could you try asking in a different way?"
                    }), 400
                
            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing error: {e} for response: {response_text}")
                return jsonify({
                    "success": False,
                    "message": f"Failed to parse query parameters: {str(e)}",
                    "humanizedResponse": "I had trouble understanding your calendar query. Could you try rephrasing it?"
                }), 500
        
    except Exception as e:
        logger.error(f"Error processing natural language: {e}")
        return jsonify({
            "success": False,
            "message": f"Error processing your request: {str(e)}",
            "humanizedResponse": "I encountered an error while processing your request. Please try again."
        }), 500

@app.route('/api/schedule-selected-slot', methods=['POST'])
def schedule_selected_slot():
    try:
        data = request.json
        slot = data.get('selectedSlot')
        event_details = data.get('eventDetails', {})
        
        if not slot or not event_details:
            return jsonify({
                "success": False,
                "message": "Missing selected slot or event details"
            }), 400
        
        creds = get_credentials()
        service = build("calendar", "v3", credentials=creds)
        
        # Use the custom summary from event_details if available, otherwise use the title from slot
        # or fall back to a default
        summary = event_details.get("summary") or slot.get("title", "Scheduled Event")
        
        event = {
            "summary": summary,
            "location": event_details.get("location", ""),
            "description": event_details.get("description", ""),
            "start": {
                "dateTime": slot["start"],
                "timeZone": timezone_str
            },
            "end": {
                "dateTime": slot["end"],
                "timeZone": timezone_str
            }
        }
        
        if event_details.get("reminders"):
            event["reminders"] = event_details.get("reminders")
        
        created_event = service.events().insert(
            calendarId=event_details.get("calendarId", "primary"), 
            body=event
        ).execute()
        
        return jsonify({
            "success": True,
            "message": "Event scheduled successfully",
            "eventLink": created_event.get('htmlLink'),
            "event": created_event
        })
    except Exception as e:
        logger.error(f"Error scheduling event: {e}")
        return jsonify({
            "success": False,
            "message": f"Error scheduling event: {str(e)}"
        }), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)


    