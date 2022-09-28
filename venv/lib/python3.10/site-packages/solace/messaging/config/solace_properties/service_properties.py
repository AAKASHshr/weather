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


"""This module contains dictionary keys for :py:class:`solace.messaging.messaging_service.MessagingService`
properties. """  # pylint: disable=trailing-whitespace

VPN_NAME = "solace.messaging.service.vpn-name"
"""Property constant defining the key for configuring the message vpn name. 

  This key may be used in the :py:class:`solace.messaging.messaging_service.MessagingService` properties 
  when configured from a dictionary.
"""

GENERATE_SENDER_ID = "solace.messaging.service.generate-sender-id"
"""Property constant defining the key for enabling sender-id auto-generation. 

  This key may be used in the :py:class:`solace.messaging.messaging_service.MessagingService` properties 
  when configured from a dictionary.

  When enabled, GENERATE_SENDER_ID applies to all messages published by 
  :py:class:`solace.messaging.publisher.message_publisher.MessagePublisher` that exist on the messaging service. 
  Each message published will include the SenderId property. The application_id set in 
  :py:meth:`MessagingServiceClientBuilder.build()<solace.messaging.messaging_service.MessagingServiceClientBuilder.build>`
  is used as the SenderId.
"""

GENERATE_RECEIVE_TIMESTAMPS = "solace.messaging.service.generate-receive-timestamps"
"""Property constant defining the key for enabling receive timestamps in received messages. 

  This key may be used in the :py:class:`solace.messaging.messaging_service.MessagingService` properties 
  when configured from a dictionary.

  When enabled, GENERATE_RECEIVE_TIMESTAMPS applies to all messages received by
  :py:class:`solace.messaging.receiver.message_receiver.MessageReceiver` that exist on the messaging service. Each 
  message received will include a receive timestamp that reflects the time the message was received from the
  PubSub+ event broker by the underlying native API.
"""

GENERATE_SEND_TIMESTAMPS = "solace.messaging.service.generate-send-timestamps"
"""Property constant defining the key for generating send timestamps in published messages. 

  This key may be used in the :py:class:`solace.messaging.messaging_service.MessagingService` properties 
  when configured from a dictionary.

  When enabled, GENERATE_SEND_TIMESTAMPS applies to all messages published by
  :py:class:`solace.messaging.publisher.message_publisher.MessagePublisher` that exist on the messaging service. Each 
  message published includes a timestamp that reflects the time that the message was queued for transmission to
  the PubSub+ event broker by the underlying native API.
"""
