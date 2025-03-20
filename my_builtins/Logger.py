import logging
import json
from datetime import datetime
from time import time

class Logger:

    SEND = "send"
    RECV = "recv"
    JOIN = "join"
    LEAVE = "leave"
    ENCODE = "encode"
    DECODE = "decode"
    EPOCH = "epoch"

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
        logging.info(json.dumps({
            'event': event,
            'timestamp': datetime.now().isoformat(),
            **kwargs
        }))
    

    @staticmethod
    def time(event: str):
        def decorator(func):
            def wrapper(*args, **kwargs):
                start = time()
                res = func(*args, **kwargs)
                end = time()
                Logger.log(
                    event,
                    time=end-start
                )
                return res
            return wrapper
        return decorator