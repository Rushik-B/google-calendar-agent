import React, { useState, useRef, useEffect } from 'react';
import PropTypes from 'prop-types';

// ChatHeader component with bot info
export const ChatHeader = () => {
  return (
    <div className="chat-header bg-white border-b border-gray-200 p-4 flex items-center" style={{
      backgroundColor: 'var(--ghibli-cream)',
      borderColor: 'rgba(156, 123, 101, 0.2)',
      borderBottomWidth: '2px',
      borderRadius: '12px 12px 0 0'
    }}>
      <div className="w-10 h-10 rounded-full flex items-center justify-center mr-3" style={{
        background: 'var(--ghibli-blue)',
        boxShadow: '0 3px 6px var(--ghibli-shadow)'
      }}>
        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="white">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
      </div>
      <div>
        <h3 className="font-medium text-gray-800" style={{
          fontFamily: 'var(--heading-font)',
          color: 'var(--ghibli-brown)',
          fontSize: '1.1rem'
        }}>Calendar Assistant</h3>
        <p className="text-xs text-gray-500" style={{ color: '#8a7865' }}>Always available to help manage your schedule</p>
      </div>
    </div>
  );
};

// ChatMessage component for individual messages
export const ChatMessage = ({ sender, content, isCalendarView = false, children, className = '' }) => {
  const isBot = sender === 'bot';
  
  // Determine if this is likely a rich formatted message based on content (if string)
  const isRichContent = typeof content === 'string' && (
    content.includes('styled-event-list') || 
    content.includes('<div class="event-item">')
  );
  
  return (
    <div className={`chat-message flex mb-4 ${isBot ? '' : 'justify-end'} ${className}`}>
      {isBot && (
        <div className="w-8 h-8 rounded-full flex items-center justify-center mr-2 flex-shrink-0" style={{
          background: 'var(--ghibli-blue)',
          boxShadow: '0 2px 4px var(--ghibli-shadow)'
        }}>
          <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="white">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        </div>
      )}
      
      <div className={`
        message-content 
        ${isRichContent || isCalendarView ? 'max-w-3xl w-full md:w-[90%]' : 'max-w-xl'}
        ${isBot 
          ? 'text-gray-800 rounded-tr-xl rounded-br-xl rounded-bl-xl' 
          : 'text-white rounded-tl-xl rounded-bl-xl rounded-br-xl ml-2'}
        ${isCalendarView ? 'p-0 overflow-hidden' : (isRichContent ? 'p-3 pb-1' : 'p-3')}
      `}
      style={{
        backgroundColor: isBot ? 'var(--ghibli-cream)' : 'var(--ghibli-blue)',
        boxShadow: '0 3px 10px var(--ghibli-shadow)',
        border: isBot ? '1px solid rgba(156, 123, 101, 0.2)' : 'none',
        fontFamily: 'var(--body-font)'
      }}>
        {isCalendarView ? children : <div dangerouslySetInnerHTML={{ __html: content }} />}
      </div>
      
      {!isBot && (
        <div className="w-8 h-8 rounded-full flex items-center justify-center ml-2 flex-shrink-0" style={{
          background: 'var(--ghibli-blue)',
          boxShadow: '0 2px 4px var(--ghibli-shadow)'
        }}>
          <span className="text-sm font-bold text-white">You</span>
        </div>
      )}
    </div>
  );
};

ChatMessage.propTypes = {
  sender: PropTypes.oneOf(['user', 'bot']).isRequired,
  content: PropTypes.string,
  isCalendarView: PropTypes.bool,
  children: PropTypes.node,
  className: PropTypes.string
};

