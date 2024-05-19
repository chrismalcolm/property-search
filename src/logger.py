import datetime
from enum import Enum

class LogLevel(Enum):
    INFO = 'INFO'
    WARNING = 'WARNING'
    ERROR = 'ERROR'

class LogEntry:

    def __init__(self, message: str, level: LogLevel):
        self.message = message
        self.level = level
        self.timestamp = datetime.datetime.now()

    def __str__(self):
        return f'{self.timestamp} [{self.level.value}] {self.message}'

class Logger:
    def __init__(self, log_file='app.log'):
        self.log_file = log_file
        self.history = []

    def info(self, message):
        entry = LogEntry(message, LogLevel.INFO)
        self._log(entry)
        self.history.append(entry)

    def warning(self, message):
        entry = LogEntry(message, LogLevel.WARNING)
        self._log(entry)
        self.history.append(entry)

    def error(self, message):
        entry = LogEntry(message, LogLevel.ERROR)
        self._log(entry)
        self.history.append(entry)

    def _log(self, entry):
        with open(self.log_file, 'a') as f:
            f.write(str(entry) + '\n')