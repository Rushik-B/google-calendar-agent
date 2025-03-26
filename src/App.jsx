import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import './App.css';
import FullCalendar from '@fullcalendar/react';
import dayGridPlugin from '@fullcalendar/daygrid';
import timeGridPlugin from '@fullcalendar/timegrid';
import interactionPlugin from '@fullcalendar/interaction';

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
  const [calendars, setCalendars] = useState([]);
  const [selectedCalendars, setSelectedCalendars] = useState([]);
  const [dateRange, setDateRange] = useState({
    start: new Date(),
    end: new Date(new Date().setDate(new Date().getDate() + 7))
  });

  // Fetch all calendars and current preferences on mount
  useEffect(() => {
    const fetchData = async () => {
      try {
        // Fetch all calendars
        const calendarsResponse = await axios.get('http://127.0.0.1:5000/api/get-calendars');
        if (!calendarsResponse.data.success) {
          throw new Error('Failed to fetch calendars');
        }
        const allCalendars = calendarsResponse.data.calendars;
        setCalendars(allCalendars);

        // Fetch current preferred calendars
        const prefsResponse = await axios.get('http://127.0.0.1:5000/api/get-preferred-calendars');
        if (!prefsResponse.data.success) {
          throw new Error('Failed to fetch preferred calendars');
        }
        const preferredCals = prefsResponse.data.calendars;

        // If there are saved preferences, use them; otherwise, default to primary
        if (preferredCals.length > 0) {
          // Ensure the saved preferences match the full calendar data (e.g., include all fields)
          const syncedPrefs = preferredCals.map(pref => 
            allCalendars.find(cal => cal.id === pref.id) || pref
          );
          setSelectedCalendars(syncedPrefs);
        } else {
          const primaryCal = allCalendars.find(cal => cal.primary);
          if (primaryCal) {
            setSelectedCalendars([primaryCal]);
          }
        }
      } catch (error) {
        console.error('Error fetching data:', error);
        setError('Error loading calendars or preferences.');
      }
    };
    fetchData();
  }, []);

  // Send preferences to backend only when user changes them
  useEffect(() => {
    if (selectedCalendars.length > 0) {
      const sendPreferences = async () => {
        try {
          const response = await axios.post('http://127.0.0.1:5000/api/set-preferred-calendars', {
            calendars: selectedCalendars
          });
          if (!response.data.success) {
            throw new Error(response.data.message);
          }
        } catch (error) {
          console.error('Error setting preferred calendars:', error);
          setError('Error saving calendar preferences.');
        }
      };
      sendPreferences();
    }
  }, [selectedCalendars]);

  const fetchExistingEvents = useCallback(async () => {
    try {
      const startDate = formatDate(dateRange.start);
      const endDate = formatDate(dateRange.end);
      const response = await axios.get(`http://127.0.0.1:5000/api/get-events?start=${startDate}&end=${endDate}`);
      
      if (response.data.success) {
        setExistingEvents(response.data.events);
      } else {
        console.error('Error fetching events:', response.data.message);
      }
    } catch (error) {
      console.error('Error fetching events:', error);
    }
  }, [dateRange]);

  // Fetch existing events when dateRange changes or when viewing calendar
  useEffect(() => {
    if (showCalendar) {
      fetchExistingEvents();
    }
  }, [dateRange, showCalendar, fetchExistingEvents]);

  const formatDate = (date) => {
    const d = new Date(date);
    let month = '' + (d.getMonth() + 1);
    let day = '' + d.getDate();
    const year = d.getFullYear();

    if (month.length < 2) month = '0' + month;
    if (day.length < 2) day = '0' + day;

    return [year, month, day].join('-');
  };

  const handleCalendarSelect = (cal) => {
    setSelectedCalendars((prev) => {
      if (prev.some((selected) => selected.id === cal.id)) {
        return prev.filter((selected) => selected.id !== cal.id);
      } else {
        return [...prev, cal];
      }
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;

    setLoading(true);
    setError("");
    setMessage("");
    setAvailableSlots([]);
    setCalendarEvents([]);
    setSelectedSlots([]);
    setShowCalendar(false);

    try {
      const response = await axios.post('http://127.0.0.1:5000/api/natural-language-event', {
        text
      });

      if (response.data.success) {
        // Use humanizedResponse from backend if available
        if (response.data.humanizedResponse) {
          setMessage(response.data.humanizedResponse);
        }
        
        if (response.data.intent === "find_time") {
          setAvailableSlots(response.data.availableSlots);
          setCalendarEvents(response.data.calendarEvents);
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
            summary: getEventSummaryFromText(text),
            description: text,
            calendarId: "primary"
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
  };

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
      } else {
        event.setProp('backgroundColor', '#8bc34a');
        event.setProp('borderColor', '#689f38');
      }
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
    setDateRange({
      start: dateInfo.start,
      end: dateInfo.end
    });
  };
  
  const getAllEvents = () => {
    // Combine existing events with suggested slots
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
          title: isSelected ? 'Selected Time' : 'Suggested Time'
        });
      });
    }
    
    return allEvents;
  };

  return (
    <div className="natural-language-form">
      <h2>Create Event with Natural Language</h2>

      <div className="calendar-selection">
        <h3>Select Calendars to Monitor:</h3>
        {calendars.length > 0 ? (
          calendars.map((cal) => (
            <label key={cal.id} style={{ display: 'block', margin: '5px 0' }}>
              <input
                type="checkbox"
                checked={selectedCalendars.some((selected) => selected.id === cal.id)}
                onChange={() => handleCalendarSelect(cal)}
                disabled={loading}
              />
              {cal.summary} {cal.primary ? '(Primary)' : ''}
            </label>
          ))
        ) : (
          <p>Loading calendars...</p>
        )}
      </div>

      {error && <div className="error-message">{error}</div>}
      {message && <div className="success-message">{message}</div>}

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
            <div className="legend-item">
              <span className="legend-color existing-event-color"></span>
              <span>Existing Events</span>
            </div>
            <div className="legend-item">
              <span className="legend-color suggested-event-color"></span>
              <span>Suggested Work Slots</span>
            </div>
            <div className="legend-item">
              <span className="legend-color selected-event-color"></span>
              <span>Selected Work Slots</span>
            </div>
          </div>
          <div className="calendar-container">
            <FullCalendar
              plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
              initialView="timeGridWeek"
              headerToolbar={{
                left: 'prev,next today',
                center: 'title',
                right: 'dayGridMonth,timeGridWeek,timeGridDay'
              }}
              events={getAllEvents()}
              eventClick={handleEventClick}
              eventContent={renderEventContent}
              height="800px"
              nowIndicator={true}
              datesSet={handleDatesSet}
              slotMinTime="00:00:00"
              slotMaxTime="24:00:00"
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
            />
          </div>
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

function renderEventContent(eventInfo) {
  const isSuggested = eventInfo.event.extendedProps.suggestedSlot;
  // eslint-disable-next-line no-unused-vars
  const isExisting = eventInfo.event.extendedProps.existingEvent;
  
  // Format the time more cleanly
  let timeText = eventInfo.timeText;
  if (timeText.includes('-')) {
    // Simplify time range display
    const times = timeText.split('-');
    timeText = times[0].trim() + ' - ' + times[1].trim();
  }
  
  return (
    <div className={`event-content ${isSuggested ? 'suggested-event' : 'existing-event'}`}>
      <b>{timeText}</b>
      <i>{eventInfo.event.title}</i>
    </div>
  );
}

function App() {
  return (
    <div className="App">
      <NaturalLanguageForm />
      <hr />
    </div>
  );
}

export default App;