// ChatInput component
export const ChatInput = ({ value, onChange, onSubmit, loading, placeholder }) => {
  const inputRef = useRef(null);
  
  // Focus the input when component mounts
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.focus();
    }
  }, []);
  
  // Handle Enter key press
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSubmit(e);
    }
  };
  
  return (
    <div className="chat-input border-t p-3" style={{
      backgroundColor: 'var(--ghibli-cream)',
      borderTopColor: 'rgba(156, 123, 101, 0.2)',
      borderTopWidth: '1px',
      borderRadius: '0 0 12px 12px'
    }}>
      <form onSubmit={onSubmit} className="flex items-end">
        <div className="relative flex-grow">
          <textarea
            ref={inputRef}
            className="w-full px-4 py-3 text-gray-700 rounded-lg focus:outline-none border"
            style={{
              backgroundColor: 'rgba(255, 255, 255, 0.7)',
              borderColor: 'rgba(156, 123, 101, 0.2)',
              borderWidth: '2px',
              boxShadow: 'inset 0 2px 4px rgba(0, 0, 0, 0.05)',
              borderRadius: '15px',
              fontFamily: 'var(--body-font)',
              transition: 'all 0.3s ease',
              resize: 'none'
            }}
            rows="1"
            value={value}
            onChange={onChange}
            onKeyDown={handleKeyDown}
            disabled={loading}
            placeholder={placeholder || "Ask your calendar assistant something..."}
            required
          />
        </div>
        <button
          type="submit"
          disabled={loading || !value.trim()}
          className="ml-3 p-3 rounded-full flex items-center justify-center"
          style={{
            backgroundColor: (!value.trim() || loading) 
              ? '#d1d5db' 
              : 'var(--ghibli-blue)',
            color: 'white',
            boxShadow: (!value.trim() || loading) 
              ? 'none' 
              : '0 3px 6px rgba(0, 0, 0, 0.15)',
            transition: 'all 0.3s ease',
            cursor: (!value.trim() || loading) ? 'not-allowed' : 'pointer'
          }}
        >
          {loading ? (
            <svg className="animate-spin h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
          ) : (
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-8.707l-3-3a1 1 0 00-1.414 0l-3 3a1 1 0 001.414 1.414L9 9.414V13a1 1 0 102 0V9.414l1.293 1.293a1 1 0 001.414-1.414z" clipRule="evenodd" />
            </svg>
          )}
        </button>
      </form>
    </div>
  );
};

ChatInput.propTypes = {
  value: PropTypes.string.isRequired,
  onChange: PropTypes.func.isRequired,
  onSubmit: PropTypes.func.isRequired,
  loading: PropTypes.bool,
  placeholder: PropTypes.string
};

// ChatContainer component
export const ChatContainer = ({ children }) => {
  return (
    <div className="chat-container flex flex-col h-full overflow-hidden" style={{
      background: 'rgba(248, 243, 231, 0.8)',
      backdropFilter: 'blur(8px)',
      WebkitBackdropFilter: 'blur(8px)', 
      borderRadius: '15px',
      boxShadow: '0 10px 30px var(--ghibli-shadow), 0 0 15px rgba(255, 255, 255, 0.3) inset',
      border: '1px solid rgba(255, 255, 255, 0.5)'
    }}>
      {children}
    </div>
  );
};

ChatContainer.propTypes = {
  children: PropTypes.node.isRequired
};

// ChatMessages container with auto-scroll
export const ChatMessages = ({ children }) => {
  const messagesEndRef = useRef(null);
  
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };
  
  useEffect(() => {
    scrollToBottom();
  }, [children]);
  
  return (
    <div className="chat-messages flex-grow p-4 overflow-y-auto">
      {children}
      <div ref={messagesEndRef} />
    </div>
  );
};

ChatMessages.propTypes = {
  children: PropTypes.node
};

