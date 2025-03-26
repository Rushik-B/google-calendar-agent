import datetime
import json
import logging
import os
from dateutil.parser import parse as dateutil_parse
import google.generativeai as genai
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import re

# Import user preferences from config file
from config import timezone_str, timezone, time_periods, deadline_thresholds

# Configure logging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Suppress Google API client logs
logging.getLogger('googleapiclient').setLevel(logging.ERROR)
logging.getLogger('google_auth_oauthlib').setLevel(logging.ERROR)
logging.getLogger('google.auth').setLevel(logging.ERROR)

# Global User Preferences - will be set from app.py
user_preferred_calendars = []

# Define constants
SCOPES = ["https://www.googleapis.com/auth/calendar"]

def set_user_preferred_calendars(calendars):
    """Set the user preferred calendars - to be called from app.py"""
    global user_preferred_calendars
    user_preferred_calendars = calendars

def get_credentials():
    """Get Google credentials"""
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return creds

def get_calendar_id(calendar_name):
    """Get calendar ID from calendar name"""
    if not user_preferred_calendars:
        return "primary"
    if calendar_name.lower() == "primary":
        for cal in user_preferred_calendars:
            if cal['id'] == "primary" or cal.get('primary', False):
                return cal['id']
        return "primary"
    for cal in user_preferred_calendars:
        if cal['summary'].lower() == calendar_name.lower():
            return cal['id']
    return "primary"

def fetch_events(service, calendar_ids, time_min, time_max):
    """Fetch events from the specified calendars within the given time range."""
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
            # Filter out all-day events
            events = [e for e in events if 'dateTime' in e.get('start', {}) and 'dateTime' in e.get('end', {})]
            all_events.extend(events)
        except Exception as e:
            logger.error(f"Error fetching events from calendar {calendar_id}: {e}")
            continue
    return all_events

def normalize_date_time(date_string, timezone_param=timezone):
    """Normalize date string to ISO format with timezone"""
    if not date_string:
        return None
    try:
        if 'T' in date_string and (date_string.endswith('Z') or '+' in date_string):
            return date_string
        dt = dateutil_parse(date_string)
        iso_format = dt.isoformat()
        if '+' not in iso_format and '-' not in iso_format[10:]:
            return f"{iso_format}-07:00"
        return iso_format
    except Exception as e:
        logger.error(f"Date parsing error: {e} for input: {date_string}")
        return date_string

def calculate_end_time(start_time, duration):
    """Calculate end time based on start time and duration"""
    try:
        start_time = normalize_date_time(start_time)
        hours, minutes = map(int, duration.split(':'))
        start_dt = dateutil_parse(start_time)
        end_dt = start_dt + datetime.timedelta(hours=hours, minutes=minutes)
        return end_dt.isoformat()
    except Exception as e:
        logger.error(f"Error calculating end time: {e}")
        start_dt = dateutil_parse(start_time)
        end_dt = start_dt + datetime.timedelta(hours=1)
        return end_dt.isoformat()

def get_color_from_calendar_id(calendar_id):
    """Get color ID from calendar ID"""
    try:
        creds = get_credentials()
        service = build("calendar", "v3", credentials=creds)
        # Fetch the specific calendar's details
        calendar = service.calendars().get(calendarId=calendar_id).execute()
        color_id = calendar.get('colorId', '1')  # Default to "1" (lavender) if not set
        # Validate color_id is within 1-11
        if color_id not in [str(i) for i in range(1, 12)]:
            logger.warning(f"Invalid colorId '{color_id}' for calendar {calendar_id}, defaulting to '1'")
            return "1"
        return color_id
    except HttpError as e:
        logger.error(f"Error fetching color for calendar {calendar_id}: {e}")
        return "1"  # Default to "1" on error
    except Exception as e:
        logger.error(f"Unexpected error in get_color_from_calendar_id: {e}")
        return "1"

