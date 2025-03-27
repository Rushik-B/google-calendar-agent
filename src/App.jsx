import React, { useState, useEffect, useCallback, memo, useMemo, Suspense, lazy } from 'react';
import axios from 'axios';
import './App.css';

// Remove lazy loading for FullCalendar and its plugins
// Old code:
// const FullCalendar = lazy(() => import('@fullcalendar/react'));
// const dayGridPlugin = lazy(() => import('@fullcalendar/daygrid'));
// const timeGridPlugin = lazy(() => import('@fullcalendar/timegrid'));
// const interactionPlugin = lazy(() => import('@fullcalendar/interaction'));

// New code: import synchronously
import FullCalendar from '@fullcalendar/react';
import dayGridPlugin from '@fullcalendar/daygrid';
import timeGridPlugin from '@fullcalendar/timegrid';
import interactionPlugin from '@fullcalendar/interaction';

// Define the script at global level to ensure the functions are globally accessible
const setupGlobalFunctions = () => {
  if (typeof window !== 'undefined') {
    // Create a custom event for scheduling breaks
    window.scheduleBreak = (startTime, endTime) => {
      console.log("scheduleBreak called with:", startTime, endTime);
      // Dispatch a custom event that the React component can listen for
      window.dispatchEvent(
        new CustomEvent('scheduleCalendarItem', {
          detail: {
            type: 'break',
            startTime,
            endTime
          }
        })
      );
    };
    
    // Create a custom event for scheduling tasks  
    window.scheduleTask = (startTime, endTime) => {
      console.log("scheduleTask called with:", startTime, endTime);
      window.dispatchEvent(
        new CustomEvent('scheduleCalendarItem', {
          detail: {
            type: 'task',
            startTime,
            endTime
          }
        })
      );
    };
    
    // Log to verify functions are attached
    console.log("Global scheduling functions attached:", 
      typeof window.scheduleBreak === 'function', 
      typeof window.scheduleTask === 'function');
  }
};

// Memoize the renderEventContent function to avoid recreating it on each render
const renderEventContent = (eventInfo) => {
  // Determine if this is a suggested slot or existing event
  const isSuggested = eventInfo.event.extendedProps?.suggestedSlot === true;
  const isExisting = eventInfo.event.extendedProps?.existingEvent === true;
  
  // Format the time more cleanly
  let timeText = eventInfo.timeText || '';
  if (timeText.includes('-')) {
    // Simplify time range display
    const times = timeText.split('-');
    timeText = times[0].trim() + ' - ' + times[1].trim();
  }
  
  // Get the calendar name if available
  let calendarName = '';
  if (isExisting && eventInfo.event.extendedProps?.calendarName) {
    calendarName = `(${eventInfo.event.extendedProps.calendarName})`;
  }
  
  // Get the event title with fallback options
  const title = eventInfo.event.title || 
                eventInfo.event.extendedProps?.summary || 
                (isSuggested ? 'Suggested Time' : 'Event');
  
  return (
    <div className={`event-content ${isSuggested ? 'suggested-event' : 'existing-event'}`}>
      <b>{timeText}</b>
      <i>{title} {calendarName}</i>
    </div>
  );
};

// Define the Calendar component outside of the main component
const CalendarComponent = memo(({ 
  events, 
  handleEventClick, 
  handleDatesSet, 
  loading,
  renderEventContent 
}) => {
  return (
    <div className={`calendar-container ${loading ? 'loading' : ''}`}>
      <FullCalendar
        plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
        initialView="timeGridWeek"
        headerToolbar={{
          left: 'prev,next today',
          center: 'title',
          right: 'dayGridMonth,timeGridWeek,timeGridDay'
        }}
        events={events}
        eventClick={handleEventClick}
        eventContent={renderEventContent}
        height="800px"
        nowIndicator={true}
        datesSet={handleDatesSet}
        slotMinTime="07:00:00"
        slotMaxTime="23:00:00"
        eventTimeFormat={{
          hour: 'numeric',
          minute: '2-digit',
          meridiem: 'short'
        }}
        slotLabelFormat={{
          hour: 'numeric',
          minute: '2-digit',
          hour12: true
        }}
        allDaySlot={false}
        eventDisplay="block"
        eventBackgroundColor="#4285f4"
        eventBorderColor="#3b78e7"
        eventTextColor="#ffffff"
        displayEventTime={true}
        displayEventEnd={true}
        forceEventDuration={true}
        eventMinHeight={30}
        lazyFetching={true}
      />
    </div>
  );
});

CalendarComponent.displayName = 'CalendarComponent';

