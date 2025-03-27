# Calendar Assistant App

A smart calendar management application that combines Google Calendar integration with natural language processing to help you manage your schedule more efficiently.

## Features

- **Natural Language Processing**: Interact with your calendar using everyday language
  - "What do I have next weekend?"
  - "Schedule a meeting with the team on Friday at 2pm"
  - "Reschedule my dentist appointment to next Tuesday"
  
- **Calendar Integration**: Connect with Google Calendar
  - View and manage multiple calendars
  - Set preferred calendars for different types of events
  
- **Smart Event Management**:
  - Find free time slots in your schedule
  - Create, modify, and delete events
  - View upcoming events filtered by date, calendar, or event type

## Technology Stack

- **Frontend**: React.js
- **Backend**: Flask (Python)
- **APIs**: Google Calendar API
- **NLP**: Custom intent recognition and parameter extraction

## Setup Instructions

### Prerequisites

- Node.js and npm
- Python 3.7+
- Google API credentials

### Installation

1. Clone the repository

2. Install frontend dependencies:
   ```
   npm install
   ```

3. Install backend dependencies:
   ```
   pip install flask google-auth-oauthlib google-auth-httplib2 google-api-python-client
   ```

4. Set up Google Calendar API:
   - Create a project in Google Developer Console
   - Enable the Google Calendar API
   - Create OAuth credentials
   - Download the credentials as `credentials.json` and place in the project root

### Running the Application

1. Start the Flask backend:
   ```
   python app.py
   ```

2. In a separate terminal, start the React frontend:
   ```
   npm start
   ```

3. Open your browser and navigate to `http://localhost:3000`

4. On first run, you'll be prompted to authorize access to your Google Calendar

## Usage Examples

### View Events
- "What's on my calendar tomorrow?"
- "Show me my meetings for next week"
- "What do I have scheduled in my Work calendar?"

### Create Events
- "Schedule lunch with Alex on Friday at noon"
- "Add CMPT 310 lecture every Tuesday and Thursday from 2:30pm to 4:20pm"

### Modify Events
- "Reschedule my dentist appointment to next Monday at 9am"
- "Move my team meeting to the afternoon"

## License

This project is licensed under the MIT License - see the LICENSE file for details.
