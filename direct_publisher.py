## Goal: Simple Publisher, event handling and message properties setting
import os
import platform
import time
import requests
import schedule
import json

# Import Solace Python  API modules from the solace package
from solace.messaging.messaging_service import MessagingService, ReconnectionListener, ReconnectionAttemptListener, ServiceInterruptionListener, RetryStrategy, ServiceEvent
from solace.messaging.resources.topic import Topic
from solace.messaging.publisher.direct_message_publisher import PublishFailureListener, FailedPublishEvent

if platform.uname().system == 'Windows': os.environ["PYTHONUNBUFFERED"] = "1" # Disable stdout buffer 

#MSG_COUNT = 5
TOPIC_PREFIX = "get/live/weather"

# Inner classes for error handling
class ServiceEventHandler(ReconnectionListener, ReconnectionAttemptListener, ServiceInterruptionListener):
    def on_reconnected(self, e: ServiceEvent):
        print("\non_reconnected")
        print(f"Error cause: {e.get_cause()}")
        print(f"Message: {e.get_message()}")
    
    def on_reconnecting(self, e: "ServiceEvent"):
        print("\non_reconnecting")
        print(f"Error cause: {e.get_cause()}")
        print(f"Message: {e.get_message()}")

    def on_service_interrupted(self, e: "ServiceEvent"):
        print("\non_service_interrupted")
        print(f"Error cause: {e.get_cause()}")
        print(f"Message: {e.get_message()}")

 
class PublisherErrorHandling(PublishFailureListener):
    def on_failed_publish(self, e: "FailedPublishEvent"):
        print("on_failed_publish")

# Broker Config. Note: Could pass other properties Look into
broker_props = {
    "solace.messaging.transport.host": os.environ.get('SOLACE_HOST') or "ws://localhost:8008",
    "solace.messaging.service.vpn-name": os.environ.get('SOLACE_VPN') or "default",
    "solace.messaging.authentication.scheme.basic.username": os.environ.get('SOLACE_USERNAME') or "default",
    "solace.messaging.authentication.scheme.basic.password": os.environ.get('SOLACE_PASSWORD') or "default"
    }

# Build A messaging service with a reconnection strategy of 20 retries over an interval of 3 seconds
# Note: The reconnections strategy could also be configured using the broker properties object
messaging_service = MessagingService.builder().from_properties(broker_props)\
                    .with_reconnection_retry_strategy(RetryStrategy.parametrized_retry(20,3))\
                    .build()

# Blocking connect thread
messaging_service.connect()
print(f'Messaging Service connected? {messaging_service.is_connected}')

# Event Handling for the messaging service
service_handler = ServiceEventHandler()
messaging_service.add_reconnection_listener(service_handler)
messaging_service.add_reconnection_attempt_listener(service_handler)
messaging_service.add_service_interruption_listener(service_handler)

# Create a direct message publisher and start it
direct_publisher = messaging_service.create_direct_message_publisher_builder().build()
direct_publisher.set_publish_failure_listener(PublisherErrorHandling())

# Blocking Start thread
direct_publisher.start()
print(f'Direct Publisher ready? {direct_publisher.is_ready()}')

# Prepare outbound message payload and body
outbound_msg_builder = messaging_service.message_builder() \
                .with_application_message_id("live weather") \
                .with_property("developer: ", "Aakash") \
                .with_property("language", "Python") \

print("\nSend a KeyboardInterrupt to stop publishing\n")

###
url = "https://api.tomorrow.io/v4/timelines"
querystring = {
"location":"-26.6559759, 153.0918365",         #lat long of sunshine coast 
"fields":["temperature","windSpeed","humidity"],
"units":"metric",                               #celcius    
"timesteps":"current",                              
"apikey":"VM5OHj1SWudXbY1U1OWELCO4Iyp5q6xR"}

print("sending message")

###
def start():
    response = requests.request("GET", url, params=querystring)
    print(response.text)
    data = response.text
    outbound_msg = outbound_msg_builder\
                        .with_application_message_id(f'NEW')\
                        .build(data)
    direct_publisher.publish(destination=topic, message= outbound_msg)

###
try: 
    while True:
        topic = Topic.of(TOPIC_PREFIX + f'/direct/pub/')
        # Direct publish the message 
        #schedule.every().day.at("00:00").do(start)
        #schedule.every().hour.do(start)
        schedule.every(20).seconds.do(start)
        print(f'Publishing message on {topic}')
        while True:
            schedule.run_pending()
            time.sleep(1)
    

except KeyboardInterrupt:
    print('\nTerminating Publisher')
    direct_publisher.terminate()
    print('\nDisconnecting Messaging Service')
    messaging_service.disconnect()