def generate_humanized_view_response(events_data):
    """Generate a humanized response for the view events intent using Gemini."""
    try:
        model = genai.GenerativeModel(model_name="gemini-2.0-flash")
        
        # Format the events data for better prompt creation
        formatted_events = []
        if events_data.get("query_type") == "list_events":
            events = events_data.get("events", [])
            for event in events:
                formatted_event = {
                    "summary": event.get("summary", "Untitled Event"),
                    "start": event.get("start", ""),
                    "end": event.get("end", ""),
                    "duration": event.get("duration", ""),
                    "location": event.get("location", "")
                }
                formatted_events.append(formatted_event)
        
        # Create the prompt based on event type
        if events_data.get("query_type") == "list_events":
            date_range = events_data.get("date_range", "")
            total_events = events_data.get("total_events", 0)
            
            prompt = f"""
            Generate a friendly, conversational response describing the user's calendar events.
            
            Date range queried: {date_range}
            Total events found: {total_events}
            
            Events:
            {json.dumps(formatted_events, indent=2)}
            
            Instructions:
            1. If there are no events, mention that their schedule is clear for the specified period.
            2. If there are events, summarize them concisely by mentioning the number of events and highlighting key ones.
            3. Include start times for events happening today.
            4. Keep your response brief and conversational.
            5. Do not use bullet points or formatting.
            6. Do not introduce yourself or add pleasantries like "Here's what I found".
            7. Use a friendly, helpful tone.
            
            Response:
            """
        elif events_data.get("query_type") == "check_free_time":
            free_slots = events_data.get("free_slots", [])
            date_range = events_data.get("date_range", "")
            total_free_slots = events_data.get("total_free_slots", 0)
            
            # Parse requested duration (if any)
            requested_duration_str = events_data.get("free_time_duration", "any")
            required_duration_minutes = 60  # Default to 60 minutes (1 hour)
            
            logger.info(f"DURATION DEBUG: Raw free_time_duration value received: '{requested_duration_str}'")
            
            if requested_duration_str != "any" and requested_duration_str != "60 minutes":
                try:
                    # Try to parse duration like "5 hours" or "30 minutes"
                    if "hour" in requested_duration_str or "hr" in requested_duration_str:
                        # Extract the numeric part (handle cases like "5 hours", "5 hrs", "5hr", etc.)
                        hours_match = re.search(r'(\d+(\.\d+)?)\s*(hour|hr|hrs)', requested_duration_str)
                        if hours_match:
                            hours = float(hours_match.group(1))
                            required_duration_minutes = int(hours * 60)
                            logger.info(f"Parsed {hours} hours from '{requested_duration_str}', converted to {required_duration_minutes} minutes")
                    elif "minute" in requested_duration_str:
                        minutes_match = re.search(r'(\d+)\s*minute', requested_duration_str)
                        if minutes_match:
                            required_duration_minutes = int(minutes_match.group(1))
                    
                    logger.info(f"Filtering for slots with at least {required_duration_minutes} minutes duration")
                except Exception as e:
                    logger.error(f"Error parsing duration '{requested_duration_str}': {e}")
            
            # Filter slots based on required duration
            matching_slots = []
            shorter_slots = []
            
            for slot in free_slots:
                duration_minutes = slot.get("duration_minutes", 0)
                if duration_minutes >= required_duration_minutes:
                    matching_slots.append(slot)
                elif duration_minutes >= 15:  # Only include reasonable gaps (15+ minutes)
                    shorter_slots.append(slot)
            
            # Don't use Gemini model for this response - directly use our custom format with buttons
            if matching_slots:
                next_slot = matching_slots[0]
                start_time = next_slot.get("start_time", "")
                end_time = next_slot.get("end_time", "")
                
                # Convert to 12-hour format
                try:
                    start_dt = datetime.datetime.strptime(start_time, "%H:%M")
                    end_dt = datetime.datetime.strptime(end_time, "%H:%M")
                    start_formatted = start_dt.strftime("%I:%M %p").lstrip("0").replace(" 0", " ")
                    end_formatted = end_dt.strftime("%I:%M %p").lstrip("0").replace(" 0", " ")
                    
                    # Format duration for display
                    duration_minutes = next_slot.get("duration_minutes", 0)
                    hours = duration_minutes // 60
                    minutes = duration_minutes % 60
                    duration_text = f"{hours} hour" + ("s" if hours != 1 else "")
                    if minutes > 0:
                        duration_text += f" {minutes} minute" + ("s" if minutes != 1 else "")
                    
                    # Get the date information
                    date_str = next_slot.get("day", "")
                    if date_str:
                        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                        today = datetime.datetime.now().date()
                        tomorrow = today + datetime.timedelta(days=1)
                        
                        if date_obj == today:
                            date_display = "today"
                        elif date_obj == tomorrow:
                            date_display = "tomorrow"
                        else:
                            date_display = date_obj.strftime("%A, %B %d")  # e.g. "Monday, March 27"
                    else:
                        date_display = ""
                    
                    # Create response with action buttons
                    free_slot_html = f"""
                    <div class="free-time-card">
                        <p>Looks like you have a nice chunk of time available {date_display} from <span class="time-slot">{start_formatted} – {end_formatted}</span>! That's a solid <b>{duration_text}</b>.</p>
                        <div class="free-time-actions">
                            <button class="action-button" onclick="showDurationSelector('{start_time}', '{end_time}', 'duration-selector-{start_time.replace(":", "")}', 'duration-display-{start_time.replace(":", "")}', 'duration-slider-{start_time.replace(":", "")}')">Schedule a break</button>
                            <button class="action-button" onclick="scheduleTask('{start_time}', '{end_time}')">Schedule a task</button>
                        </div>
                        <div id="duration-selector-{start_time.replace(':', '')}" class="duration-selector" style="display:none; margin-top: 15px;">
                            <p>Select break duration: <span id="duration-display-{start_time.replace(':', '')}">60 min</span></p>
                            <input type="range" id="duration-slider-{start_time.replace(':', '')}" min="15" max="{duration_minutes}" value="60" step="15" 
                                   oninput="updateDurationDisplay(this.value, 'duration-display-{start_time.replace(':', '')}')">
                            <div style="display: flex; justify-content: space-between; margin-top: 5px;">
                                <button class="action-button" onclick="scheduleBreakWithDuration('{start_time}', '{end_time}', 'duration-slider-{start_time.replace(':', '')}')">Confirm</button>
                                <button class="action-button secondary" onclick="cancelDurationSelection('duration-selector-{start_time.replace(':', '')}')">Cancel</button>
                            </div>
                        </div>
                    </div>
                    """
                    logger.debug(f"Generated free slot HTML: {free_slot_html}")
                    return free_slot_html
                except Exception as e:
                    logger.error(f"Error formatting free time response: {e}")
                    # Simplified fallback without buttons
                    return f"You have a free chunk of time from {start_time} to {end_time} in the requested time period."
            elif shorter_slots and required_duration_minutes > 60:
                # We have shorter slots but not long enough for the requested duration
                return f"<div class='free-time-card'>You don't have any {requested_duration_str} long free slots in the requested time period.</div>"
            elif shorter_slots:
                try:
                    # Get the date of the first shorter slot to determine if it's today, tomorrow, etc.
                    first_slot = shorter_slots[0]
                    date_str = first_slot.get("day", "")
                    date_display = ""
                    
                    if date_str:
                        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                        today = datetime.datetime.now().date()
                        tomorrow = today + datetime.timedelta(days=1)
                        
                        if date_obj == today:
                            date_display = "today"
                        elif date_obj == tomorrow:
                            date_display = "tomorrow"
                        else:
                            date_display = date_obj.strftime("%A, %B %d")  # e.g. "Monday, March 27"
                    
                    response = f"<div class='free-time-card'><b>You don't have a full free hour {date_display}, but here are some available gaps:</b><br><br>"
                    
                    # Display top 3 shorter slots
                    for i, slot in enumerate(shorter_slots[:3]):
                        start_time = slot.get("start_time", "")
                        end_time = slot.get("end_time", "")
                        duration = slot.get("duration_minutes", 0)
                        
                        try:
                            start_dt = datetime.datetime.strptime(start_time, "%H:%M")
                            end_dt = datetime.datetime.strptime(end_time, "%H:%M")
                            start_formatted = start_dt.strftime("%I:%M %p").lstrip("0").replace(" 0", " ")
                            end_formatted = end_dt.strftime("%I:%M %p").lstrip("0").replace(" 0", " ")
                            
                            # Add button for each slot
                            response += f"""
                            <div class="slot-item">
                                <span class="time-slot">{start_formatted} – {end_formatted}</span> ({duration} min)
                                <div class="free-time-actions">
                                    <button class="action-button small" onclick="scheduleTask('{start_time}', '{end_time}')">Schedule</button>
                                </div>
                            </div>
                            """
                        except:
                            response += f"{start_time} – {end_time} ({duration} min)<br>"
                    
                    response += "</div>"
                    return response
                except Exception as e:
                    logger.error(f"Error formatting shorter slots: {e}")
                    return "<b>You don't have a full free hour in the requested time period, but you do have some shorter gaps.</b>"
            else:
                return "<div class='free-time-card'>Your calendar is fully booked for the requested time period.</div>"
        elif events_data.get("query_type") in ["event_duration", "event_details"]:
            matching_events = events_data.get("matching_events", [])
            event_name = events_data.get("event_name", "")
            
            prompt = f"""
            Generate a friendly, conversational response describing the details of specific events.
            
            Event name queried: {event_name}
            Total matching events found: {len(matching_events)}
            
            Matching events:
            {json.dumps(matching_events, indent=2)}
            
            Instructions:
            1. If there are no matching events, mention that no events with that name were found.
            2. If there are matching events, describe when they're scheduled and their duration.
            3. Keep your response brief and conversational.
            4. Do not use bullet points or formatting.
            5. Do not introduce yourself or add pleasantries like "Here's what I found".
            6. Use a friendly, helpful tone.
            
            Response:
            """
        else:
            # Default prompt for unknown query types
            prompt = f"""
            Generate a friendly, conversational response about the user's calendar.
            
            Calendar data:
            {json.dumps(events_data, indent=2)}
            
            Instructions:
            1. Summarize the information concisely.
            2. Keep your response brief and conversational.
            3. Do not use bullet points or formatting.
            4. Do not introduce yourself or add pleasantries like "Here's what I found".
            5. Use a friendly, helpful tone.
            
            Response:
            """
        
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Error generating humanized response: {e}")
        
        # Fallback responses based on query type
        if events_data.get("query_type") == "list_events":
            total_events = events_data.get("total_events", 0)
            date_range = events_data.get("date_range", "today")
            return f"You have {total_events} events scheduled for {date_range}."
        elif events_data.get("query_type") == "check_free_time":
            free_slots = events_data.get("free_slots", [])
            
            # Simple fallback that doesn't use the model
            if not free_slots:
                return "<div class='free-time-card'>Your calendar is fully booked for the requested time period.</div>"
            
            # Parse requested duration (if any)
            requested_duration_str = events_data.get("free_time_duration", "any")
            required_duration_minutes = 60  # Default to 60 minutes (1 hour)
            
            if requested_duration_str != "any" and requested_duration_str != "60 minutes":
                try:
                    # Try to parse duration like "5 hours" or "30 minutes"
                    if "hour" in requested_duration_str or "hr" in requested_duration_str:
                        # Extract the numeric part (handle cases like "5 hours", "5 hrs", "5hr", etc.)
                        hours_match = re.search(r'(\d+(\.\d+)?)\s*(hour|hr|hrs)', requested_duration_str)
                        if hours_match:
                            hours = float(hours_match.group(1))
                            required_duration_minutes = int(hours * 60)
                            logger.info(f"Parsed {hours} hours from '{requested_duration_str}', converted to {required_duration_minutes} minutes")
                    elif "minute" in requested_duration_str:
                        minutes_match = re.search(r'(\d+)\s*minute', requested_duration_str)
                        if minutes_match:
                            required_duration_minutes = int(minutes_match.group(1))
                except Exception:
                    pass  # Use default 60 minutes
            
            # Find slots with the required duration
            matching_slots = [slot for slot in free_slots if slot.get("duration_minutes", 0) >= required_duration_minutes]
            
            if matching_slots:
                next_slot = matching_slots[0]
                start_time = next_slot.get("start_time", "")
                end_time = next_slot.get("end_time", "")
                
                # Convert to 12-hour format
                try:
                    start_dt = datetime.datetime.strptime(start_time, "%H:%M")
                    end_dt = datetime.datetime.strptime(end_time, "%H:%M")
                    start_formatted = start_dt.strftime("%I:%M %p").lstrip("0").replace(" 0", " ")
                    end_formatted = end_dt.strftime("%I:%M %p").lstrip("0").replace(" 0", " ")
                    
                    # Format duration for display
                    duration_minutes = next_slot.get("duration_minutes", 0)
                    hours = duration_minutes // 60
                    minutes = duration_minutes % 60
                    duration_text = f"{hours} hour" + ("s" if hours != 1 else "")
                    if minutes > 0:
                        duration_text += f" {minutes} minute" + ("s" if minutes != 1 else "")
                    
                    # Get the date information
                    date_str = next_slot.get("day", "")
                    if date_str:
                        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                        today = datetime.datetime.now().date()
                        tomorrow = today + datetime.timedelta(days=1)
                        
                        if date_obj == today:
                            date_display = "today"
                        elif date_obj == tomorrow:
                            date_display = "tomorrow"
                        else:
                            date_display = date_obj.strftime("%A, %B %d")  # e.g. "Monday, March 27"
                    else:
                        date_display = ""
                    
                    # Create response with action buttons
                    response_html = f"""
                    <div class="free-time-card">
                        <p>You have a free chunk of time {date_display} from <span class="time-slot">{start_formatted} – {end_formatted}</span>. That's {duration_text}.</p>
                        <div class="free-time-actions">
                            <button class="action-button" onclick="showDurationSelector('{start_time}', '{end_time}', 'duration-selector-{start_time.replace(":", "")}', 'duration-display-{start_time.replace(":", "")}', 'duration-slider-{start_time.replace(":", "")}')">Schedule a break</button>
                            <button class="action-button" onclick="scheduleTask('{start_time}', '{end_time}')">Schedule a task</button>
                        </div>
                        <div id="duration-selector-{start_time.replace(':', '')}" class="duration-selector" style="display:none; margin-top: 15px;">
                            <p>Select break duration: <span id="duration-display-{start_time.replace(':', '')}">60 min</span></p>
                            <input type="range" id="duration-slider-{start_time.replace(':', '')}" min="15" max="{duration_minutes}" value="60" step="15" 
                                   oninput="updateDurationDisplay(this.value, 'duration-display-{start_time.replace(':', '')}')">
                            <div style="display: flex; justify-content: space-between; margin-top: 5px;">
                                <button class="action-button" onclick="scheduleBreakWithDuration('{start_time}', '{end_time}', 'duration-slider-{start_time.replace(':', '')}')">Confirm</button>
                                <button class="action-button secondary" onclick="cancelDurationSelection('duration-selector-{start_time.replace(':', '')}')">Cancel</button>
                            </div>
                        </div>
                    </div>
                    """
                    logger.debug(f"Generated fallback free slot HTML: {response_html}")
                    return response_html
                except:
                    return f"You have a free chunk of time from {start_time} to {end_time} in the requested time period."
            elif required_duration_minutes > 60:
                return f"<div class='free-time-card'>You don't have any {requested_duration_str} long free slots in the requested time period.</div>"
            else:
                return "<div class='free-time-card'>You don't have any hour-long free slots in the requested time period.</div>"
        elif events_data.get("query_type") in ["event_duration", "event_details"]:
            event_name = events_data.get("event_name", "")
            matching_count = len(events_data.get("matching_events", []))
            return f"Found {matching_count} events matching '{event_name}'."
        else:
            return "Here's your calendar information."

