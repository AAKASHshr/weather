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

"""Module contains the implementation cass and methods for the DirectMessageReceiver"""
# pylint: disable=too-many-ancestors, too-many-instance-attributes, missing-class-docstring, missing-function-docstring
# pylint: disable=no-else-break,no-else-return,inconsistent-return-statements,protected-access

import concurrent
import logging
import queue
import threading
from typing import Union

from solace.messaging import _SolaceServiceAdapter
from solace.messaging.builder._impl._message_receiver_builder import DirectMessageReceiverBackPressure
from solace.messaging.config._solace_message_constants import DISPATCH_FAILED, RECEIVER_SERVICE_DOWN_EXIT_MESSAGE, \
    RECEIVE_MESSAGE_FROM_BUFFER
from solace.messaging.core import _solace_session
from solace.messaging.errors.pubsubplus_client_error import PubSubPlusClientError
from solace.messaging.receiver._impl._message_receiver import _MessageReceiverState, \
    _DirectRequestReceiver
from solace.messaging.receiver._impl._receiver_utilities import validate_subscription_type
from solace.messaging.receiver.direct_message_receiver import DirectMessageReceiver
from solace.messaging.receiver.inbound_message import InboundMessage
from solace.messaging.receiver.message_receiver import MessageHandler
from solace.messaging.resources.topic_subscription import TopicSubscription
from solace.messaging.utils._solace_utilities import is_not_negative, convert_ms_to_seconds, is_type_matches, \
    COMPLETED_FUTURE, _PubSubPlusQueue
from solace.messaging.utils.manageable import Metric

logger = logging.getLogger('solace.messaging.receiver')


