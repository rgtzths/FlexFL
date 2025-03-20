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
    def send(func):
        def wrapper(*args, **kwargs):
            Logger.log(
                Logger.SEND,
                node_id=args[1],
                payload_size=len(args[2])
            )
            return func(*args, **kwargs)
        return wrapper
    

    @staticmethod
    def recv(func):
        def wrapper(*args, **kwargs):
            node_id, data = func(*args, **kwargs)
            Logger.log(
                Logger.RECV, 
                node_id=node_id, 
                payload_size=len(data)
            )
            return node_id, data
        return wrapper
    

    @staticmethod
    def encode(func):
        def wrapper(*args, **kwargs):
            start = time()
            res = func(*args, **kwargs)
            end = time()
            Logger.log(
                Logger.ENCODE,
                time=end-start
            )
            return res
        return wrapper
    

    @staticmethod
    def decode(func):
        def wrapper(*args, **kwargs):
            start = time()
            res = func(*args, **kwargs)
            end = time()
            Logger.log(
                Logger.DECODE,
                time=end-start
            )
            return res
        return wrapper