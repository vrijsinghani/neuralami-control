# Crew Execution and Human Input

This document provides an overview of the crew execution process and the human input feature in the CrewAI platform.

## Crew Execution

Crews are executed using the following process:

1. A user initiates a crew execution from the crew detail page.
2. The `execute_crew` Celery task is triggered, which creates a `CrewExecution` instance.
3. The crew is executed using the CrewAI library.
4. If the execution completes successfully, the results are stored in the `CrewExecution` instance.
5. If an error occurs, the execution is marked as failed, and an error message is logged.

## Human Input Feature

The human input feature allows crews to request input from users during execution. Here's how it works:

1. If a task in the crew requires human input, it raises a `HumanInputRequired` exception.
2. The `execute_crew` task catches this exception and updates the `CrewExecution` status to "WAITING_FOR_HUMAN_INPUT".
3. The execution detail page displays the human input request to the user.
4. The user submits their input through a form on the execution detail page.
5. The `resume_crew_execution` task is triggered, which continues the execution with the provided human input.

### Implementation Details

- The `CrewExecution` model includes fields for `human_input_request` and `human_input_response`.
- The `execution_detail.html` template includes a form for submitting human input when required.
- The `tasks.py` file contains the logic for handling human input requests and resuming execution.

## Testing

Unit tests for crew execution and human input handling can be found in `tests.py`. These tests cover:

- Basic crew execution
- Handling of human input requests
- Resuming execution after human input
- Creation of crew messages

To run the tests, use the following command:

```
python manage.py test apps.agents
```

## Future Improvements

- Implement a notification system to alert users when their input is required.
- Add more comprehensive error handling and recovery mechanisms.
- Enhance the user interface for a more intuitive human input experience.

For any questions or issues, please contact the development team.