// The calendar selection component
const CalendarSelectionComponent = memo(({ calendars, selected, onSelect, disabled }) => {
  return (
    <div className="calendar-selection">
      <h3>Select Calendars to Monitor:</h3>
      {calendars.length > 0 ? (
        calendars.map((cal) => (
          <label key={cal.id} style={{ 
            display: 'block', 
            margin: '5px 0',
            padding: '8px',
            backgroundColor: selected.some(s => s.id === cal.id) ? '#f0f7ff' : 'transparent',
            borderRadius: '4px',
            cursor: disabled ? 'not-allowed' : 'pointer'
          }}>
            <input
              type="checkbox"
              checked={selected.some((s) => s.id === cal.id)}
              onChange={() => onSelect(cal)}
              disabled={disabled}
            />
            <span style={{
              marginLeft: '8px',
              color: cal.primary ? '#1a73e8' : 'inherit',
              fontWeight: cal.primary ? '500' : 'normal'
            }}>
              {cal.summary} {cal.primary ? '(Primary)' : ''}
            </span>
          </label>
        ))
      ) : (
        <p>Loading calendars...</p>
      )}
    </div>
  );
});

CalendarSelectionComponent.displayName = 'CalendarSelectionComponent';

function NaturalLanguageForm() {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  // eslint-disable-next-line no-unused-vars
  const [availableSlots, setAvailableSlots] = useState([]);
  const [calendarEvents, setCalendarEvents] = useState([]);
  const [existingEvents, setExistingEvents] = useState([]);
  const [showCalendar, setShowCalendar] = useState(false);
  const [eventDetails, setEventDetails] = useState({});
  const [selectedSlots, setSelectedSlots] = useState([]);
  // Add cache for events data
  const [eventsCache, setEventsCache] = useState({});
  const [fetchingEvents, setFetchingEvents] = useState(false);
  
  // Call the setup function on load
  useEffect(() => {
    setupGlobalFunctions();
  }, []);
  
  const [calendars, setCalendars] = useState([]);
  const [selectedCalendars, setSelectedCalendars] = useState([]);
  const [dateRange, setDateRange] = useState({
    start: new Date(),
    end: new Date(new Date().setDate(new Date().getDate() + 7))
  });

  // Helper function to format date to YYYY-MM-DD
  const formatDate = (date) => {
    const d = new Date(date);
    let month = '' + (d.getMonth() + 1);
    let day = '' + d.getDate();
    const year = d.getFullYear();

    if (month.length < 2) month = '0' + month;
    if (day.length < 2) day = '0' + day;

    return [year, month, day].join('-');
  };

  // Helper function to get color for a specific calendar
  const getCalendarColor = (calendarId, darker = false) => {
    // Find the calendar in our list
    const calendar = calendars.find(cal => cal.id === calendarId);
    if (calendar && calendar.backgroundColor) {
      // Enhance color vibrancy by ensuring full opacity
      let color = calendar.backgroundColor;
      
      // If it's an RGBA color, convert to fully opaque
      if (color.startsWith('rgba')) {
        const rgbaPattern = /rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*[\d.]+\s*\)/;
        const match = color.match(rgbaPattern);
        if (match) {
          color = `rgb(${match[1]}, ${match[2]}, ${match[3]})`;
        }
      }
      
      if (darker) {
        // Create a slightly darker version for the border
        return darkenColor(color, 0.2);
      }
      return color;
    }
    // Default color if calendar not found - using a more vibrant blue
    return darker ? '#1565C0' : '#1E88E5';
  };

  // Helper function to darken a color
  const darkenColor = (color, amount) => {
    try {
      // Handle RGB format
      if (color.startsWith('rgb')) {
        const rgbPattern = /rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)/;
        const match = color.match(rgbPattern);
        if (match) {
          let r = parseInt(match[1], 10);
          let g = parseInt(match[2], 10);
          let b = parseInt(match[3], 10);
          
          r = Math.max(0, Math.floor(r * (1 - amount)));
          g = Math.max(0, Math.floor(g * (1 - amount)));
          b = Math.max(0, Math.floor(b * (1 - amount)));
          
          return `rgb(${r}, ${g}, ${b})`;
        }
      }
      
      // Remove the hash if it exists for hex colors
      color = color.replace('#', '');
      
      // Parse the color
      let r = parseInt(color.substring(0, 2), 16);
      let g = parseInt(color.substring(2, 4), 16);
      let b = parseInt(color.substring(4, 6), 16);
      
      // Darken the color
      r = Math.max(0, Math.floor(r * (1 - amount)));
      g = Math.max(0, Math.floor(g * (1 - amount)));
      b = Math.max(0, Math.floor(b * (1 - amount)));
      
      // Convert back to hex
      return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`;
    } catch (e) {
      console.error('Error darkening color:', e);
      return color; // Return original color if there's an error
    }
  };

  // Define fetchExistingEvents before it's used in the event listener
  const fetchExistingEvents = useCallback(async (forceRefresh = false) => {
    // Prevent multiple simultaneous requests
    if (fetchingEvents) return;
    
    try {
      setFetchingEvents(true);
      const startDate = formatDate(dateRange.start);
      const endDate = formatDate(dateRange.end);
      
      // Skip logging in production
      if (process.env.NODE_ENV !== 'production') {
        console.log("Fetching events from:", startDate, "to", endDate);
      }
      
      // Create the calendar IDs parameter
      const calendarIds = selectedCalendars.map(cal => cal.id).join(',');
      
      // Create a cache key based on date range and selected calendars
      const cacheKey = `${startDate}_${endDate}_${calendarIds}`;
      
      // Check if we have cached data and not forcing refresh
      if (!forceRefresh && eventsCache[cacheKey] && eventsCache[cacheKey].expiry > Date.now()) {
        setExistingEvents(eventsCache[cacheKey].data);
        setFetchingEvents(false);
        return;
      }
      
      // Add retry logic
      let retries = 0;
      const maxRetries = 3;
      let response;
      
      while (retries < maxRetries) {
        try {
          response = await axios.get(
            `http://127.0.0.1:5000/api/get-events?start=${startDate}&end=${endDate}&calendars=${calendarIds}`
          );
          break; // Success, exit retry loop
        } catch (err) {
          const currentRetry = retries; // Capture current value to avoid the loop reference issue
          retries++;
          if (currentRetry === maxRetries - 1) throw err;
          // Wait before retrying (exponential backoff)
          await new Promise(resolve => setTimeout(resolve, 1000 * Math.pow(2, currentRetry + 1)));
        }
      }
      
      if (response.data.success) {
        // Check if there are any events in the response
        let events = response.data.events || [];
        
        // If no events are returned and we're in development mode, add some mock events for testing
        if (events.length === 0 && process.env.NODE_ENV === 'development') {
          console.log("No events returned from API, adding mock events for testing");
          // Create a few mock events for the current week
          const now = new Date();
          const tomorrow = new Date(now);
          tomorrow.setDate(tomorrow.getDate() + 1);
          
          events = [
            {
              id: 'mock-1',
              title: 'Team Meeting',
              start: new Date(now.getFullYear(), now.getMonth(), now.getDate(), 10, 0).toISOString(),
              end: new Date(now.getFullYear(), now.getMonth(), now.getDate(), 11, 0).toISOString(),
              calendarId: 'primary',
              calendarName: 'Primary Calendar'
            },
            {
              id: 'mock-2',
              title: 'Lunch Break',
              start: new Date(now.getFullYear(), now.getMonth(), now.getDate(), 12, 0).toISOString(),
              end: new Date(now.getFullYear(), now.getMonth(), now.getDate(), 13, 0).toISOString(),
              calendarId: 'primary',
              calendarName: 'Primary Calendar'
            },
            {
              id: 'mock-3',
              title: 'Project Review',
              start: new Date(tomorrow.getFullYear(), tomorrow.getMonth(), tomorrow.getDate(), 14, 0).toISOString(),
              end: new Date(tomorrow.getFullYear(), tomorrow.getMonth(), tomorrow.getDate(), 15, 30).toISOString(),
              calendarId: 'work',
              calendarName: 'Work Calendar'
            }
          ];
        }
        
        if (events.length > 0) {
          // Process all events at once with minimal logging
          const eventsWithMetadata = events.map(event => ({
            ...event,
            title: event.title || event.summary || "Untitled Event",
            existingEvent: true,
            backgroundColor: event.backgroundColor || getCalendarColor(event.calendarId),
            borderColor: event.borderColor || getCalendarColor(event.calendarId, true),
            textColor: event.textColor || '#ffffff',
            classNames: ['calendar-event']  // Add a class for additional styling
          }));
          
          // Update the cache with a 5-minute expiration
          setEventsCache(prev => ({
            ...prev,
            [cacheKey]: {
              data: eventsWithMetadata,
              expiry: Date.now() + 5 * 60 * 1000 // 5 minutes
            }
          }));
          
          setExistingEvents(eventsWithMetadata);
        } else {
          setExistingEvents([]);
        }
      } else {
        console.error('Error fetching events:', response.data.message);
      }
    } catch (error) {
      console.error('Error fetching events:', error);
      setError('Failed to load events. Please try again.');
    } finally {
      setFetchingEvents(false);
    }
  }, [dateRange, formatDate, getCalendarColor, selectedCalendars, eventsCache, fetchingEvents, setError]);

  // Define handleSubmit with useCallback before it's used in handleScheduleItem
  const handleSubmit = useCallback(async (e) => {
    e.preventDefault();
    console.log("handleSubmit called with text:", text);
    if (!text.trim()) return;

    setLoading(true);
    setError("");
    setMessage("");
    setAvailableSlots([]);
    setCalendarEvents([]);
    setSelectedSlots([]);
    setShowCalendar(false);

    try {
      console.log("Making API call with text:", text);
      const response = await axios.post('http://127.0.0.1:5000/api/natural-language-event', {
        text
      });
      console.log("API response:", response.data);

      if (response.data.success) {
        // Use humanizedResponse from backend if available
        if (response.data.humanizedResponse) {
          if (response.data.intent === "check_free_time") {
            // For check_free_time intent, we need to render HTML
            setMessage('');
            // Use a timeout to ensure state updates don't conflict
            setTimeout(() => {
              const messageElement = document.querySelector('.success-message');
              if (messageElement) {
                messageElement.innerHTML = response.data.humanizedResponse;
              } else {
                // Fallback in case the element isn't found
                setMessage(response.data.humanizedResponse);
              }
            }, 10);
            setText("");
          } else {
            // For other intents, just set the text message
            setMessage(response.data.humanizedResponse);
          }
        }
        
        if (response.data.intent === "find_time") {
          setAvailableSlots(response.data.availableSlots);
          setCalendarEvents(response.data.events || []);
          setShowCalendar(true);
          
          // Check if we have the insufficientTime flag
          if (response.data.insufficientTime) {
            // eslint-disable-next-line no-unused-vars
            const requestedHours = response.data.requestedHours;
            // eslint-disable-next-line no-unused-vars
            const foundHours = response.data.foundHours;
            // Use the humanizedResponse for error message if available
            setError(`INSUFFICIENT TIME: ${response.data.humanizedResponse || response.data.message} Select these slots or try a different timeframe.`);
          } else if (!response.data.humanizedResponse) {
            // Only set this default message if humanizedResponse wasn't already set
            setMessage("Here are suggested time slots on your calendar. Click on slots to select/deselect them for scheduling.");
          }
          
          setEventDetails({
            summary: response.data.calendar_title || getEventSummaryFromText(text),
            description: text,
            calendarId: response.data.predicted_calendar || "primary"
          });
        } else if (response.data.intent === "view_events") {
          // Just display the humanized response for view_events, no calendar needed
          setText("");
        } else if (response.data.intent === "Create event" && !response.data.humanizedResponse) {
          // Fallback for create event if no humanizedResponse is available
          setMessage(`Event created! ${response.data.eventLink ? `View it here: ${response.data.eventLink}` : ''}`);
          setText("");
        } else {
          // For other intents or if we already set humanizedResponse
          setText("");
        }
      } else {
        setError(`Error: ${response.data.humanizedResponse || response.data.message}`);
      }
    } catch (error) {
      setError(`Error: ${error.response?.data?.message || error.message}`);
    } finally {
      setLoading(false);
    }
  }, [text, setLoading, setError, setMessage, setAvailableSlots, setCalendarEvents, 
      setSelectedSlots, setShowCalendar, setText, setEventDetails]);

  // Event handler for scheduling items - using useCallback to avoid dependency issues
  const handleScheduleItem = useCallback((event) => {
    console.log("Custom event received:", event.detail);
    const { type, startTime, endTime } = event.detail;
    const startDate = new Date();
    const formattedDate = startDate.toLocaleDateString('en-US', { 
      month: 'long', 
      day: 'numeric',
      year: 'numeric'
    });
    
    if (type === 'break') {
      const newText = `Schedule a break on ${formattedDate} from ${startTime} to ${endTime}`;
      console.log("Setting text for break:", newText);
      setText(newText);
      // Submit after React has updated the state
      setTimeout(() => {
        handleSubmit({ preventDefault: () => {} });
      }, 50);
    } else if (type === 'task') {
      // Show prompt for task name
      const taskName = prompt("What would you like to name this task?", "Work Session");
      if (taskName) {
        const newText = `Schedule ${taskName} on ${formattedDate} from ${startTime} to ${endTime}`;
        console.log("Setting text for task:", newText);
        setText(newText);
        // Submit after React has updated the state
        setTimeout(() => {
          handleSubmit({ preventDefault: () => {} });
        }, 50);
      }
    }
  }, [setText, handleSubmit]);
  
  // Set up event listeners
  useEffect(() => {
    window.addEventListener('scheduleCalendarItem', handleScheduleItem);
    
    // Add event listener for refreshCalendar event
    const handleRefreshCalendar = () => {
      if (showCalendar) {
        console.log("Refreshing calendar events via refreshCalendar event");
        fetchExistingEvents();
      }
    };
    
    window.addEventListener('refreshCalendar', handleRefreshCalendar);
    
    // Clean up event listeners
    return () => {
      window.removeEventListener('scheduleCalendarItem', handleScheduleItem);
      window.removeEventListener('refreshCalendar', handleRefreshCalendar);
    };
  }, [handleScheduleItem, fetchExistingEvents, showCalendar]);

  // Fetch existing events when calendar is shown or date range changes
  useEffect(() => {
    if (showCalendar) {
      console.log("Fetching existing events because calendar is shown or date range changed");
      fetchExistingEvents();
    }
  }, [showCalendar, dateRange, fetchExistingEvents]);

  // Fetch all calendars and current preferences on mount
  useEffect(() => {
    const fetchData = async () => {
      try {
        // Use Promise.all to fetch calendars and preferences in parallel
        const [calendarsResponse, prefsResponse] = await Promise.all([
          axios.get('http://127.0.0.1:5000/api/get-calendars'),
          axios.get('http://127.0.0.1:5000/api/get-preferred-calendars')
        ]);
        
        if (!calendarsResponse.data.success) {
          throw new Error(`Failed to fetch calendars: ${calendarsResponse.data.message || 'Unknown error'}`);
        }
        
        if (!prefsResponse.data.success) {
          throw new Error(`Failed to fetch preferred calendars: ${prefsResponse.data.message || 'Unknown error'}`);
        }
        
        const allCalendars = calendarsResponse.data.calendars;
        const preferredCals = prefsResponse.data.calendars;

        // Update state all at once to avoid multiple re-renders
        if (preferredCals.length > 0) {
          // Ensure the saved preferences match the full calendar data
          const syncedPrefs = preferredCals.map(pref => 
            allCalendars.find(cal => cal.id === pref.id) || pref
          );
          setCalendars(allCalendars);
          setSelectedCalendars(syncedPrefs);
        } else {
          const primaryCal = allCalendars.find(cal => cal.primary);
          setCalendars(allCalendars);
          if (primaryCal) {
            setSelectedCalendars([primaryCal]);
          }
        }
      } catch (error) {
        console.error('Error fetching data:', error);
        setError(`Error loading calendars or preferences: ${error.message}`);
      }
    };
    fetchData();
  }, []);

  // Send preferences to backend only when user changes them
  useEffect(() => {
    if (selectedCalendars.length > 0) {
      const sendPreferences = async () => {
        try {
          // Debounce the API call to avoid excessive requests
          const timeoutId = setTimeout(async () => {
            const response = await axios.post('http://127.0.0.1:5000/api/set-preferred-calendars', {
              calendars: selectedCalendars
            });
            if (!response.data.success) {
              throw new Error(response.data.message);
            }
          }, 500); // Wait 500ms before sending the request
          
          // Clear the timeout if the effect runs again before it fires
          return () => clearTimeout(timeoutId);
        } catch (error) {
          console.error('Error setting preferred calendars:', error);
          setError('Error saving calendar preferences.');
        }
      };
      sendPreferences();
    }
  }, [selectedCalendars]);

  const handleCalendarSelect = useCallback((cal) => {
    setSelectedCalendars((prev) => {
      // Check if we're adding or removing a calendar
      const isRemovingCalendar = prev.some((selected) => selected.id === cal.id);
      const newCalendars = isRemovingCalendar
        ? prev.filter((selected) => selected.id !== cal.id)
        : [...prev, cal];
        
      // Clear events cache when calendars change
      setEventsCache({});
      return newCalendars;
    });
  }, [setEventsCache]);

  const getEventSummaryFromText = (text) => {
    const firstSentence = text.split('.')[0];
    if (firstSentence.length <= 50) return firstSentence;
    return firstSentence.substring(0, 50) + '...';
  };

  const handleEventClick = (info) => {
    const { event } = info;
    
    // Only handle suggested slots
    if (event.extendedProps.suggestedSlot) {
      const eventData = {
        start: event.start.toISOString(),
        end: event.end.toISOString()
      };
      
      // Toggle selection
      setSelectedSlots(prev => {
        const isAlreadySelected = prev.some(slot => 
          slot.start === eventData.start && slot.end === eventData.end
        );
        
        if (isAlreadySelected) {
          // Remove from selection
          return prev.filter(slot => 
            !(slot.start === eventData.start && slot.end === eventData.end)
          );
        } else {
          // Add to selection
          return [...prev, eventData];
        }
      });
      
      // Update event color based on selection
      const isSelected = !selectedSlots.some(slot => 
        slot.start === eventData.start && slot.end === eventData.end
      );
      
      if (isSelected) {
        event.setProp('backgroundColor', '#4caf50');
        event.setProp('borderColor', '#2e7d32');
        event.setProp('title', 'Selected Time');
      } else {
        event.setProp('backgroundColor', '#8bc34a');
        event.setProp('borderColor', '#689f38');
        event.setProp('title', 'Suggested Time');
      }
    } else {
      // For existing events, show some details in a tooltip or alert
      const eventTitle = event.title;
      const eventTime = `${event.start.toLocaleTimeString()} - ${event.end.toLocaleTimeString()}`;
      const calendarName = event.extendedProps.calendarName || 'Unknown Calendar';
      
      // Simple alert for demonstration - in a real app, you might want a tooltip or modal
      alert(`Event: ${eventTitle}\nTime: ${eventTime}\nCalendar: ${calendarName}`);
    }
  };

  const calculateTotalHours = () => {
    let totalMinutes = 0;
    selectedSlots.forEach(slot => {
      const start = new Date(slot.start);
      const end = new Date(slot.end);
      const diffMinutes = (end - start) / (1000 * 60);
      totalMinutes += diffMinutes;
    });
    const hours = Math.floor(totalMinutes / 60);
    const minutes = Math.floor(totalMinutes % 60);
    return `${hours}h ${minutes}m`;
  };

  const handleScheduleSelected = async () => {
    if (selectedSlots.length === 0) return;

    setLoading(true);
    try {
      // Create multiple events, one for each selected slot
      const promises = selectedSlots.map(slot => {
        return axios.post('http://127.0.0.1:5000/api/schedule-selected-slot', {
          selectedSlot: slot,
          eventDetails
        });
      });
      
      const results = await Promise.all(promises);
      const allSuccessful = results.every(r => r.data.success);
      
      if (allSuccessful) {
        setMessage(`All ${selectedSlots.length} events scheduled successfully!`);
        setText("");
        setShowCalendar(false);
        setAvailableSlots([]);
        setCalendarEvents([]);
        setSelectedSlots([]);
      } else {
        setError(`Error: Some events could not be scheduled.`);
      }
    } catch (error) {
      setError(`Error: ${error.response?.data?.message || error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleFindDifferentTimes = () => {
    setMessage("Let's find another time. Please provide more details:");
    setShowCalendar(false);
    setAvailableSlots([]);
    setCalendarEvents([]);
    setSelectedSlots([]);
  };
  
  const handleDatesSet = (dateInfo) => {
    console.log("Calendar dates changed:", dateInfo.startStr, "to", dateInfo.endStr);
    setDateRange({
      start: dateInfo.start,
      end: dateInfo.end
    });
    
    // If calendar is currently showing, fetch events for the new date range
    if (showCalendar) {
      console.log("Fetching events for new date range");
      fetchExistingEvents();
    }
  };
  
  // Optimize to avoid recalculation on each render
  const getAllEvents = useCallback(() => {
    // Start with existing events
    const allEvents = [...existingEvents];
    
    // Add suggested slots with updated colors based on selection
    if (calendarEvents.length > 0) {
      calendarEvents.forEach(event => {
        const isSelected = selectedSlots.some(slot => 
          slot.start === event.start && slot.end === event.end
        );
        
        allEvents.push({
          ...event,
          backgroundColor: isSelected ? '#4caf50' : '#8bc34a',
          borderColor: isSelected ? '#2e7d32' : '#689f38',
          textColor: '#ffffff',
          title: isSelected ? 'Selected Time' : 'Suggested Time',
          display: 'block',
          extendedProps: {
            ...event.extendedProps,
            suggestedSlot: true
          }
        });
      });
    }
    
    return allEvents;
  }, [existingEvents, calendarEvents, selectedSlots]);

  // Precalculate events to avoid useMemo in render
  const currentEvents = getAllEvents();

  return (
    <div className="natural-language-form">
      <h2>Create Event with Natural Language</h2>

      <CalendarSelectionComponent 
        calendars={calendars}
        selected={selectedCalendars}
        onSelect={handleCalendarSelect}
        disabled={loading}
      />

      {error && <div className="error-message">{error}</div>}
      {message && <div className="success-message" dangerouslySetInnerHTML={{ __html: message }} />}

      {!showCalendar ? (
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Describe your event:</label>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              disabled={loading}
              rows={3}
              placeholder="e.g., 'Schedule a team meeting next Tuesday at 2pm' or 'Find me time to work on my project tomorrow afternoon'"
              required
            />
          </div>
          <button type="submit" disabled={loading} className="submit-button">
            {loading ? 'Processing...' : 'Submit'}
          </button>
        </form>
      ) : (
        <div className="calendar-view">
          {selectedSlots.length > 0 && (
            <div className="selection-summary">
              <p>Selected {selectedSlots.length} slot(s) - Total time: {calculateTotalHours()}</p>
            </div>
          )}
          <div className="calendar-legend">
            {/* Legend for suggested/selected slots */}
            <div className="legend-section">
              <div className="legend-item">
                <span className="legend-color suggested-event-color"></span>
                <span>Suggested Work Slots</span>
              </div>
              <div className="legend-item">
                <span className="legend-color selected-event-color"></span>
                <span>Selected Work Slots</span>
              </div>
            </div>
            
            {/* Legend for calendars */}
            <div className="legend-section">
              <div className="legend-title">Your Calendars:</div>
              {selectedCalendars.map(cal => (
                <div className="legend-item" key={cal.id}>
                  <span 
                    className="legend-color" 
                    style={{ 
                      backgroundColor: cal.backgroundColor || getCalendarColor(cal.id),
                      border: `1px solid ${cal.borderColor || getCalendarColor(cal.id, true)}`
                    }}
                  ></span>
                  <span>{cal.summary}</span>
                </div>
              ))}
            </div>
          </div>
          
          {/* Use the memoized calendar component with precalculated events */}
          <CalendarComponent 
            events={currentEvents}
            handleEventClick={handleEventClick}
            handleDatesSet={handleDatesSet}
            loading={loading || fetchingEvents} 
            renderEventContent={renderEventContent}
          />
          
          <div className="calendar-actions">
            <button
              onClick={handleScheduleSelected}
              disabled={selectedSlots.length === 0 || loading}
              className="confirm-button"
            >
              {loading ? 'Scheduling...' : `Schedule ${selectedSlots.length} Selected Time${selectedSlots.length === 1 ? '' : 's'}`}
            </button>
            <button
              onClick={handleFindDifferentTimes}
              disabled={loading}
              className="reject-button"
            >
              Find Different Times
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function App() {
  return (
    <div className="App">
      <script dangerouslySetInnerHTML={{
        __html: `
          // Directly define functions in the global scope
          window.scheduleBreak = function(startTime, endTime) {
            console.log("DOM scheduleBreak called with:", startTime, endTime);
            if (window.dispatchEvent) {
              window.dispatchEvent(
                new CustomEvent('scheduleCalendarItem', {
                  detail: {
                    type: 'break',
                    startTime,
                    endTime
                  }
                })
              );
            }
          };
          
          window.scheduleTask = function(startTime, endTime) {
            console.log("DOM scheduleTask called with:", startTime, endTime);
            if (window.dispatchEvent) {
              window.dispatchEvent(
                new CustomEvent('scheduleCalendarItem', {
                  detail: {
                    type: 'task',
                    startTime,
                    endTime
                  }
                })
              );
            }
          };
          
          // Duration selector functions
          window.showDurationSelector = function(startTime, endTime, selectorId, displayId, sliderId) {
            console.log("Showing duration selector", selectorId);
            const durationSelector = document.getElementById(selectorId);
            if (durationSelector) {
              durationSelector.style.display = 'block';
            } else {
              console.error("Duration selector element not found:", selectorId);
            }
          };
          
          window.updateDurationDisplay = function(minutes, displayId) {
            console.log("Updating duration display to", minutes, "for", displayId);
            const durationDisplay = document.getElementById(displayId);
            if (!durationDisplay) {
              console.error("Duration display element not found:", displayId);
              return;
            }
            
            let display = "";
            if (minutes >= 60) {
              const hours = Math.floor(minutes / 60);
              const remainingMinutes = minutes % 60;
              display = hours + " hour" + (hours > 1 ? "s" : "");
              if (remainingMinutes > 0) {
                display += " " + remainingMinutes + " min";
              }
            } else {
              display = minutes + " min";
            }
            durationDisplay.textContent = display;
          };
          
          window.scheduleBreakWithDuration = function(startTime, endTime, sliderId) {
            console.log("Scheduling break with duration using slider", sliderId);
            const durationSlider = document.getElementById(sliderId);
            if (!durationSlider) {
              console.error("Duration slider not found:", sliderId);
              return;
            }
            
            const durationMinutes = durationSlider.value;
            console.log("Duration selected:", durationMinutes);
            
            const startDateTime = new Date();
            const [startHours, startMinutes] = startTime.split(':').map(Number);
            startDateTime.setHours(startHours, startMinutes, 0);
            
            // Calculate end time based on selected duration
            const endDateTime = new Date(startDateTime);
            endDateTime.setMinutes(startDateTime.getMinutes() + parseInt(durationMinutes));
            
            const formattedEndTime = endDateTime.getHours().toString().padStart(2, '0') + ':' + 
                                  endDateTime.getMinutes().toString().padStart(2, '0');
            
            console.log("Calculated end time:", formattedEndTime);
            
            // Call the existing scheduleBreak function
            window.scheduleBreak(startTime, formattedEndTime);
          };
          
          window.cancelDurationSelection = function(selectorId) {
            console.log("Canceling duration selection for", selectorId);
            const durationSelector = document.getElementById(selectorId);
            if (durationSelector) {
              durationSelector.style.display = 'none';
            } else {
              console.error("Duration selector element not found:", selectorId);
            }
          };
          
          console.log("Inline scheduling functions defined and attached to window object");
        `
      }} />
      <style jsx="true">{`
        .success-message {
          white-space: pre-line;
          line-height: 1.5;
          padding: 15px;
          border-radius: 8px;
          background-color: #f5f5f5;
          margin: 15px 0;
        }
        
        .success-message b {
          font-weight: 600;
        }
        
        .time-slot {
          font-weight: 500;
          color: #1a73e8;
        }
        
        .free-time-card {
          background-color: #e8f5e9;
          border-radius: 8px;
          padding: 15px;
          margin: 10px 0;
        }
        
        .free-time-actions {
          display: flex;
          gap: 10px;
          margin-top: 15px;
        }
        
        .action-button {
          background-color: #4caf50;
          color: white;
          border: none;
          border-radius: 4px;
          padding: 8px 16px;
          cursor: pointer;
          font-size: 14px;
          transition: background-color 0.3s;
        }
        
        .action-button:hover {
          background-color: #388e3c;
        }
        
        .action-button.small {
          padding: 4px 12px;
          font-size: 12px;
        }
        
        .slot-item {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 6px 10px;
          margin: 8px 0;
          background-color: #f0f8ff;
          border-radius: 4px;
        }
        
        .duration-selector {
          background-color: #f9f9f9;
          border-radius: 6px;
          padding: 12px;
          margin-top: 10px;
          border: 1px solid #ddd;
        }
        
        .duration-selector input[type="range"] {
          width: 100%;
          margin: 10px 0;
        }
        
        .action-button.secondary {
          background-color: #9e9e9e;
        }
        
        .action-button.secondary:hover {
          background-color: #757575;
        }
        
        .loading-calendar {
          display: flex;
          align-items: center;
          justify-content: center;
          height: 500px;
          background-color: #f9f9f9;
          border-radius: 8px;
          font-size: 18px;
          color: #666;
          border: 1px dashed #ddd;
        }
        
        .loading-calendar::after {
          content: "";
          display: inline-block;
          width: 20px;
          height: 20px;
          margin-left: 10px;
          border: 3px solid #ddd;
          border-top-color: #3498db;
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
          to {
            transform: rotate(360deg);
          }
        }
        
        .calendar-container {
          position: relative;
          min-height: 500px;
        }
        
        .calendar-container::before {
          content: "";
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background-color: rgba(255, 255, 255, 0.7);
          z-index: 5;
          display: none;
        }
        
        .calendar-container.loading::before {
          display: block;
        }
        
        .fc-event {
          transition: background-color 0.2s ease;
        }
        
        .fc-event:hover {
          filter: brightness(110%);
        }
        
        .suggested-event-color {
          background-color: #8bc34a;
        }
        
        .selected-event-color {
          background-color: #4caf50;
        }
        
        .event-content {
          padding: 2px 4px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          font-size: 12px;
        }
        
        .suggested-event {
          font-weight: bold;
        }
        
        /* Optimize rendering performance */
        .fc-view-harness {
          contain: content;
          will-change: transform;
        }
        
        /* Prevent layout shifts */
        .natural-language-form {
          min-height: 800px;
        }
      `}</style>
      <Suspense fallback={<div>Loading application...</div>}>
        <NaturalLanguageForm />
      </Suspense>
      <hr />
    </div>
  );
}

export default App;