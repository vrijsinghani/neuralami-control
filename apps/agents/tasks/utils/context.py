from contextvars import ContextVar

current_task_id = ContextVar('current_task_id', default=None)

class TaskContext:
    def __init__(self, task_id):
        self.task_id = task_id
        self.token = None

    def __enter__(self):
        self.token = current_task_id.set(self.task_id)
        return self

    def __exit__(self, *args):
        current_task_id.reset(self.token) 