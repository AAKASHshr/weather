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
# pylint: disable=missing-function-docstring,no-else-raise,no-member,no-else-return,inconsistent-return-statements
# pylint: disable=broad-except,consider-using-with

"""
Module that abstracts message receiving behavior; it is a base class for all receivers.
"""
import concurrent
import copy
import logging
import threading
import weakref
from concurrent.futures.thread import ThreadPoolExecutor
from ctypes import c_uint32, py_object, c_void_p, Structure, CFUNCTYPE, c_int
from enum import Enum
from queue import Queue, Full

from solace.messaging import _SolaceServiceAdapter
from solace.messaging.config._sol_constants import SOLCLIENT_OK, SOLCLIENT_CALLBACK_OK, SOLCLIENT_CALLBACK_TAKE_MSG
from solace.messaging.config._solace_message_constants import GRACE_PERIOD_DEFAULT_MS, \
    RECEIVER_TERMINATED_UNABLE_TO_START, CANNOT_ADD_SUBSCRIPTION, RECEIVER_TERMINATED, \
    CANNOT_REMOVE_SUBSCRIPTION, RECEIVER_ALREADY_TERMINATED, \
    UNCLEANED_TERMINATION_EXCEPTION_MESSAGE_RECEIVER, UNABLE_TO_RECEIVE_MESSAGE_MESSAGE_SERVICE_NOT_CONNECTED, \
    UNABLE_TO_RECEIVE_MESSAGE_RECEIVER_ALREADY_TERMINATED, \
    UNABLE_TO_UNSUBSCRIBE_TO_TOPIC, RECEIVER_CANNOT_BE_STARTED_MSG_SERVICE_NOT_CONNECTED, \
    RECEIVER_TERMINATION_IS_IN_PROGRESS
from solace.messaging.core._solace_message import _SolaceMessage, message_cleanup
from solace.messaging.errors.pubsubplus_client_error import IllegalStateError, IncompleteMessageDeliveryError, \
    PubSubPlusCoreClientError, PubSubPlusClientError
from solace.messaging.receiver._impl._inbound_message import _InboundMessage
from solace.messaging.receiver._impl._receiver_utilities import is_message_service_connected
from solace.messaging.receiver._inbound_message_utility import topic_unsubscribe_with_dispatch, \
    topic_subscribe_with_dispatch
from solace.messaging.receiver.message_receiver import MessageReceiver
from solace.messaging.utils._solace_utilities import executor_shutdown, convert_ms_to_seconds, COMPLETED_FUTURE, \
    _Released, _PubSubPlusQueue, get_last_error_info, validate_grace_period
#from solace.messaging.utils._solace_utilities import get_last_error_info
#from solace.messaging.utils._solace_utilities import validate_grace_period

logger = logging.getLogger('solace.messaging.receiver')


class _MessageReceiverState(Enum):  # pylint: disable=too-few-public-methods, missing-class-docstring
    # enum class for defining the message receiver state
    NOT_STARTED = 0
    STARTING = 1
    STARTED = 2
    TERMINATING = 3
    TERMINATED = 4


