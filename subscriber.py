from distutils.command.build import build
import time
import json
from solace.messaging.messaging_service import MessagingService
from solace.messaging.resources.topic import Topic
from solace.messaging.resources.topic_subscription import TopicSubscription
from solace.messaging.receiver.message_receiver import MessageHandler
from solace.messaging.receiver.inbound_message import InboundMessage

class MessageHandlerImpl(MessageHandler):
    def on_message(self, message: "InboundMessage"):
        message_dump=str(message)
        payload = message.get_payload_as_string()
        print(f"\n message_dump: {message_dump}")
        print(f"\n Payload: {payload}")
###
broker_props = {
    "solace.messaging.transport.host": "ws://localhost:8008",
    "solace.messaging.service.vpn-name": "default",
    "solace.messaging.authentication.scheme.basic.username": "default",
    "solace.messaging.authentication.scheme.basic.password": "default"
}
###
messaging_service = MessagingService.builder().from_properties(broker_props).build()
messaging_service.connect()


###
topic = ("GET")
topic_sub =[]
for t in topic:
    topic_sub.append(TopicSubscription.of(t))
print(topic_sub)
###
direct_receiver = messaging_service.create_direct_message_receiver_builder().with_subscriptions(topic_sub).build()
direct_receiver.start()


print(f"Direct subscriber is running {direct_receiver.is_running()}")

###
try:
    #callback for received messages
    print(f"subscribing to: {topic_sub}")
    direct_receiver.receive_async(MessageHandlerImpl())

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Disconnecting Messaging Service")
finally:
    direct_receiver.terminate()
    messaging_service.disconnect()
