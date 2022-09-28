# pubsubplus-python-client
#
# Copyright 2021-2022 Solace Corporation. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# 	http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Module for solace internal utilities"
# pylint: disable=missing-module-docstring,too-many-arguments,inconsistent-return-statements,no-else-raise
# pylint: disable=missing-function-docstring,no-else-return,missing-class-docstring
# pylint: disable=line-too-long	,consider-using-with
import concurrent
import configparser
import logging
import os
import queue
from queue import Full
import threading
from abc import abstractmethod
from concurrent.futures import ThreadPoolExecutor
from os.path import dirname
from time import time
from typing import Callable

from solace.messaging._solace_logging._core_api_log import last_error_info
from solace.messaging.config._solace_message_constants import INVALID_DATATYPE, TOPIC_NAME_MAX_LENGTH, \
    TOPIC_NAME_TOO_LONG, VALUE_CANNOT_BE_NEGATIVE, GRACE_PERIOD_MIN_INVALID_ERROR_MESSAGE, DICT_CONTAINS_NONE_VALUE, \
    CCSMP_INFO_SUB_CODE, CCSMP_SUB_CODE, CCSMP_CALLER_DESC, CCSMP_INFO_CONTENTS, \
    CCSMP_RETURN_CODE, THREAD_TIMEOUT_MAX_VALUE, GRACE_PERIOD_MAX_TIMEOUT_ERROR_MESSAGE, GRACE_PERIOD_MIN_MS, \
    INVALID_EXPECTED_DATATYPE, VALUE_OUT_OF_RANGE
from solace.messaging.config.solace_properties.message_properties import APPLICATION_MESSAGE_TYPE, ELIDING_ELIGIBLE, \
    PRIORITY, HTTP_CONTENT_TYPE, HTTP_CONTENT_ENCODING, CORRELATION_ID, PERSISTENT_TIME_TO_LIVE, PERSISTENT_EXPIRATION, \
    PERSISTENT_DMQ_ELIGIBLE, PERSISTENT_ACK_IMMEDIATELY, SEQUENCE_NUMBER, APPLICATION_MESSAGE_ID, SENDER_ID
from solace.messaging.config.solace_properties._legacy_properties import _CORRELATION_ID_v1_2_0
from solace.messaging.errors.pubsubplus_client_error import PubSubPlusClientError, \
    InvalidDataTypeError, IllegalArgumentError, IllegalStateError, PubSubPlusCoreClientError


class _PythonQueueEventExtension(queue.Queue):
    # enhanced python queue for registering callbacks on important internal queue events

    # defined queue event callbacks
    ON_FULL_EVENT: int = 0
    # on full event when queue goes from having available capacity to not
    # Note this event is not called if the queue is already full on put
    ON_AVAILABLE_EVENT: int = 1

    # on available event when queue goes from not having capacity to having available capacity
    # Note this event is not called if the queue already has capacity on get

    ON_BUFFER_OVERFLOW_EVENT: int = 2
    # on buffer overflow event when queue does not have capacity but there is an inbound message.
    # Note: this event is used at least by the direct receiver when DropOldest or DropLatest
    # back pressure strategies are enabled for that direct receiver.

    @abstractmethod
    def register_on_event(self, event: int, event_handler: Callable[[], None]):
        """ registers defined event callbacks """


