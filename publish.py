import time
from solace.messaging.messaging_service import MessagingService, ReconnectionListener, ReconnectionAttemptListener, ServiceInterruptionListener, ServiceEvent
from solace.messaging.resources.topic import Topic
from solace.messaging.publisher.direct_message_publisher import PublishFailureListener

###
# class ServiceEventHandler (ReconnectionListener, ReconnectionAttemptListener, ServiceInterruptionListener):
#     def on_reconnected(self, e: ServiceEvent):
#         print("\not_reconnected")
#         print(f"Error cause : {e.get_cause()}")
#         print(f"Message : {e.get_message()}")
        
#     def on_reconnected(self, e: "ServiceEvent"):
#         print("\not_reconnecting")
#         print(f"Error cause : {e.get_cause()}")
#         print(f"Message : {e.get_message()}")
    
#     def on_reconnected(self, e: "ServiceEvent"):
#         print("\non_service_interupted")
#         print(f"Error cause : {e.get_cause()}")
#         print(f"Message : {e.get_message()}")


class PublisherErrorhandling(PublishFailureListener):
    def on_failed_publish(self, e: "FailedPublishEvent"):
        print("on_failed_publish")

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


# ###
# service_handler = ServiceEvent()
# messaging_service.add_reconnection_listener(service_handler)
# messaging_service.add_reconnection_attempt_listener(service_handler)
# messaging_service.add_service_interruption_listener(service_handler)

###
direct_publisher = messaging_service.create_direct_message_publisher_builder().build()
direct_publisher.set_publish_failure_listener(PublisherErrorhandling())

direct_publisher.start()
print("dirext publisher started")

###
message_body = "Hello world"
outbound_msg_builder = messaging_service.message_builder()\
                            .with_application_message_id("okay")\
                            .with_property("Developer", "Aakash")


###
count = 1
print("sending message")
try:
    while True:
        while count <=5:
            topic = Topic.of("Sample/Hello/"+f"live{count}")
            outbound_msg = outbound_msg_builder\
                .with_application_message_id (f'NEW{count}')\
                .build(f"{message_body}+{count}")
            direct_publisher.publish(destination=topic, message= outbound_msg)
            print(f"Published message on {topic}")
            count+=1
            time.sleep(1)
        print("\n")
        count = 1
        time.sleep(1)
except KeyboardInterrupt:
    print("\nterminating Publisher")
    direct_publisher.terminate()
    print("\nDisconnecting Messaging Service")
    messaging_service.disconnect()