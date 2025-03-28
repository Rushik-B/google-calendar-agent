import React, { useState, useEffect, useCallback, memo, useMemo, Suspense, lazy, useRef } from 'react';
import axios from 'axios';
import './App.css';

// Import our Chat UI components instead of the old NewUI
import { ChatHeader, ChatContainer, ChatMessages, ChatMessage, ChatInput, SettingsButton, CalendarSettings, WelcomeMessage, CalendarSelectionComponent, RecommendationBar } from './ChatUI';

import FullCalendar from '@fullcalendar/react';
import dayGridPlugin from '@fullcalendar/daygrid';
import timeGridPlugin from '@fullcalendar/timegrid';
import interactionPlugin from '@fullcalendar/interaction';

// SVG Path Icons for recommendation buttons
const ICONS = {
  SCHEDULE: "M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z",
  FREE_TIME: "M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z",
  MEETINGS: "M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10",
  BREAK: "M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
  ASSIGNMENT: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z",
  REMINDER: "M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
};

// Colors for suggestion pills
const COLORS = {
  BLUE: 'rgba(99, 179, 237, 0.25)',    // Vibrant blue with higher opacity
  GREEN: 'rgba(72, 187, 120, 0.25)',   // Fresh green with higher opacity
  ORANGE: 'rgba(246, 173, 85, 0.25)',  // Warm orange with higher opacity
  PURPLE: 'rgba(159, 122, 234, 0.25)', // Rich purple with higher opacity
  RED: 'rgba(245, 101, 101, 0.25)'     // Bright red with higher opacity
};

// Popular command suggestions with truncated text
const DEFAULT_SUGGESTIONS = [
  { text: "Schedule a meeting tomorrow at 2pm", color: COLORS.BLUE, icon: ICONS.SCHEDULE },
  { text: "Find me free time this week", color: COLORS.GREEN, icon: ICONS.FREE_TIME },
  { text: "What meetings do I have today?", color: COLORS.PURPLE, icon: ICONS.MEETINGS },
  { text: "Schedule a 30-minute break", color: COLORS.ORANGE, icon: ICONS.BREAK },
  { text: "Find time to work on my assignment", color: COLORS.RED, icon: ICONS.ASSIGNMENT }
];

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

