1|# Refactoring Plan: Chat Service Architecture
2|
3|## Overview
4|The current chat service architecture has several components with mixed responsibilities. This refactor aims to improve separation of concerns, maintainability, and testability by reorganizing the code into focused, single-responsibility modules.
5|
6|## Current Issues
7|- ChatService handles too many responsibilities (formatting, token management, tool management, etc.)
8|- Callback handling is split between ChatService and WebSocketCallbackHandler
9|- Formatting logic is duplicated between services
10|- Token management is scattered across different methods
11|- Tool management is tightly coupled with the chat service
12|
13|## Files to Consider
14|
15|### Core Files to Modify
16|```
17|# Backend
18|apps/agents/websockets/services/chat_service.py
19|apps/agents/websockets/handlers/callback_handler.py
20|apps/agents/chat/formatters.py
21|
22|# Frontend
23|static/js/chat.js
24|static/js/components/tool_output.js
25|```
26|
27|### Related Files to Review
28|```
29|apps/agents/chat/history.py
30|apps/agents/utils.py
31|apps/common/utils.py
32|apps/agents/models.py
33|apps/seo_manager/models.py
34|```
35|
36|## New Files to Create
37|```
38|apps/agents/chat/managers/
39|  ├── token_manager.py
40|  ├── tool_manager.py
41|  ├── prompt_manager.py
42|  └── message_manager.py
43|apps/agents/chat/formatters/
44|  ├── __init__.py
45|  ├── table_formatter.py
46|  ├── tool_formatter.py
47|  └── output_formatter.py
48|```
49|
50|## Refactoring Phases
51|
52|### Phase 1: Formatter Reorganization
53|- Move TableFormatter to its own file
54|- Create dedicated formatters for tools and output
55|- Update imports in chat_service.py and callback_handler.py
56|- Add tests for each formatter
57|
58|**Testing Criteria:**
59|- All existing table formatting still works
60|- Tool output formatting remains consistent
61|- No changes in output appearance for end users
62|
63|### Phase 2: Manager Classes Creation
64|- Implement TokenManager
65|- Implement ToolManager
66|- Implement PromptManager
67|- Implement MessageManager
68|- Add tests for each manager
69|
70|**Testing Criteria:**
71|- Token tracking remains accurate
72|- Tools load and execute correctly
73|- Prompts generate as before
74|- Message history functions properly
75|
76|### Phase 3: ChatService Refactor
77|- Update ChatService to use new managers
78|- Remove duplicated code
79|- Streamline initialization process
80|- Add integration tests
81|
82|**Testing Criteria:**
83|- All existing chat functionality works
84|- Performance remains consistent
85|- No regression in error handling
86|
87|### Phase 4: Callback Handler Integration
88|- Move all callback handling to WebSocketCallbackHandler
89|- Update ChatService to delegate callbacks
90|- Add tests for callback flow
91|
92|**Testing Criteria:**
93|- All websocket messages sent correctly
94|- No duplicate messages
95|- Error handling works as expected
96|
97|### Phase 5: Frontend Refactor
98|- Reorganize chat.js into smaller components
99|- Create dedicated message handlers for different types
100|- Improve tool output rendering and state management
101|- Add frontend tests
102|
103|**Frontend Components to Create:**
104|```
105|static/js/chat/
106|  ├── components/
107|  │   ├── message.js
108|  │   ├── message_list.js
109|  │   ├── input.js
110|  │   └── tool_outputs/
111|  │       ├── base.js
112|  │       ├── table.js
113|  │       ├── error.js
114|  │       └── generic.js
115|  ├── services/
116|  │   ├── websocket.js
117|  │   └── message_handler.js
118|  └── utils/
119|      ├── formatting.js
120|      └── validation.js
121|```
122|
123|**Testing Criteria:**
124|- All message types render correctly
125|- Tool outputs maintain functionality
126|- WebSocket communication works seamlessly
127|- Error handling and display work as expected
128|- UI remains responsive
129|
130|### Frontend Testing Strategy
131|```
132|static/js/tests/
133|  ├── components/
134|  │   ├── message.test.js
135|  │   ├── message_list.test.js
136|  │   └── tool_outputs/
137|  │       ├── table.test.js
138|  │       └── error.test.js
139|  ├── services/
140|  │   └── message_handler.test.js
141|  └── integration/
142|      └── chat_flow.test.js
143|```
144|
145|## Testing Strategy
146|
147|### Unit Tests
148|```python
149|# Example test structure
150|apps/agents/chat/tests/
151|  ├── test_formatters/
152|  ├── test_managers/
153|  ├── test_chat_service.py
154|  └── test_callback_handler.py
155|```
156|
157|### Integration Tests
158|```python
159|apps/agents/tests/integration/
160|  ├── test_chat_flow.py
161|  └── test_tool_execution.py
162|```
163|
164|### End-to-End Tests
165|```python
166|apps/e2e_tests/
167|  └── test_chat_session.py
168|```
169|
170|## Rollback Plan
171|- Keep old implementation files with `.old` suffix
172|- Maintain version control tags at each phase
173|- Document database migrations if needed
174|
175|## Success Metrics
176|- Reduced code complexity (measured by cyclomatic complexity)
177|- Improved test coverage
178|- Reduced duplicate code
179|- Faster development iteration
180|- Easier onboarding for new developers
181|- Improved frontend performance metrics
182|- Reduced JavaScript bundle size
183|- Better frontend test coverage
184|- Improved accessibility scores
185|
186|## Timeline
187|- Phase 1: 2-3 days
188|- Phase 2: 3-4 days
189|- Phase 3: 2-3 days
190|- Phase 4: 2-3 days
191|- Phase 5: 3-4 days
192|
193|Total estimated time: 12-17 days including testing
194|
195|## Future Considerations
196|- Consider adding metrics collection
197|- Plan for horizontal scaling
198|- Document extension points for new tools/formatters
199|- Consider adding feature flags for gradual rollout 