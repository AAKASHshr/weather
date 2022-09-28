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


# this module contains the exception messages used through out project scope
# pylint: disable=missing-module-docstring
from string import Template

import threading

SOLCLIENT_LIBRARY_MISSING = "Core library unavailable"
UNABLE_TO_LOAD_SOLCLIENT_LIBRARY = "Unable to load core library"

MESSAGE_SENDING_FAILED = "Failed to send message"
SET_DESTINATION_FAILED = "Failed to set destination"
BINARY_STRING_ATTACHMENT_FAILED = "Failed to create binary string attachment"
MEMORY_ALLOCATION_FAILED = "Unable to allocate solClient message"
BAD_CREDENTIALS = "The username or password is incorrect"
UNRESOLVED_SESSION = 'Could not be resolved from session'
BAD_HOST_OR_PORT = "Service can't be reached using provided host and port"
NO_VALID_SMF_HEADER_MAPPING = "Could not read valid SMF Header from network"
NOT_BYTES_TO_READ_MAPPING = "Unable to read enough bytes from stream!"
EXCEPTION_NULL = "Exception can't be null"
SESSION_FORCE_DISCONNECT = "Session is being forcefully disconnected"

QUEUE_FULL_EXCEPTION_MESSAGE = "QUEUE full."

TOPIC_UNAVAILABLE = "Topic unavailable"
CURRENT_STATUS = "Current status: "

MESSAGE_SERVICE_DISCONNECTED = "Messaging service disconnected."
MESSAGE_SERVICE_NOT_CONNECTED = "Messaging service not connected."
MESSAGE_SERVICE_NOT_ATTEMPTED_TO_CONNECT = "Messaging service is not attempted to connect."
MESSAGE_SERVICE_DISCONNECT_ALREADY = "Messaging service already disconnected."
MESSAGING_SERVICE_DOWN = "Service down"
UNABLE_TO_FORCE_DISCONNECT = f"Unable to FORCE disconnect service. {CURRENT_STATUS}"
MESSAGE_SERVICE_CONNECTION_IN_PROGRESS = f"Messaging service connection process already initiated. {CURRENT_STATUS}"
FAILURE_CODE = "Failure code: "
UNABLE_TO_DESTROY_SESSION = "Unable to destroy session"
UNABLE_TO_CONNECT_ALREADY_DISCONNECTED_SERVICE = f"Unable to connect to messaging service. {CURRENT_STATUS}"
MESSAGE_SERVICE_DISCONNECT_IN_PROGRESS = f"Messaging service disconnect process already initiated. {CURRENT_STATUS}"

PUBLISHER_CANNOT_BE_STARTED = "Publisher can't be started"
UNABLE_TO_PUBLISH_MESSAGE = "Unable to Publish message."
PUBLISHER_NOT_STARTED = "Publisher not started."
PUBLISHER_NOT_READY = "Publisher not ready."
CANNOT_TERMINATE_PUBLISHER = "Cannot terminate the publisher."
PUBLISHER_TERMINATED = "Publisher terminated."
PUBLISHER_CANNOT_BE_STARTED_MSG_SERVICE_NOT_CONNECTED = f"{PUBLISHER_CANNOT_BE_STARTED}," \
                                                        " before it is connected to a messaging service"
PUBLISHER_TERMINAL_ERROR_MESSAGE = f"{PUBLISHER_CANNOT_BE_STARTED}," \
                                   " it might reach terminal status. Try re-initiating it"
UNABLE_TO_PUBLISH_MESSAGE_PUBLISHER_NOT_STARTED = f"{UNABLE_TO_PUBLISH_MESSAGE} {PUBLISHER_NOT_STARTED}"
PUBLISHER_NOT_STARTED_CURRENT_STATUS = f"{PUBLISHER_NOT_STARTED} {CURRENT_STATUS}"
UNABLE_TO_PUBLISH_MESSAGE_PUBLISHER_TERMINATING = f"{UNABLE_TO_PUBLISH_MESSAGE} Publisher terminating"
PUBLISHER_UNAVAILABLE_FOR_TERMINATE = f"{CANNOT_TERMINATE_PUBLISHER} {CURRENT_STATUS}"
UNABLE_TO_PUBLISH_MESSAGE_PUBLISHER_NOT_READY = f"{UNABLE_TO_PUBLISH_MESSAGE} {PUBLISHER_NOT_READY}"
PUBLISH_FAILED_MESSAGING_SERVICE_NOT_CONNECTED = f"{UNABLE_TO_PUBLISH_MESSAGE} {MESSAGE_SERVICE_NOT_CONNECTED}"