class _MessageReceiver(MessageReceiver):  # pylint: disable=too-many-instance-attributes
    msg_callback_func_type = CFUNCTYPE(c_int, c_void_p, c_void_p, py_object)

    def __init__(self, builder):
        self._messaging_service = builder.messaging_service
        self._id_info = f"[SERVICE: {str(hex(id(self._messaging_service.logger_id_info)))}] " \
                        f"[RECEIVER: {str(hex(id(self)))}]"

        self.adapter = _SolaceServiceAdapter(logger, {'id_info': self._id_info})
        self._message_receiver_state = _MessageReceiverState.NOT_STARTED
        self._asked_to_terminate = False
        self._init_back_pressure(builder)
        self._start_future = None
        self._terminate_future = None
        self._start_lock = threading.Lock()
        self._start_async_lock = threading.Lock()
        self._terminate_lock = threading.Lock()
        self._terminate_async_lock = threading.Lock()
        self._receive_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(thread_name_prefix=self._id_info)
        self._finalizer = weakref.finalize(self, executor_shutdown, self._executor)
        self._can_receive_event = threading.Event()
        self._receiver_empty_event = threading.Event()
        self._message_receiver_thread_stop_event = threading.Event()
        self._message_receiver_thread = None
        self._is_unsubscribed = False
        self._running = None
        self._topic_dict = dict()

    def _init_back_pressure(self, builder):
        self._force = False
        self._block = True
        self._message_receiver_queue = _PubSubPlusQueue()

    @property
    def receiver_state(self):
        return self._message_receiver_state

    @property
    def receiver_queue(self):
        return self._message_receiver_queue

    @property
    def stop_event(self):
        return self._message_receiver_thread_stop_event

    @property
    def can_receive_event(self):
        return self._can_receive_event

    @property
    def receiver_empty_event(self):
        return self._receiver_empty_event

    def is_running(self) -> bool:
        is_running = self._message_receiver_state == _MessageReceiverState.STARTED
        if logger.isEnabledFor(logging.DEBUG):  # pragma: no cover # Ignored due to log level
            self.adapter.debug('%s is running?: %s', type(self).__name__, is_running)
        return is_running

    def is_terminated(self) -> bool:
        is_terminated = _MessageReceiverState.TERMINATED == self._message_receiver_state
        if logger.isEnabledFor(logging.DEBUG):  # pragma: no cover # Ignored due to log level
            self.adapter.debug('%s  is terminated?: %s', type(self).__name__, is_terminated)
        return is_terminated

    def is_terminating(self) -> bool:
        is_terminating = _MessageReceiverState.TERMINATING == self._message_receiver_state
        if logger.isEnabledFor(logging.DEBUG):  # pragma: no cover # Ignored due to log level
            self.adapter.debug('%s is terminating?', is_terminating)
        return is_terminating

    @property
    def asked_to_terminate(self):
        return self._asked_to_terminate

    def start_async(self) -> concurrent.futures.Future:
        # Start the Receiver asynchronously (non-blocking)
        if self.__is_connecting() or self.__is_connected():
            return self._start_future
        with self._start_async_lock:
            self._is_receiver_terminated(error_message=RECEIVER_TERMINATED_UNABLE_TO_START)
            # Even after acquiring lock still we have to check the state to avoid spinning up the executor
            if self.__is_connecting() or self.__is_connected():
                return self._start_future
            self._start_future = self._executor.submit(self.start)
            return self._start_future

    def _check_buffer(self):
        if self._message_receiver_queue in self._messaging_service.api.receiver_queues:
            # by pop-ing out we make sure callback also don't insert extra None in buffer,
            # since flow down event is received  first before we receive SOLCLIENT_SESSION_EVENT_DOWN_ERROR
            index = self._messaging_service.api.receiver_queues.index(self._message_receiver_queue)
            self._messaging_service.api.receiver_queues.pop(index)

    def terminate(self, grace_period: int = GRACE_PERIOD_DEFAULT_MS):
        # implementation will be  given in direct & persistent concrete class
        validate_grace_period(grace_period=grace_period, logger=logger)
        with self._terminate_lock:
            if not self._is_receiver_available_for_terminate() or \
                    self._message_receiver_state == _MessageReceiverState.NOT_STARTED:
                return
            self._message_receiver_state = _MessageReceiverState.TERMINATING
            self._asked_to_terminate = True  # flag to prevent  the thread to sleep while terminating
            grace_period_in_seconds = convert_ms_to_seconds(grace_period)
            self._halt_messaging()
            self._handle_events_on_terminate()
            if self.receiver_queue.qsize() > 0:  # don't wait if internal buffer is empty,
                # we have unsubscribed all topics as well as
                # we dropping messages in message callback routine in TERMINATING state (in case of persistent ,
                # we have already paused the flow and dropping the messages in the flow message
                # callback routine in  TERMINATING state)
                # Release the terminate lock when queue size drain to be done.
                with _Released(self._terminate_lock):
                    self._receiver_empty_event.wait(timeout=grace_period_in_seconds)
            self._cleanup()
            self._check_undelivered_messages()
            self._message_receiver_queue.put(None)  # unblock the blocking receive_message api
            self.adapter.info("%s", RECEIVER_TERMINATED)

    def terminate_async(self, grace_period: int = GRACE_PERIOD_DEFAULT_MS) -> concurrent.futures.Future:
        # Terminate the Receiver asynchronously (non-blocking).
        validate_grace_period(grace_period=grace_period, logger=logger)
        if self.__is_in_terminal_state():
            self._is_receiver_available_for_terminate()
            return self._terminate_future

        with self._terminate_async_lock:
            # Even after acquiring lock still we have to check the state to avoid spinning up the executor
            if self.__is_in_terminal_state():
                self._is_receiver_available_for_terminate()
                return self._terminate_future
            if self._message_receiver_state == _MessageReceiverState.NOT_STARTED:
                self._terminate_future = COMPLETED_FUTURE
            else:
                self._terminate_future = self._executor.submit(self.terminate, grace_period)
            return self._terminate_future

    def _can_add_subscription(self, error_message=None, raise_error=True):
        error_message = f'{CANNOT_ADD_SUBSCRIPTION}{self._message_receiver_state.name}' \
            if error_message is None else error_message
        self._is_receiver_available(error_message=error_message, raise_error=raise_error)

    def _can_remove_subscription(self, error_message=None, raise_error=True):
        error_message = f'{CANNOT_REMOVE_SUBSCRIPTION}{self._message_receiver_state.name}' \
            if error_message is None else error_message
        self._is_receiver_available(error_message=error_message, raise_error=raise_error)

    def _is_receiver_available(self, error_message=None, raise_error=True):
        self._is_receiver_started(error_message=error_message, raise_error=raise_error)
        self._is_receiver_terminated(error_message=error_message, raise_error=raise_error)

    def _is_receiver_available_for_terminate(self):
        return not self._is_receiver_terminating(error_message=None, raise_error=False)

    def _is_receiver_started(self, error_message, raise_error=True):
        if self._message_receiver_state == _MessageReceiverState.NOT_STARTED:
            self.adapter.warning("%s", error_message)
            if raise_error:
                raise IllegalStateError(error_message)
            else:
                return False
        return True

    def _is_receiver_terminating(self, error_message=None, raise_error=True):
        if self._message_receiver_state == _MessageReceiverState.TERMINATING or \
                self._message_receiver_state == _MessageReceiverState.TERMINATED:
            if self._message_receiver_state == _MessageReceiverState.TERMINATING:
                error_message = RECEIVER_TERMINATION_IS_IN_PROGRESS if error_message is None else error_message
            elif self._message_receiver_state == _MessageReceiverState.TERMINATED:
                error_message = RECEIVER_ALREADY_TERMINATED if error_message is None else error_message
            self.adapter.warning("%s", error_message)
            if raise_error:
                raise IllegalStateError(error_message)
            else:
                return True
        return False

    def _is_receiver_terminated(self, error_message=None, raise_error=True):
        if self._message_receiver_state == _MessageReceiverState.TERMINATED:
            error_message = RECEIVER_TERMINATED if error_message is None else error_message
            self.adapter.warning("%s", error_message)
            if raise_error:
                raise IllegalStateError(error_message)
            else:
                return True
        return False

    def _check_undelivered_messages(self):  # notify application of any remaining buffered data
        if self._message_receiver_queue.qsize() != 0:
            message = f'{UNCLEANED_TERMINATION_EXCEPTION_MESSAGE_RECEIVER}. ' \
                      f'Message count: [{self._message_receiver_queue.qsize()}]'
            self.adapter.warning("%s", message)
            self._message_receiver_queue = Queue()  # reset the queue
            raise IncompleteMessageDeliveryError(message)

    def _handle_events_on_terminate(self):
        # note this wakes the message delivery even when receiver is paused
        # this is better then blocking for the whole grace period
        self._can_receive_event.set()  # stop the thread from waiting

    def _is_message_service_connected(self, raise_error=True):
        # Method to validate message service is connected or not
        if not self._messaging_service.is_connected:
            self.adapter.warning("%s", UNABLE_TO_RECEIVE_MESSAGE_MESSAGE_SERVICE_NOT_CONNECTED)
            if raise_error:
                raise IllegalStateError(UNABLE_TO_RECEIVE_MESSAGE_MESSAGE_SERVICE_NOT_CONNECTED)
            else:
                return False
        return True

    def _can_receive_message(self):
        # """can able to receive message if message service is connected and it is not terminated"""
        self._is_message_service_connected()
        if self._message_receiver_state == _MessageReceiverState.TERMINATED:
            error_message = UNABLE_TO_RECEIVE_MESSAGE_RECEIVER_ALREADY_TERMINATED
            self.adapter.warning("%s", error_message)
            raise IllegalStateError(error_message)

    def _cleanup(self):
        self._asked_to_terminate = True  # flag to prevent  the thread to sleep while terminating
        self._message_receiver_state = _MessageReceiverState.TERMINATED
        if self._message_receiver_thread is not None:
            # set thread termination flag before waking delivery thread
            # to ensure clean exit from python message delivery thread
            self._message_receiver_thread_stop_event.set()

            self._can_receive_event.set()  # don't block the thread while terminating
            # wake message delivery thread
            # join on python message delivery thread
            self._message_receiver_thread.join()

    def __is_connecting(self):
        return self._start_future and self._message_receiver_state == _MessageReceiverState.STARTING

    def __is_connected(self):
        return self._start_future and self._message_receiver_state == _MessageReceiverState.STARTED

    def __is_in_terminal_state(self):
        return self._terminate_future and (self.__is_terminating() or self.__is_terminated())

    def __is_terminating(self):
        return self._terminate_future and self._message_receiver_state == _MessageReceiverState.TERMINATING

    def __is_terminated(self):
        return self._terminate_future and self._message_receiver_state == _MessageReceiverState.TERMINATED

    def _wakeup_terminate(self):
        if self._message_receiver_state == _MessageReceiverState.TERMINATING and \
                self._message_receiver_queue.qsize() == 0:
            self._receiver_empty_event.set()  # wakeup the terminate method if buffer is empty at TERMINATING state

    def _do_subscribe(self, topic_subscription: str):
        """ implementation will be given in child class"""

    def _do_unsubscribe(self, topic_subscription: str):
        """ implementation will be given in child class"""

    def start(self) -> MessageReceiver:
        # Start theMessageReceiver synchronously (blocking).
        # return self if we already started the receiver
        if self._message_receiver_state == _MessageReceiverState.STARTED:
            return self

        with self._start_lock:
            self._is_receiver_terminated(error_message=RECEIVER_TERMINATED_UNABLE_TO_START)
            # Even after acquiring lock still we have to check the state to avoid re-doing the work
            if self._message_receiver_state == _MessageReceiverState.STARTED:
                return self

            elif self._message_receiver_state == _MessageReceiverState.NOT_STARTED:
                self._message_receiver_state = _MessageReceiverState.STARTING
                if logger.isEnabledFor(logging.DEBUG):  # pragma: no cover # Ignored due to log level
                    self.adapter.debug(' [%s] is %s', type(self).__name__,
                                       _MessageReceiverState.STARTING.name)
                _, self._message_receiver_state = \
                    is_message_service_connected(receiver_state=self._message_receiver_state,
                                                 message_service=self._messaging_service,
                                                 logger=logger)
                self._do_start()
                return self

    def _do_start(self):
        # start the MessageReceiver (always blocking).
        errors = None
        for topic, subscribed in self._topic_dict.items():
            if not subscribed:
                try:
                    self._do_subscribe(topic)
                    self._topic_dict[topic] = True
                except PubSubPlusClientError as exception:  # pragma: no cover # Due to core error scenarios
                    errors = str(exception) if errors is None else errors + "; " + str(exception)
                    self._message_receiver_state = _MessageReceiverState.NOT_STARTED
                    self.adapter.warning("%s %s", RECEIVER_CANNOT_BE_STARTED_MSG_SERVICE_NOT_CONNECTED,
                                         str(errors))
                    raise PubSubPlusClientError \
                        (message=f"{RECEIVER_CANNOT_BE_STARTED_MSG_SERVICE_NOT_CONNECTED}{str(errors)}") from exception
                    # pragma: no cover # Due to core error scenarios
        self._running = True
        self._message_receiver_state = _MessageReceiverState.STARTED
        if logger.isEnabledFor(logging.DEBUG):  # pragma: no cover # Ignored due to log level
            self.adapter.debug('%s is %s', type(self).__name__, _MessageReceiverState.STARTED.name)

    def _halt_messaging(self):
        """ for terminating appropriately based on the receiver type"""


