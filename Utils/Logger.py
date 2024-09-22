import logging
import json
from datetime import datetime
from time import time

from Utils.CommUtils import CommUtils

class Logger:

    @staticmethod
    def setup_master(base_path: str) -> None:
        """
        Setup the master logger

        Parameters:
            base_path (str): the base path for the results
        """
        logging.basicConfig(
            filename=f'{base_path}/master.log',
            format='%(message)s',
            level=logging.DEBUG,
            filemode='w'
        )


    @staticmethod
    def setup_worker(base_path: str, worker_id: int) -> None:
        """
        Setup the worker logger

        Parameters:
            base_path (str): the base path for the results
            worker_id (int): the id of the worker process
        """
        logging.basicConfig(
            filename=f'{base_path}/worker_{worker_id}.log',
            format='%(message)s',
            level=logging.DEBUG,
            filemode='w'
        )


    @staticmethod
    def end() -> None:
        """
        Log the end of the process
        """
        logging.shutdown()
    

    @staticmethod
    def message(message: str, level = logging.INFO) -> None:
        """
        Log a message

        Parameters:
            message (str): the message to log
            level (int): the logging level
        """
        logging.log(
            level,
            json.dumps({
                'event': 'message',
                'message': message,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        )


    @staticmethod
    def custom(event: str, content: dict, level = logging.INFO) -> None:
        """
        Log a custom event

        Parameters:
            event (str): the event name
            message (str): the message to log
            level (int): the logging level
        """
        logging.log(
            level,
            json.dumps({
                'event': event,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                **content,
            })
        )


    @staticmethod
    def results(epoch: int, time: float, metrics: dict) -> None:
        """
        Log the results

        Parameters:
            epoch (int): the current epoch
            time (float): the time taken for the epoch
            metrics (dict): the metrics for the epoch
        """
        Logger.custom('results', {
            'epoch': epoch,
            'time': time,
            **metrics
        })


    @staticmethod
    def comm(data_size: int, time: float, origin: int, destination: int) -> None:
        """
        Log the communication

        Parameters:
            comm (dict): the communication to log
        """
        Logger.custom('comm', {
            'data_size': data_size,
            'time': time,
            'origin': origin,
            'destination': destination,
        })


    @staticmethod
    def send(func) -> None:
        """
        Decorator to log the send operation
        """
        def wrapper(comm: CommUtils, *args, **kwargs):
            start = time()
            result = func(comm, *args, **kwargs)
            end = time()
            if func.__name__ == 'send_master':
                worker_id = -1
                data = args[0]
            else:
                worker_id = args[0]
                data = args[1]
            data_size = comm.get_size(data)
            Logger.comm(data_size, end - start, comm.worker_id, worker_id)
            return result
        return wrapper
    

    @staticmethod
    def recv(func) -> None:
        """
        Decorator to log the receive operation
        """
        def wrapper(comm: CommUtils, *args, **kwargs):
            start = time()
            result = func(comm, *args, **kwargs)
            end = time()
            if func.__name__ == 'recv_master':
                worker_id = -1
                data = result
            else:
                worker_id = result[0]
                data = result[1]
            data_size = comm.get_size(data)
            Logger.comm(data_size, end - start, worker_id, comm.worker_id)
            return result
        return wrapper
    
                
