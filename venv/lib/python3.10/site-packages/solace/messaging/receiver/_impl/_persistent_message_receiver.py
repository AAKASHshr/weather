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

# Module contains the implementation class and methods for the PersistentMessageReceiver
# pylint: disable=too-many-instance-attributes, too-many-arguments, missing-function-docstring,no-else-raise
# pylint: disable=missing-module-docstring,protected-access,missing-class-docstring,inconsistent-return-statements
# pylint: disable=no-else-break,too-many-statements,too-many-public-methods,too-many-nested-blocks,no-else-return
# pylint: disable=expression-not-assigned,broad-except
# pylint: disable=too-many-lines

import concurrent
import copy
import ctypes
import datetime
import logging
import queue
import threading
import time
import weakref
from ctypes import Structure, c_void_p, py_object, CFUNCTYPE, c_int, POINTER, c_char_p, cast, byref, sizeof
from queue import Queue
from typing import Union, Dict

import solace
from solace.messaging import _SolaceServiceAdapter
from solace.messaging._solace_logging._core_api_log import last_error_info
from solace.messaging.config._ccsmp_property_mapping import end_point_props, CCSMP_SESSION_PROP_MAPPING, replay_prop
from solace.messaging.config._ccsmp_property_mapping import flow_props
from solace.messaging.config._sol_constants import SOLCLIENT_OK, SOLCLIENT_FLOW_PROP_BIND_NAME, \
    SOLCLIENT_FLOW_PROP_BIND_ENTITY_DURABLE, SOLCLIENT_CALLBACK_TAKE_MSG, SOLCLIENT_CALLBACK_OK, \
    SOLCLIENT_ENDPOINT_PROP_NAME, _SolClientFlowEvent, SOLCLIENT_DISPATCH_TYPE_CALLBACK, HIGH_THRESHOLD, \
    LOW_THRESHOLD, SOLCLIENT_ENDPOINT_PROP_ACCESSTYPE, SOLCLIENT_ENDPOINT_PROP_ACCESSTYPE_NONEXCLUSIVE, \
    SOLCLIENT_FLOW_PROP_SELECTOR, SOLCLIENT_FAIL, SOLCLIENT_FLOW_PROP_REPLAY_START_LOCATION
from solace.messaging.config._solace_message_constants import UNABLE_TO_SUBSCRIBE_TO_TOPIC, DISPATCH_FAILED, \
    UNABLE_TO_RECEIVE_MESSAGE_RECEIVER_NOT_STARTED, RECEIVER_TERMINATED, UNABLE_TO_UNSUBSCRIBE_TO_TOPIC, FLOW_PAUSE, \
    FLOW_RESUME, \
    RECEIVER_SERVICE_DOWN_EXIT_MESSAGE, STATE_CHANGE_LISTENER_SERVICE_DOWN_EXIT_MESSAGE, \
    UNABLE_TO_ACK, RECEIVER_TERMINATED_UNABLE_TO_START, FLOW_INACTIVE, FLOW_DOWN
from solace.messaging.config.missing_resources_creation_configuration import MissingResourcesCreationStrategy
from solace.messaging.config.receiver_activation_passivation_configuration import ReceiverStateChangeListener, \
    ReceiverState
from solace.messaging.config.replay_strategy import AllMessagesReplay, TimeBasedReplay, \
    ReplicationGroupMessageIdReplay
from solace.messaging.config.sub_code import SolClientSubCode
from solace.messaging.core import _solace_session
from solace.messaging.core._core_api_utility import prepare_array
from solace.messaging.core._message import _SolClientDestination
from solace.messaging.core._solace_message import _SolaceMessage
from solace.messaging.errors.pubsubplus_client_error import PubSubPlusClientError, IllegalStateError, \
    PubSubPlusCoreClientError, InvalidDataTypeError, MessageReplayError
from solace.messaging.receiver._impl._inbound_message import _InboundMessage
from solace.messaging.receiver._impl._message_receiver import _MessageReceiver, _MessageReceiverState
from solace.messaging.receiver._impl._receiver_utilities import is_message_service_connected, validate_subscription_type
from solace.messaging.receiver._inbound_message_utility import acknowledge_message, pause, resume, \
    flow_topic_subscribe_with_dispatch, flow_topic_unsubscribe_with_dispatch, end_point_provision, \
    topic_endpoint_subscribe, topic_endpoint_unsubscribe, flow_destination
from solace.messaging.receiver.inbound_message import InboundMessage
from solace.messaging.receiver.message_receiver import MessageHandler
from solace.messaging.receiver.persistent_message_receiver import PersistentMessageReceiver
from solace.messaging.resources.topic_subscription import TopicSubscription
from solace.messaging.utils._impl._manageable_receiver import _PersistentReceiverInfo
from solace.messaging.utils._solace_utilities import get_last_error_info, is_type_matches, is_not_negative, \
    convert_ms_to_seconds, COMPLETED_FUTURE, _ThreadingUtil, _Released, _PubSubPlusQueue
from solace.messaging.utils.life_cycle_control import TerminationEvent, TerminationNotificationListener
from solace.messaging.utils.manageable import Metric

logger = logging.getLogger('solace.messaging.receiver')


def flow_cleanup(flow_p, session_p):
    #   Destroys a previously created Flow. Upon return, the opaque Flow pointer
    #   is set to NULL.
    #   This operation <b>must not</b> be performed in a Flow callback
    #   for the Flow being destroyed.
    # Args:
    #  flow_p :  A pointer to the opaque Flow pointer that was returned when
    #   the Session was created.
    # Returns:
    #   SOLCLIENT_OK, SOLCLIENT_FAIL
    try:
        if session_p and flow_p:  # proceed to clean-up only if we still have  the session
            return_code = solace.CORE_LIB.solClient_flow_destroy(ctypes.byref(flow_p))
            if return_code != SOLCLIENT_OK:  # pragma: no cover # Due to failure scenario
                exception: PubSubPlusCoreClientError = get_last_error_info(return_code=return_code,
                                                                           caller_description='flow_cleanup')
                logger.warning(str(exception))
    except PubSubPlusClientError as exception:  # pragma: no cover # Due to failure scenario
        logger.warning('Flow cleanup failed. Exception: %s ', str(exception))