class _DirectRequestReceiver(_MessageReceiver):
    def __init__(self, builder):
        super().__init__(builder)
        self._group_name = None
        self._msg_callback_func_routine = self.msg_callback_func_type(self._message_receive_callback_routine)

    class SolClientReceiverCreateRxMsgDispatchFuncInfo(Structure) \
            :  # pylint: disable=too-few-public-methods, missing-class-docstring
        # """ Conforms to solClient_session_rxMsgDispatchFuncInfo """

        _fields_ = [
            ("dispatch_type", c_uint32),  # The type of dispatch described
            ("callback_p", CFUNCTYPE(c_int, c_void_p, c_void_p, py_object)),  # An application-defined callback
            # function; may be NULL if there is no callback.
            ("user_p", py_object),  # A user pointer to return with the callback; must be NULL if callback_p is NULL.
            ("rffu", c_void_p)  # Reserved for Future use; must be NULL
        ]
        # common for direct & RR receiver

    def _unsubscribe(self):
        # called as part of terminate
        if self._is_unsubscribed:
            return
        if self._topic_dict and self._messaging_service.is_connected:
            self._is_unsubscribed = True
            topics = [*copy.deepcopy(self._topic_dict)]
            # unsubscribe topics as part of teardown activity
            for topic in topics:
                try:
                    self._do_unsubscribe(topic)
                except PubSubPlusClientError as exception:  # pragma: no cover # Due to core error scenarios
                    self.adapter.warning(exception)

    def _message_receive_callback_routine(self, _opaque_session_p, msg_p, _user_p) \
            :  # pragma: no cover
        # The message callback is invoked for each Direct/Request Reply message received by the Session
        # only enqueue message while the receiver is live
        if self._message_receiver_state not in [_MessageReceiverState.STARTING,
                                                _MessageReceiverState.STARTED]:
            # Unfortunately its not possible to determine how many
            # in-flight messages remaining in the  message window on shutdown.
            # Drop messages while terminating to prevent a race between
            # native layer message dispatch and draining the python
            # internal message queue for graceful terminate.
            return SOLCLIENT_CALLBACK_OK  # return the received message to native layer
        ret = SOLCLIENT_CALLBACK_TAKE_MSG # By default the Python API takes the received message
        void_pointer = None
        try:
            void_pointer = c_void_p(msg_p)
            rx_msg = _InboundMessage(_SolaceMessage(void_pointer))
            removed_message = self._message_receiver_queue.put(rx_msg, force=self._force, block=self._block)
            if removed_message:
                removed_message._solace_message.cleanup()
            self._can_receive_event.set()
            if logger.isEnabledFor(logging.DEBUG):  # pragma: no cover # Ignored due to log level
                self.adapter.debug('PUT message to %s buffer/queue', type(self).__name__)
        except Full as exception:
            # The Full exception is only thrown by the put() method, so we can call the _can_receive_event.set()
            # method here without risk of duplicate calls to the method
            self._can_receive_event.set()

            if void_pointer:
                void_pointer.value = None

            if logger.isEnabledFor(logging.INFO):  # pragma: no cover # Ignored due to log level
                self.adapter.info(f'DROPPED message since there was no room left in the queue.')
            ret = SOLCLIENT_CALLBACK_OK # Dropped message is returned to the C API
        except Exception as exception:
            self.adapter.error(exception)
            raise PubSubPlusClientError(message=exception) from exception
        return ret

    def _do_subscribe(self, topic_subscription: str):
        # Subscribe to a topic (always blocking).
        if self._group_name is None or self._group_name == '':
            subscribe_to = topic_subscription
        else:
            subscribe_to = "#share/" + self._group_name + "/" + topic_subscription
        if logger.isEnabledFor(logging.DEBUG):  # pragma: no cover # Ignored due to log level
            self.adapter.debug('SUBSCRIBE to: [%s]', subscribe_to)

        dispatch_info = self.SolClientReceiverCreateRxMsgDispatchFuncInfo(
            c_uint32(1),
            self._msg_callback_func_routine,
            py_object(self),
            c_void_p(None))

        return_code = topic_subscribe_with_dispatch(self._messaging_service.session_pointer,
                                                    subscribe_to, dispatch_info)
        if return_code == SOLCLIENT_OK:
            self._topic_dict[topic_subscription] = True
        else:
            failure_message = f'{UNABLE_TO_UNSUBSCRIBE_TO_TOPIC} [{topic_subscription}].'
            exception: PubSubPlusCoreClientError = \
                get_last_error_info(return_code=return_code,
                                    caller_description=f'{type(self).__name__}->_do_subscribe',
                                    exception_message=failure_message)
            self.adapter.warning('%s. Status code: %d. %s', failure_message, return_code,
                                 str(exception))  # pragma: no cover # Due to core error scenarios
            raise exception  # pragma: no cover

    def _do_unsubscribe(self, topic_subscription: str):
        # Unsubscribe from a topic (always blocking).
        if self._group_name is None or self._group_name == '':
            unsubscribe_to = topic_subscription
        else:
            unsubscribe_to = "#share/" + self._group_name + "/" + topic_subscription
        if logger.isEnabledFor(logging.DEBUG):  # pragma: no cover # Ignored due to log level
            self.adapter.debug('UNSUBSCRIBE to: [%s]', unsubscribe_to)
        dispatch_info = self.SolClientReceiverCreateRxMsgDispatchFuncInfo(c_uint32(1), self._msg_callback_func_routine,
                                                                          py_object(self), c_void_p(None))

        return_code = topic_unsubscribe_with_dispatch(self._messaging_service.session_pointer, unsubscribe_to,
                                                      dispatch_info)
        if topic_subscription in self._topic_dict:
            del self._topic_dict[topic_subscription]
        if return_code != SOLCLIENT_OK:
            failure_message = f'{UNABLE_TO_UNSUBSCRIBE_TO_TOPIC} [{unsubscribe_to}].'
            exception: PubSubPlusCoreClientError = \
                get_last_error_info(return_code=return_code,
                                    caller_description=f'{type(self).__name__}->_do_unsubscribe',
                                    exception_message=failure_message)
            self.adapter.warning("%s", str(exception))
            raise exception