UNABLE_TO_SET_LISTENER = "Unable to set publish listener receiver"
DELIVERY_LISTENER_SERVICE_DOWN_EXIT_MESSAGE = f"{MESSAGING_SERVICE_DOWN} exiting the publish listener thread"
PUBLISHER_SERVICE_DOWN_EXIT_MESSAGE = f"{MESSAGING_SERVICE_DOWN}, exiting the PUBLISHER thread"

PUBLISHER_ALREADY_TERMINATED = "Message publisher already terminated"
PUBLISH_TIME_OUT = "Message publish timeout"
UNABLE_TO_PUBLISH_EMPTY_MESSAGE = "Unable to publish an empty message"
RECEIVER_SERVICE_DOWN_EXIT_MESSAGE = f"{MESSAGING_SERVICE_DOWN} exiting the RECEIVER thread"
UNABLE_TO_PUBLISH_MESSAGE_PUBLISHER_TERMINATED = f"{UNABLE_TO_PUBLISH_MESSAGE} {PUBLISHER_TERMINATED}"
PERSISTENT_PUBLISHER_TERMINATED = f"Persistent {PUBLISHER_TERMINATED}"
STATE_CHANGE_LISTENER_SERVICE_DOWN_EXIT_MESSAGE = f"{MESSAGING_SERVICE_DOWN} exiting the state change listener thread"
PUBLISHER_READINESS_SERVICE_DOWN_EXIT_MESSAGE = f"{MESSAGING_SERVICE_DOWN} exiting the PUBLISHER readiness thread"
PUBLISHER_START_IN_PROGRESS = "Starting publisher."
UNABLE_TO_START_ALREADY_DISCONNECTED_PUBLISHER = f"Unable to start publisher. {CURRENT_STATUS}"
PUBLISHER_TERMINATE_IN_PROGRESS = f"Publisher termination already initiated. {CURRENT_STATUS}"
PUBLISHER_TERMINATED_UNABLE_TO_START = "Publisher already terminated, cannot be started."

RECEIVER_START_IN_PROGRESS = "Starting receiver."
RECEIVER_CANNOT_BE_STARTED = "Receiver can't be started"
CANNOT_TERMINATE_RECEIVER = "Cannot terminate the receiver."
RECEIVER_NOT_STARTED = "Receiver not started."
RECEIVER_TERMINATED = "Receiver terminated."
UNABLE_TO_RECEIVE_MESSAGE = "Unable to Receive message."
RECEIVER_ALREADY_TERMINATED = "Message receiver already terminated"
UNABLE_TO_RECEIVE_MESSAGE_RECEIVER_ALREADY_TERMINATED = f"{UNABLE_TO_RECEIVE_MESSAGE} {RECEIVER_ALREADY_TERMINATED}"
RECEIVER_TERMINATION_IS_IN_PROGRESS = "Message receiver termination is in-progress"
UNABLE_TO_RECEIVE_MESSAGE_RECEIVER_NOT_STARTED = f"{UNABLE_TO_RECEIVE_MESSAGE} {RECEIVER_NOT_STARTED}"
RECEIVER_NOT_STARTED_CURRENT_STATUS = f"{RECEIVER_NOT_STARTED} {CURRENT_STATUS}"
UNABLE_TO_RECEIVE_MESSAGE_MESSAGE_SERVICE_NOT_CONNECTED = f"{UNABLE_TO_RECEIVE_MESSAGE} {MESSAGE_SERVICE_DISCONNECTED}"
RECEIVER_TERMINATED_UNABLE_TO_RECEIVE_MESSAGE = f"{UNABLE_TO_RECEIVE_MESSAGE} {RECEIVER_TERMINATED}"
RECEIVER_CANNOT_BE_STARTED_MSG_SERVICE_NOT_CONNECTED = f"{RECEIVER_CANNOT_BE_STARTED}, " \
                                                       f"before it is connected to a messaging service"
