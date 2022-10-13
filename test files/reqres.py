import time
import requests
import schedule
import json
from solace.messaging.messaging_service import MessagingService
from solace.messaging.resources.topic import Topic
from solace.messaging.publisher.direct_message_publisher import PublishFailureListener, FailedPublishEvent

from timer import start



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



###
direct_publisher = messaging_service.create_direct_message_publisher_builder().build()
direct_publisher.set_publish_failure_listener(PublisherErrorhandling())

direct_publisher.start()
print("direct publisher started")

##
outbound_msg_builder = messaging_service.message_builder()\
                            .with_application_message_id("live_weather")\
                            .with_property("Developer", "Aakash")


###
url = "https://reqres.in/api/users/2"
querystring = {
"location":"-26.6559759, 153.0918365",         #lat long of sunshine coast 
"fields":["temperature","sunriseTime","sunsetTime","windSpeed","humidity"],
"units":"metric",                               #celcius    
"timesteps":"1h",   
"startTime":"now",
"endTime":"nowPlus1h",                             
"apikey":"VM5OHj1SWudXbY1U1OWELCO4Iyp5q6xR"}

print("sending message")


def start():
    '''getting the data from the api and pushing it into the solace pubsubplus'''   
    response = requests.request("GET", url)
    print(response.text)
    data = json.loads(response.text)
    outbound_msg = outbound_msg_builder.build(data)
    direct_publisher.publish(destination=topic, message= outbound_msg)
###
try:
    while True:
        topic = Topic.of("solace/samples/python/test")

        schedule.every(10).seconds.do(start)

        while True:
            schedule.run_pending()
            time.sleep(1)

        

except KeyboardInterrupt:
    print("\nterminating Publisher")
    direct_publisher.terminate()
    print("\nDisconnecting Messaging Service")
    messaging_service.disconnect()