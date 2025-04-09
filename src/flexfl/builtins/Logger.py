import logging
import json
import time

class Logger:

    SEND = "send"
    RECV = "recv"
    JOIN = "join"
    NEW_WORKER = "new_worker"
    LEAVE = "leave"
    ENCODE = "encode"
    DECODE = "decode"
    EPOCH = "epoch"
    START = "start"
    END = "end"
    WORKING_START = "working_start"
    WORKING_END = "working_end"
    VALIDATION_START = "validation_start"
    VALIDATION_END = "validation_end"
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
    def end():
        logging.shutdown()


    @staticmethod
    def log(event: str, **kwargs):
        timestamp = time.time()
        logging.info(json.dumps({
            'event': event,
            'timestamp': timestamp,
            **kwargs
        }))
    

    @staticmethod
    def time(event: str):
        def decorator(func):
            def wrapper(*args, **kwargs):
                start = time.time()
                res = func(*args, **kwargs)
                end = time.time()
                Logger.log(event, time=end-start)
                return res
            return wrapper
        return decorator