RECEIVER_TERMINAL_ERROR_MESSAGE = f"{RECEIVER_CANNOT_BE_STARTED}," \
                                  " it might reach terminal status. Try re-initiating it"
UNABLE_TO_START_ALREADY_DISCONNECTED_RECEIVER = f"{RECEIVER_CANNOT_BE_STARTED} {CURRENT_STATUS}"
RECEIVER_TERMINATE_IN_PROGRESS = F"Receiver termination already initiated. {CURRENT_STATUS}"
RECEIVER_TERMINATED_UNABLE_TO_START = f"{RECEIVER_ALREADY_TERMINATED}, cannot be started."
RECEIVE_MESSAGE_FROM_BUFFER = "Get message from queue/buffer"

FAILED_TO_GET_DUPLICATE_MESSAGE = "Failed to get a duplicate message"

INCOMPATIBLE_MESSAGE = "Incompatible message, provided converter can't be used"
INVALID_PROPERTY_KEY = "The property key can not be None or empty"
INVALID_PROPERTY_VALUE = "The property value can not be None"
EMPTY_PROPERTY_VALUE = "The property value can not be empty"

UNABLE_TO_SUBSCRIBE_TO_TOPIC = "Unable to subscribe Topic"
UNABLE_TO_UNSUBSCRIBE_TO_TOPIC = "Unable to unsubscribe Topic"
CANNOT_ADD_SUBSCRIPTION = "Cannot add subscription. Current status: "
CANNOT_REMOVE_SUBSCRIPTION = "Cannot remove subscription. Current status: "
TOPIC_NAME_MAX_LENGTH = 250
TOPIC_NAME_TOO_LONG = f"Invalid topic: Too long (encoding must be <= {TOPIC_NAME_MAX_LENGTH} bytes)"
QUEUE_NAME_MAX_LENGTH = 200
QUEUE_NAME_TOO_LONG = f"Invalid queue: Too long Queue Name, it cannot be longer than {QUEUE_NAME_MAX_LENGTH} characters"
TOPIC_NAME_CANNOT_BE_EMPTY = "Topic cannot be empty string"
TOPICSUBSCRIPTION_NAME_CANNOT_BE_EMPTY = "TopicSubscription cannot be empty string"
MAX_QUEUE_LIMIT_REACHED = "Queue maximum limit is reached"
FAILED_TO_SHUTDOWN_GRACEFULLY = "Failed to shutdown gracefully"
GRACE_PERIOD_MIN_MS = 0
GRACE_PERIOD_DEFAULT_MS = 600000  # 10 minutes
THREAD_TIMEOUT_MAX_VALUE = threading.TIMEOUT_MAX * 1000  # Maximum TIME OUT Value for threading event Milli Secs
GRACE_PERIOD_MIN_INVALID_ERROR_MESSAGE = f"grace_period must be greater than {GRACE_PERIOD_MIN_MS}"
GRACE_PERIOD_MAX_TIMEOUT_ERROR_MESSAGE = f"grace_period exceeds max thread timeout value {THREAD_TIMEOUT_MAX_VALUE}"

ESTABLISH_SESSION_ON_HOST = 'ESTABLISH SESSION ON HOST'
SESSION_CREATION_FAILED = "SESSION CREATION UNSUCCESSFUL."
TCP_CONNECTION_FAILURE = f"{SESSION_CREATION_FAILED} TCP connection failure, Connection refused."
FAILED_TO_LOAD_TRUST_STORE = f"{SESSION_CREATION_FAILED} Failed to load trust store."
FAILED_TO_LOADING_CERTIFICATE_AND_KEY = f"{SESSION_CREATION_FAILED} Failed to load certificate."
UNTRUSTED_CERTIFICATE_MESSAGE = f"{SESSION_CREATION_FAILED} Untrusted certificate."
WOULD_BLOCK_EXCEPTION_MESSAGE = f"{UNABLE_TO_PUBLISH_MESSAGE}. Would block exception occurred"