// SettingsButton component for toggling calendar settings
export const SettingsButton = ({ onClick, isOpen }) => {
  return (
    <div className="absolute top-4 right-4 flex items-center">
      <span 
        className={`mr-2 text-sm transition-opacity duration-200 ${isOpen ? 'opacity-100' : 'opacity-0'}`}
        style={{ 
          color: 'var(--ghibli-brown)', 
          fontFamily: 'var(--heading-font)',
          fontWeight: '500',
          textShadow: '0 1px 2px rgba(255, 255, 255, 0.3)'
        }}
      >
        Calendar Settings
      </span>
      <button 
        onClick={onClick}
        className={`w-10 h-10 rounded-full flex items-center justify-center transition-all duration-300`}
        style={{
          backgroundColor: isOpen 
            ? 'rgba(129, 168, 197, 0.4)' 
            : 'rgba(255, 255, 255, 0.7)',
          color: isOpen 
            ? 'var(--ghibli-blue)' 
            : 'var(--ghibli-brown)',
          boxShadow: isOpen 
            ? 'inset 0 2px 4px rgba(0, 0, 0, 0.1)' 
            : '0 3px 6px var(--ghibli-shadow)',
          border: '1px solid',
          borderColor: isOpen 
            ? 'rgba(129, 168, 197, 0.5)' 
            : 'rgba(255, 255, 255, 0.7)',
          transform: isOpen ? 'rotate(5deg)' : 'rotate(0deg)',
          backdropFilter: 'blur(4px)', 
          WebkitBackdropFilter: 'blur(4px)',
        }}
        aria-label={isOpen ? "Close calendar settings" : "Open calendar settings"}
        title={isOpen ? "Close calendar settings" : "Open calendar settings"}
      >
        <svg 
          xmlns="http://www.w3.org/2000/svg" 
          className={`h-5 w-5 transition-transform duration-500 ${isOpen ? 'rotate-90' : ''}`} 
          fill="none" 
          viewBox="0 0 24 24" 
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      </button>
    </div>
  );
};

SettingsButton.propTypes = {
  onClick: PropTypes.func.isRequired,
  isOpen: PropTypes.bool
};

