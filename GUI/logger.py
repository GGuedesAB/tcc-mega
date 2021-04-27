import logging

# Create a new module for Logger
class Logger ():
    def __init__ (self, logger_name=None):
        if logger_name:
            self.logger = logging.getLogger(logger_name)
        else:
            self.logger = logging.getLogger(__name__)
        self.log_format = logging.Formatter("[%(name)s] %(levelname)s: %(message)s")
        self.console_handle = logging.StreamHandler()
        self.console_handle.setFormatter(self.log_format)
        self.logger.addHandler(self.console_handle)

    def set_debug(self):
        self.logger.setLevel(logging.DEBUG)

    def set_info(self):
        self.logger.setLevel(logging.INFO)

    def set_warning(self):
        self.logger.setLevel(logging.WARNING)

    def set_error(self):
        self.logger.setLevel(logging.ERROR)

    def error(self, msg):
        self.logger.error(msg)
    
    def debug(self, msg):
        self.logger.debug(msg)

    def info(self, msg):
        self.logger.info(msg)

    def warning(self, msg):
        self.logger.warning(msg)