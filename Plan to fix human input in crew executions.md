# Plan to Fix Human Input in Crew Executions
Validate First, Act Second
Always check inputs, parameters, and context before processing—don’t assume they’re there.

Fail Loudly, Fix Quietly
Catch errors early with clear logging and recovery, not silent assumptions.

Keep It Simple, Single, and Clear
Assign one responsibility per component—avoid tangled logic or overcomplicated state.

Pause and Ask When Lost
If context or input is unclear, halt and request clarification instead of guessing.

Track Every Step
Log progress and state religiously—make debugging a breeze, not a battle.

Test the Edges, Not Just the Middle
Validate edge cases and failures, not just the happy path.

Stick to the Plan, Don’t Patch the Past
Integrate cleanly with existing systems—don’t hack around them.

Validate Resources Early: Fetch and check critical resources (e.g., DB objects) at the start, with error handling.

Robust Error Handling: Wrap external interactions (e.g., DB, APIs) in try-except blocks, log errors, and clean up.

Preserve Working Code: Modify functional code only for specific needs; revert if changes lack clear benefits.

Consistent State Management: Set, maintain, and clean up state/context across all paths, using explicit storage and final blocks.

Incremental Changes: Apply small, focused updates, testing each step, rather than broad overhauls.

Validate Inputs: Check parameters for existence and type before use, with clear naming.

Detailed Logging: Log key operations (resource access, state changes, errors) with context and stack traces.

Realistic Testing: Test in real-world and edge-case scenarios, verifying behavior and cleanup.

Simplify State: Use simple state management, avoiding complexity unless necessary, leveraging existing structures.

Clear Responsibilities: Assign each component a single, documented purpose; refactor overlaps.

Respectful Integration: Extend external systems via inheritance/config, avoiding internal patches.

Resource Management: Set timeouts and explicitly release resources in all cases (e.g., cleanup blocks).


## Requirements

### Purpose
Enable CrewAI agents to interact with human users during task execution, allowing for:
1. Dynamic workflow customization
2. Real-time decision making
3. Human oversight and intervention
4. Information gathering from users

### Core Requirements
1. **Task Flow**
   - Agents must be able to request human input during task execution
   - Tasks should pause execution while waiting for input
   - Input should be properly integrated into the agent's context
   - Multiple input requests in sequence should work correctly

2. **User Experience**
   - Clear prompts for what input is needed
   - Real-time feedback on input status
   - Proper error handling and timeout messages
   - No UI freezing or unresponsive states

3. **System Integration**
   - Seamless integration with CrewAI's task execution flow
   - Proper handling of WebSocket connections
   - Reliable state management across the system
   - Consistent error handling and recovery

4. **Performance**
   - Minimal latency in input processing
   - No resource leaks during long waits
   - Proper timeout handling
   - Scalable to multiple concurrent executions

## Current Issues
1. Complex cache-based state management causing race conditions
2. Multiple places handling human input differently
3. Patching CrewAI internals leading to fragile code
4. Infinite loops and stalled executions
5. Lack of clear responsibility in the code

## Proposed Solution
Create a proper task-based approach that works with CrewAI instead of against it.

### 1. Core Components

#### HumanInputTask Class
- Extends CrewAI's Task class
- Handles its own execution flow
- Uses existing CrewExecution model for state
- Communicates via WebSocket for real-time updates
- Clear single responsibility: manage human input for a task

#### WebSocket Communication
- Simplified message format
- Clear status updates
- Real-time UI feedback
- No complex cache management

### Implementation Plan & Progress Tracking

#### Phase 1: Core Task Implementation [Status: Not Started]
- [ ] 1.1 Create HumanInputTask Class
  - [ ] Basic class structure extending CrewAI Task
  - [ ] Simple input request/response flow
  - [ ] Timeout handling
  - [ ] Error handling

- [ ] 1.2 WebSocket Communication
  - [ ] Define message formats
  - [ ] Implement request broadcasting
  - [ ] Handle response processing
  - [ ] Add connection management

#### Phase 2: Code Cleanup [Status: Not Started]
- [ ] 2.1 Remove Old Code
  - [ ] Remove cache-based handlers
  - [ ] Clean up CrewAI patches
  - [ ] Update imports and dependencies

- [ ] 2.2 Real-time Testing & Fixes
  - [ ] Test basic input/output flow
  - [ ] Test timeout scenarios
  - [ ] Test error handling
  - [ ] Fix issues as they arise

#### Phase 3: UI Improvements [Status: Not Started]
- [ ] 3.1 Frontend Updates
  - [ ] Update WebSocket handlers
  - [ ] Add loading states
  - [ ] Improve error messages
  - [ ] Add timeout indicators

### Success Criteria
1. No infinite loops or stalled executions
2. Clear error messages and handling
3. Proper timeout management
4. Real-time UI feedback
5. No race conditions
6. Works with CrewAI's natural flow

### Progress Updates
[Date] - Initial plan created
