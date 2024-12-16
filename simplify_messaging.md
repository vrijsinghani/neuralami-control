# Simplify Messaging Plan

Goal: Standardize on LangGraph native message types and remove legacy dictionary formats for cleaner, more maintainable code.

## Phase 1: Core Message Structure & Editing
- [x] Implement proper message editing functionality
  - [x] Remove messages after edited message from display
  - [x] Clear messages from chat history
- [x] Fix output parsing errors
  - [x] Handle simple text responses from LLM
  - [x] Ensure proper JSON formatting for tool calls
- [ ] Standardize message structure
- [ ] Remove legacy format conversions
- [ ] Implement consistent error handling
- [ ] Add proper tool message logging

## Phase 2: Standardize Output Handling ⏳ (In Progress)
- [x] Add LangGraph type imports (`AgentAction`, `AgentFinish`)
- [x] Update WebSocket Callback Handler
  - [x] Standardize message structure
  - [x] Remove legacy format conversions
  - [x] Implement consistent error handling
  - [x] Test all message types flow correctly
- [ ] Fix tool message handling
  - [x] Add proper console logging for tool messages
  - [ ] Remove null message responses
  - [ ] Ensure tool start/end messages are properly tracked
  - [ ] Add structured logging for debugging
- [ ] Verify frontend receives properly structured messages
- [ ] Confirm no regressions in existing functionality

## Phase 3: Update Tool Call Node 🔄 (Not Started)
- [ ] Simplify `_tool_call_node` implementation
  - [ ] Remove dictionary format handling
  - [ ] Handle only native LangGraph types
  - [ ] Implement clean error handling
- [ ] Test tool execution with direct `AgentAction` inputs
- [ ] Verify tool outputs are properly handled
- [ ] Ensure error cases are properly managed

## Phase 4: Clean Up Legacy Code 🔄 (Not Started)
- [ ] Remove all legacy format handling
  - [ ] Clean up message processing
  - [ ] Remove dictionary conversions
  - [ ] Update any remaining code to use native types
- [ ] Update tests
  - [ ] Remove legacy format tests
  - [ ] Add native format tests
  - [ ] Update test fixtures
- [ ] Final verification
  - [ ] Full conversation flow testing
  - [ ] Tool execution testing
  - [ ] Error handling testing

## Testing Notes
For each phase:
1. Test regular message flow
2. Test tool execution
3. Test error handling
4. Test message editing and history management
5. Verify frontend display
6. Check message structure in browser console
7. Verify tool message logging
8. Check for null or invalid messages

## Current Status
Currently implementing Phase 1, moving on to message editing functionality after completing the callback handler standardization.

## Completion Log
- 2024-XX-XX: Started Phase 1
  - Added LangGraph type imports
  - Initial callback handler updates
  - Added message editing fix to scope
  - Added tool message logging fix to scope
- 2024-XX-XX: Completed callback handler standardization
  - Standardized message structure
  - Removed legacy format conversions
  - Implemented consistent error handling
  - Added proper tool message logging
- 2024-XX-XX: Completed message editing functionality
  - Implemented removal of messages after edited message
  - Added chat history clearing
- 2024-XX-XX: Fixed output parsing
  - Added handling for direct text responses
  - Maintained JSON format for tool calls