def parse_view_event_query(text):
    """Parse and extract query parameters for viewing events using Gemini API."""
    try:
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
        
        return json.loads(response_text)
    except Exception as e:
        logger.error(f"Error parsing view event query: {e}")
        return {
            "query_type": "list_events",
            "date_range": datetime.datetime.now().strftime("%Y-%m-%d")
        }

def extract_time_from_query(natural_language):
    """Extract time information from a time-specific query."""
    try:
        model = genai.GenerativeModel(model_name="gemini-2.0-flash")
        prompt = f"""
        Extract the specific time mentioned in this query: "{natural_language}"
        
        Instructions:
        1. Look for time references like "2 PM", "3:30", "afternoon", etc.
        2. Return the time in 24-hour format (HH:MM)
        3. For general time periods, use these defaults:
           - "morning" → "{time_periods['morning']['default_time']}"
           - "afternoon" → "{time_periods['afternoon']['default_time']}"
           - "evening" → "{time_periods['evening']['default_time']}"
           - "night" → "{time_periods['night']['default_time']}"
        4. If no specific time is mentioned, return "12:00"
        
        Return ONLY the time in HH:MM format, nothing else.
        """
        
        response = model.generate_content(prompt)
        time_text = response.text.strip()
        
        # Validate the time format
        try:
            datetime.datetime.strptime(time_text, "%H:%M")
            logger.info(f"Extracted time from query: {time_text}")
            return time_text
        except ValueError:
            logger.warning(f"Invalid time format extracted: {time_text}, using default")
            return "12:00"
    except Exception as e:
        logger.error(f"Error extracting time from query: {e}")
        return "12:00" 