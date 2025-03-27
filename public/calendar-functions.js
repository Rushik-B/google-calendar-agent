// Define global calendar functions
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

window.scheduleBreak = function(startTime, endTime) {
  console.log("Global scheduleBreak called with:", startTime, endTime);
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
  console.log("Global scheduleTask called with:", startTime, endTime);
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

// Function to handle event selection for modification
window.selectEventToModify = function(eventId, calendarId, modificationType, queryParams) {
  console.log("Selecting event for modification:", eventId, calendarId, modificationType);
  
  // Send the request to modify the selected event
  fetch('/api/modify-selected-event', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      eventId: eventId,
      calendarId: calendarId,
      modificationType: modificationType,
      queryParams: queryParams
    })
  })
  .then(response => response.json())
  .then(data => {
    console.log("Modification response:", data);
    
    if (data.success) {
      // Dispatch an event to notify the React app about the successful modification
      window.dispatchEvent(
        new CustomEvent('eventModified', {
          detail: {
            success: true,
            eventId: eventId,
            calendarId: calendarId,
            modificationType: modificationType,
            message: data.message,
            humanizedResponse: data.humanizedResponse
          }
        })
      );
      
      // Refresh the calendar to show the updated event
      window.dispatchEvent(new Event('refreshCalendar'));
    } else {
      // Handle error
      console.error("Error modifying event:", data.message);
      
      // Dispatch event for error handling
      window.dispatchEvent(
        new CustomEvent('eventModified', {
          detail: {
            success: false,
            message: data.message,
            humanizedResponse: data.humanizedResponse
          }
        })
      );
    }
  })
  .catch(error => {
    console.error("Error calling modify-selected-event API:", error);
    
    // Dispatch event for error handling
    window.dispatchEvent(
      new CustomEvent('eventModified', {
        detail: {
          success: false,
          message: "Failed to communicate with the server",
          humanizedResponse: "I encountered an error while trying to modify the event. Please try again."
        }
      })
    );
  });
};

// Function to reschedule event (used in conflict resolution)
window.rescheduleEvent = function(eventId, newStart, newEnd, calendarId) {
  console.log("Rescheduling event:", eventId, "to", newStart, newEnd);
  
  // Convert ISO string to date objects for easier formatting
  const startDate = new Date(newStart);
  const endDate = new Date(newEnd);
  
  // Format the time for display
  const formatTime = (date) => {
    return date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
  };
  
  // Create query params with new time and date information
  const queryParams = {
    modification_type: "reschedule",
    new_time: startDate.getHours().toString().padStart(2, '0') + ":" + startDate.getMinutes().toString().padStart(2, '0'),
    new_date: startDate.toISOString().split('T')[0]  // YYYY-MM-DD format
  };
  
  // Call the API to reschedule the event
  fetch('/api/modify-selected-event', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      eventId: eventId,
      calendarId: calendarId || "primary",
      modificationType: "reschedule",
      queryParams: queryParams
    })
  })
  .then(response => response.json())
  .then(data => {
    console.log("Reschedule response:", data);
    
    if (data.success) {
      // Notify about successful rescheduling
      window.dispatchEvent(
        new CustomEvent('eventModified', {
          detail: {
            success: true,
            eventId: eventId,
            calendarId: calendarId,
            modificationType: "reschedule",
            message: data.message,
            humanizedResponse: data.humanizedResponse
          }
        })
      );
      
      // Refresh the calendar
      window.dispatchEvent(new Event('refreshCalendar'));
    } else {
      // Handle error
      console.error("Error rescheduling event:", data.message);
      
      window.dispatchEvent(
        new CustomEvent('eventModified', {
          detail: {
            success: false,
            message: data.message,
            humanizedResponse: data.humanizedResponse
          }
        })
      );
    }
  })
  .catch(error => {
    console.error("Error calling reschedule API:", error);
    
    window.dispatchEvent(
      new CustomEvent('eventModified', {
        detail: {
          success: false,
          message: "Failed to communicate with the server",
          humanizedResponse: "I encountered an error while trying to reschedule the event. Please try again."
        }
      })
    );
  });
};

console.log("Calendar functions loaded from external file"); 