class _DirectMessageReceiverThread(threading.Thread):  # pylint: disable=missing-class-docstring
    # Thread used to dispatch received messages on a receiver.

    def __init__(self, direct_message_receiver, messaging_service, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._id_info = f"_DirectMessageReceiverThread Id: {str(hex(id(self)))}"
        self.adapter = _SolaceServiceAdapter(logger, {'id_info': self._id_info})
        if logger.isEnabledFor(logging.DEBUG):  # pragma: no cover # Ignored due to log level
            self.adapter.debug('THREAD: [%s] initialized', type(self).__name__)
        self._message_receiver = direct_message_receiver
        self._message_receiver_queue = self._message_receiver.receiver_queue
        self._message_handler = None
        self._stop_event = self._message_receiver.stop_event  # we receive this from direct message impl class
        self._can_receive_event = self._message_receiver.can_receive_event
        self._receiver_empty_event = self._message_receiver.receiver_empty_event
        self._messaging_service = messaging_service

    @property
    def message_handler(self):
        return self._message_handler

    @message_handler.setter
    def message_handler(self, message_handler):
        self._message_handler = message_handler

    def run(self):  # pylint: disable=missing-function-docstring
        # Start running thread
        if logger.isEnabledFor(logging.DEBUG):  # pragma: no cover # Ignored due to log level
            self.adapter.debug('THREAD: [%s] started', type(self).__name__)
        while not self._message_receiver.stop_event.is_set():
            # stop the thread only when the internal buffer is empty to ensure the delivery of all messages
            # when service is down
            if self._messaging_service.api.message_service_state == _solace_session._MessagingServiceState.DOWN and \
                    self._message_receiver_queue.qsize() == 0:
                # call the receiver's terminate method to ensure proper cleanup of thread
                self.adapter.warning("%s", RECEIVER_SERVICE_DOWN_EXIT_MESSAGE)
                if self._message_receiver.asked_to_terminate:
                    self._message_receiver.receiver_empty_event.set()  # wakeup main thread when the service is down
                break
            else:
                if not self._message_receiver.can_receive_event.is_set() and \
                        not self._message_receiver.asked_to_terminate:
                    self._message_receiver.can_receive_event.wait()
                # don't attempt to retrieve message once buffer is declared as empty  at terminating
                # state( there is a chance we may keep receiving message callback which are in transit)
                if self._message_receiver_queue.qsize() > 0 and not \
                        self._message_receiver.receiver_empty_event.is_set():
                    inbound_message = self._message_receiver_queue.get()
                    if inbound_message:
                        if inbound_message.get_message_discard_notification().has_internal_discard_indication():
                            # Since we are always dealing with one message at a time, 
                            # and the discard indication is a boolean, we only need to 
                            # increment by one each time, so we can hardcode it here
                            self._message_receiver._int_metrics._increment_internal_stat(Metric.INTERNAL_DISCARD_NOTIFICATIONS, 1)
                        try:
                            self._message_handler.on_message(inbound_message)
                        except Exception as exception:  # pylint: disable=broad-except
                            self.adapter.warning("%s %s", DISPATCH_FAILED, str(exception))

                # don't block the thread at terminating state
                elif not self._message_receiver.asked_to_terminate:
                    self._message_receiver.can_receive_event.clear()

                if self._message_receiver_queue.qsize() == 0 and \
                        self._message_receiver.asked_to_terminate and \
                        not self._message_receiver.receiver_empty_event.is_set():
                    # let the main thread stop waiting in terminating state
                    self._message_receiver.receiver_empty_event.set()


class _DirectMessageReceiver(_DirectRequestReceiver, DirectMessageReceiver):
    # class for direct message receiver, it is the base class used to receive direct messages

    def __init__(self, builder: 'DirectMessageReceiverBuilder'):  # pylint: disable=duplicate-code
        super().__init__(builder)
        if logger.isEnabledFor(logging.DEBUG):  # pragma: no cover # Ignored due to log level
            self.adapter.debug('[%s] initialized', type(self).__name__)
        self._running = False

        self._message_handler = None
        self._can_receive_event = threading.Event()
        self._can_receive_id = "can_receive_" + str(hex(id(self)))
        setattr(self._messaging_service.api,
                self._can_receive_id, self._can_receive_event)
        self._messaging_service.api.can_receive.append(self._can_receive_id)
        self._direct_message_receiver_thread = None
        self._int_metrics = self._messaging_service.metrics()
        key = "subscriptions"
        if key in builder.topic_dict:
            subscription = builder.topic_dict[key]
            if isinstance(subscription, str):
                self._topic_dict[subscription] = False  # not applied
            else:
                for topic in subscription:
                    self._topic_dict[topic] = False  # not applied
        key = "group_name"
        if key in builder.topic_dict:
            self._group_name = builder.topic_dict[key]
        self._message_receiver_state = _MessageReceiverState.NOT_STARTED
        self.__init_back_pressure(builder)

    def __init_back_pressure(self, builder: 'DirectMessageReceiverBuilder'):
        # This method presumes that the buffer type and capacity have previously been validated.
        if builder.receiver_back_pressure_type != DirectMessageReceiverBackPressure.Elastic:
            if builder.receiver_back_pressure_type == DirectMessageReceiverBackPressure.DropOldest:
                self._force = True
                self._block = True
                self._message_receiver_queue = _PubSubPlusQueue(maxsize=builder._buffer_capacity)
                
            elif builder.receiver_back_pressure_type == DirectMessageReceiverBackPressure.DropLatest:
                self._force = False
                self._block = False
                self._message_receiver_queue = _PubSubPlusQueue(maxsize=builder._buffer_capacity)

            def on_buffer_overflow(discarded):
                if discarded and isinstance(discarded, InboundMessage):
                    peeked_message = self._message_receiver_queue.unsafe_peek()
                    if peeked_message:
                        peeked_message.get_message_discard_notification().set_internal_discard_indication()
                    # We do this for every message that is received if the queue is full, so we only need to 
                    # increment the metric by one each time. Since we increment by the same amount every time,
                    # we can hardcode it
                    self._int_metrics._increment_internal_stat(Metric.RECEIVED_MESSAGES_BACKPRESSURE_DISCARDED, 1)

            self._message_receiver_queue.register_on_event(_PubSubPlusQueue.ON_BUFFER_OVERFLOW_EVENT, on_buffer_overflow)
        else:
            # elastic case
            self._message_receiver_queue = _PubSubPlusQueue()

    def _cleanup(self):
        self._asked_to_terminate = True  # flag to prevent  the thread to sleep while terminating
        self._message_receiver_state = _MessageReceiverState.TERMINATED
        if self._direct_message_receiver_thread is not None:
            # set thread termination flag before waking delivery thread
            # to ensure clean exit from python message delivery thread
            self.stop_event.set()

            self._can_receive_event.set()  # don't block the thread while terminating
            # wake message delivery thread
            # join on python message delivery thread
            self._direct_message_receiver_thread.join()
            #  set start and terminate futures
        with self._start_async_lock:
            if self._start_future is None:
                self._start_future = COMPLETED_FUTURE
        with self._terminate_async_lock:
            if self._terminate_future is None:
                self._terminate_future = COMPLETED_FUTURE
        # shutdown async executor non blocking
        self._executor.shutdown(wait=False)


    def add_subscription(self, another_subscription: TopicSubscription):
        # Subscribe to a topic synchronously (blocking). """
        validate_subscription_type(subscription=another_subscription, logger=logger)
        self._can_add_subscription()
        self._do_subscribe(another_subscription.get_name())

    def add_subscription_async(self, topic_subscription: TopicSubscription) -> concurrent.futures.Future:
        # method to add the subscription asynchronously
        return self._executor.submit(self.add_subscription, topic_subscription)

    def receive_message(self, timeout: int = None) -> Union[InboundMessage, None]:
        # Get a message, blocking for the time configured in the receiver builder.
        # may return None when the flow goes api is called after TERMINATING state & internal buffer is empty
        # as well as when service goes down """
        self._can_receive_message()
        if timeout is not None:
            is_not_negative(input_value=timeout, logger=logger)

        if logger.isEnabledFor(logging.DEBUG):  # pragma: no cover # Ignored due to log level
            self.adapter.debug("%s", RECEIVE_MESSAGE_FROM_BUFFER)
        if timeout is None:  # used in deciding whether to put None in queue or not when service goes down
            self._messaging_service.api.receiver_queues.append(self._message_receiver_queue)  # used to unblock
        try:
            message = self._message_receiver_queue.get(block=True,
                                                       timeout=convert_ms_to_seconds(
                                                           timeout) if timeout is not None else None)
            # This first condition checks to make sure the message is not None
            if message and message.get_message_discard_notification().has_internal_discard_indication():
                # Since we are always dealing with one message at a time, and the discard indication is a boolean,
                # we only need to increment by one each time, so we can hardcode it here
                self._int_metrics._increment_internal_stat(Metric.INTERNAL_DISCARD_NOTIFICATIONS, 1)

            self._check_buffer()
            self._wakeup_terminate()
            return message
        except queue.Empty:  # when timeout arg is given just return None on timeout
            return
        except (PubSubPlusClientError, KeyboardInterrupt) as exception:
            logger.warning(str(exception))
            raise exception

    def receive_async(self, message_handler: MessageHandler):
        # Specify the asynchronous message handler.
        is_type_matches(actual=message_handler, expected_type=MessageHandler, logger=logger)
        with self._receive_lock:
            self._can_receive_message()
            if self._direct_message_receiver_thread is None:
                self._direct_message_receiver_thread = _DirectMessageReceiverThread(self, self._messaging_service)
                self._direct_message_receiver_thread.message_handler = message_handler
                self._direct_message_receiver_thread.daemon = True
                self._direct_message_receiver_thread.start()
            else:  # just update the thread's message handler
                self._direct_message_receiver_thread.message_handler = message_handler

    def remove_subscription(self, subscription: TopicSubscription):
        # Unsubscribe from a topic synchronously (blocking).
        validate_subscription_type(subscription=subscription, logger=logger)
        self._can_remove_subscription()
        self._do_unsubscribe(subscription.get_name())

    def remove_subscription_async(self, topic_subscription: TopicSubscription) -> concurrent.futures.Future:
        # method to remove the subscription asynchronously
        validate_subscription_type(topic_subscription)
        return self._executor.submit(self.remove_subscription, topic_subscription)

    def _halt_messaging(self):
        self._unsubscribe()