class _PubSubPlusQueue(_PythonQueueEventExtension):
    # extension to base fifo queue.Queue for thread safe peek
    # and wait for empty condition
    def __init__(self, maxsize=0):
        super().__init__(maxsize)
        self._is_empty = threading.Condition(self.mutex)
        self._registered_events = dict()

    def register_on_event(self, event: int, event_handler: Callable[[], None]):
        with self.mutex:
            self._registered_events[event] = event_handler

    def _get(self):
        # override _get note self.mutex is assumed to be held during this function
        if self.maxsize > 0:
            presize = self._qsize()
            item = super()._get()
            if presize >= self.maxsize and self._qsize() < self.maxsize:
                on_available = self._registered_events.get(_PubSubPlusQueue.ON_AVAILABLE_EVENT)
                if on_available:
                    on_available()
        else:
            item = super()._get()
        if self._qsize() == 0:
            self._is_empty.notify_all()
        return item

    def put(self, item, block=True, force=False, timeout=None):
        """Put an item into the queue.
        If optional args 'block' is true and 'timeout' is None (the default),
        block if necessary until a free slot is available. If 'timeout' is
        a non-negative number, it blocks at most 'timeout' seconds and raises
        the Full exception if no free slot was available within that time.
        Otherwise ('block' is false), put an item on the queue if a free slot
        is immediately available, else raise the Full exception ('timeout'
        is ignored in that case)."""
        _put_has_not_been_called = True
        with self.not_full:
            removed = None
            if self.maxsize > 0:
                if not block:
                    if self._qsize() >= self.maxsize:
                        on_overflow = self._registered_events.get(_PubSubPlusQueue.ON_BUFFER_OVERFLOW_EVENT)
                        if on_overflow:
                            on_overflow(item)
                        raise Full
                elif timeout is None:
                    if force and (self._qsize() >= self.maxsize):
                        # The queue must be in its final state before calling the callback method.
                        # This means that the oldest message must be removed and the incoming
                        # message must be added before calling the callback method.
                        removed = self._get()
                        self._put(item)
                        _put_has_not_been_called = False
                        on_overflow = self._registered_events.get(_PubSubPlusQueue.ON_BUFFER_OVERFLOW_EVENT)
                        if on_overflow:                                                                                                                                                                 on_overflow(removed)
                    else:
                        while self._qsize() >= self.maxsize:
                            self.not_full.wait()
                elif timeout < 0:
                    raise ValueError("'timeout' must be a non-negative number")
                else:
                    endtime = time() + timeout
                    while self._qsize() >= self.maxsize:
                        remaining = endtime - time()
                        if remaining <= 0.0:
                            on_overflow = self._registered_events.get(_PubSubPlusQueue.ON_BUFFER_OVERFLOW_EVENT)
                            if on_overflow:
                                on_overflow(item)
                            raise Full
                        self.not_full.wait(remaining)
            if _put_has_not_been_called:
                # If nothing has been put on the queue yet,
                # we'll add to the queue now 
                self._put(item)
            self.unfinished_tasks += 1
            self.not_empty.notify()
            return removed

    def _put(self, item):
        # override _put note self.mutex is assumed to be held during this function
        if self.maxsize > 0:
            presize = self._qsize()
            super()._put(item)
            if presize < self.maxsize and self._qsize() >= self.maxsize:
                on_full = self._registered_events.get(_PubSubPlusQueue.ON_FULL_EVENT)
                if on_full:
                    on_full()
        else:
            super()._put(item)

    def wait_for_empty(self, timeout: float = None, predicate: Callable[[], bool] = None) -> float:
        with self._is_empty:
            def is_false() -> bool:
                return False

            additional_condition = is_false if predicate is None else predicate
            if timeout is None:
                starttime = time()
                while self._qsize() != 0 or additional_condition():
                    self._is_empty.wait()
                remaining = time() - starttime
            else:
                remaining = timeout
                endtime = time() + timeout
                while self._qsize() != 0 or additional_condition():
                    remaining = endtime - time()
                    if remaining < 0.0:
                        remaining = 0.0
                        break
                    self._is_empty.wait(remaining)
            return remaining

    def peek(self):
        # thread safe peek extension
        with self.mutex:
            return self.unsafe_peek()

    def unsafe_peek(self):
        # unsafe thread peek extension
        if len(self.queue) > 0:
            return self.queue[0]
        else:
            return None

    def unsafe_full(self):
        # returns the internal queue full indication without mutex protection
        # used for performance first state checking not for garenteed accuracy
        return 0 < self.maxsize <= self._qsize()


class _ThreadingUtil:
    # threading utilities
    @staticmethod
    def create_serialized_executor(name_prefix: str = None) -> 'Executor':
        # utility method for global api serialization construction
        # should ThreadPoolExecutor not be performant this can replace all constructed
        # serialized executors in the api
        prefix = name_prefix if name_prefix is not None else 'pubsubplus_python_client_thread'
        return ThreadPoolExecutor(max_workers=1, thread_name_prefix=prefix)


def is_type_matches(actual, expected_type, raise_exception=True, ignore_none=False, exception_message=None,
                    logger=None) -> bool:
    # Args:
    #     actual: target input parameter
    #     expected_type: compare ACTUAL data type with this
    #     raise_exception: if actual and expected date type doesn't matches
    #     ignore_none: ignore type check if ACTUAL is None
    #
    # Returns: True if actual and expected date type matches, else False
    if isinstance(actual, expected_type) or (ignore_none and actual is None):
        return True
    if raise_exception:
        if exception_message is None:
            exception_message = f'{INVALID_DATATYPE} Expected type: [{expected_type}], ' \
                                f'but actual [{type(actual)}]'
        if logger is not None:
            logger.warning(exception_message)
        raise InvalidDataTypeError(exception_message)
    return False

def validate_message_props(props: dict):
    properties_type_mapping = {APPLICATION_MESSAGE_TYPE: [str],
                               ELIDING_ELIGIBLE: [int],
                               PRIORITY: [int],
                               HTTP_CONTENT_TYPE: [str],
                               HTTP_CONTENT_ENCODING: [str],
                               SENDER_ID: [str, type(None)],
                               CORRELATION_ID: [str],
                               _CORRELATION_ID_v1_2_0: [str],
                               PERSISTENT_TIME_TO_LIVE: [int],
                               PERSISTENT_EXPIRATION: [int],
                               PERSISTENT_DMQ_ELIGIBLE: [int],
                               PERSISTENT_ACK_IMMEDIATELY: [int],
                               SEQUENCE_NUMBER: [int],
                               APPLICATION_MESSAGE_ID: [str]}
    for key in props:
        if key in properties_type_mapping:
            if not type(props[key]) in properties_type_mapping[key]:  # pylint: disable=unidiomatic-typecheck
                if isinstance(props[key], bool):
                    return
                raise InvalidDataTypeError(INVALID_EXPECTED_DATATYPE.substitute(actual_type=type(props[key]),
                                                                                expected_type=properties_type_mapping[
                                                                                    key]))

