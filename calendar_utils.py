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
            
            # Check if this is a deadline-related query
            deadline_related = False
            if events_data.get("filters"):
                filters = events_data.get("filters")
                if isinstance(filters, str):
                    filters = [f.lower() for f in filters.split(",")]
                else:
                    filters = [f.lower() for f in filters]
                
                deadline_related = any(keyword in filter_term for filter_term in filters 
                                      for keyword in ["deadline", "due", "assignment", "project", "homework"])
            
            # If this is a deadline query, create a custom formatted response with structured list
            if deadline_related and events:
                # Sort events by start date/time
                sorted_events = sorted(events, key=lambda e: e.get("start", ""))
                
                # Convert to a well-structured HTML response with better formatting
                html_response = "<div class='deadline-list-card'>"
                html_response += f"<h3>Upcoming Deadlines ({len(sorted_events)})</h3>"
                html_response += "<ul class='deadline-list'>"
                
                # Group events by date
                event_dates = {}
                for event in sorted_events:
                    event_date = event.get("start", "").split(" ")[0] if " " in event.get("start", "") else ""
                    if event_date:
                        if event_date not in event_dates:
                            event_dates[event_date] = []
                        event_dates[event_date].append(event)
                
                # Format each date's events
                for date_str in sorted(event_dates.keys()):
                    try:
                        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                        date_display = date_obj.strftime("%A, %B %d, %Y")  # e.g., "Monday, April 7, 2025"
                        
                        html_response += f"<li class='date-group'><div class='date-header'>{date_display}</div>"
                        html_response += "<ul class='event-list'>"
                        
                        for event in event_dates[date_str]:
                            summary = event.get("summary", "Untitled Event")
                            time_str = event.get("start", "").split(" ")[1] if " " in event.get("start", "") else ""
                            
                            # Format time to be more readable (e.g., "3:00 PM")
                            formatted_time = ""
                            if time_str:
                                try:
                                    time_obj = datetime.datetime.strptime(time_str, "%H:%M")
                                    formatted_time = time_obj.strftime("%I:%M %p").lstrip("0").replace(" 0", " ")
                                except:
                                    formatted_time = time_str
                            
                            location = f" at {event.get('location')}" if event.get("location") else ""
                            
                            html_response += f"<li class='event-item'><span class='event-time'>{formatted_time}</span> - <span class='event-title'>{summary}</span>{location}</li>"
                        
                        html_response += "</ul></li>"
                    except Exception as e:
                        logger.error(f"Error formatting date group: {e}")
                        continue
                
                html_response += "</ul></div>"
                
                logger.debug(f"Generated custom HTML deadline list: {html_response}")
                return html_response
            
            # Otherwise format events for Gemini prompt
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
            
            # Check if we're dealing with deadline filters
            deadline_filters = False
            if events_data.get("filters"):
                filters = events_data.get("filters")
                if isinstance(filters, str):
                    filters = filters.lower()
                    deadline_filters = any(keyword in filters for keyword in ["deadline", "due", "assignment", "project", "homework"])
                else:
                    deadline_filters = any(keyword in filter_term.lower() for filter_term in filters 
                                          for keyword in ["deadline", "due", "assignment", "project", "homework"])
            
            prompt = f"""
            Generate a friendly, conversational response describing the user's calendar events.
            
            Date range queried: {date_range}
            Total events found: {total_events}
            {"This is a deadline or assignment query." if deadline_filters else ""}
            
            Events:
            {json.dumps(formatted_events, indent=2)}
            
            Instructions:
            1. If there are no events, mention that their schedule is clear for the specified period.
            2. If there are events, list them chronologically and include specific dates and times.
            3. Group events by date if there are multiple days involved.
            4. If these are deadlines or assignments, clearly state the due dates and times.
            5. Use a structured, easy-to-read format. Make sure dates and times are clearly visible.
            6. Keep your response conversational but organized.
            7. Do not introduce yourself or add pleasantries like "Here's what I found".
            8. Use a friendly, helpful tone.
            9. Format your response with bullet points or numbers for clarity.
            
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
            
            # Check if this is a query about an assignment or deadline
            is_assignment_query = any(keyword in event_name.lower() for keyword in ["assignment", "due", "deadline", "homework", "project"])
            
            prompt = f"""
            Generate a friendly, conversational response describing the details of specific events.
            
            Event name queried: {event_name}
            Total matching events found: {len(matching_events)}
            
            {"This is an assignment due date query." if is_assignment_query else ""}
            
            Matching events:
            {json.dumps(matching_events, indent=2)}
            
            Instructions:
            1. If there are no matching events, mention that no events with that name were found.
            2. If there are matching events, describe when they're scheduled and their duration.
            3. If this is a query about an assignment due date, clearly emphasize the due date (e.g., "Your CMPT 213 assignment is due on Friday, April 7th at 11:59 PM").
            4. For assignment due dates, if there are multiple matching events, prioritize the ones with "due", "deadline", or "assignment" in the title.
            5. Keep your response brief and conversational.
            6. Do not use bullet points or formatting.
            7. Do not introduce yourself or add pleasantries like "Here's what I found".
            8. Use a friendly, helpful tone.
            
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
            # Create a more structured fallback response
            try:
                events = events_data.get("events", [])
                date_range = events_data.get("date_range", "today")
                
                if not events:
                    return f"You don't have any events scheduled for {date_range}."
                
                # Sort events by start date/time
                sorted_events = sorted(events, key=lambda e: e.get("start", ""))
                
                # Create a simple formatted text response
                response = f"<div class='events-list'><h3>Your Schedule ({len(sorted_events)} events)</h3><ul>"
                
                # Group events by date
                event_dates = {}
                for event in sorted_events:
                    event_date = event.get("start", "").split(" ")[0] if " " in event.get("start", "") else ""
                    if event_date:
                        if event_date not in event_dates:
                            event_dates[event_date] = []
                        event_dates[event_date].append(event)
                
                # Format each date's events
                for date_str in sorted(event_dates.keys()):
                    try:
                        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                        date_display = date_obj.strftime("%A, %B %d")  # e.g., "Monday, April 7"
                        
                        response += f"<li><strong>{date_display}</strong><ul>"
                        
                        for event in event_dates[date_str]:
                            summary = event.get("summary", "Untitled Event")
                            time_str = event.get("start", "").split(" ")[1] if " " in event.get("start", "") else ""
                            
                            # Format time to be more readable
                            formatted_time = ""
                            if time_str:
                                try:
                                    time_obj = datetime.datetime.strptime(time_str, "%H:%M")
                                    formatted_time = time_obj.strftime("%I:%M %p").lstrip("0").replace(" 0", " ")
                                except:
                                    formatted_time = time_str
                            
                            duration = f" ({event.get('duration')})" if event.get("duration") else ""
                            location = f" at {event.get('location')}" if event.get("location") else ""
                            
                            response += f"<li>{formatted_time} - {summary}{duration}{location}</li>"
                        
                        response += "</ul></li>"
                    except Exception as e:
                        logger.error(f"Error in fallback formatting for date {date_str}: {e}")
                        continue
                
                response += "</ul></div>"
                return response
            except Exception as fallback_error:
                logger.error(f"Error in structured fallback response: {fallback_error}")
                # Ultimate simple fallback
                total_events = len(events_data.get("events", []))
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
        
        # Check if the query is about an assignment or deadline
        deadline_keywords = ["assignment", "due", "deadline", "homework", "project", "submission", "hand in", "turn in"]
        is_assignment_query = any(keyword in text.lower() for keyword in deadline_keywords)
        is_exam_query = any(keyword in text.lower() for keyword in ["exam", "test", "midterm", "final", "quiz"])
        
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # For assignment/exam queries, use a 90-day forward-looking window by default
        default_date_range = current_date
        if is_assignment_query or is_exam_query:
            future_date = (datetime.datetime.now() + datetime.timedelta(days=90)).strftime("%Y-%m-%d")
            default_date_range = f"{current_date} to {future_date}"
        
        extraction_prompt = f"""
        Current date: {current_date}
        Current time: {datetime.datetime.now().strftime("%H:%M")}
        
        Extract calendar query parameters from this text: "{text}"
        
        Parse the following parameters:
        1. query_type: The type of calendar query (options: "list_events", "event_duration", "event_details")
        2. date_range: The date or date range being queried (e.g., "today", "tomorrow", "this week", "2023-05-01", "2023-05-01 to 2023-05-07")
        3. filters: Any filters for events (e.g., "meetings", "work", "personal", etc.)
        4. event_name: If asking about a specific event, its name.
        5. calendar_name: If specifying a calendar, its name
        
        Special instructions:
        - IMPORTANT: For queries about exams, assignments, deadlines, etc., set date_range to "{default_date_range}" if no specific date is mentioned.
        - NEVER return null/None for date_range. Use "{default_date_range}" as a fallback for any query where a date range isn't clearly specified.
        - For assignment/deadline/exam queries, be more flexible with event_name matching (e.g., "cmpt213 assignment" should match "cmpt 213 assignment due").
        - For queries about "next", "upcoming", or "following" events (e.g., "Where is my next class?"), set query_type to "event_details" and set event_name appropriately (e.g., "class" for "Where is my next class?").
        - When a query asks about location ("where") of a specific event, always use "event_details" as the query_type.
        
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
            parsed_response = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error in parse_view_event_query: {e}")
            # Determine the appropriate query type
            is_next_event_query = any(keyword in text.lower() for keyword in ["next", "upcoming", "following"])
            is_location_query = "where" in text.lower()
            
            if is_exam_query or is_assignment_query or is_next_event_query or is_location_query:
                query_type = "event_details"
                # Extract event name from the query
                event_name = text.lower()
                event_name = event_name.replace("when is", "").replace("where is", "")
                event_name = event_name.replace("my", "").replace("the", "").replace("?", "").strip()
                # For "next class" type queries, extract just the event type
                if is_next_event_query:
                    # Try to extract what comes after "next" or "upcoming"
                    for keyword in ["next", "upcoming", "following"]:
                        if keyword in event_name:
                            parts = event_name.split(keyword, 1)
                            if len(parts) > 1 and parts[1].strip():
                                event_name = parts[1].strip()
                                break
            else:
                query_type = "list_events"
                event_name = ""
                
            parsed_response = {
                "query_type": query_type, 
                "date_range": default_date_range,
                "event_name": event_name
            }
        
        # Double-check that date_range is not None
        if parsed_response.get("date_range") is None:
            logger.warning("Date range is still None after parsing, applying default")
            parsed_response["date_range"] = default_date_range
        
        # Make sure we don't accidentally return check_free_time query_type
        if parsed_response.get("query_type") == "check_free_time":
            logger.warning("LLM returned check_free_time query_type, converting to list_events")
            parsed_response["query_type"] = "list_events"
        
        # For CMPT course queries about exams or assignments, always use the 90-day forward range
        event_name = parsed_response.get("event_name", "").lower()
        if event_name and ("cmpt" in event_name) and (is_assignment_query or is_exam_query):
            parsed_response["date_range"] = default_date_range
            logger.info(f"Applied 90-day forward-looking window for CMPT course query: {event_name}")
        
        return parsed_response
    except Exception as e:
        logger.error(f"Error parsing view event query: {e}")
        # For assignment queries, use a 90-day window by default
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        future_date = (datetime.datetime.now() + datetime.timedelta(days=90)).strftime("%Y-%m-%d")
        deadline_keywords = ["assignment", "due", "deadline", "homework", "project", "submission", "hand in", "turn in"]
        exam_keywords = ["exam", "test", "midterm", "final", "quiz"]
        next_keywords = ["next", "upcoming", "following"]
        
        is_deadline_query = any(keyword in text.lower() for keyword in deadline_keywords)
        is_exam_query = any(keyword in text.lower() for keyword in exam_keywords)
        is_next_query = any(keyword in text.lower() for keyword in next_keywords)
        is_location_query = "where" in text.lower()
        
        if is_deadline_query or is_exam_query or is_next_query or is_location_query:
            # Process event name based on query type
            event_name = text.lower().replace("when is", "").replace("where is", "")
            event_name = event_name.replace("my", "").replace("the", "").replace("?", "").strip()
            
            # For "next" queries, extract what comes after "next"
            if is_next_query:
                for keyword in next_keywords:
                    if keyword in event_name:
                        parts = event_name.split(keyword, 1)
                        if len(parts) > 1 and parts[1].strip():
                            event_name = parts[1].strip()
                            break
            
            return {
                "query_type": "event_details",
                "date_range": f"{current_date} to {future_date}",
                "event_name": event_name
            }
        return {
            "query_type": "list_events",
            "date_range": current_date
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

def parse_modify_event_query(text):
    """Parse and extract query parameters for modifying events using Gemini API."""
    try:
        model = genai.GenerativeModel(model_name="gemini-2.0-flash")
        
        # Check for common modification keywords
        is_rescheduling = any(keyword in text.lower() for keyword in ["reschedule", "move", "shift", "postpone", "change time"])
        is_cancellation = any(keyword in text.lower() for keyword in ["cancel", "remove", "delete", "clear"])
        is_duration_change = any(keyword in text.lower() for keyword in ["extend", "shorten", "lengthen", "longer", "shorter", "duration"])
        is_detail_change = any(keyword in text.lower() for keyword in ["rename", "change name", "update", "modify", "edit", "location"])
        is_conflict_resolution = any(keyword in text.lower() for keyword in ["resolve conflict", "fix overlap", "alternative time"])
        
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        current_time = datetime.datetime.now().strftime("%H:%M")


  
        extraction_prompt = f"""
        Current date: {current_date}
        Current time: {current_time}
        
        Extract calendar event modification parameters from this text: "{text}"
        
        Parse the following parameters:
        1. modification_type: Type of modification requested (options: "reschedule", "cancel", "change_duration", "change_details", "resolve_conflict")
        2. event_name: The name/title of the event to be modified
        3. date: Date of the event (in YYYY-MM-DD format or "today", "tomorrow", etc.)
        4. original_time: Original time of the event (if specified)
        5. new_time: New time for the event (if rescheduling)
        6. new_date: New date for the event (if rescheduling to a different day)
        7. duration_change: Change in duration (e.g., "+30" for adding 30 minutes, "-15" for subtracting 15 minutes)
        8. new_duration: New total duration in minutes (e.g., "45" for 45 minutes)
        9. field_to_change: Field to update (e.g., "location", "title", "description")
        10. new_value: New value for the field being changed
        11. calendar_name: Calendar containing the event (if specified)
        
        Special instructions:
        - For rescheduling, capture both the original and new times/dates if provided
        - For cancellations, identify if it's for a specific event or time period
        - For duration changes, extract both relative changes (e.g., "add 30 minutes") and absolute values (e.g., "make it 45 minutes")
        - For location changes, capture the new location exactly as stated
        - For conflict resolution, identify the conflicting events if possible
        - If date isn't specified, assume today ({current_date})
        - Convert time references to 24-hour format (e.g., "3 PM" → "15:00")
        
        Return a JSON object with these fields. Leave fields empty if not provided in the query.
        Provide only the JSON output, no explanations.
        """
        
        response = model.generate_content(extraction_prompt)
        response_text = response.text.strip()
        
        # Handle JSON formatting
        if response_text.startswith("```json"):
            response_text = response_text[7:-3]
        elif response_text.startswith("```"):
            response_text = response_text[3:-3]
        
        logger.info(f"Extracted modification parameters: {response_text}")
        
        try:
            parsed_response = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error in parse_modify_event_query: {e}")
            # Fallback - infer modification type based on keywords
            parsed_response = {
                "event_name": "",
                "date": current_date
            }
            
            if is_rescheduling:
                parsed_response["modification_type"] = "reschedule"
            elif is_cancellation:
                parsed_response["modification_type"] = "cancel"
            elif is_duration_change:
                parsed_response["modification_type"] = "change_duration"
            elif is_detail_change:
                parsed_response["modification_type"] = "change_details"
            elif is_conflict_resolution:
                parsed_response["modification_type"] = "resolve_conflict"
            else:
                parsed_response["modification_type"] = "unknown"
                
            # Try to extract event name from the query
            # Remove common modification phrases
            clean_text = text.lower()
            for phrase in ["reschedule", "cancel", "remove", "delete", "extend", "shorten", 
                          "change", "modify", "update", "move", "shift", "postpone"]:
                clean_text = clean_text.replace(phrase, "")
                
            # Extract what seems to be the event name
            for phrase in ["my", "the", "event", "meeting", "appointment", "session", "class"]:
                if phrase in clean_text:
                    parts = clean_text.split(phrase, 1)
                    if len(parts) > 1 and parts[1].strip():
                        potential_name = parts[1].strip()
                        # Remove any trailing text after prepositions
                        for prep in ["to", "from", "by", "at", "for", "on"]:
                            if f" {prep} " in potential_name:
                                potential_name = potential_name.split(f" {prep} ")[0].strip()
                        
                        # Remove punctuation at the end
                        potential_name = potential_name.rstrip(".,:;!?")
                        parsed_response["event_name"] = potential_name
                        break
        
        # Ensure event_name is not None
        if parsed_response.get("event_name") is None:
            parsed_response["event_name"] = ""
            
        # Ensure date is not None
        if parsed_response.get("date") is None:
            parsed_response["date"] = current_date
            
        return parsed_response
    except Exception as e:
        logger.error(f"Error parsing modify event query: {e}")
        return {
            "modification_type": "unknown",
            "event_name": "",
            "date": datetime.datetime.now().strftime("%Y-%m-%d")
        }

def match_events_for_modification(service, calendar_ids, query_params, time_min=None, time_max=None):
    """Match events based on query parameters for modification."""
    try:
        # Set default time range if not provided
        if not time_min or not time_max:
            # Default to a 7-day window (3 days back, 3 days forward)
            now = datetime.datetime.now()
            start_date = (now - datetime.timedelta(days=3)).strftime("%Y-%m-%dT00:00:00-07:00")
            end_date = (now + datetime.timedelta(days=3)).strftime("%Y-%m-%dT23:59:59-07:00")
            time_min = start_date
            time_max = end_date
            
            # If a specific date is provided, use that day's range
            if query_params.get("date"):
                date_str = query_params.get("date")
                # Handle relative dates
                if date_str.lower() == "today":
                    date_obj = now.date()
                elif date_str.lower() == "tomorrow":
                    date_obj = (now + datetime.timedelta(days=1)).date()
                elif date_str.lower() == "yesterday":
                    date_obj = (now - datetime.timedelta(days=1)).date()
                else:
                    # Try to parse the date
                    try:
                        date_obj = dateutil_parse(date_str).date()
                    except:
                        # Fall back to today
                        date_obj = now.date()
                
                time_min = f"{date_obj.isoformat()}T00:00:00-07:00"
                time_max = f"{date_obj.isoformat()}T23:59:59-07:00"
        
        # Fetch all events in the time range
        all_events = fetch_events(service, calendar_ids, time_min, time_max)
        
        # If we have original_time, use it to narrow down the search
        original_time = query_params.get("original_time")
        if original_time:
            try:
                time_obj = dateutil_parse(original_time).time()
                # Filter events to those close to the specified time
                hour, minute = time_obj.hour, time_obj.minute
                filtered_events = []
                
                for event in all_events:
                    start_time = dateutil_parse(event['start']['dateTime']).time()
                    # Allow a 15-minute margin
                    start_hour, start_minute = start_time.hour, start_time.minute
                    time_diff = abs(hour * 60 + minute - start_hour * 60 - start_minute)
                    if time_diff <= 30:  # Within 30 minutes
                        filtered_events.append(event)
                
                all_events = filtered_events
            except Exception as e:
                logger.error(f"Error filtering by original time: {e}")
        
        # Extract the event name to match
        event_name = query_params.get("event_name", "").lower()
        if not event_name:
            # If no event name provided but we have filtered by time, return the filtered events
            if original_time and len(all_events) <= 3:
                return all_events
            # Otherwise, we can't match without more info
            return []
        
        # Use LLM to find matching events, which is more flexible than exact matching
        model = genai.GenerativeModel(model_name="gemini-2.0-flash")
        
        # Prepare a concise list of event summaries and times for matching
        event_summaries = []
        for event in all_events:
            start_dt = dateutil_parse(event['start']['dateTime'])
            summary = event.get('summary', 'Untitled Event')
            event_summaries.append({
                "id": event['id'], 
                "summary": summary, 
                "start_time": start_dt.strftime("%H:%M"),
                "location": event.get('location', ''),
                "description": event.get('description', '')[:100] if event.get('description') else ''
            })
        
        # Using a prompt to match events
        matching_prompt = f"""
        Find the best matching event(s) from this list for the query: "{event_name}"
        
        Events:
        {json.dumps(event_summaries, indent=2)}
        
        Instructions:
        1. Match based on event title, but also consider time, location, and description.
        2. Return only the IDs of the matching events in a JSON array.
        3. If there are multiple matches with the same name, order them by likely relevance.
        4. Return at most 3 matching events.
        5. Return an empty array if no match is found.
        
        Return only the JSON array of event IDs, nothing else:
        """
        
        response = model.generate_content(matching_prompt)
        matching_ids_text = response.text.strip()
        
        # Handle JSON formatting
        if matching_ids_text.startswith("```json"):
            matching_ids_text = matching_ids_text[7:-3]
        elif matching_ids_text.startswith("```"):
            matching_ids_text = matching_ids_text[3:-3]
        
        try:
            matching_ids = json.loads(matching_ids_text)
            
            # Filter to just the matched events
            matched_events = [event for event in all_events if event['id'] in matching_ids]
            
            return matched_events if matched_events else []
        except Exception as e:
            logger.error(f"Error matching events with LLM: {e}")
            
            # Fallback to basic matching
            matched_events = []
            for event in all_events:
                event_summary = event.get('summary', '').lower()
                event_description = event.get('description', '').lower() if event.get('description') else ''
                event_location = event.get('location', '').lower() if event.get('location') else ''
                
                # Check if event name matches or contains the query
                if (event_name in event_summary or event_name in event_description or 
                    (event_location and event_name in event_location)):
                    matched_events.append(event)
                # Try matching individual words for more flexibility
                elif any(word in event_summary.split() for word in event_name.split() if len(word) > 2):
                    matched_events.append(event)
            
            return matched_events[:3]  # Limit to 3 matches
    except Exception as e:
        logger.error(f"Error in match_events_for_modification: {e}")
        return [] 

def apply_event_modification(service, event, modification_type, modification_params):
    """Apply modifications to an event based on the modification type and parameters."""
    try:
        calendar_id = event.get('calendarId', 'primary')
        event_id = event.get('id')
        
        # First, get the full event from the API to ensure we have all fields
        full_event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        
        # Create a modified copy of the event
        modified_event = full_event.copy()
        
        if modification_type == "reschedule":
            # Handle rescheduling - need to update start and end times
            new_time = modification_params.get("new_time")
            new_date = modification_params.get("new_date")
            
            # Parse the current start and end times
            start_dt = dateutil_parse(full_event['start']['dateTime'])
            end_dt = dateutil_parse(full_event['end']['dateTime'])
            duration = (end_dt - start_dt).total_seconds() / 60  # Duration in minutes
            
            # If we have new_time, new_date, or both, update the start time
            if new_time or new_date:
                try:
                    # Create new date obj, using the new_date if provided or the original date otherwise
                    if new_date:
                        # Handle relative date references
                        if new_date.lower() == "today":
                            new_date_obj = datetime.datetime.now().date()
                        elif new_date.lower() == "tomorrow":
                            new_date_obj = (datetime.datetime.now() + datetime.timedelta(days=1)).date()
                        else:
                            # Try to parse the date
                            new_date_obj = dateutil_parse(new_date).date()
                    else:
                        new_date_obj = start_dt.date()
                    
                    # Parse the new time if provided, otherwise keep original time
                    if new_time:
                        # Check if it's a time period name from config.py
                        new_time_lower = new_time.lower()
                        if new_time_lower in time_periods:
                            # Use the default time for this time period
                            new_time = time_periods[new_time_lower]['default_time']
                            logger.info(f"Using default time {new_time} for time period {new_time_lower}")
                        
                        # Now parse with dateutil
                        new_time_obj = dateutil_parse(new_time).time()
                    else:
                        # Keep the original time
                        new_time_obj = start_dt.time()
                        logger.info(f"No new time provided, keeping original time {new_time_obj}")
                    
                    # Create new start datetime
                    new_start_dt = datetime.datetime.combine(new_date_obj, new_time_obj)
                    
                    # Create new end datetime by adding the duration
                    new_end_dt = new_start_dt + datetime.timedelta(minutes=duration)
                    
                    # Update the event with new start and end times
                    modified_event['start']['dateTime'] = new_start_dt.isoformat()
                    modified_event['end']['dateTime'] = new_end_dt.isoformat()
                    
                    # Ensure timezone is preserved
                    if 'timeZone' in full_event['start']:
                        modified_event['start']['timeZone'] = full_event['start']['timeZone']
                    if 'timeZone' in full_event['end']:
                        modified_event['end']['timeZone'] = full_event['end']['timeZone']
                except Exception as e:
                    logger.error(f"Error rescheduling event: {e}")
                    return {"success": False, "message": f"Error rescheduling: {str(e)}"}
            else:
                return {"success": False, "message": "No new date or time provided for rescheduling"}
            
            # Update the event
            updated_event = service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=modified_event
            ).execute()
            
            # Format response
            start_dt = dateutil_parse(updated_event['start']['dateTime'])
            formatted_start = start_dt.strftime("%A, %B %d at %I:%M %p")
            
            return {
                "success": True, 
                "message": f"Event rescheduled to {formatted_start}",
                "event": updated_event
            }
            
        elif modification_type == "cancel":
            # Delete the event
            service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
            
            return {
                "success": True,
                "message": f"Event '{full_event.get('summary', 'Untitled Event')}' has been cancelled"
            }
            
        elif modification_type == "change_duration":
            # Update event duration
            duration_change = modification_params.get("duration_change")
            new_duration = modification_params.get("new_duration")
            
            try:
                # Parse the current start and end times
                start_dt = dateutil_parse(full_event['start']['dateTime'])
                end_dt = dateutil_parse(full_event['end']['dateTime'])
                current_duration = (end_dt - start_dt).total_seconds() / 60  # Duration in minutes
                
                # Calculate new duration
                if new_duration:
                    # Absolute duration specified
                    updated_duration = int(new_duration)
                elif duration_change:
                    # Relative change specified
                    if duration_change.startswith("+"):
                        minutes_to_add = int(duration_change[1:])
                        updated_duration = current_duration + minutes_to_add
                    elif duration_change.startswith("-"):
                        minutes_to_subtract = int(duration_change[1:])
                        updated_duration = current_duration - minutes_to_subtract
                    else:
                        # If no sign, assume it's an absolute value
                        updated_duration = int(duration_change)
                else:
                    # No change specified
                    return {"success": False, "message": "No duration change specified"}
                
                # Ensure minimum duration
                if updated_duration < 5:
                    updated_duration = 5  # Minimum 5 minutes
                
                # Calculate new end time
                new_end_dt = start_dt + datetime.timedelta(minutes=updated_duration)
                modified_event['end']['dateTime'] = new_end_dt.isoformat()
                
                # Update the event
                updated_event = service.events().update(
                    calendarId=calendar_id,
                    eventId=event_id,
                    body=modified_event
                ).execute()
                
                # Format the duration for display
                hours, minutes = divmod(updated_duration, 60)
                duration_text = ""
                if hours > 0:
                    duration_text += f"{int(hours)} hour" + ("s" if hours != 1 else "")
                if minutes > 0:
                    if duration_text:
                        duration_text += " and "
                    duration_text += f"{int(minutes)} minute" + ("s" if minutes != 1 else "")
                
                return {
                    "success": True,
                    "message": f"Event duration updated to {duration_text}",
                    "event": updated_event
                }
            except Exception as e:
                logger.error(f"Error changing event duration: {e}")
                return {"success": False, "message": f"Error changing duration: {str(e)}"}
                
        elif modification_type == "change_details":
            # Update event details
            field = modification_params.get("field_to_change", "").lower()
            new_value = modification_params.get("new_value", "")
            
            if not field or not new_value:
                return {"success": False, "message": "No field or new value specified"}
                
            # Update the appropriate field
            if field == "title" or field == "summary":
                modified_event['summary'] = new_value
            elif field == "location":
                modified_event['location'] = new_value
            elif field == "description":
                modified_event['description'] = new_value
            else:
                return {"success": False, "message": f"Unsupported field to change: {field}"}
                
            # Update the event
            updated_event = service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=modified_event
            ).execute()
            
            return {
                "success": True,
                "message": f"Event {field} updated to '{new_value}'",
                "event": updated_event
            }
            
        elif modification_type == "resolve_conflict":
            # Check for conflicts and suggest alternative times
            # This is a simplified implementation - a more sophisticated version would
            # analyze the user's schedule and find truly optimal times
            
            start_dt = dateutil_parse(full_event['start']['dateTime'])
            end_dt = dateutil_parse(full_event['end']['dateTime'])
            duration = (end_dt - start_dt).total_seconds() / 60  # Duration in minutes
            
            # Generate some alternative time slots
            alternatives = []
            
            # 1. Try later the same day
            later_slot_start = end_dt + datetime.timedelta(minutes=30)
            # Ensure it's not too late in the day
            if later_slot_start.hour < 20:  # Before 8 PM
                later_slot_end = later_slot_start + datetime.timedelta(minutes=duration)
                alternatives.append({
                    "start": later_slot_start.isoformat(),
                    "end": later_slot_end.isoformat(),
                    "description": f"Later today at {later_slot_start.strftime('%I:%M %p')}"
                })
            
            # 2. Try earlier the same day
            earlier_slot_end = start_dt - datetime.timedelta(minutes=30)
            # Ensure it's not too early
            if earlier_slot_end.hour >= 7:  # After 7 AM
                earlier_slot_start = earlier_slot_end - datetime.timedelta(minutes=duration)
                if earlier_slot_start.hour >= 7:  # Still after 7 AM
                    alternatives.append({
                        "start": earlier_slot_start.isoformat(),
                        "end": earlier_slot_end.isoformat(),
                        "description": f"Earlier today at {earlier_slot_start.strftime('%I:%M %p')}"
                    })
            
            # 3. Try same time next day
            next_day = start_dt + datetime.timedelta(days=1)
            next_day_end = end_dt + datetime.timedelta(days=1)
            alternatives.append({
                "start": next_day.isoformat(),
                "end": next_day_end.isoformat(),
                "description": f"Tomorrow at {next_day.strftime('%I:%M %p')}"
            })
            
            # 4. Try same time in two days
            day_after = start_dt + datetime.timedelta(days=2)
            day_after_end = end_dt + datetime.timedelta(days=2)
            alternatives.append({
                "start": day_after.isoformat(),
                "end": day_after_end.isoformat(),
                "description": f"{day_after.strftime('%A')} at {day_after.strftime('%I:%M %p')}"
            })
            
            return {
                "success": True,
                "message": "Here are some alternative times for your event",
                "event": full_event,
                "alternatives": alternatives
            }
            
        else:
            return {"success": False, "message": f"Unsupported modification type: {modification_type}"}
    
    except Exception as e:
        logger.error(f"Error modifying event: {e}")
        return {"success": False, "message": f"Error modifying event: {str(e)}"}

def generate_modification_response(modification_result, modification_type, event_summary):
    """Generate a user-friendly response for event modifications."""
    try:
        if not modification_result.get("success"):
            return f"Sorry, I couldn't modify the event: {modification_result.get('message')}"
        
        if modification_type == "reschedule":
            start_dt = dateutil_parse(modification_result["event"]["start"]["dateTime"])
            formatted_time = start_dt.strftime("%I:%M %p")
            formatted_date = start_dt.strftime("%A, %B %d")
            
            # Check if the date is today or tomorrow for more natural responses
            today = datetime.datetime.now().date()
            tomorrow = today + datetime.timedelta(days=1)
            
            if start_dt.date() == today:
                date_str = "today"
            elif start_dt.date() == tomorrow:
                date_str = "tomorrow"
            else:
                date_str = formatted_date
                
            return f"I've rescheduled '{event_summary}' to {date_str} at {formatted_time}."
            
        elif modification_type == "cancel":
            return f"I've cancelled '{event_summary}' from your calendar."
            
        elif modification_type == "change_duration":
            # Extract the updated duration from the message
            duration_text = modification_result.get("message", "").replace("Event duration updated to ", "")
            return f"I've updated the duration of '{event_summary}' to {duration_text}."
            
        elif modification_type == "change_details":
            # Extract what was changed from the message
            change_message = modification_result.get("message", "")
            field = "details"
            if "title updated" in change_message:
                field = "title"
            elif "location updated" in change_message:
                field = "location"
            elif "description updated" in change_message:
                field = "description"
                
            return f"I've updated the {field} of '{event_summary}'."
            
        elif modification_type == "resolve_conflict":
            alternatives = modification_result.get("alternatives", [])
            if not alternatives:
                return f"I couldn't find any alternative times for '{event_summary}'."
                
            response = f"<div class='alternatives-card'><p>Here are some alternative times for '{event_summary}':</p><ul>"
            
            for alt in alternatives:
                desc = alt.get("description", "")
                start = alt.get("start", "")
                end = alt.get("end", "")
                
                # Add a button to reschedule
                response += f"""
                <li>
                    <div class="alternative-time">
                        {desc}
                        <button class="action-button small" onclick="rescheduleEvent('{modification_result['event']['id']}', '{start}', '{end}', '{modification_result['event'].get('calendarId', 'primary')}')">Select</button>
                    </div>
                </li>
                """
            
            response += "</ul></div>"
            return response
        
        # Default response if we can't generate something specific
        return modification_result.get("message", "Event modified successfully")
        
    except Exception as e:
        logger.error(f"Error generating modification response: {e}")
        return "Event modification completed, but I had trouble generating a user-friendly response." 