from enum import Enum


class LogLevel(Enum):
    INFO = "INFO"
    DEBUG = "DEBUG"
    WARNING = "WARNING"
    ERROR = "ERROR"


colors = {
    LogLevel.INFO: "\033[94m",
    LogLevel.DEBUG: "\033[92m",
    LogLevel.WARNING: "\033[93m",
    LogLevel.ERROR: "\033[91m",
    "ENDC": "\033[0m",
}


class Logger:
    def __init__(self, debug: bool = False, silent: bool = False):
        self.debug_mode = debug
        self.silent_mode = silent

    def info(self, message: str):
        if not self.silent_mode:
            print(
                f"{colors[LogLevel.INFO]}[{LogLevel.INFO.value}]{colors['ENDC']} {message}"
            )

    def debug(self, message: str):
        if self.debug_mode and not self.silent_mode:
            print(
                f"{colors[LogLevel.DEBUG]}[{LogLevel.DEBUG.value}]{colors['ENDC']} {message}"
            )

    def warning(self, message: str):
        if not self.silent_mode:
            print(
                f"{colors[LogLevel.WARNING]}[{LogLevel.WARNING.value}]{colors['ENDC']} {message}"
            )

    def error(self, message: str):
        if not self.silent_mode:
            print(
                f"{colors[LogLevel.ERROR]}[{LogLevel.ERROR.value}]{colors['ENDC']} {message}"
            )

    def panic(self, message: str):
        self.error(message)
        exit(1)