RECONNECTION_LISTENER_NOT_EXISTS = Template("ReconnectionListener: [$listener] not exists.")
RECONNECTION_ATTEMPT_LISTENER_NOT_EXISTS = Template("ReconnectionAttemptListener: [$listener] not exists.")
RECONNECTION_LISTENER_SHOULD_BE_TYPE_OF = "Reconnection listener should be an instance of "
RECONNECTION_ATTEMPT_LISTENER_SHOULD_BE_TYPE_OF = "Reconnection attempt listener should be an instance of "
INTERRUPTION_LISTENER_SHOULD_BE_TYPE_OF = "Service Interruption listener should be an instance of"

CCSMP_CALLER_DESC = 'caller_description'
CCSMP_RETURN_CODE = 'return_code'
CCSMP_SUB_CODE = 'sub_code'
CCSMP_INFO_SUB_CODE = 'error_info_sub_code'
CCSMP_INFO_CONTENTS = 'error_info_contents'

CCSMP_CERTIFICATE_ERROR = "certificate verify failed"
CCSMP_TCP_CONNECTION_FAILURE = "TCP connection failure"

CCSMP_SUB_CODE_UNRESOLVED_HOST = "SOLCLIENT_SUBCODE_UNRESOLVED_HOST"
CCSMP_SUB_CODE_INTERNAL_ERROR = "SOLCLIENT_SUBCODE_INTERNAL_ERROR"
CCSMP_SUB_CODE_UNTRUSTED_COMMONNAME = "SOLCLIENT_SUBCODE_UNTRUSTED_COMMONNAME"
CCSMP_SUB_CODE_LOGIN_FAILURE = "SOLCLIENT_SUBCODE_LOGIN_FAILURE"
CCSMP_SUB_CODE_FAILED_TO_LOAD_TRUST_STORE = "SOLCLIENT_SUBCODE_FAILED_LOADING_TRUSTSTORE"
CCSMP_SUB_CODE_FAILED_LOADING_CERTIFICATE_AND_KEY = "SOLCLIENT_SUBCODE_FAILED_LOADING_CERTIFICATE_AND_KEY"
CCSMP_SUBCODE_UNTRUSTED_CERTIFICATE = "SOLCLIENT_SUBCODE_UNTRUSTED_CERTIFICATE"
CCSMP_SUB_CODE_OK = "SOLCLIENT_SUBCODE_OK"
CCSMP_SUBCODE_COMMUNICATION_ERROR = 'SOLCLIENT_SUBCODE_COMMUNICATION_ERROR'
CCSMP_SUBCODE_SUBCODE_UNKNOWN_QUEUE_NAME = 'SOLCLIENT_SUBCODE_UNKNOWN_QUEUE_NAME'
CCSMP_SUBCODE_PARAM_OUT_OF_RANGE = 'SOLCLIENT_SUBCODE_PARAM_OUT_OF_RANGE'
CCSMP_SUBCODE_DATA_OTHER = 'SOLCLIENT_SUBCODE_DATA_OTHER'

STATS_ERROR = "FAILED TO RETRIEVE THE STATISTICS"

VALUE_CANNOT_BE_NONE = "Value cannot be none"
VALUE_CANNOT_BE_EMPTY = "Value cannot be empty"
VALUE_CANNOT_BE_NEGATIVE = "Value cannot be negative "
VALUE_MUST_BE_POSITIVE = "Value must be greater than 0"
VALUE_OUT_OF_RANGE = 'Value is out of range '

SHARE_NAME_CANT_BE_NONE = "ShareName can't be none"
SHARE_NAME_ILLEGAL_CHAR_ERROR_MESSAGE = "Literals '>' and '*' are not permitted in a ShareName"

NOT_FOUND_MESSAGE = "Not Found"
FAILED_TO_RETRIEVE = "Failed to retrieve"
FAILED_TO_GET_APPLICATION_TYPE = 'Unable to get application message type.'
FAILED_TO_GET_APPLICATION_ID = 'Unable to get application message id'