class PersistentStateChangeListenerThread(threading.Thread) \
        :  # pylint: disable=missing-class-docstring, too-many-instance-attributes, too-many-arguments
    # Thread used to dispatch received flow state on a receiver.

    def __init__(self, state_change_queue: Queue, receiver_state_change_listener: ReceiverStateChangeListener,
                 can_listen_event, state_change_stop_event, messaging_service, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._id_info = f"PersistentStateChangeListenerThread Id: {str(hex(id(self)))}"
        self.adapter = _SolaceServiceAdapter(logger, {'id_info': self._id_info})
        if logger.isEnabledFor(logging.DEBUG):  # pragma: no cover # Ignored due to log level
            self.adapter.debug('THREAD: [%s] initialized', type(self).__name__)
        self._state_change_queue = state_change_queue
        self.receiver_state_change_listener = receiver_state_change_listener
        self._running = False
        self._state_change_stop_event = state_change_stop_event
        self._can_listen_event = can_listen_event
        self._messaging_service_state = messaging_service.api.message_service_state

    def run(self):
        # Start running thread
        if logger.isEnabledFor(logging.DEBUG):  # pragma: no cover # Ignored due to log level
            self.adapter.debug('THREAD: [%s] started', type(self).__name__)
        while not self._state_change_stop_event.is_set():
            if self._messaging_service_state == _solace_session._MessagingServiceState.DOWN:
                # call the receiver's terminate method to ensure proper cleanup of thread
                self.adapter.warning(STATE_CHANGE_LISTENER_SERVICE_DOWN_EXIT_MESSAGE)
                break
            else:
                if not self._can_listen_event.is_set():
                    self._can_listen_event.wait()
                if self._state_change_queue.qsize() > 0:
                    old_state, new_state, time_stamp = self._state_change_queue.get()
                    try:
                        self.receiver_state_change_listener.on_change(old_state, new_state, time_stamp)
                    except Exception as exception \
                            :  # pylint: disable=broad-except  # pragma: no cover # Due to failure scenario
                        self.adapter.warning("%s %s", DISPATCH_FAILED, str(exception))
                else:
                    self._can_listen_event.clear()


class PersistentMessageReceiverThread(threading.Thread):  # pylint: disable=missing-class-docstring
    # Thread used to dispatch received messages on a receiver.
    def __init__(self, persistent_message_receiver,
                 message_pop_func, messaging_service, auto_ack,
                 *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._id_info = f"PersistentMessageReceiverThread Id: {str(hex(id(self)))}"
        self.adapter = _SolaceServiceAdapter(logger, {'id_info': self._id_info})
        if logger.isEnabledFor(logging.DEBUG):  # pragma: no cover # Ignored due to log level
            self.adapter.debug('THREAD: [%s] initialized', type(self).__name__)
        self._persistent_message_receiver = persistent_message_receiver
        self._message_handler = None  # update via property every time new message handler is provided
        # closure function to return an inbound message
        # function signature is parameterless
        self._message_pop = message_pop_func
        self._messaging_service = messaging_service
        self._auto_ack = auto_ack

    @property
    def message_handler(self):
        return self._message_handler

    @message_handler.setter
    def message_handler(self, message_handler):
        self._message_handler = message_handler

    def run(self):  # pylint: disable=too-many-branches
        # Start running thread
        if logger.isEnabledFor(logging.DEBUG):  # pragma: no cover # Ignored due to log level
            self.adapter.debug('THREAD: [%s] started', type(self).__name__)
        while not self._persistent_message_receiver.stop_event.is_set():
            if self._persistent_message_receiver.is_receiver_down:
                self.adapter.warning(RECEIVER_SERVICE_DOWN_EXIT_MESSAGE)
                if self._persistent_message_receiver.asked_to_terminate:
                    self._persistent_message_receiver.receiver_empty_event.set()  # wakeup main thread when \
                    # the service is down while terminating
                # stop the thread when service is down
                # call the receiver's terminate method to ensure proper cleanup of thread
                break
            else:
                if not self._persistent_message_receiver.can_receive_event.is_set() and \
                        not self._persistent_message_receiver.asked_to_terminate:
                    self._persistent_message_receiver.can_receive_event.wait()
                # don't attempt to retrieve message once buffer is declared as empty  at terminating
                # state( there is a chance we may keep receiving message callback which are in transit)
                if self._persistent_message_receiver.receiver_queue.qsize() > 0 and not \
                        self._persistent_message_receiver.receiver_empty_event.is_set():
                    inbound_message = self._message_pop()
                    if inbound_message:
                        try:
                            self._message_handler.on_message(inbound_message)
                            if self._auto_ack:  # if auto ack is enabled send ack to broker after sending  the message
                                self._persistent_message_receiver.ack(inbound_message)
                        except Exception as exception:  # pylint: disable=broad-except
                            self.adapter.warning("%s [%s] %s", DISPATCH_FAILED,
                                                 type(self._message_handler),
                                                 str(exception))
                elif not self._persistent_message_receiver.asked_to_terminate:
                    self._persistent_message_receiver.can_receive_event.clear()
                # wakeup main thread to proceed to call clean-up
                if self._persistent_message_receiver.receiver_queue.qsize() == 0 and \
                        self._persistent_message_receiver.asked_to_terminate and \
                        not self._persistent_message_receiver.receiver_empty_event.is_set():
                    self._persistent_message_receiver.receiver_empty_event.set()  # let the main \
                    # thread stop waiting in terminating state
        if logger.isEnabledFor(logging.DEBUG):  # pragma: no cover # Ignored due to log level
            self.adapter.debug('THREAD: [%s] stopped', type(self).__name__)


class _PersistentMessageReceiver(_MessageReceiver, PersistentMessageReceiver) \
        :  # pylint: disable=missing-class-docstring, too-many-ancestors, too-many-instance-attributes

    class SolClientFlowEventCallbackInfo(Structure):  # pylint: disable=too-few-public-methods
        # Conforms to solClient_flow_eventCallbackInfo_t
        _fields_ = [
            ("flow_event", c_int),
            ("response_code", c_int),
            ("info_p", c_char_p),
        ]

    class SolClientFlowCreateRxCallbackFuncInfo(Structure) \
            :  # pylint: disable=too-few-public-methods, missing-class-docstring
        # Conforms to solClient_flow_rxMsgDispatchFuncInfo_t

        _fields_ = [
            ("dispatch_type", ctypes.c_uint32),  # The type of dispatch described
            ("callback_p", CFUNCTYPE(c_int, c_void_p, c_void_p, py_object)),  # An application-defined callback
            # function; may be NULL if there is no callback.
            ("user_p", py_object),
            # A user pointer to return with the callback; must be NULL if callback_p is NULL.
            ("rffu", c_void_p)  # Reserved for Future use; must be NULL
        ]

    flow_msg_callback_func_type = CFUNCTYPE(c_int, c_void_p, c_void_p, py_object)
    solClient_flow_eventCallbackInfo_pt = POINTER(SolClientFlowEventCallbackInfo)

    _event_callback_func_type = CFUNCTYPE(c_int, c_void_p,
                                          solClient_flow_eventCallbackInfo_pt, py_object)
    _event_callback_func_routine = None
    _flow_msg_callback_func_routine = None
    _replay_error_list = [SolClientSubCode.SOLCLIENT_SUBCODE_REPLAY_NOT_SUPPORTED.name,
                          SolClientSubCode.SOLCLIENT_SUBCODE_REPLAY_DISABLED.name,
                          SolClientSubCode.SOLCLIENT_SUBCODE_CLIENT_INITIATED_REPLAY_NON_EXCLUSIVE_NOT_ALLOWED.name,
                          SolClientSubCode.SOLCLIENT_SUBCODE_CLIENT_INITIATED_REPLAY_INACTIVE_FLOW_NOT_ALLOWED.name,
                          SolClientSubCode.SOLCLIENT_SUBCODE_CLIENT_INITIATED_REPLAY_BROWSER_FLOW_NOT_ALLOWED.name,
                          SolClientSubCode.SOLCLIENT_SUBCODE_REPLAY_TEMPORARY_NOT_SUPPORTED.name,
                          SolClientSubCode.SOLCLIENT_SUBCODE_UNKNOWN_START_LOCATION_TYPE.name,
                          SolClientSubCode.SOLCLIENT_SUBCODE_REPLAY_MESSAGE_UNAVAILABLE.name,
                          SolClientSubCode.SOLCLIENT_SUBCODE_REPLAY_STARTED.name,
                          SolClientSubCode.SOLCLIENT_SUBCODE_REPLAY_CANCELLED.name,
                          SolClientSubCode.SOLCLIENT_SUBCODE_REPLAY_START_TIME_NOT_AVAILABLE.name,
                          SolClientSubCode.SOLCLIENT_SUBCODE_REPLAY_MESSAGE_REJECTED.name,
                          SolClientSubCode.SOLCLIENT_SUBCODE_REPLAY_LOG_MODIFIED.name,
                          SolClientSubCode.SOLCLIENT_SUBCODE_MISMATCHED_ENDPOINT_ERROR_ID.name,
                          SolClientSubCode.SOLCLIENT_SUBCODE_OUT_OF_REPLAY_RESOURCES.name,
                          SolClientSubCode.SOLCLIENT_SUBCODE_REPLAY_START_MESSAGE_UNAVAILABLE.name,
                          SolClientSubCode.SOLCLIENT_SUBCODE_MESSAGE_ID_NOT_COMPARABLE.name]

    def __init__(self, builder: '_PersistentMessageReceiverBuilder') \
            :  # pylint: disable=duplicate-code
        super().__init__(builder)
        self._flow_p = c_void_p(None)
        self._messaging_service = builder.messaging_service
        self._missing_resource_strategy = builder.missing_resources_creation_strategy
        self._replay_strategy = builder.replay_strategy
        self._is_durable = builder.endpoint_to_consume_from.is_durable()
        self._is_exclusive = builder.endpoint_to_consume_from.is_exclusively_accessible()
        self._queue_name = builder.endpoint_to_consume_from.get_name()
        self._auto_ack = builder.auto_ack
        # we can add topic subscription before starting the flow only for durable queue,
        # but for non durable queue we can add topic subscription only after starting the flow
        self._end_point_topics_dict = dict(
            (topic, False) for topic in builder.topics) if self._is_durable else dict()
        self._topic_dict = dict(
            (topic, False) for topic in builder.topics) if not self._is_durable else dict()

        self._end_point_props = end_point_props
        self._is_unsubscribed = False
        self._asked_to_terminate = None
        self._msg_wait_time = None
        self._can_receive_id = "can_receive_" + str(hex(id(self)))
        setattr(self._messaging_service.api, self._can_receive_id, self._can_receive_event)
        self._messaging_service.api.can_receive.append(self._can_receive_id)
        self._persistent_message_receiver_thread = None
        self._receiver_state_change_listener = builder.receiver_state_change_listener
        self._flow_state = list()  # to keep track of flow state when listener is provided
        self._running = False  # used for pause & resume when True application callbacks should be dispatching
        self._flow_stopped = False  # used for flow control to close the flow message window
        self._end_point_arr = None
        self._error_notification_dispatcher: TerminationNotificationDispatcher = \
            TerminationNotificationDispatcher()
        self._int_metrics = self._messaging_service.metrics()
        self._state_change_listener_queue = None
        if self._receiver_state_change_listener:
            self._state_change_listener_queue = Queue()
            self._state_change_can_listen_event = threading.Event()
            self._state_change_id = "state_change_" + str(hex(id(self)))
            setattr(self._messaging_service.api,
                    self._state_change_id, self._state_change_can_listen_event)
            self._messaging_service.api.state_change.append(self._state_change_id)
            self._state_change_stop_event = threading.Event()
            self._state_change_listener_thread = None
        else:
            self._state_change_listener_queue = None
        self._flow_msg_callback_func_routine = self.flow_msg_callback_func_type(
            self._flow_message_receive_callback_routine)
        self._message_receiver_state = _MessageReceiverState.NOT_STARTED
        self._config = dict()

        # add props received from builder
        for key, value in builder.config.items():
            if key in CCSMP_SESSION_PROP_MAPPING:
                # Note: Here order if elif to check bool & int is very important don't change them
                if isinstance(value, bool):
                    value = str(int(value))
                elif isinstance(value, int):
                    value = str(value)

                self._config[CCSMP_SESSION_PROP_MAPPING[key]] = value
        if not self._is_durable and self._queue_name is None:
            # don't add  SOLCLIENT_FLOW_PROP_BIND_NAME when we didn't receive queue name for non-durable exclusive queue
            pass
        else:
            self._config[SOLCLIENT_FLOW_PROP_BIND_NAME] = self._queue_name
        self._config[SOLCLIENT_FLOW_PROP_BIND_ENTITY_DURABLE] = str(int(self._is_durable))
        if builder.message_selector:  # Message selector applied here
            self._config[SOLCLIENT_FLOW_PROP_SELECTOR] = builder.message_selector
        self._event_callback_func_routine = self._event_callback_func_type(self._event_callback_routine)
        self._flow_msg_callback_func_routine = self.msg_callback_func_type(self._flow_message_receive_callback_routine)
        self.__add_replay_props()  # Add REPLAY property based on ReplayStrategy
        self._config = {**flow_props, **self._config}  # Merge & override happens here
        self._flow_arr = prepare_array(self._config)
        self._is_receiver_down = False  # when receiver goes down don't attempt to deliver the messages
        self._flow_clean_not_needed = False  # set to True when flow clean up is not needed.
        # clean-up the flow as part of gc
        self._finalizer = weakref.finalize(self, flow_cleanup, self._flow_p,
                                           self._messaging_service.api.session_pointer)

    def set_termination_notification_listener(self, listener: TerminationNotificationListener):
        if isinstance(listener, TerminationNotificationListener):
            self._error_notification_dispatcher.set_termination_notification_listener(listener)
        else:
            raise InvalidDataTypeError(f"Expected to receive instance of {TerminationNotificationListener}", )

    @property
    def is_receiver_down(self):
        return self._is_receiver_down

    def _start_state_listener(self):
        # This method will be used to start the receiver state change listener thread
        if self._receiver_state_change_listener:
            self._state_change_listener_thread = PersistentStateChangeListenerThread(
                self._state_change_listener_queue, self._receiver_state_change_listener,
                self._state_change_can_listen_event, self._state_change_stop_event, self._messaging_service)
            self._state_change_listener_thread.daemon = True
            self._state_change_listener_thread.start()

    def _flow_message_receive_callback_routine(self, _opaque_flow_p, msg_p, _user_p):  # pragma: no cover
        # The message callback will be invoked for each Persistent message received by the Session
        # only enqueue message while the receiver is live
        if self._message_receiver_state not in [_MessageReceiverState.STARTING,
                                                _MessageReceiverState.STARTED]:
            # Unfortunately its not possible to determine how many
            # in-flight messages remaining in the flow message window on shutdown.
            # Drop messages while terminating to prevent a race between
            # native layer message dispatch and draining the python
            # internal message queue for graceful terminate.
            return SOLCLIENT_CALLBACK_OK  # return the received message to native layer
        # python receiver is life enqueue native message to python delivery queue
        try:
            solace_message = _SolaceMessage(c_void_p(msg_p))
            rx_msg = _InboundMessage(solace_message)
            self._msg_queue_put(rx_msg)
            if self._running:
                # only signal message dispatch thread if python message dispatch is running
                self._can_receive_event.set()
            if logger.isEnabledFor(logging.DEBUG):  # pragma: no cover # Ignored due to log level
                self.adapter.debug('PUT message to %s buffer/queue', PersistentMessageReceiver.__name__)
        except Exception as exception:
            self.adapter.error("%s ", exception)
            raise PubSubPlusClientError(message=exception) from exception
        return SOLCLIENT_CALLBACK_TAKE_MSG  # we took the received message

    def _event_callback_routine(self, _opaque_flow_p, event_info_p, _user_p) \
            :  # pragma: no cover # Due to invocation in callbacks
        # Flow event callback from the C API.

        event = event_info_p.contents.flow_event

        if event in [_SolClientFlowEvent.SOLCLIENT_FLOW_EVENT_DOWN_ERROR.value]:

            self._flow_clean_not_needed = True
            self._is_receiver_down = True  # signals receiver thread stops from delivering messages

            response_code = event_info_p.contents.response_code

            error_info = last_error_info(response_code, "flow callback")

            # set the receiver state to Terminated when the flow event or session is down.
            with self._terminate_lock:
                self.__handle_receiver_down(error_info)
        #  pause the receiver thread when flow goes inactive this will also prevents
        #  the race between receive_async &
        #  receive_message when we put None to unblock receive_message
        if event == _SolClientFlowEvent.SOLCLIENT_FLOW_EVENT_INACTIVE.value:
            self.adapter.info(FLOW_INACTIVE)
            self._can_receive_event.clear()
        # resume the receiver thread
        elif event == _SolClientFlowEvent.SOLCLIENT_FLOW_EVENT_ACTIVE.value and \
                not self._can_receive_event.is_set():
            self._can_receive_event.set()
        self.__do_state_change_event(event)
        return SOLCLIENT_CALLBACK_OK

    def __handle_receiver_down(self, error_info):
        self.adapter.warning(FLOW_DOWN)
        if not self._asked_to_terminate:
            self._message_receiver_state = _MessageReceiverState.TERMINATED
            if self.is_running() is False and self.is_terminated() is True:
                # invoke the termination notification event dispatcher with the cause on a lifecycle thread
                # also metrics is updated & perform resource cleanup
                self._executor.submit(self._notify_metrics_and_cleanup, error_info)
        else:
            self._receiver_empty_event.set()  # unblock the terminate method if its called

    def __do_state_change_event(self, event):
        if self._state_change_listener_queue:
            events = {_SolClientFlowEvent.SOLCLIENT_FLOW_EVENT_ACTIVE.value:
                          (ReceiverState.PASSIVE, ReceiverState.ACTIVE),
                      _SolClientFlowEvent.SOLCLIENT_FLOW_EVENT_INACTIVE.value:
                          (ReceiverState.ACTIVE, ReceiverState.PASSIVE)}
            if event in events:
                old_state, new_state = events[event]
                self._state_change_can_listen_event.set()
                self._state_change_listener_queue.put((old_state, new_state, int(time.time() * 1000)))

    def _resource_cleanup(self):
        with self._terminate_lock:
            self._cleanup()

    def _create_end_point(self):
        # create only for durable Queue, non-durable(temporary) Queue will be created during flow creation automatically
        if self._missing_resource_strategy and \
                self._missing_resource_strategy.value == MissingResourcesCreationStrategy.CREATE_ON_START.value and \
                self._is_durable:

            self._end_point_props[SOLCLIENT_ENDPOINT_PROP_NAME] = self._queue_name  # set Queue name
            if not self._is_exclusive:
                self._end_point_props[SOLCLIENT_ENDPOINT_PROP_ACCESSTYPE] = \
                    SOLCLIENT_ENDPOINT_PROP_ACCESSTYPE_NONEXCLUSIVE

            self._end_point_arr = prepare_array(self._end_point_props)

            return_code = end_point_provision(self._end_point_arr,
                                              self._messaging_service.api.session_pointer)

            error_info = last_error_info(status_code=return_code, caller_desc="Endpoint Creation ")

            if return_code != SOLCLIENT_OK:
                if error_info['sub_code'] == SolClientSubCode.SOLCLIENT_SUBCODE_ENDPOINT_ALREADY_EXISTS:
                    self.adapter.info("%s already exists", self._queue_name)
                else:
                    self.adapter.warning("%s creation failed with the following sub code %s", self._queue_name,
                                         error_info['sub_code'])
                    raise PubSubPlusClientError(f"{self._queue_name}creation failed with the"
                                                f" following sub code{error_info['sub_code']} ")
            elif return_code == SOLCLIENT_OK:
                self.adapter.info("%s endpoint is created successfully", self._queue_name)

    def _msg_queue_put(self, message: 'InboundMessage'):
        self._message_receiver_queue.put(message)
        if self._message_receiver_queue.qsize() >= HIGH_THRESHOLD and not self._flow_stopped:
            # close c layer flow message window
            return_code = pause(self._flow_p)
            if return_code == SOLCLIENT_OK:
                # set c layer flow stopped state flag to stopped
                self._flow_stopped = True
                self.adapter.info("%s", FLOW_PAUSE)

    def _msg_queue_get(self, block: bool = True, timeout: float = None):
        if timeout is not None:
            if logger.isEnabledFor(logging.DEBUG):  # pragma: no cover # Ignored due to log level
                self.adapter.debug('Get message from queue/buffer with block: %s, timeout: %f', block, timeout)
        elif timeout is None and logger.isEnabledFor(logging.DEBUG):  # pragma: no cover # Ignored due to log level
            self.adapter.debug('Get message from queue/buffer with block: %s, timeout: %s', block, timeout)
        if timeout is None:  # used  in deciding whether to put None in queue or not when flow goes down
            self._messaging_service.api.receiver_queues.append(self._message_receiver_queue)  # used to unblock
        # when service goes down if we are waiting on blocking receive_message call
        msg = self._message_receiver_queue.get(block, timeout)

        # resume flow messaging, if enough messages are processed and receiver state is Started
        if self._message_receiver_queue.qsize() <= LOW_THRESHOLD and self._flow_stopped \
                and self._message_receiver_state == _MessageReceiverState.STARTED:
            return_code = resume(self._flow_p)  # open C layer flow message window
            if return_code == SOLCLIENT_OK:
                self._flow_stopped = False  # set C layer flow stopped state flag to started
                self.adapter.info("%s", FLOW_RESUME)
        return msg

    def _unsubscribe_from_topics(self, topic_dict: Dict):
        topics = [*copy.deepcopy(topic_dict)]
        # unsubscribe topics as part of teardown activity
        for topic in topics:
            try:
                self._do_unsubscribe(topic)
            except PubSubPlusClientError as exception:  # pragma: no cover # Due to core error scenarios
                self.adapter.warning(exception)

    def _cleanup(self):  # pylint: disable=duplicate-code
        # Method to stop the receiver thread and set the stop event and cleanup receiver resources

        self._asked_to_terminate = True  # flag to prevent  the thread to sleep while terminating
        self._message_receiver_state = _MessageReceiverState.TERMINATED
        if self._messaging_service.is_connected and not self._is_receiver_down:
            if self._topic_dict:  # cleanup topics added after flow started as well as topics added
                # after receiver started
                self._is_unsubscribed = True
                self._unsubscribe_from_topics(self._topic_dict)
            # cleanup topics added before flow started for durable queue
            if self._end_point_topics_dict:
                self._unsubscribe_from_topics(self._end_point_topics_dict)

        with self._start_async_lock:
            if self._start_future is None:
                self._start_future = COMPLETED_FUTURE
        with self._terminate_async_lock:
            if self._terminate_future is None:
                self._terminate_future = COMPLETED_FUTURE

        if self._persistent_message_receiver_thread is not None:
            # stop the receiver thread
            # set termination flag first
            self.stop_event.set()  # this stops the thread
            # then wake up receiver thread to end run function
            self._can_receive_event.set()  # this wake up the thread
            with _Released(self._terminate_lock):
                self._persistent_message_receiver_thread.join()

        # stop the state change listener thread
        if self._receiver_state_change_listener:
            self._state_change_can_listen_event.set()
            self._state_change_stop_event.set()
            with _Released(self._terminate_lock):
                self._state_change_listener_thread.join()

        self._executor.shutdown(wait=False)
        session_p = self._messaging_service.api.session_pointer \
            if self._messaging_service.api and self._messaging_service.api.session_pointer \
            else c_void_p(None)
        # # release c resources
        if not self._flow_clean_not_needed:
            with _Released(self._terminate_lock):
                flow_cleanup(self._flow_p, session_p)
            self._flow_clean_not_needed = False
        # shut down the termination event dispatcher thread
        with _Released(self._terminate_lock):
            if self._error_notification_dispatcher is not None:
                self._error_notification_dispatcher.shutdown()

    def __do_metrics(self):  # Incrementing the internal discarded received messages metrics after acquiring lock
        if self._message_receiver_queue is not None and self._message_receiver_queue.qsize() > 0:
            if self._message_receiver_queue.queue[-1] is not None:
                value = self._message_receiver_queue.qsize()
            else:
                value = self._message_receiver_queue.qsize() - 1  # we have None as last item so subtract 1 from qsize
            self._int_metrics._increment_internal_stat(Metric.RECEIVED_MESSAGES_TERMINATION_DISCARDED, value)

    def __do_start(self):  # pylint: disable=no-else-raise
        # Method to start
        class SolClientFlowCreateRxCallbackFuncInfo(Structure):  # pylint: disable=too-few-public-methods
            # Conforms to solClient_flow_createRxCallbackFuncInfo_t (deprecated)
            _fields_ = [
                ("callback_p", c_void_p),
                ("user_p", c_void_p)
            ]

        class SolClientFlowCreateEventCallbackFuncInfo(Structure):  # pylint: disable=too-few-public-methods
            # Conforms to solClient_flow_createEventCallbackFuncInfo_t
            _fields_ = [
                ("callback_p", self._event_callback_func_type),
                ("user_p", py_object)
            ]

        class SolClientFlowCreateRxMsgCallbackFuncInfo(Structure):  # pylint: disable=too-few-public-methods
            # Conforms to solClient_flow_createRxMsgCallbackFuncInfo_t
            _fields_ = [
                ("callback_p", _MessageReceiver.msg_callback_func_type),
                ("user_p", py_object)
            ]

        class SolClientFlowCreateFuncInfo(Structure):  # pylint: disable=too-few-public-methods
            # Conforms to solClient_flow_createFuncInfo_t
            _fields_ = [
                ("rx_info", SolClientFlowCreateRxCallbackFuncInfo),  # deprecated
                ("event_info", SolClientFlowCreateEventCallbackFuncInfo),
                ("rx_msg_info", SolClientFlowCreateRxMsgCallbackFuncInfo)
            ]

        flow_func_info = SolClientFlowCreateFuncInfo(
            (c_void_p(None), c_void_p(None)),
            (self._event_callback_func_routine, self),
            (self._flow_msg_callback_func_routine, self))
        # Creates a new Flow within a specified Session. Flow characteristics and behavior are
        # defined by Flow properties. The Flow properties
        #   are supplied as an array of name/value pointer pairs, where the name and value are both strings.
        #   \ref flowProps "FLOW" and \ref endpointProps "ENDPOINT" configuration property names are
        # processed; other property names
        #   are ignored. If the Flow creation specifies a non-durable endpoint, ENDPOINT properties can
        # be used to change the default
        #   properties on the non-durable endpoint. Any values not supplied are set to default values.
        #
        #   When the Flow is created, an opaque Flow pointer is returned to the caller, and this value
        # is then used for any
        #   Flow-level operations (for example, starting/stopping a Flow, getting statistics, sending
        # an acknowledgment).
        #   The passed-in structure functInfo_p provides information on the message receive callback
        #   function and the Flow event function which the application has provided for this Flow.
        #   Both of these callbacks are mandatory. The message receive callback is invoked for each
        #   received message on this Flow. The Flow event callback is invoked when Flow events
        #   occur, such as the Flow going up or down. Both callbacks are invoked in the context
        #   of the Context thread to which the controlling Session belongs.
        #
        #   Flow creation can be carried out in a blocking or
        #   non-blocking mode, depending upon the Flow property
        #   SOLCLIENT_FLOW_PROP_BIND_BLOCKING.
        #   In blocking mode, the calling thread is blocked until the Flow connection attempt either
        #   succeeds or is determined to have failed. If the connection succeeds, SOLCLIENT_OK is
        #   returned, and if the Flow could not be connected, SOLCLIENT_NOT_READY is returned.
        #   In non-blocking mode, SOLCLIENT_IN_PROGRESS is returned upon a successful Flow create
        #   request, and the connection attempt proceeds in the background.
        #   In both a non-blocking and blocking mode, a Flow event is generated for the Session:
        #   SOLCLIENT_FLOW_EVENT_UP_NOTICE, if the Flow was connected successfully; or
        #   SOLCLIENT_FLOW_EVENT_BIND_FAILED_ERROR, if the Flow failed to connect.
        #  For blocking mode, the Flow event is issued before the call to
        #  solClient_session_createFlow() returns. For non-blocking mode, the timing is undefined (that is,
        #  it could occur before or after the call returns, but it will typically be after).
        #  A Flow connection timer, controlled by the Flow property
        #  SOLCLIENT_SESSION_PROP_BIND_TIMEOUT_MS, controls the maximum amount of
        #  time a Flow connect attempt lasts for. Upon expiry of this time,
        #  a SOLCLIENT_FLOW_EVENT_BIND_FAILED_ERROR event is issued for the Session.
        #  If there is an error when solClient_session_createFlow() is invoked, then SOLCLIENT_FAIL
        #  is returned, and a Flow event is not subsequently issued. Thus, the caller must
        #  check for a return code of SOLCLIENT_FAIL if it has logic that depends upon a subsequent
        #  Flow event to be issued.
        #  For a non-blocking Flow create invocation, if the Flow create attempt eventually
        #  fails, the error information that indicates the reason for the failure cannot be
        #  determined by the calling thread. It must be discovered through the Flow event
        #  callback (and solClient_getLastErrorInfo can be called in the Flow event callback
        #  to get further information).
        #  For a blocking Flow create invocation, if the Flow create attempt does not
        #  return SOLCLIENT_OK, then the calling thread can determine the failure reason by immediately
        #  calling solClient_getLastErrorInfo. For a blocking Flow creation, SOLCLIENT_NOT_READY is returned
        #  if the created failed due to the bind timeout expiring (see SOLCLIENT_FLOW_PROP_BIND_TIMEOUT_MS).
        #  Note that the property values are stored internally in the API and the caller does not have to maintain
        #  the props array or the strings that are pointed to after this call completes. The API does not modify any of
        #  the strings pointed to by props when processing the property list.
        #
        #  If the flow property SOLCLIENT_FLOW_PROP_BIND_ENTITY_ID is set to SOLCLIENT_FLOW_PROP_BIND_ENTITY_TE,
        #  the flow Topic property SOLCLIENT_FLOW_PROP_TOPIC <b>must</b> be set, which will replace any existing
        #  topic on the topic-endpoint.
        #
        #  <b>WARNING:</b> By default the SOLCLIENT_FLOW_PROP_ACKMODE is set to SOLCLIENT_FLOW_PROP_ACKMODE_AUTO,
        #  which automatically acknowledges all received messages.
        # Function SolClient_flow_sendAck returns SOLCLIENT_OK
        #  in the mode SOLCLIENT_FLOW_PROP_ACKMODE_AUTO, but with a warning that solClient_flow_sendAck
        #  is ignored as flow is in auto-ack mode.
        # return SOLCLIENT_OK, SOLCLIENT_FAIL, SOLCLIENT_NOT_READY, SOLCLIENT_IN_PROGRESS
        return_code = solace.CORE_LIB.solClient_session_createFlow(cast(self._flow_arr, POINTER(c_char_p)),
                                                                   self._messaging_service.api.session_pointer,
                                                                   byref(self._flow_p),
                                                                   byref(flow_func_info),

                                                                   sizeof(flow_func_info))
        if return_code != SOLCLIENT_OK:  # pylint: disable=no-else-raise
            error_info = last_error_info(status_code=return_code, caller_desc="flow topic add sub ")
            self.adapter.warning("Flow creation failed for Queue[%s] with sub code [%s]",
                                 self._queue_name, error_info['sub_code'])
            if error_info['sub_code'] in _PersistentMessageReceiver._replay_error_list:
                raise MessageReplayError(error_info, error_info['error_info_sub_code'])
            else:
                raise PubSubPlusClientError(error_info, error_info['error_info_sub_code'])
        else:
            self._message_receiver_state = _MessageReceiverState.STARTED
            self._flow_stopped = False

    def _do_subscribe(self, topic_subscription):
        # Method to subscribe
        if self._flow_p.value is None:
            self.adapter.warning("%s", "Flow Pointer is NULL")
            return
        dispatch_info = _PersistentMessageReceiver.SolClientFlowCreateRxCallbackFuncInfo(
            ctypes.c_uint32(SOLCLIENT_DISPATCH_TYPE_CALLBACK), self._flow_msg_callback_func_routine,
            py_object(self), c_void_p(None))
        return_code = flow_topic_subscribe_with_dispatch(self._flow_p, topic_subscription, dispatch_info)
        if return_code == SOLCLIENT_OK:
            self._topic_dict[topic_subscription] = True
        else:
            last_error = last_error_info(return_code, f"{type(self).__name__}->_do_subscribe")
            self.adapter.warning('%s %s. Status code: %d. %s',
                                 UNABLE_TO_SUBSCRIBE_TO_TOPIC, topic_subscription,
                                 return_code, last_error)  # pragma: no cover # Ignored due to core error scenarios
            raise PubSubPlusClientError(message=f'{UNABLE_TO_SUBSCRIBE_TO_TOPIC} {topic_subscription}. '
                                                f'Status code: {return_code}. {last_error}')  # pragma: no cover
            # Ignored due to core error scenarios

    def _do_unsubscribe(self, topic_subscription):
        # Method to unsubscribe
        if self._flow_p.value is None:
            self.adapter.warning("%s", "Flow Pointer is NULL")
            return
        dispatch_info = _PersistentMessageReceiver. \
            SolClientFlowCreateRxCallbackFuncInfo(ctypes.c_uint32(SOLCLIENT_DISPATCH_TYPE_CALLBACK),
                                                  self._flow_msg_callback_func_routine, py_object(self), c_void_p(None))

        return_code = flow_topic_unsubscribe_with_dispatch(self._flow_p, topic_subscription, dispatch_info)
        if return_code == SOLCLIENT_OK:
            if logger.isEnabledFor(logging.DEBUG):  # pragma: no cover # Ignored due to log level
                self.adapter.debug('Unsubscribed [%s]', topic_subscription)
            if topic_subscription in self._topic_dict:
                del self._topic_dict[topic_subscription]
        else:
            last_error = last_error_info(return_code, f"{type(self).__name__}->_do_unsubscribe")
            self.adapter.warning('%s %s. Status code: %d. %s',
                                 UNABLE_TO_UNSUBSCRIBE_TO_TOPIC, topic_subscription,
                                 return_code, last_error)  # pragma: no cover # Ignored due to core error scenarios
            raise PubSubPlusClientError(message=f'{UNABLE_TO_UNSUBSCRIBE_TO_TOPIC} {topic_subscription}. '
                                                f'Status code: {return_code}. {last_error}')  # pragma: no cover
            # Ignored due to core error scenarios

    def __is_receiver_started(self) -> bool:
        # Method to validate receiver is properly started or not
        _, self._message_receiver_state = \
            is_message_service_connected(receiver_state=self._message_receiver_state,
                                         message_service=self._messaging_service,
                                         logger=logger)
        if self._message_receiver_state == _MessageReceiverState.NOT_STARTED or \
                self._message_receiver_state == _MessageReceiverState.STARTING:
            raise IllegalStateError(UNABLE_TO_RECEIVE_MESSAGE_RECEIVER_NOT_STARTED)
        elif self._message_receiver_state == _MessageReceiverState.TERMINATING or \
                self._message_receiver_state == _MessageReceiverState.TERMINATED:
            raise IllegalStateError(RECEIVER_TERMINATED)
        elif self._message_receiver_state != _MessageReceiverState.STARTED:
            raise IllegalStateError(UNABLE_TO_RECEIVE_MESSAGE_RECEIVER_NOT_STARTED)
        if logger.isEnabledFor(logging.DEBUG):  # pragma: no cover # Due to core error scenarios
            self.adapter.debug('[%s] %s', PersistentMessageReceiver.__name__, _MessageReceiverState.STARTED.name)
        return True

    def _stop_flow(self):
        # Shutdown all c api message dispatching
        if not self._flow_stopped and self._messaging_service.api.session_pointer and self._flow_p:
            # pause the flow of inbound messages only if its not done already
            # close the c layer flow message window to stop receiver new messages for dispatch
            with _Released(self._terminate_lock):
                return_code = pause(self._flow_p)
            # confirm success
            if return_code != SOLCLIENT_OK:
                exception: PubSubPlusCoreClientError = \
                    get_last_error_info(return_code=return_code,
                                        caller_description='_PersistentMessageReceiver->_stop_flow')
                self.adapter.warning(str(exception))
                raise exception
            else:
                # update c layer flow start stop state flag
                self._flow_stopped = True

    # for non durable queue this should be called after start method if queue name
    # wasn't given while building the receiver
    def receiver_info(self) -> _PersistentReceiverInfo:
        return _PersistentReceiverInfo(self._is_durable, self._queue_name)

    def __add_replay_props(self):
        if isinstance(self._replay_strategy, AllMessagesReplay):
            self._config = {**replay_prop, **self._config}
        elif isinstance(self._replay_strategy, TimeBasedReplay):

            # the input datetime object is converted to utc and then to epoch value here
            replay_date_epoch = self._replay_strategy.get_replay_date().astimezone(datetime.timezone.utc).timestamp()

            replay_date_epoch_with_prefix = f'DATE:{int(replay_date_epoch)}'

            self._config[SOLCLIENT_FLOW_PROP_REPLAY_START_LOCATION] = replay_date_epoch_with_prefix
        elif isinstance(self._replay_strategy, ReplicationGroupMessageIdReplay):
            self._replay_strategy: ReplicationGroupMessageIdReplay
            self._config[SOLCLIENT_FLOW_PROP_REPLAY_START_LOCATION] = \
                str(self._replay_strategy.replication_group_message_id)

    @property
    def flow_p(self):
        # Property which holds and returns the flow pointer
        return self._flow_p

    def start(self) -> 'PersistentMessageReceiver':
        # return self if we already started the receiver
        if self._message_receiver_state == _MessageReceiverState.STARTED:
            return self

        with self._start_lock:
            self._is_receiver_terminated(error_message=RECEIVER_TERMINATED_UNABLE_TO_START)
            # Even after acquiring lock still we have to check the state to avoid re-doing the work
            if self._message_receiver_state == _MessageReceiverState.STARTED:
                return self

            if self._message_receiver_state == _MessageReceiverState.NOT_STARTED:
                self._message_receiver_state = _MessageReceiverState.STARTING
                _, self._message_receiver_state = \
                    is_message_service_connected(receiver_state=self._message_receiver_state,
                                                 message_service=self._messaging_service,
                                                 logger=logger)
                self._create_end_point()
                if self._end_point_arr is None and self._is_durable:  # need to prepare array
                    # for durable queue to add topic subscription
                    self._end_point_props[SOLCLIENT_ENDPOINT_PROP_NAME] = self._queue_name  # set Queue name
                    self._end_point_arr = prepare_array(self._end_point_props)

                for topic, _ in self._end_point_topics_dict.items():  # add end point topic for durable queue
                    # before starting the flow
                    self.__endpoint_topic_subscribe(topic)
                self._start_state_listener()
                self.__do_start()  # flow start
                # we cant add topic subscriptions for non durable queue before starting the flow
                for topic, _ in self._topic_dict.items():
                    self.add_subscription(TopicSubscription.of(topic))
                self._message_receiver_state = _MessageReceiverState.STARTED
                self._running = True
                self.__get_queue_name()
                return self

    def __get_queue_name(self):
        if not self._is_durable and self._queue_name is None:  # attempt to get  the queue name only
            # for non durable queue when queue name is empty
            try:
                destination = _SolClientDestination()
                return_code = flow_destination(self._flow_p, destination)
                if return_code == SOLCLIENT_OK:
                    self._queue_name = destination.dest.decode()
                elif return_code == SOLCLIENT_FAIL:  # pragma: no cover
                    self.adapter.warning(last_error_info((return_code, "flow destination")))
            except Exception as error:  # TODO: broad-except validate if it should be too generic
                self.adapter.warning(str(error))

    def __endpoint_topic_subscribe(self, topic):
        return_code = topic_endpoint_subscribe(self._end_point_arr, self._messaging_service.api.session_pointer, topic)
        if return_code != SOLCLIENT_OK:
            last_error = last_error_info(return_code, "_PersistentMessageReceiver->__endpoint_topic_subscribe")
            self.adapter.warning(last_error)
            raise PubSubPlusClientError(last_error)
        self._end_point_topics_dict[topic] = True

    def __endpoint_topic_unsubscribe(self, topic):
        return_code = topic_endpoint_unsubscribe(self._end_point_arr, self._messaging_service.api.session_pointer,
                                                 topic)
        if return_code != SOLCLIENT_OK:
            last_error = last_error_info(return_code, "_PersistentMessageReceiver->__endpoint_topic_unsubscribe")
            self.adapter.warning(last_error)
            raise PubSubPlusClientError(last_error)
        del self._end_point_topics_dict[topic]

    def pause(self):
        # Pause message delivery to an asynchronous message handler or stream
        if self.__is_receiver_started():
            self._running = False
            self._can_receive_event.clear()

    def resume(self):
        # Resumes previously paused message delivery
        if self.__is_receiver_started():
            self._running = True
            self._can_receive_event.set()

    def add_subscription(self, another_subscription: TopicSubscription):
        # Method to add the topic subscription
        validate_subscription_type(subscription=another_subscription, logger=logger)
        self._can_add_subscription()
        self._do_subscribe(another_subscription.get_name())

    def add_subscription_async(self, topic_subscription: TopicSubscription) -> concurrent.futures.Future:
        # method to add the subscription asynchronously
        return self._executor.submit(self.add_subscription, topic_subscription)

    def remove_subscription(self, subscription: TopicSubscription):
        # Method to remove topic subscriptions
        validate_subscription_type(subscription)
        self._can_remove_subscription()
        self._do_unsubscribe(subscription.get_name()) if subscription.get_name() in self._topic_dict else \
            self.__endpoint_topic_unsubscribe(subscription.get_name())

    def remove_subscription_async(self, topic_subscription: TopicSubscription) -> concurrent.futures.Future:
        # """method to remove the subscription asynchronously"""
        return self._executor.submit(self.remove_subscription, topic_subscription)

    def _emit_notify_event(self, error_info) -> concurrent.futures.Future:
        if error_info['sub_code'] in _PersistentMessageReceiver._replay_error_list:
            error_type = MessageReplayError
        else:
            error_type = PubSubPlusClientError
        return self._error_notification_dispatcher.on_exception(
            error_type(error_info,
                       error_info['error_info_sub_code']),
            int(time.time() * 1000))

    def _notify_metrics_and_cleanup(self, error_info):
        self._emit_notify_event(error_info)
        # Acquire a metrics lock to update the message discard count variable and then reset Queue
        self.__do_metrics()
        self._message_receiver_queue = _PubSubPlusQueue()  # reset queue
        # invoke the clean up process on a different lifecycle thread
        self._resource_cleanup()

    def receive_async(self, message_handler: 'MessageHandler'):
        # Receives the messages asynchronously
        is_type_matches(message_handler, MessageHandler, logger=logger)
        self._can_receive_message()

        def _receiver_thread_msg_queue_pop():
            if logger.isEnabledFor(logging.DEBUG):  # pragma: no cover # Ignored due to log level
                self.adapter.debug('Receiver [%s]: dispatching message, for endpoint [%s]', type(self).__name__,
                                   self._queue_name)
            return self._msg_queue_get()

        with self._receive_lock:
            if self._persistent_message_receiver_thread is None:
                self._persistent_message_receiver_thread = \
                    PersistentMessageReceiverThread(self, _receiver_thread_msg_queue_pop,
                                                    self._messaging_service, self._auto_ack)
                self._persistent_message_receiver_thread.message_handler = message_handler
                self._persistent_message_receiver_thread.daemon = True
                self._persistent_message_receiver_thread.start()
            else:  # just update the thread's message handler
                self._persistent_message_receiver_thread.message_handler = message_handler

    def receive_message(self, timeout: int = None) -> Union[InboundMessage, None]:
        # Get a message, blocking for the time passed in timeout,
        # None will be returned  as part of clean-up process after terminate method is called to
        # prevent infinite blocking when the api is waiting for a new message
        self._can_receive_message()
        if timeout is not None:
            is_not_negative(timeout, logger=logger)
        try:
            message = self._msg_queue_get(block=True,
                                          timeout=convert_ms_to_seconds(timeout) if timeout is not None else None)
            if self._auto_ack and message is not None:
                self.ack(message)
            self._check_buffer()
            self._wakeup_terminate()
            return message
        except queue.Empty:  # when timeout arg is given just return None on timeout
            return
        except (PubSubPlusClientError, KeyboardInterrupt) as exception:
            logger.warning(str(exception))
            raise exception

    def ack(self, message: 'InboundMessage'):
        # Method to ack the message
        is_type_matches(message, InboundMessage, logger=logger)
        if message is not None:  # None may be received on receive_message time out
            if self._message_receiver_state in [_MessageReceiverState.STARTED, _MessageReceiverState.TERMINATING]:
                return_code = acknowledge_message(self._flow_p, message.message_id)
                if return_code != SOLCLIENT_OK:
                    exception: PubSubPlusCoreClientError = \
                        get_last_error_info(return_code=return_code,
                                            caller_description='PersistentMessageReceiver->ack')
                    self.adapter.warning(str(exception))
                    raise exception
            else:
                exception_message = f"{UNABLE_TO_ACK}: {self._message_receiver_state}"
                self.adapter.warning(exception_message)
                raise IllegalStateError(exception_message)

    def _halt_messaging(self):
        self._stop_flow()

    def _check_undelivered_messages(self):
        self.__do_metrics()
        super()._check_undelivered_messages()


class ScheduledFailureNotification:  # pylint: disable=missing-class-docstring, missing-function-docstring
    # Class contains methods for scheduling an failure notification
    def __init__(self, dispatcher, exception: Exception, time_stamp: int):
        self._dispatcher = dispatcher
        self._exception = exception
        self._time_stamp = time_stamp

    def call(self) -> None:
        # This method schedules the notification by calling the on_termination()
        listener: 'TerminationNotificationListener' = self._dispatcher.termination_notification_listener
        if listener is None:
            # the listener was removed/un-set , skip
            return
        listener.on_termination(TerminationNotificationEvent(self.map_exception(self._exception),
                                                             self._time_stamp))

    @staticmethod
    def map_exception(exception: Exception) -> PubSubPlusClientError:
        # This method returns the exception map
        if isinstance(exception, PubSubPlusClientError):
            return exception
        return PubSubPlusClientError(exception)


class TerminationNotificationDispatcher:  # pylint: disable=missing-class-docstring, missing-function-docstring
    # Dispatcher class for notifying the receive failures

    def __init__(self):
        self._termination_notification_listener: 'TerminationNotificationListener' = None
        self._failure_notification_executor_service = None

    @property
    def termination_notification_listener(self):
        return self._termination_notification_listener

    def shutdown(self):
        if self._failure_notification_executor_service:
            self._failure_notification_executor_service.shutdown(wait=True)

    def on_termination(self, pending_receive_queue, error: PubSubPlusClientError, time_stamp: int):
        # get listener
        listener: 'TerminationNotificationListener' = self._termination_notification_listener
        # only dispatch failures there is a listener, an error and a pending queue
        if listener is None or error is None or pending_receive_queue is None:
            return
        # submit event to executor
        # receiver down error typically occur from the native api thread
        try:
            return self._failure_notification_executor_service.submit(self.on_exception, error, time_stamp)
        except Exception as exception:  # pragma: no cover # Due to failure scenario
            logger.exception(exception)

    def on_exception(self, exception_occurred: Exception, time_stamp: int = None):
        # Method to invoke the listener thread when receive mechanism fails
        #
        # Args:
        #     exception_occurred: occurred exception message
        #     time_stamp: current time stamp in Epoch milliseconds.
        if time_stamp is None:
            time_stamp = int(time.time() * 1000)
        listener: 'TerminationNotificationListener' = self._termination_notification_listener
        if listener is None or exception_occurred is None:
            return
        notification: 'ScheduledFailureNotification' = ScheduledFailureNotification(self, exception_occurred,
                                                                                    time_stamp)
        try:
            self._failure_notification_executor_service.submit(notification.call)
        except PubSubPlusClientError as exception:  # pragma: no cover # Due to failure scenario
            logger.exception(exception)
            # if the thread fails to call the notification.call() we explicitly call it to
            # run on same thread when scheduler is full
            try:
                notification.call()
            except PubSubPlusClientError as exception:
                logger.exception(exception)

    def set_termination_notification_listener(self,
                                              termination_notification_listener:
                                              'TerminationNotificationListener') -> None:
        # Method for setting the TerminationNotificationListener
        #
        # Args:
        #     receive_failure_listener: is of type TerminationNotificationListener

        # lazy init of executor
        if self._failure_notification_executor_service is None and \
                termination_notification_listener is not None:
            self._failure_notification_executor_service = \
                _ThreadingUtil.create_serialized_executor('TerminationEventNotifier')
        self._termination_notification_listener = termination_notification_listener

    @property
    def failure_notification_executor_service(self):
        return self._failure_notification_executor_service


class TerminationNotificationEvent(TerminationEvent):
    """Encapsulates details of a failed attempt to receive, used for failure notification processing
    such as timestamp, exception"""

    def __init__(self, exception: PubSubPlusClientError, timestamp: Union[float, None]):
        self._exception = exception
        self._timestamp = timestamp if timestamp is not None else datetime.datetime.now().microsecond

    @property
    def timestamp(self):
        """Retrieves the timestamp of the event, number of milliseconds from the epoch of 1970-01-01T00:00:00Z

        Returns:
            long value of the timestamp
        """
        return self._timestamp

    @property
    def cause(self):
        """Retrieves exception associated with a given event

        Returns:
            exception for the event
        """
        return self._exception

    @property
    def message(self):
        return f"{type(self).__name__}  timestamp: {self._timestamp}  cause : {self._exception}"
