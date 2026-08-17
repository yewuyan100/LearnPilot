import os
import sqlite3
from pathlib import Path
from threading import RLock

os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver


class AgentRuntime:
    def __init__(self, settings):
        self.settings=settings; self.connection=None; self.locks: dict[str,RLock]={}
        if settings.agent_checkpoint_enabled:
            path=Path(settings.agent_checkpoint_db_path); path.parent.mkdir(parents=True,exist_ok=True)
            self.connection=sqlite3.connect(path,check_same_thread=False)
            self.checkpointer=SqliteSaver(self.connection); self.checkpointer.setup()
        else:
            self.checkpointer=InMemorySaver()

    def lock(self, thread_id: str) -> RLock:
        return self.locks.setdefault(thread_id, RLock())

    def close(self):
        if self.connection is not None: self.connection.close()
