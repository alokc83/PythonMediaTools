from PyQt5.QtCore import QObject, pyqtSignal

class ToolOrchestrator(QObject):
    """
    Central service to manage signal passing between running tools and the Dashboard.
    Singleton-ish usage (passed down from MainWindow).
    """
    # Signal emitted when a new task starts
    # task_id (str), task_name (str), view_id (int - logical ID for navigation)
    task_added = pyqtSignal(str, str, int)

    # Signal emitted when task progress updates
    # task_id (str), current (int), total (int), message (str)
    task_progress = pyqtSignal(str, int, int, str)

    # Signal emitted when a task log occurs (usually the same as message in progress, but separate channel if needed)
    # task_id (str), message (str)
    task_log = pyqtSignal(str, str)

    # Signal emitted when a task finishes
    # task_id (str)
    task_finished = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        # Keep track of active tasks just in case we need to query them
        # Format: { 'task_id': { 'name': '...', 'status': '...' } }
        self.active_tasks = {}

    def start_task(self, task_id, task_name, view_id):
        """
        Register a new task and notify listeners (Dashboard).
        """
        if task_id in self.active_tasks:
            return # Already running
            
        self.active_tasks[task_id] = {
            'name': task_name,
            'view_id': view_id,
            'status': 'Running'
        }
        self.task_added.emit(task_id, task_name, view_id)

    def report_progress(self, task_id, current, total, message):
        """
        Tools call this to update their status.
        """
        if task_id in self.active_tasks:
            self.task_progress.emit(task_id, current, total, message)

    def report_log(self, task_id, message):
        """
        Tools call this to send a log message (separate from progress status).
        """
        if task_id in self.active_tasks:
            self.task_log.emit(task_id, message)

    def finish_task(self, task_id):
        """
        Tools call this when they are done/stopped.
        """
        if task_id in self.active_tasks:
            del self.active_tasks[task_id]
            self.task_finished.emit(task_id)
