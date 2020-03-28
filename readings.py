import asyncio
from datetime import datetime, timedelta
import requests, json
from common import read_line_from
from ui import Label

GET_TIMEOUT = 20
REFRESH_INTERVAL = 10 # in seconds
CACHE_LIFE = timedelta(minutes = 20)
URL = read_line_from('sensors_url.txt')
URL_OUT = URL + '/get?json'
URL_OUT_AVG = URL + '/get?json&days=1' # average for last day
URL_IN = URL + '/get?client=rasp_c&json'
KEYS = {
    'client': 'Client',
    'timestamp_pretty': 'When',
    # 'bme_humidity': 'Humidity',
    # 'bme_pressure': 'Pressure',
    'ds18_short_temp': 'Outside temp',
    'ds18_long_temp': 'Inside temp',
    'pm25_aqi_label': 'PM2.5 label',
    'pm25_aqi_label_avg': 'PM2.5 label day avg',
    'pm10_aqi_label': 'PM10 label',
    'pm10_aqi_label_avg': 'PM10 label day avg',
}

class readings:
    def get_data(self):
        outside, avg_outside, inside = [
            requests.get(u, timeout = GET_TIMEOUT).json() \
            for u in [ URL_OUT, URL_OUT_AVG, URL_IN ]
        ]

        return outside, avg_outside, inside

    def format(self, json):
        output = ''

        # get sorting from KEYS
        for key, value in KEYS.items():
            if key in json:
                output += '%s: %s\n' % (value, json[key])

        return output

    def update_readings(self):
        outside, avg_outside, inside = self.get_data()

        # Add labels per last day average.
        outside['pm25_aqi_label_avg'] = avg_outside['pm25_aqi_label']
        outside['pm10_aqi_label_avg'] = avg_outside['pm10_aqi_label']

        self.queue.put((Label.rasp_b, self.format(outside)))
        self.queue.put((Label.rasp_c, self.format(inside)))
        self.last_update = datetime.now()

    def cache_old(self):
        now = datetime.now()
        if now - self.last_update > CACHE_LIFE:
            return True

        return False

    # We get these readings from the _home-sensors_ project, which is served on
    # a free-quota-using Google Cloud server. In order to remain within the free
    # quota indefinitely, let's try to hit it as less frequently as possible. We
    # can use two ways of achieving that:
    #   1. Use a cache for the readings received - considering their values
    #   don't currently get updated often, it's OK to have this set at a
    #   CACHE_LIFE time delta.
    #   2. Only update the cache while the monitor showing it is actually
    #   powered (regardless of its routine).
    async def update_state(self):
        while True:
            now = datetime.now()

            monitor_on = self.monitor.status()
            if monitor_on and self.cache_old():
                tries = 3 # to connect with server
                for i in range(tries):
                    try:
                        print('Readings cache expired @', datetime.now())

                        # TODO: spawn a new thread; then do this:
                        self.update_readings()

                        print('Updated readings @', self.last_update)

                        break
                    except (requests.exceptions.RequestException,
                            ValueError): # includes JSONDecodeError

                        # OK, so maybe no Internet then? Display an error and
                        # carry on trying.
                        self.queue.put((
                            Label.rasp_b,
                            'Error getting data, try: %i' % (i + 1)
                        ))

            await asyncio.sleep(REFRESH_INTERVAL)

    def __init__(self, monitor, queue):
        self.monitor = monitor
        self.queue = queue
        self.last_update = datetime.min