UNSUPPORTED_METRIC_TYPE = "Unsupported metric value type."
ERROR_WHILE_RETRIEVING_METRIC = "Error while retrieving API metric."
INVALID_DATATYPE = "Invalid datatype."
INVALID_EXPECTED_DATATYPE = Template('Invalid datatype. Expected type: [$expected_type], but actual [$actual_type]')
BROKER_MANDATORY_KEY_MISSING_ERROR_MESSAGE = "Mandatory broker properties are missing. Try adding these missing keys :"
BROKER_MANDATORY_MINIMUM_ONE_KEY_MISSING_ERROR_MESSAGE = "Mandatory broker properties are missing. Try adding at least one of the following missing keys :"

MISSING_BUFFER_CAPACITY = "Missing buffer capacity"
ILLEGAL_COMPRESSION_LEVEL = "Illegal compression level"
DISPATCH_FAILED = "Failed to dispatch the callback"
HOSTNAME_MISMATCH = "Hostname mismatch"
IP_ADDRESS_MISMATCH = "IP address mismatch"
PEER_CERTIFICATE_IS_NOT_TRUSTED = "The peer certificate is not trusted"
UNKNOWN_QUEUE = 'Unknown Queue'

UNCLEANED_TERMINATION_EXCEPTION_MESSAGE_PUBLISHER = "Failed to publish messages, publisher terminated"
UNCLEANED_TERMINATION_EXCEPTION_MESSAGE_RECEIVER = "Failed to deliver messages, receiver terminated"
DISCARD_INDICATION_FALSE = "Has discard indication!: [0]"
UNPUBLISHED_MESSAGE_COUNT = "Unpublished message count:"
UNPUBLISHED_PUBLISH_RECEIPT_COUNT = "Undelivered publish receipt count:"

FLOW_PAUSE = "Flow paused after reaching internal threshold upper limit"
FLOW_RESUME = "Flow resumed after reaching internal threshold lower limit"
NO_INCOMING_MESSAGE = "No incoming message"
DICT_KEY_CANNOT_NONE = "Key in dictionary cannot be empty/none"
DICT_CONTAINS_NONE_VALUE = "Any value in dictionary cannot be empty/none"
INVALID_ADDITIONAL_PROPS = f"Invalid additional properties. {DICT_CONTAINS_NONE_VALUE}"
INVALID_TYPE_IN_ADDITIONAL_PROPS_VALUE = Template("The given property value type: [$value_type] is not supported")
FLOW_DOWN_UNBLOCK_RECEIVE_MESSAGE = "Flow Down, subscriber may receive None"
FLOW_INACTIVE = "Flow is  inactive"
FLOW_DOWN = "Flow is Down"
UNABLE_TO_ACK = "Cannot acknowledge the message in current state"
UNSUPPORTED_MESSAGE_TYPE = Template("$message_type is unsupported at the moment to publish a message")
SDT_KEY_MAP_ERROR = Template('Key: [$key] cannot be added. [$type] type not supported in SDT Map Key')
SDT_VALUE_MAP_ERROR = Template('Value: [$value] cannot be added. [$type] type not supported in SDT Map value')
SDT_STREAM_ERROR = Template('Value: [$value] cannot be added. [$type] type not supported in SDT Stream')
REQUEST_REPLY_TIMEOUT_SHOULD_BE_INT = f"reply_timeout must be [{int}]"
REQUEST_REPLY_MIN_TIMEOUT = 0
REQUEST_REPLY_MIN_TIMEOUT_ERROR_MESSAGE = f"reply_timeout must be greater than {REQUEST_REPLY_MIN_TIMEOUT}"
REQUEST_REPLY_NO_REPLY_MESSAGE = Template("No reply within $reply_timeout milliseconds")
UNSUPPORTED_MESSAGE_TYPE = Template("$message_type is unsupported at the moment to publish a message")
REQUEST_REPLY_OUTSTANDING_REQUESTS = "Outstanding requests do not have a response on terminate after" \
                                     " timeout has expired."
REQUEST_REPLY_OUTSTANDING_REQUESTS_COUNT = "Outstanding ReplyRequest count:"

BROKER_EXCLUDED_PROPERTY = "Parent property is not present so broker will ignore property:"
