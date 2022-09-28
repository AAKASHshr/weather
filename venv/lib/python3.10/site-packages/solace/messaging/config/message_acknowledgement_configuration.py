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

"""
This module defines the interface for configuring message acknowledgement strategy. In some scenarios,
when a specific message is published, the receiver that has received that message can send an
acknowledgement for the message that was received back to the publisher. With auto-acknowledgement,
you can automatically acknowledge each message. With client-acknowledgement, the user-defined 
application must deliberately acknowledge messages.
"""

from abc import abstractmethod
from solace.messaging.config.message_auto_acknowledgement_configuration import MessageAutoAcknowledgementConfiguration


class MessageAcknowledgementConfiguration(MessageAutoAcknowledgementConfiguration):
    """
    An abstract class that defines the interface to configure message acknowledgement strategy.

    The default strategy enables client-acknowledgement and disables auto-acknowledgement.
    """

    @abstractmethod
    def with_message_client_acknowledgement(self) -> 'MessageAcknowledgementConfiguration':
        """
        Enables support for message client-acknowledgement (client-ack) on all receiver methods,
        which includes both synchronous and asynchronous methods. Client-acknowledgement must be
        executed by the user-defined application. It is recommended that client-acknowledgement
        be written in the on_message method of the user defined message handler. This message handler would be
        of type :py:class:`solace.messaging.receiver.message_receiver.MessageHandler`.

        Returns:
            An instance of itself for method chaining.
        """
