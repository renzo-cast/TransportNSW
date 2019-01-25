"""A module to query Transport NSW (Australia) departure times."""
from datetime import datetime
import requests.exceptions
import requests
import logging

ATTR_STOP_ID = 'stop_id'
ATTR_ROUTE = 'route'
ATTR_DUE_IN = 'due'
ATTR_DELAY = 'delay'
ATTR_REALTIME = 'real_time'
ATTR_DESTINATION = 'destination'
ATTR_MODE = 'mode'
ATTR_STOP_LAT = 'stop_latitude' 
ATTR_STOP_LNG = 'stop_longitude'
ATTR_BUS_LAT = 'bus_latitude'
ATTR_BUS_LNG = 'bus_longitude'

logger = logging.getLogger(__name__)

class TransportNSW(object):
    """The Class for handling the data retrieval."""

    def __init__(self):
        """Initialize the data object with default values."""
        self.stop_id = None
        self.route = None
        self.destination = None
        self.api_key = None
        self.info = {
            ATTR_STOP_ID: 'n/a',
            ATTR_ROUTE: 'n/a',
            ATTR_DUE_IN: 'n/a',
            ATTR_DELAY: 'n/a',
            ATTR_REALTIME: 'n/a',
            ATTR_DESTINATION: 'n/a',
            ATTR_MODE: 'n/a',
            ATTR_STOP_LAT: 'n/a',
            ATTR_STOP_LNG: 'n/a'
        }

    def get_departures(self, stop_id, route, destination, api_key):
        """Get the latest data from Transport NSW."""
        self.stop_id = stop_id
        self.route = route
        self.destination = destination
        self.api_key = api_key

        #print('calling get_departures')


        # Build the URL including the STOP_ID and the API key
        url = \
            'https://api.transport.nsw.gov.au/v1/tp/departure_mon?' \
            'outputFormat=rapidJSON&coordOutputFormat=EPSG%3A4326&' \
            'mode=direct&type_dm=stop&name_dm=' \
            + self.stop_id \
            + '&departureMonitorMacro=true&TfNSWDM=true&version=10.2.1.42'
        auth = 'apikey ' + self.api_key
        header = {'Accept': 'application/json', 'Authorization': auth}

        # Send query or return error
        try:
            response = requests.get(url, headers=header, timeout=10)
        except:
            logger.warning("Network or Timeout error")
            return self.info

        # If there is no valid request
        if response.status_code != 200:
            logger.warning("Error with the request sent; check api key")
            return self.info

        # Parse the result as a JSON object
        result = response.json()

        # If there is no stop events for the query
        try:
            result['stopEvents']
        except KeyError:
            logger.warning("No stop events for this query")
            return self.info

        # Set variables
        maxresults = 1
        monitor = []
        if self.destination != '':
            for i in range(len(result['stopEvents'])):
                destination = result['stopEvents'][i]['transportation']['destination']['name']
                if destination == self.destination:
                    event = self.parseEvent(result, i)
                    if event != None:
                        monitor.append(event)
                    if len(monitor) >= maxresults:
                        # We found enough results, lets stop
                        break
        elif self.route != '':
            # Find the next stop events for a specific route
            for i in range(len(result['stopEvents'])):
                number = result['stopEvents'][i]['transportation']['number']
                if number == self.route:
                    event = self.parseEvent(result, i)
                    if event != None:
                        monitor.append(event)
                    if len(monitor) >= maxresults:
                        # We found enough results, lets stop
                        break
        else:
            # No route defined, find any route leaving next
            for i in range(0, maxresults):
                event = self.parseEvent(result, i)
                if event != None:
                    monitor.append(event)

        if monitor:
            self.info = {
                ATTR_STOP_ID: self.stop_id,
                ATTR_ROUTE: monitor[0][0],
                ATTR_DUE_IN: monitor[0][1],
                ATTR_DELAY: monitor[0][2],
                ATTR_REALTIME: monitor[0][5],
                ATTR_DESTINATION: monitor[0][6],
                ATTR_MODE: monitor[0][7],
                ATTR_STOP_LAT: monitor[0][8][0],
                ATTR_STOP_LNG: monitor[0][8][1],
            }
        return self.info

    def get_bus_gps(self, info, api_key):

        from google.transit import gtfs_realtime_pb2

        """Get the latest data from Transport NSW."""
        self.route = info['route']
        self.location = [ info[ATTR_STOP_LAT], info[ATTR_STOP_LNG]]
        self.api_key = api_key

        self.info = info
        self.bus = {
                    ATTR_BUS_LAT: 'n/a',
                    ATTR_BUS_LNG: 'n/a'
        }

        if(info['mode'].lower() != "bus" ):
          logger.warning("GPS location only available for busses")
          return self.bus


        # Build the URL including the STOP_ID and the API key
        url = \
            'https://api.transport.nsw.gov.au/v1/gtfs/vehiclepos/buses'
        auth = 'apikey ' + self.api_key
        header = {'Authorization': auth}

        # Send query or return error
        try:
            response = requests.get(url, headers=header, timeout=100)
        except:
            logger.warning("Network or Timeout error")
            return self.bus

        # If there is no valid request
        if response.status_code != 200:
            logger.warning("Error with the request sent; check api key")
            return self.bus

        # Parse the response feed as a Protobuffer object
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(response.content)

        buses = []
        for entity in feed.entity:

            # the third item in the id is the bus number (route)
            if (entity.id.split('_')[3] == self.route):


                bus = {
                    #ATTR_ID: entity.id,
                    ATTR_BUS_LAT: entity.vehicle.position.latitude,
                    ATTR_BUS_LNG: entity.vehicle.position.longitude
                    # ATTR_BEARING: entity.vehicle.position.bearing,
                    # ATTR_SPEED: entity.vehicle.position.speed
                }

                # all of these buses are for this route
                buses.append(bus);

                # print(entity.id,
                #       entity.vehicle.position.latitude,
                #       entity.vehicle.position.longitude,
                #       entity.vehicle.position.bearing,
                #       entity.vehicle.position.speed
                #      )

        # If there is no stop events for the query
        if len(buses) < 1:
            logger.warning("No bus locations currently found for this route")
            return self.bus

        # find the correct (closest) bus to the stop
        self.bus = self.get_closest_bus(buses, self.location);
        print(self.bus)
        return self.bus;



    def get_closest_bus(self, buses, location):
        from math import sin, cos, sqrt, atan2, radians

        closest = {
          'bus': 'n/a',
          'distance': 'n/a'
        }

        for bus in buses:
            # approximate radius of earth in km
            R = 6373.0

            lat1 = bus[ATTR_BUS_LAT]
            lon1 = bus[ATTR_BUS_LNG]
            lat2 = location[0]
            lon2 = location[1]

            dlon = lon2 - lon1
            dlat = lat2 - lat1

            a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
            c = 2 * atan2(sqrt(a), sqrt(1 - a))

            distance = R * c # km

            if closest['distance'] == 'n/a' or distance < closest['distance']:
                closest = {
                    'bus': bus,
                    'distance': distance
                }

        return closest['bus']




    def parseEvent(self, result, i):

        """Parse the current event and extract data."""
        fmt = '%Y-%m-%dT%H:%M:%SZ'
        due = 0
        delay = 0
        real_time = 'n'
        number = result['stopEvents'][i]['transportation']['number']
        planned = datetime.strptime(result['stopEvents'][i]
            ['departureTimePlanned'], fmt)
        destination = result['stopEvents'][i]['transportation']['destination']['name']
        mode = self.get_mode(result['stopEvents'][i]['transportation']['product']['class'])
        estimated = planned
        if 'isRealtimeControlled' in result['stopEvents'][i]:
            real_time = 'y'
            estimated = datetime.strptime(result['stopEvents'][i]
                ['departureTimeEstimated'], fmt)
        stop_location = result['stopEvents'][i]['location']['coord']
        # Only deal with future leave times
        if estimated > datetime.utcnow():
            due = self.get_due(estimated)
            delay = self.get_delay(planned, estimated)
            return[
                number,
                due,
                delay,
                planned,
                estimated,
                real_time,
                destination,
                mode,
                stop_location
                ]
        else:
            return None

    def get_due(self, estimated):
        """Min till next leave event."""
        due = 0
        due = round((estimated - datetime.utcnow()).seconds / 60)
        return due

    def get_delay(self, planned, estimated):
        """Min of delay on planned departure."""
        delay = 0                   # default is no delay
        if estimated >= planned:    # there is a delay
            delay = round((estimated - planned).seconds / 60)
        else:                       # leaving earlier
            delay = round((planned - estimated).seconds / 60) * -1
        return delay

    def get_mode(self, iconId):
        """Map the iconId to proper modes string."""
        modes = {
            1: "Train",
            4: "Lightrail",
            5: "Bus",
            7: "Coach",
            9: "Ferry",
            11: "Schoolbus"
        }
        return modes.get(iconId, None)
