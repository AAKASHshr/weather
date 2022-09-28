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

"""Module contains the implementation class and methods for the PersistentMessageReceiverBuilder"""
# pylint: disable=missing-function-docstring,inconsistent-return-statements,no-else-return

import logging

from solace.messaging.builder._impl._message_receiver_builder import _MessageReceiverBuilder
from solace.messaging.builder.persistent_message_receiver_builder import PersistentMessageReceiverBuilder
from solace.messaging.config.missing_resources_creation_configuration import MissingResourcesCreationStrategy
from solace.messaging.config.receiver_activation_passivation_configuration import ReceiverStateChangeListener
from solace.messaging.config.replay_strategy import ReplayStrategy, AllMessagesReplay, TimeBasedReplay, \
    ReplicationGroupMessageIdReplay
from solace.messaging.config.solace_constants import receiver_constants
from solace.messaging.config.solace_properties import receiver_properties
from solace.messaging.receiver._impl._persistent_message_receiver import _PersistentMessageReceiver
from solace.messaging.receiver.persistent_message_receiver import PersistentMessageReceiver
from solace.messaging.resources.queue import Queue
from solace.messaging.utils._solace_utilities import is_type_matches

logger = logging.getLogger('solace.messaging.receiver')


class _PersistentMessageReceiverBuilder(_MessageReceiverBuilder, PersistentMessageReceiverBuilder) \
        :  # pylint: disable=too-many-ancestors,too-many-instance-attributes, missing-class-docstring, missing-module-docstring
    # Builder class for persistent message receiver

    def __init__(self, messaging_service: 'MessagingService'):
        super().__init__(messaging_service)
        self._missing_resources_creation_strategy: MissingResourcesCreationStrategy
        self._missing_resources_creation_strategy = None
        self._replay_strategy: ReplayStrategy
        self._replay_strategy = None

        self._receiver_state_change_listener: ReceiverStateChangeListener
        self._receiver_state_change_listener = None
        self._config: dict = dict()
        self._message_selector: str
        self._message_selector = ''
        self._auto_ack: bool = False
        self._endpoint_to_consume_from: Queue
        self._endpoint_to_consume_from = None

    def with_activation_passivation_support(self, receiver_state_change_listener: ReceiverStateChangeListener) \
            -> 'PersistentMessageReceiverBuilder':
        # Enables receiver to receive broker notifications about state changes of the give receiver instance
        is_type_matches(receiver_state_change_listener, ReceiverStateChangeListener, logger=logger)
        self._receiver_state_change_listener = receiver_state_change_listener
        return self

    def from_properties(self, configuration: dict) -> 'PersistentMessageReceiverBuilder':
        # Set PersistentMessageReceiver properties from the dictionary of (property,value) tuples.
        is_type_matches(configuration, dict, logger=logger)
        self.__build_replay_strategy_from_props(configuration)
        self.__build_message_selector_from_props(configuration)
        self.__build_missing_resources_creation_strategy_from_props(configuration)
        self.__build_message_ack_strategy_from_props(configuration)
        self._config = configuration
        return self

    def with_missing_resources_creation_strategy(self, strategy: 'MissingResourcesCreationStrategy') \
            -> 'PersistentMessageReceiverBuilder':
        # Implementation method for creating a PersistentMessageReceiverBuilder
        #  using the MissingResourcesCreationStrategy
        is_type_matches(strategy, MissingResourcesCreationStrategy, logger=logger)
        self._missing_resources_creation_strategy = strategy
        return self

    def with_message_auto_acknowledgement(self) -> 'PersistentMessageReceiverBuilder':
        # Implementation method for creating a PersistentMessageReceiverBuilder using the
        # message auto acknowledgement
        self._auto_ack = True
        return self

    def with_message_client_acknowledgement(self) -> 'PersistentMessageReceiverBuilder':
        # Implementation method for creating a PersistentMessageReceiverBuilder without
        # using the message auto acknowledgement
        self._auto_ack = False
        return self

    def with_message_selector(self, selector_query_expression: str) -> 'PersistentMessageReceiverBuilder':
        # Implementation method for creating the PersistentMessageReceiverBuilder using the message
        # selector expression for selecting the messages based on the expression
        is_type_matches(selector_query_expression, str, logger=logger)
        self._message_selector = selector_query_expression
        return self

    def with_message_replay(self, replay_strategy: 'ReplayStrategy') -> 'PersistentMessageReceiverBuilder':
        is_type_matches(replay_strategy, ReplayStrategy, logger=logger)
        self._replay_strategy = replay_strategy
        return self

    @property
    def messaging_service(self):
        # Property to hold and return the messaging service
        return self._messaging_service

    @property
    def missing_resources_creation_strategy(self):
        # Property to hold and return the MissingResourcesCreationStrategy
        return self._missing_resources_creation_strategy

    @property
    def replay_strategy(self):
        # Property to hold and return the ReplayStrategy
        return self._replay_strategy

    @property
    def receiver_state_change_listener(self):
        # Property to hold and return the receiver state change listener value
        return self._receiver_state_change_listener

    @property
    def topics(self):
        # Property to hold and return the topics
        return self._topic_subscriptions

    @property
    def config(self):
        # Property to hold and return the configuration dictionary
        return self._config

    @property
    def message_selector(self):
        # Property to hold and return the message selector expression
        return self._message_selector

    @property
    def endpoint_to_consume_from(self):
        # Property to hold and return the endpoint from which a message to be consumed
        return self._endpoint_to_consume_from

    @property
    def auto_ack(self):
        # Property to hold and return the auto acknowledgement value
        return self._auto_ack

    def build(self, endpoint_to_consume_from: Queue) -> PersistentMessageReceiver:
        # Implementation method to build the PersistentMessageReceiver
        is_type_matches(endpoint_to_consume_from, Queue, logger=logger)
        self._endpoint_to_consume_from = endpoint_to_consume_from
        return _PersistentMessageReceiver(self)

    def __build_replay_strategy_from_props(self, configuration: dict):
        if receiver_properties.PERSISTENT_MESSAGE_REPLAY_STRATEGY in configuration.keys():
            if configuration[receiver_properties.PERSISTENT_MESSAGE_REPLAY_STRATEGY] \
                    == receiver_constants.PERSISTENT_REPLAY_ALL:
                self._replay_strategy = AllMessagesReplay()
            elif configuration[receiver_properties.PERSISTENT_MESSAGE_REPLAY_STRATEGY] \
                    == receiver_constants.PERSISTENT_REPLAY_TIME_BASED:
                self._replay_strategy = TimeBasedReplay(
                    configuration[receiver_properties.PERSISTENT_MESSAGE_REPLAY_STRATEGY_TIME_BASED_START_TIME])
            elif configuration[receiver_properties.PERSISTENT_MESSAGE_REPLAY_STRATEGY] \
                    == receiver_constants.PERSISTENT_REPLAY_ID_BASED:
                self._replay_strategy = ReplicationGroupMessageIdReplay(
                    configuration[receiver_properties.PERSISTENT_MESSAGE_REPLAY_STRATEGY_ID_BASED_REPLICATION_GROUP_MESSAGE_ID])
            return self
        else:
            logger.debug('KEY is not available in the receiver properties')
    
    def __build_message_selector_from_props(self, configuration: dict):
        if receiver_properties.PERSISTENT_MESSAGE_SELECTOR_QUERY in configuration.keys():
            self.with_message_selector(configuration[receiver_properties.PERSISTENT_MESSAGE_SELECTOR_QUERY])

    def __build_missing_resources_creation_strategy_from_props(self, configuration: dict):
        if receiver_properties.PERSISTENT_MISSING_RESOURCE_CREATION_STRATEGY in configuration.keys():
            if configuration[receiver_properties.PERSISTENT_MISSING_RESOURCE_CREATION_STRATEGY] \
                    == receiver_constants.PERSISTENT_RECEIVER_CREATE_ON_START_MISSING_RESOURCES:
                self.with_missing_resources_creation_strategy(MissingResourcesCreationStrategy.CREATE_ON_START)
            elif configuration[receiver_properties.PERSISTENT_MISSING_RESOURCE_CREATION_STRATEGY] \
                    == receiver_constants.PERSISTENT_RECEIVER_DO_NOT_CREATE_MISSING_RESOURCES:
                self.with_missing_resources_creation_strategy(MissingResourcesCreationStrategy.DO_NOT_CREATE)

    def __build_message_ack_strategy_from_props(self, configuration: dict):
        if receiver_properties.PERSISTENT_MESSAGE_ACK_STRATEGY in configuration.keys():
            if configuration[receiver_properties.PERSISTENT_MESSAGE_ACK_STRATEGY] \
                    == receiver_constants.PERSISTENT_RECEIVER_AUTO_ACK:
                self.with_message_auto_acknowledgement()
            elif configuration[receiver_properties.PERSISTENT_MESSAGE_ACK_STRATEGY] \
                    == receiver_constants.PERSISTENT_RECEIVER_CLIENT_ACK:
                self.with_message_client_acknowledgement()
