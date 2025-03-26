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

console.log("Calendar functions loaded from external file"); 