// Note: We're using CalendarSelectionComponent from ChatUI.jsx

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
  
  // Chat-specific state
  const [chatMessages, setChatMessages] = useState([]);
  const [showSettings, setShowSettings] = useState(false);
  
  // Recommendation system state
  const [suggestions, setSuggestions] = useState([]);
  const [showRecommendations, setShowRecommendations] = useState(false);
  
  // Call the setup function on load
  useEffect(() => {
    setupGlobalFunctions();
    // Add welcome message
    setChatMessages([{ sender: 'bot', type: 'welcome' }]);
    
    // Load saved popular commands from localStorage
    loadPopularCommands();
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

  // Recommendation system functions
  const loadPopularCommands = () => {
    try {
      const savedCommands = localStorage.getItem('popularCommands');
      if (savedCommands) {
        const commands = JSON.parse(savedCommands);
        // Get top 5 most used commands
        const topCommands = commands
          .sort((a, b) => b.count - a.count)
          .slice(0, 5);
          
        if (topCommands.length > 0) {
          // Format commands with icons and colors
          const formattedCommands = topCommands.map((cmd, index) => {
            // Detect command type to assign appropriate icon and color
            let icon = ICONS.SCHEDULE;
            let color = COLORS.BLUE;
            
            const lowerText = cmd.text.toLowerCase();
            
            if (lowerText.includes('free time') || lowerText.includes('availability')) {
              icon = ICONS.FREE_TIME;
              color = COLORS.GREEN;
            } else if (lowerText.includes('meeting') || lowerText.includes('have') || lowerText.includes('scheduled')) {
              icon = ICONS.MEETINGS;
              color = COLORS.PURPLE;
            } else if (lowerText.includes('break') || lowerText.includes('rest')) {
              icon = ICONS.BREAK;
              color = COLORS.ORANGE;
            } else if (lowerText.includes('assignment') || lowerText.includes('work on')) {
              icon = ICONS.ASSIGNMENT;
              color = COLORS.RED;
            } else if (lowerText.includes('remind') || lowerText.includes('notification')) {
              icon = ICONS.REMINDER;
              color = COLORS.ORANGE;
            }
            
            return {
              text: cmd.text,
              count: cmd.count,
              icon,
              color
            };
          });
          
          setSuggestions(formattedCommands);
          setShowRecommendations(true);
        } else {
          setSuggestions(DEFAULT_SUGGESTIONS);
          setShowRecommendations(true);
        }
      } else {
        // No saved commands, use defaults
        setSuggestions(DEFAULT_SUGGESTIONS);
        setShowRecommendations(true);
      }
    } catch (error) {
      console.error('Error loading popular commands:', error);
      setSuggestions(DEFAULT_SUGGESTIONS);
      setShowRecommendations(true);
    }
  };
  
  const trackCommand = (commandText) => {
    try {
      // Skip tracking empty commands
      if (!commandText.trim()) return;
      
      // Get existing commands or initialize empty array
      const existingCommands = JSON.parse(localStorage.getItem('popularCommands') || '[]');
      
      // Check if this command already exists
      const existingIndex = existingCommands.findIndex(
        cmd => cmd.text.toLowerCase() === commandText.toLowerCase()
      );
      
      if (existingIndex >= 0) {
        // Increment count for existing command
        existingCommands[existingIndex].count += 1;
        existingCommands[existingIndex].lastUsed = new Date().toISOString();
      } else {
        // Add new command
        existingCommands.push({
          text: commandText,
          count: 1,
          lastUsed: new Date().toISOString()
        });
      }
      
      // Save back to localStorage
      localStorage.setItem('popularCommands', JSON.stringify(existingCommands));
      
      // Update suggestions
      loadPopularCommands();
    } catch (error) {
      console.error('Error tracking command:', error);
    }
  };
  
  const handleSelectSuggestion = (suggestion) => {
    setText(suggestion);
    // Focus the input field
    document.querySelector('.chat-input textarea').focus();
  };

  const handleSubmit = useCallback(async (e) => {
    e.preventDefault();
    console.log("handleSubmit called with text:", text);
    if (!text.trim()) return;

    // Track the command for the recommendation system
    trackCommand(text);

    // Add user message to chat
    setChatMessages(prev => [...prev, { sender: 'user', content: text }]);
    
    setLoading(true);
    setError("");
    setMessage("");
    setAvailableSlots([]);
    setCalendarEvents([]);
    setSelectedSlots([]);

    try {
      console.log("Making API call with text:", text);
      const response = await axios.post('http://127.0.0.1:5000/api/natural-language-event', {
        text
      });
      console.log("API response:", response.data);

      if (response.data.success) {
        // Handle the response in chat format
        if (response.data.humanizedResponse) {
          if (response.data.intent === "check_free_time") {
            // For check_free_time intent with HTML
            setChatMessages(prev => [...prev, { 
              sender: 'bot', 
              content: response.data.humanizedResponse 
            }]);
            setText("");
          } else {
            // For other intents with text response
            setChatMessages(prev => [...prev, { 
              sender: 'bot', 
              content: response.data.humanizedResponse 
            }]);
          }
        }
        
        if (response.data.intent === "find_time") {
          setAvailableSlots(response.data.availableSlots);
          setCalendarEvents(response.data.events || []);
          setShowCalendar(true);
          
          // Check if we have the insufficientTime flag
          if (response.data.insufficientTime) {
            // Add error message to chat
            setChatMessages(prev => [...prev, { 
              sender: 'bot', 
              type: 'error',
              content: `INSUFFICIENT TIME: ${response.data.humanizedResponse || response.data.message} Select these slots or try a different timeframe.` 
            }]);
          } else if (!response.data.humanizedResponse) {
            // Only set this default message if humanizedResponse wasn't already set
            setChatMessages(prev => [...prev, { 
              sender: 'bot', 
              content: "Here are suggested time slots on your calendar. Click on slots to select/deselect them for scheduling." 
            }]);
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
          setChatMessages(prev => [...prev, { 
            sender: 'bot', 
            type: 'success',
            content: `Event created! ${response.data.eventLink ? `View it here: ${response.data.eventLink}` : ''}` 
          }]);
          setText("");
        } else {
          // For other intents or if we already set humanizedResponse
          setText("");
        }
      } else {
        // Add error message to chat
        setChatMessages(prev => [...prev, { 
          sender: 'bot', 
          type: 'error',
          content: `Error: ${response.data.humanizedResponse || response.data.message}` 
        }]);
      }
    } catch (error) {
      // Add error message to chat
      setChatMessages(prev => [...prev, { 
        sender: 'bot', 
        type: 'error',
        content: `Error: ${error.response?.data?.message || error.message}` 
      }]);
    } finally {
      setLoading(false);
    }
  }, [text, setLoading, setText, setChatMessages, setAvailableSlots, setCalendarEvents, setSelectedSlots, setShowCalendar, setEventDetails]);

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
        // Add success message to chat
        setChatMessages(prev => [...prev, { 
          sender: 'bot', 
          type: 'success',
          content: `All ${selectedSlots.length} events scheduled successfully!` 
        }]);
        
        setText("");
        setShowCalendar(false);
        setAvailableSlots([]);
        setCalendarEvents([]);
        setSelectedSlots([]);
      } else {
        // Add error message to chat
        setChatMessages(prev => [...prev, { 
          sender: 'bot', 
          type: 'error',
          content: `Error: Some events could not be scheduled.` 
        }]);
      }
    } catch (error) {
      // Add error message to chat
      setChatMessages(prev => [...prev, { 
        sender: 'bot', 
        type: 'error',
        content: `Error: ${error.response?.data?.message || error.message}` 
      }]);
    } finally {
      setLoading(false);
    }
  };

  const handleFindDifferentTimes = () => {
    // Add message to chat
    setChatMessages(prev => [...prev, { 
      sender: 'bot', 
      content: "Let's find another time. Please provide more details:"
    }]);
    
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

  // Render calendar in a chat message
  const renderCalendarMessage = () => {
    if (!showCalendar) return null;
    
    const currentEvents = getAllEvents();
    
    return (
      <ChatMessage sender="bot" isCalendarView={true} className="calendar-message">
        <div className="calendar-view w-full">
          {selectedSlots.length > 0 && (
            <div className="bg-blue-50 border border-blue-100 rounded-lg p-4 mb-4 text-blue-800 font-medium">
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
          
          <div className="flex mt-6 space-x-4">
            <button
              onClick={handleScheduleSelected}
              disabled={selectedSlots.length === 0 || loading}
              className={`
                px-6 py-3 rounded-lg font-medium flex items-center justify-center
                ${selectedSlots.length === 0 || loading 
                  ? 'bg-gray-300 cursor-not-allowed text-gray-500' 
                  : 'bg-green-600 hover:bg-green-700 text-white shadow-md hover:shadow-lg transition-all duration-200'}
              `}
            >
              {loading ? (
                <div className="flex items-center">
                  <svg className="animate-spin -ml-1 mr-2 h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Scheduling...
                </div>
              ) : `Schedule ${selectedSlots.length} Selected Time${selectedSlots.length === 1 ? '' : 's'}`}
            </button>
            <button
              onClick={handleFindDifferentTimes}
              disabled={loading}
              className="px-6 py-3 bg-red-500 hover:bg-red-600 text-white rounded-lg font-medium shadow-md hover:shadow-lg transition-all duration-200"
            >
              Find Different Times
            </button>
          </div>
        </div>
      </ChatMessage>
    );
  };

  // Format events in a user-friendly way
  const formatStyledEventList = (responseText) => {
    console.log("Formatting response:", responseText); // Debug to see what's being processed
    
    // First, check for specific format with Cmpt 310 or other course names
    if (responseText.includes("Cmpt 310") || responseText.includes("CMPT 310")) {
      try {
        // Extract date more flexibly
        let dateMatch = responseText.match(/for\s+([A-Za-z]+\s+\d+(?:st|nd|rd|th)?,\s+\d{4})/i);
        const dateStr = dateMatch ? dateMatch[1] : "Today";
        
        // Simpler regex to match formatted times and course info
        const eventPattern = /\*\*([^*]+)\*\*:\s*([^*\n]+?)(?:\sin\s+([^*\n]*))?(?=\s*\*\*|\s*$)/g;
        let match;
        const events = [];
        
        while ((match = eventPattern.exec(responseText)) !== null) {
          console.log("Matched event:", match); // Debug
          const timeRange = match[1].trim();
          const title = match[2].trim();
          const location = match[3] ? match[3].trim() : '';
          
          events.push({
            timeRange,
            title,
            location,
            duration: calculateDuration(timeRange)
          });
        }
        
        // If we couldn't extract events with the regex, try a direct approach for the specific format
        if (events.length === 0 && responseText.includes("AM") && responseText.includes("PM")) {
          // Direct parsing for the specific format in the image
          const timeMatch = responseText.match(/(\d+:\d+\s*(?:AM|PM)\s*-\s*\d+:\d+\s*(?:AM|PM))/i);
          const courseMatch = responseText.match(/Cmpt\s+\d+|CMPT\s+\d+/i);
          const locationMatch = responseText.match(/at\s+([A-Z]+\s+\d+)/i);
          
          if (timeMatch && courseMatch) {
            events.push({
              timeRange: timeMatch[1].trim(),
              title: courseMatch[0].trim() + (responseText.includes("OH") ? " Office Hours" : ""),
              location: locationMatch ? locationMatch[1].trim() : "",
              duration: calculateDuration(timeMatch[1].trim())
            });
            console.log("Direct parse event:", events[0]); // Debug
          }
        }
        
        // If we extracted events, format them nicely
        if (events.length > 0) {
          // Generate intro text
          const introMatch = responseText.match(/^([^*]+)/);
          const introText = introMatch ? introMatch[0].trim() : `Here's your schedule for ${dateStr}:`;
          
          return generateEventHTML(introText, dateStr, events);
        }
      } catch (error) {
        console.error("Error formatting events:", error);
      }
    }
    
    // Check if this is a schedule/calendar response with events
    if ((responseText.includes("schedule") || responseText.includes("calendar") || 
         responseText.includes("looks like for") || responseText.includes("have") || 
         responseText.includes("Monday") || responseText.includes("monday")) && 
        (responseText.includes("**") || responseText.includes("AM") || responseText.includes("PM"))) {
      try {
        // Extract date
        let dateMatch = responseText.match(/(?:for|on)\s+([A-Za-z]+\s+\d+(?:st|nd|rd|th)?,\s+\d{4})/i);
        const dateStr = dateMatch ? dateMatch[1] : 
                       (responseText.toLowerCase().includes("monday") ? "Monday" : "Today");
        
        // Parse events from the text - improved regex pattern to better capture events
        const eventPattern = /\*\*([0-9:.APM\s-]+)\*\*:\s*([^*\n]+?)(?:\sin\s+([^*\n]*))?(?=\s*\*\*|\s*$)/g;
        let match;
        const events = [];
        
        while ((match = eventPattern.exec(responseText)) !== null) {
          const timeRange = match[1].trim();
          const title = match[2].trim();
          const location = match[3] ? match[3].trim() : '';
          
          events.push({
            timeRange,
            title,
            location,
            duration: calculateDuration(timeRange)
          });
        }
        
        // Try alternative pattern if no events found
        if (events.length === 0) {
          const altPattern = /(\d+(?::\d+)?\s*(?:AM|PM)\s*-\s*\d+(?::\d+)?\s*(?:AM|PM))[\s:]*([^()\n,]+)(?:\s+in\s+([^()\n,]+))?/gi;
          while ((match = altPattern.exec(responseText)) !== null) {
            events.push({
              timeRange: match[1].trim(),
              title: match[2].trim(),
              location: match[3] ? match[3].trim() : '',
              duration: calculateDuration(match[1].trim())
            });
          }
        }
        
        // If we extracted events, format them nicely
        if (events.length > 0) {
          // Generate intro text
          const introMatch = responseText.match(/^([^*]+)/);
          const introText = introMatch ? introMatch[0].trim() : `Here's your schedule for ${dateStr}:`;
          
          return generateEventHTML(introText, dateStr, events);
        } else {
          // If we still couldn't find events, fall back to default formatting
          return defaultStyledFormat(responseText);
        }
      } catch (error) {
        console.error("Error formatting events:", error);
        return defaultStyledFormat(responseText);
      }
    }
    
    // For regular text responses, make them more visually interesting
    if (!responseText.includes("<div") && !responseText.includes("<p") && !responseText.includes("<ul")) {
      // If it mentions free time, use a special format
      if (responseText.toLowerCase().includes("free time") || 
          responseText.toLowerCase().includes("available") || 
          responseText.toLowerCase().includes("time slot")) {
        return generateFreeTimeHTML(responseText);
      }
      
      // If it's a confirmation or completion message
      if (responseText.toLowerCase().includes("scheduled") || 
          responseText.toLowerCase().includes("created") || 
          responseText.toLowerCase().includes("added")) {
        return generateConfirmationHTML(responseText);
      }
      
      // Default enhanced format for other responses
      return defaultStyledFormat(responseText);
    }
    
    // Return original if no formatting applied
    return responseText;
  };
  
  // Helper function to calculate duration from a time range
  const calculateDuration = (timeRange) => {
    if (!timeRange || !timeRange.includes("-")) return "";
    
    try {
      const [startTime, endTime] = timeRange.split("-").map(t => t.trim());
      
      const parseTime = (timeStr) => {
        const [time, modifier] = timeStr.split(/\s+/);
        let [hours, minutes] = (time || "").split(':').map(Number);
        minutes = minutes || 0;
        if (modifier && modifier.toUpperCase() === 'PM' && hours < 12) hours += 12;
        if (modifier && modifier.toUpperCase() === 'AM' && hours === 12) hours = 0;
        return hours * 60 + minutes;
      };
      
      const startMinutes = parseTime(startTime);
      const endMinutes = parseTime(endTime);
      const durationMinutes = endMinutes - startMinutes;
      
      if (durationMinutes > 0) {
        const hours = Math.floor(durationMinutes / 60);
        const mins = durationMinutes % 60;
        return hours > 0 
          ? `${hours} hour${hours > 1 ? 's' : ''}${mins > 0 ? ` ${mins} min` : ''}` 
          : `${mins} min`;
      }
      return "";
    } catch (e) {
      console.error("Error calculating duration:", e);
      return "";
    }
  };
  
  // Helper function to generate HTML for events
  const generateEventHTML = (introText, dateStr, events) => {
    return `
      <div>
        <p>${introText}</p>
        <div class="styled-event-list">
          <div class="event-date">${dateStr}</div>
          ${events.map(event => {
            // Determine background color based on event title (for courses)
            let bgColor = '#e5edff'; // default blue background
            let iconColor = '#3b82f6'; // default blue icon
            
            if (event.title.includes('CMPT 310') || event.title.includes('Cmpt 310')) {
              bgColor = '#f3e8ff'; // purple for CMPT 310
              iconColor = '#8b5cf6';
            } else if (event.title.includes('CMPT 213') || event.title.includes('Cmpt 213')) {
              bgColor = '#e0f2fe'; // light blue for CMPT 213
              iconColor = '#0ea5e9';
            } else if (event.title.includes('CMPT 276') || event.title.includes('Cmpt 276')) {
              bgColor = '#dcfce7'; // green for CMPT 276
              iconColor = '#22c55e';
            } else if (event.title.includes('CMPT 105W') || event.title.includes('Cmpt 105W')) {
              bgColor = '#ffedd5'; // orange for CMPT 105W
              iconColor = '#f97316';
            } else if (event.title.includes('OH') || event.title.includes('Office Hours')) {
              bgColor = '#ffe4e6'; // pink for Office Hours
              iconColor = '#e11d48';
            }
            
            return `
            <div class="event-item">
              <div class="event-item-icon" style="background-color: ${bgColor}; color: ${iconColor};">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                  <line x1="16" y1="2" x2="16" y2="6"></line>
                  <line x1="8" y1="2" x2="8" y2="6"></line>
                  <line x1="3" y1="10" x2="21" y2="10"></line>
                </svg>
              </div>
              <div>
                <div class="event-time">${event.timeRange}</div>
                <div class="event-content">
                  <div class="event-title">${event.title}</div>
                  ${event.location ? `
                    <div class="event-location">
                      <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                        <circle cx="12" cy="10" r="3"></circle>
                      </svg>
                      ${event.location}
                    </div>
                  ` : ''}
                  ${event.duration ? `<div class="event-duration">${event.duration}</div>` : ''}
                </div>
              </div>
            </div>
            `;
          }).join('')}
        </div>
      </div>
    `;
  };
  
  // Helper function for free time format
  const generateFreeTimeHTML = (responseText) => {
    return `
      <div class="styled-event-list">
        <div class="event-item">
          <div class="event-item-icon" style="background-color: #ebf7ee; color: #34d399;">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
              <polyline points="22 4 12 14.01 9 11.01"></polyline>
            </svg>
          </div>
          <div class="event-content">
            <p>${responseText}</p>
          </div>
        </div>
      </div>
    `;
  };
  
  // Helper function for confirmation format
  const generateConfirmationHTML = (responseText) => {
    return `
      <div class="styled-event-list">
        <div class="event-item">
          <div class="event-item-icon" style="background-color: #e5edff; color: #3b82f6;">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
          </div>
          <div class="event-content">
            <p>${responseText}</p>
          </div>
        </div>
      </div>
    `;
  };
  
  // Helper function for default format
  const defaultStyledFormat = (responseText) => {
    return `
      <div class="styled-event-list">
        <div class="event-item">
          <div class="event-item-icon" style="background-color: #f5f3ff; color: #8b5cf6;">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="16" x2="12" y2="12"></line>
              <line x1="12" y1="8" x2="12.01" y2="8"></line>
            </svg>
          </div>
          <div class="event-content">
            <p>${responseText}</p>
          </div>
        </div>
      </div>
    `;
  };

  // Render message content based on type
  const renderMessage = (message, index) => {
    if (message.type === 'welcome') {
      return <WelcomeMessage key={index} />;
    }
    
    if (message.type === 'error') {
      return (
        <ChatMessage 
          key={index} 
          sender={message.sender} 
          content={`<div class="error-content">${message.content}</div>`} 
        />
      );
    }
    
    if (message.type === 'success') {
      return (
        <ChatMessage 
          key={index} 
          sender={message.sender} 
          content={`<div class="success-content">${message.content}</div>`} 
        />
      );
    }
    
    // Format event lists in responses
    const formattedContent = message.sender === 'bot' 
      ? formatStyledEventList(message.content) 
      : message.content;
    
    return (
      <ChatMessage 
        key={index} 
        sender={message.sender} 
        content={formattedContent} 
      />
    );
  };

  return (
    <div className="w-full h-full">
      <ChatContainer>
        <div className="relative">
          <ChatHeader />
          <SettingsButton 
            onClick={() => setShowSettings(!showSettings)} 
            isOpen={showSettings} 
          />
        </div>
        
        <div className={`settings-transition ${showSettings ? 'settings-open' : 'settings-closed'}`}>
          {showSettings && (
            <CalendarSettings 
              calendars={calendars}
              selected={selectedCalendars}
              onSelect={handleCalendarSelect}
              disabled={loading}
            />
          )}
        </div>
        
        <ChatMessages>
          {chatMessages.map((msg, idx) => renderMessage(msg, idx))}
          {showCalendar && renderCalendarMessage()}
        </ChatMessages>
        
        {showRecommendations && suggestions.length > 0 && (
          <RecommendationBar 
            suggestions={suggestions} 
            onSelectSuggestion={handleSelectSuggestion} 
          />
        )}
        
        <ChatInput
          value={text}
          onChange={(e) => setText(e.target.value)}
          onSubmit={handleSubmit}
          loading={loading}
        />
      </ChatContainer>
    </div>
  );
}

function App() {
  return (
    <div className="App w-full">
      <h1 className="app-title">Calendar Companion</h1>
      <div className="app-container">
        <Suspense fallback={<div className="text-center p-10 text-white">Loading application...</div>}>
          <NaturalLanguageForm />
        </Suspense>
      </div>
      
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
    </div>
  );
}

export default App;