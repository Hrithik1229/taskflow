from app.schemas.task import TaskRead


class TaskVersionConflict(Exception):
    def __init__(self, current: TaskRead) -> None:
        self.current = current
        super().__init__("Task was changed by another request.")
