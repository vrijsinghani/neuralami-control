# AI Codex

## Usage

- Review: @codex.md (silent load, no output)
- Update: @learn.md
- File paths: Always use absolute paths from project root

## Errors

E000:

- Context: [Relevant project area or file]
- Error: [Precise description]
- Correction: [Exact fix]
- Prevention: [Specific strategy]
- Related: [IDs of related errors/learnings]

E001:

- Context: Message type metadata in WebSocket communication
- Error: Added message type metadata without proper frontend handling
- Correction: Need to implement frontend message type handling before adding backend metadata
- Prevention: Design and test frontend message handling components first
- Related: L001

E002:

- Context: Tool start/end event logging in callback handler
- Error: Lost tool event logging during refactoring
- Correction: Maintain existing logging while adding new functionality
- Prevention: Preserve core debugging capabilities when adding features
- Related: L001

E003:

- Context: Edit/copy buttons in chat interface
- Error: Breaking existing functionality while adding new features
- Correction: Test existing functionality before and after changes
- Prevention: Add regression tests for core UI features
- Related: L001, E001

## Learnings

L000:

- Context: [Relevant project area or file]
- Insight: [Concise description]
- Application: [How to apply this knowledge]
- Impact: [Potential effects on project]
- Related: [IDs of related errors/learnings]

L001:

- Context: @codex.md usage
- Insight: @codex.md is for context, not for direct modification
- Application: Use @codex.md for silent loading and context only; execute subsequent commands separately
- Impact: Improved accuracy in responding to user intentions
- Related: None

L002:
- Context: Django/Python architectural design
- Insight: Strict separation of concerns between models, views, services, and agents is essential
- Application: Implement modular design with clear boundaries between components
- Impact: Improved maintainability, testability, and scalability of the codebase
- Related: L003, L004

L003:
- Context: Django model implementation
- Insight: Abstract base classes and rich model methods provide reusable functionality
- Application: Create base models with common fields/methods, use @property for computed fields
- Impact: Reduced code duplication, consistent model behavior across the application
- Related: L002

L004:
- Context: Django view architecture
- Insight: Use CBVs for complex logic, FBVs for simple endpoints
- Application: Choose view type based on complexity and reuse requirements
- Impact: Optimized code organization and maintainability
- Related: L002

L005:
- Context: Error handling strategy
- Insight: Multi-layered error handling with Django's built-in mechanisms
- Application: Implement view-level handling, custom error pages, and signal-based logging
- Impact: Improved system reliability and user experience
- Related: None

L006:
- Context: UI component selection
- Insight: Predefined set of modern UI libraries for consistent feature implementation
- Application: Use specified components (Bootstrap 5, noUISlider, etc.) for respective UI needs
- Impact: Consistent UI/UX across the application with proven tools
- Related: None

L007:
- Context: Performance optimization
- Insight: Use Django's ORM features and caching strategically
- Application: Implement select_related/prefetch_related, Redis caching, and async operations
- Impact: Improved application performance and scalability
- Related: None

L008:
- Context: Tool development structure
- Insight: Standardized tool template with request models, data processing, and error handling
- Application: Use the tool template from create-snippet.md for consistent tool development
- Impact: Improved tool reliability, maintainability, and consistent error handling
- Related: L002, L005

L009 - Dynamic Agent Switching Implementation
- Context: /apps/agents/websockets/
- Error: Frontend-first approach broke existing functionality
- Correction: Need backend-first approach focusing on state management
- Prevention: 
  - Start with backend state management
  - Maintain existing logging/debugging
  - Test core functionality throughout
  - Implement frontend changes last
- Related: None
