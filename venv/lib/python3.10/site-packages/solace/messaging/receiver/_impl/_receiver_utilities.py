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

# Module contains the receiver utility methods


# pylint: disable=missing-module-docstring,missing-class-docstring,missing-function-docstring,protected-access

from solace.messaging.config._solace_message_constants import RECEIVER_CANNOT_BE_STARTED_MSG_SERVICE_NOT_CONNECTED
from solace.messaging.receiver._impl import _message_receiver
from solace.messaging.resources.topic_subscription import TopicSubscription
from solace.messaging.utils._solace_utilities import is_type_matches, raise_illegal_state_error


def validate_subscription_type(subscription, logger=None):
    # To validate TopicSubscription type
    is_type_matches(subscription, TopicSubscription, logger=logger)


def is_message_service_connected(receiver_state, message_service, logger):
    # Method to validate message service is connected or not
    if not message_service.is_connected:
        receiver_state = _message_receiver._MessageReceiverState.NOT_STARTED
        logger.debug('Receiver is [%s]. MessagingService NOT connected',
                     _message_receiver._MessageReceiverState.NOT_STARTED.name)
        raise_illegal_state_error(error_message=RECEIVER_CANNOT_BE_STARTED_MSG_SERVICE_NOT_CONNECTED)
    return True, receiver_state