def get_last_error_info(return_code: int, caller_description: str, exception_message: str = None):
    last_error = last_error_info(return_code, caller_desc=caller_description)
    cleansed_last_error = f'Caller Description: {last_error[CCSMP_CALLER_DESC]}. ' \
                          f'Error Info Sub code: [{last_error[CCSMP_INFO_SUB_CODE]}]. ' \
                          f'Error: [{last_error[CCSMP_INFO_CONTENTS]}]. ' \
                          f'Sub code: [{last_error[CCSMP_SUB_CODE]}]. ' \
                          f'Return code: [{last_error[CCSMP_RETURN_CODE]}]'
    if exception_message:
        cleansed_last_error = f'{exception_message}\n{cleansed_last_error}'
    return PubSubPlusCoreClientError(cleansed_last_error, last_error[CCSMP_INFO_SUB_CODE])


def is_topic_valid(topic_name, logger, error_message):
    if topic_name is None or len(topic_name) == 0:
        logger.warning(error_message)
        raise IllegalArgumentError(error_message)
    if len(topic_name) > TOPIC_NAME_MAX_LENGTH:
        logger.warning(TOPIC_NAME_TOO_LONG)
        raise IllegalArgumentError(TOPIC_NAME_TOO_LONG)
    return True


def is_not_negative(input_value, raise_exception=True, exception_message=None, logger=None) -> bool:
    is_type_matches(input_value, int, logger=logger)
    if input_value < 0:
        error_message = VALUE_CANNOT_BE_NEGATIVE if exception_message is None else exception_message
        if logger:
            logger.warning(error_message)
        if raise_exception:
            raise IllegalArgumentError(VALUE_CANNOT_BE_NEGATIVE)
    return False


def is_value_out_of_range(lower_bound, upper_bound, input_value, raise_exception=True, exception_message=None, logger=None) -> bool:
    is_type_matches(input_value, int, logger=logger)
    if input_value < lower_bound or input_value > upper_bound:
        error_message = VALUE_OUT_OF_RANGE + f"{lower_bound} to {upper_bound}, inclusive." if exception_message is None else exception_message
        if logger:
            logger.warning(error_message)
        if raise_exception:
            raise IllegalArgumentError(error_message)
    return False


def convert_ms_to_seconds(milli_seconds):
    return milli_seconds / 1000


def handle_none_for_str(input_value):
    if input_value is None:
        return str(None)
    return input_value


def validate_grace_period(grace_period, logger):
    if grace_period < GRACE_PERIOD_MIN_MS:
        logger.warning(GRACE_PERIOD_MIN_INVALID_ERROR_MESSAGE)
        raise IllegalArgumentError(GRACE_PERIOD_MIN_INVALID_ERROR_MESSAGE)

    if grace_period > THREAD_TIMEOUT_MAX_VALUE:
        logger.warning(GRACE_PERIOD_MAX_TIMEOUT_ERROR_MESSAGE)
        raise IllegalArgumentError(GRACE_PERIOD_MAX_TIMEOUT_ERROR_MESSAGE)


def raise_illegal_state_error(error_message, logger=None):
    if logger:
        logger.warning(error_message)
    raise IllegalStateError(error_message)


def is_none_or_empty_exists(given_dict, error_message=None, logger=None, raise_error=True):
    is_none_exists = all((value == '' or value is None) for value in given_dict.values())
    if error_message is None:
        error_message = DICT_CONTAINS_NONE_VALUE
    if is_none_exists:
        if logger:
            logger.warning(error_message)
        if raise_error:
            raise IllegalArgumentError(error_message)
        else:
            return True
    return False


def _create_completed_future():
    exc = _ThreadingUtil.create_serialized_executor()

    def _to_run():
        pass

    future = exc.submit(_to_run)
    exc.shutdown(wait=True)
    future.result()
    return future


COMPLETED_FUTURE = _create_completed_future()


def executor_shutdown(executor):
    try:
        if isinstance(executor, concurrent.futures.thread.ThreadPoolExecutor):
            executor.shutdown()
    except RuntimeError as error:  # this shouldn't happen ideally when this function is called by weakref finalize
        logging.getLogger('solace.messaging').warning(str(error))


class _Released:  # this would a context to temporarily release an acquired lock for long waits
    def __init__(self, lock):
        self.lock = lock

    def __enter__(self):
        self.lock.release()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.lock.acquire()