// Enhanced CalendarSettings component that combines both styling approaches
export const CalendarSettings = ({ calendars, selected, onSelect, disabled }) => {
  return (
    <div className="calendar-settings p-4 mb-4" style={{
      backgroundColor: 'var(--ghibli-cream)',
      borderRadius: '15px',
      boxShadow: '0 5px 15px var(--ghibli-shadow)',
      border: '1px solid rgba(156, 123, 101, 0.2)'
    }}>
      <h3 className="text-lg font-semibold mb-4" style={{
        fontFamily: 'var(--heading-font)',
        color: 'var(--ghibli-brown)'
      }}>My Calendars</h3>
      
      {calendars.length === 0 ? (
        <div className="py-4 text-center text-gray-500 rounded-lg" style={{
          backgroundColor: 'rgba(255, 255, 255, 0.5)'
        }}>
          <svg xmlns="http://www.w3.org/2000/svg" className="h-10 w-10 mx-auto mb-2" style={{ color: 'var(--ghibli-blue)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          <p style={{ color: 'var(--ghibli-brown)' }}>Loading calendars...</p>
        </div>
      ) : (
        <>
          <div className="text-sm mb-3" style={{ color: 'var(--ghibli-brown)' }}>
            Select which calendars to display and monitor. Changes are saved automatically.
          </div>
          
          <div className="max-h-60 overflow-y-auto pr-1 custom-scrollbar">
            <div className="grid grid-cols-1 gap-2">
              {calendars.map((cal) => (
                <div 
                  key={cal.id} 
                  className={`
                    flex items-center p-3 rounded-lg transition-all duration-200
                    ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
                  `}
                  style={{
                    backgroundColor: selected.some(s => s.id === cal.id) 
                      ? 'rgba(129, 168, 197, 0.15)' 
                      : 'rgba(255, 255, 255, 0.5)',
                    borderWidth: '1px',
                    borderStyle: 'solid',
                    borderColor: selected.some(s => s.id === cal.id)
                      ? 'rgba(129, 168, 197, 0.4)'
                      : 'rgba(156, 123, 101, 0.15)',
                    boxShadow: selected.some(s => s.id === cal.id)
                      ? '0 2px 4px rgba(0, 0, 0, 0.05)'
                      : 'none',
                    transform: selected.some(s => s.id === cal.id)
                      ? 'translateY(-1px)'
                      : 'none'
                  }}
                  onClick={() => !disabled && onSelect(cal)}
                >
                  <div className="relative">
                    <input
                      type="checkbox"
                      className="form-checkbox h-5 w-5 rounded transition duration-150 ease-in-out"
                      checked={selected.some((s) => s.id === cal.id)}
                      onChange={() => {}}
                      disabled={disabled}
                      style={{
                        borderColor: 'var(--ghibli-blue)',
                        color: 'var(--ghibli-blue)'
                      }}
                    />
                    {selected.some((s) => s.id === cal.id) && (
                      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                        <svg className="h-3 w-3 text-white" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                        </svg>
                      </div>
                    )}
                  </div>
                  <div className="ml-3 flex items-center flex-grow">
                    <div 
                      className="w-4 h-4 rounded-full mr-2 flex-shrink-0" 
                      style={{ 
                        backgroundColor: cal.backgroundColor || '#4285f4',
                        boxShadow: '0 1px 2px rgba(0, 0, 0, 0.1)'
                      }}
                    ></div>
                    <span style={{
                      color: cal.primary ? 'var(--ghibli-blue)' : 'var(--ghibli-brown)',
                      fontWeight: cal.primary ? '600' : '500',
                      fontSize: '0.9rem'
                    }} className="truncate">
                      {cal.summary} {cal.primary ? '(Primary)' : ''}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
          
          <div className="text-xs mt-3 pt-2 border-t" style={{ 
            borderColor: 'rgba(156, 123, 101, 0.1)',
            color: 'var(--ghibli-brown)'
          }}>
            {selected.length} of {calendars.length} calendars selected
          </div>
        </>
      )}
    </div>
  );
};

CalendarSettings.propTypes = {
  calendars: PropTypes.array.isRequired,
  selected: PropTypes.array.isRequired,
  onSelect: PropTypes.func.isRequired,
  disabled: PropTypes.bool
};

// CalendarSelectionComponent for better reusability
export const CalendarSelectionComponent = ({ calendars, selected, onSelect, disabled }) => {
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
};

CalendarSelectionComponent.propTypes = {
  calendars: PropTypes.array.isRequired,
  selected: PropTypes.array.isRequired,
  onSelect: PropTypes.func.isRequired,
  disabled: PropTypes.bool
};

// WelcomeMessage component
export const WelcomeMessage = () => {
  return (
    <ChatMessage 
      sender="bot" 
      content={`
        <div style="font-family: var(--body-font);">
          <p style="font-family: var(--heading-font); font-size: 1.1rem; color: var(--ghibli-brown); margin-bottom: 10px; font-weight: 600;">👋 Hi there! I'm your Calendar Assistant.</p>
          <p style="margin-bottom: 10px; color: #6b5d4f;">I can help you schedule events, find free time, and manage your calendar using natural language.</p>
          <p style="margin-bottom: 10px; color: #6b5d4f;">Try saying something like:</p>
          <ul style="list-style-type: none; padding-left: 5px; margin-bottom: 10px;">
            <li style="margin-bottom: 8px; display: flex; align-items: center;">
              <span style="display: inline-block; width: 18px; height: 18px; background-color: var(--ghibli-blue); border-radius: 50%; margin-right: 8px; flex-shrink: 0;"></span>
              Schedule a team meeting next Tuesday at 2pm
            </li>
            <li style="margin-bottom: 8px; display: flex; align-items: center;">
              <span style="display: inline-block; width: 18px; height: 18px; background-color: var(--ghibli-green); border-radius: 50%; margin-right: 8px; flex-shrink: 0;"></span>
              Find me free time tomorrow afternoon
            </li>
            <li style="margin-bottom: 8px; display: flex; align-items: center;">
              <span style="display: inline-block; width: 18px; height: 18px; background-color: var(--ghibli-orange); border-radius: 50%; margin-right: 8px; flex-shrink: 0;"></span>
              Schedule a 30-minute break at noon
            </li>
            <li style="display: flex; align-items: center;">
              <span style="display: inline-block; width: 18px; height: 18px; background-color: var(--ghibli-red); border-radius: 50%; margin-right: 8px; flex-shrink: 0;"></span>
              What meetings do I have today?
            </li>
          </ul>
          <p style="color: #6b5d4f; font-style: italic; margin-top: 15px; border-top: 1px solid rgba(156, 123, 101, 0.2); padding-top: 10px;">You can also toggle your calendar settings using the gear icon in the top right.</p>
        </div>
      `}
    />
  );
};

// RecommendationBar component
export const RecommendationBar = ({ suggestions, onSelectSuggestion }) => {
  return (
    <div className="recommendation-bar" style={{
      backgroundColor: 'rgba(255, 255, 255, 0.98)',
      borderTop: '1px solid rgba(156, 123, 101, 0.15)',
      backdropFilter: 'blur(10px)',
      WebkitBackdropFilter: 'blur(10px)',
      padding: '14px 20px 16px',
      marginTop: '4px'
    }}>
      <p style={{ 
        color: 'var(--ghibli-brown)', 
        fontFamily: 'var(--heading-font)',
        fontSize: '0.85rem',
        marginBottom: '12px',
        fontWeight: '600',
        opacity: 0.95,
        textAlign: 'center',
        letterSpacing: '0.5px',
        textShadow: '0 1px 1px rgba(255, 255, 255, 0.8)'
      }}>
        Popular Commands
      </p>
      <div className="flex flex-wrap gap-3 justify-center">
        {suggestions.map((suggestion, index) => {
          // Truncate text if needed
          const displayText = suggestion.text.length > 32 
            ? suggestion.text.substring(0, 32) + '...' 
            : suggestion.text;
            
          return (
            <button
              key={index}
              onClick={() => onSelectSuggestion(suggestion.text)}
              className="suggestion-pill"
              title={suggestion.text}
              style={{
                backgroundColor: 'white',
                color: '#5D4B3C',
                border: '1px solid rgba(156, 123, 101, 0.2)',
                borderRadius: '24px',
                padding: '8px 16px',
                boxShadow: '0 2px 6px rgba(0, 0, 0, 0.06)',
                fontFamily: 'var(--body-font)',
                fontSize: '0.95rem',
                fontWeight: '500',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                maxWidth: '220px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'all 0.3s ease',
                position: 'relative',
                background: `linear-gradient(120deg, white, white 65%, ${suggestion.color || 'rgba(129, 168, 197, 0.3)'} 200%)`,
              }}
            >
              <span style={{
                width: '24px',
                height: '24px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                marginRight: '8px',
                borderRadius: '50%',
                backgroundColor: suggestion.color || 'rgba(129, 168, 197, 0.2)',
                flexShrink: 0,
                boxShadow: 'inset 0 1px 2px rgba(0, 0, 0, 0.08)'
              }}>
                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="#4A3C30" style={{ opacity: 0.95 }}>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d={suggestion.icon} />
                </svg>
              </span>
              <span style={{ 
                maxWidth: '175px', 
                overflow: 'hidden', 
                textOverflow: 'ellipsis',
                textShadow: '0 0.5px 0 rgba(255, 255, 255, 0.9)'
              }}>
                {displayText}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
};

RecommendationBar.propTypes = {
  suggestions: PropTypes.arrayOf(
    PropTypes.shape({
      text: PropTypes.string.isRequired,
      color: PropTypes.string,
      icon: PropTypes.string.isRequired
    })
  ).isRequired,
  onSelectSuggestion: PropTypes.func.isRequired
}; 