import logging
import json
from datetime import datetime
import signal
import sys

class Logger:

    SEND = "send"
    RECV = "recv"
    JOIN = "join"
    LEAVE = "leave"
    ENCODE = "encode"
    DECODE = "decode"
    EPOCH = "epoch"
    START = "start"
    END = "end"
    WORKING = "working"
    FAILURE = "failure"

    @staticmethod
    def setup(file_path: str):
        logging.basicConfig(
            level=logging.INFO,
            filename=file_path,
            format='%(message)s',
            filemode='w'
        )


    @staticmethod
    def setup_failure():
        def handle_terminate(signal, frame):
            Logger.log(Logger.FAILURE)
            Logger.end()
            sys.exit(0)
        signal.signal(signal.SIGTERM, handle_terminate)
        signal.signal(signal.SIGINT, handle_terminate)

    
    @staticmethod
    def end():
        logging.shutdown()


    @staticmethod
    def log(event: str, **kwargs):
        logging.info(json.dumps({
            'event': event,
            'timestamp': datetime.now().isoformat(),
            **kwargs
        }))
    

    @staticmethod
    def time(event: str):
        def decorator(func):
            def wrapper(*args, **kwargs):
                start = datetime.now()
                res = func(*args, **kwargs)
                end = datetime.now()
                logging.info(json.dumps({
                    'event': event,
                    'start': start.isoformat(),
                    'end': end.isoformat(),
                    'duration(ms)': (end - start).total_seconds() * 1000
                }))
                return res
            return wrapper
        return decorator