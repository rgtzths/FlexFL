import logging
import json
from time import time

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
            level=logging.DEBUG
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
            level=logging.DEBUG
        )
    

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
                'timestamp': time()
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
                'timestamp': time(),
                **content,
            })
        )


    @staticmethod
    def results(content: dict) -> None:
        """
        Log the results

        Parameters:
            results (dict): the results to log
        """
        Logger.custom('results', content)


    @staticmethod
    def comm(content: dict) -> None:
        """
        Log the communication

        Parameters:
            comm (dict): the communication to log
        """
        Logger.custom('comm', content)