from dataclasses import dataclass


@dataclass(frozen=True)
class Task:
    task_id: str
    user_query: str
    workspace_root: str
    task_class: str
