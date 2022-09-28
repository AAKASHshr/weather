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

"""This module contains the abstract class and methods for the AcknowledgementSupport."""

from abc import ABC, abstractmethod

from solace.messaging.receiver.inbound_message import InboundMessage


class AcknowledgementSupport(ABC):
    """
        A class that defines the interface for manual message acknowledgement (receiver acknowledges message to the
        broker).

        Client acknowledgement signals to the event broker the message has been received and processed.
        When all receivers have acknowledged that a message has been delivered, the message is removed
        from the permanent storage on the event broker.

        Acknowledgement, or withholding acknowledgement, has no bearing on flow-control or back-pressure.
    """

    @abstractmethod
    def ack(self, message: InboundMessage):
        """
        Generates and sends an acknowledgement for an inbound message (``InboundMessage``).

        Args:
            message: The inbound message.

        Raises:
            PubSubPlusClientError: If it was not possible to acknowledge the message.
        """
