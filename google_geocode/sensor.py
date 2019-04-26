"""
Support for Google Geocode sensors.

For more details about this platform, please refer to the documentation at
https://github.com/fsteccanella/GoogleGeocode-HASS
"""
from datetime import datetime
from datetime import timedelta 
import logging
import json
import requests
from requests import get

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_API_KEY, CONF_NAME, CONF_SCAN_INTERVAL, EVENT_HOMEASSISTANT_START, ATTR_ATTRIBUTION, ATTR_LATITUDE, ATTR_LONGITUDE, ATTR_ENTITY_PICTURE)
import homeassistant.helpers.location as location
from homeassistant.util import Throttle
from homeassistant.helpers.entity import Entity
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

CONF_ORIGIN = 'origin'
CONF_OPTIONS = 'options'
CONF_DISPLAY_ZONE = 'display_zone'
CONF_ATTRIBUTION = "Data provided by maps.google.com"
CONF_GRAVATAR = 'gravatar'

ATTR_STREET_NUMBER = "Street Number"
ATTR_STREET = 'Street'
ATTR_CITY = 'City'
ATTR_POSTAL_TOWN = "Postal Town"
ATTR_POSTAL_CODE = "Postal Code"
ATTR_REGION = 'State'
ATTR_COUNTRY = 'Country'
ATTR_COUNTY = 'County'
ATTR_FORMATTED_ADDRESS = "Formatted Address"

DEFAULT_STATE = "Awaiting Update"
DEFAULT_NAME = "Google Geocode"
DEFAULT_OPTION = "street, city"
DEFAULT_DISPLAY_ZONE = 'display'
DEFAULT_KEY = "no key"

SCAN_INTERVAL = timedelta(seconds=60)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_ORIGIN): cv.string,
    vol.Optional(CONF_API_KEY, default=DEFAULT_KEY): cv.string,
    vol.Optional(CONF_OPTIONS, default=DEFAULT_OPTION): cv.string,
    vol.Optional(CONF_DISPLAY_ZONE, default=DEFAULT_DISPLAY_ZONE): cv.string,
    vol.Optional(CONF_GRAVATAR, default=None): vol.Any(None, cv.string),
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_SCAN_INTERVAL, default=SCAN_INTERVAL):
        cv.time_period,
})

TRACKABLE_DOMAINS = ['device_tracker', 'sensor', 'person']

def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the sensor platform."""
    def run_setup(event):
        """
        Delay the setup until Home Assistant is fully initialized.
        This allows any entities to be created already
        """
        name = config.get(CONF_NAME)
        api_key = config.get(CONF_API_KEY)
        origin = config.get(CONF_ORIGIN)
        options = config.get(CONF_OPTIONS)
        display_zone = config.get(CONF_DISPLAY_ZONE)
        gravatar = config.get(CONF_GRAVATAR) 

        if origin.split('.', 1)[0] in TRACKABLE_DOMAINS:
            add_devices([GoogleGeocode(hass, origin, name, api_key, options, display_zone, gravatar)])
        else:
            _LOGGER.error("You have defined an untrackable entity as origin.")
    
     # Wait until start event is sent to load this component.
    hass.bus.listen_once(EVENT_HOMEASSISTANT_START, run_setup)


class GoogleGeocode(Entity):
    """Representation of a Google Geocode Sensor."""

    def __init__(self, hass, origin, name, api_key, options, display_zone, gravatar):
        """Initialize the sensor."""
        self._hass = hass
        self._origin_entity_id = origin
        self._name = name
        self._api_key = api_key
        self._options = options.lower()
        self._display_zone = display_zone.lower()
        
        self._set_state(DEFAULT_STATE)
        self._street_number = None
        self._street = None
        self._city = None
        self._postal_town = None
        self._postal_code = None
        self._city = None
        self._region = None
        self._country = None
        self._county = None
        self._formatted_address = None
        self._latlong = None
 
        if gravatar is not None:
            self._picture = self._get_gravatar_for_email(gravatar)
        else:
            self._picture = self._get_picture_from_entity()


    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def entity_picture(self):
        """Return the picture of the device."""
        return self._picture
        
    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return{
            ATTR_STREET_NUMBER: self._street_number,
            ATTR_STREET: self._street,
            ATTR_CITY: self._city,
            ATTR_POSTAL_TOWN: self._postal_town,
            ATTR_POSTAL_CODE: self._postal_code,
            ATTR_REGION: self._region,
            ATTR_COUNTRY: self._country,
            ATTR_COUNTY: self._county,
            ATTR_FORMATTED_ADDRESS: self._formatted_address,
            ATTR_ATTRIBUTION: CONF_ATTRIBUTION
        }

    @Throttle(SCAN_INTERVAL)
    def update(self):
        """Get the latest data and updates the states."""
        entity_latlong = self._get_location_from_entity()

        _LOGGER.debug("Entity: "+str(self._origin_entity_id))
        _LOGGER.debug("Old latlong: "+str(self._latlong))
        _LOGGER.debug("New latlong: "+str(entity_latlong))

        """Update if location has changed."""
        if entity_latlong == None:
            _LOGGER.debug("Location empty...resetting attributes")
            self._set_state(DEFAULT_STATE)
            self._reset_attributes()
            pass
        if entity_latlong == self._latlong:
            _LOGGER.debug("Location not changed...")
            pass
        else:
            _LOGGER.debug("Location changed...updating")
            self._reset_attributes()
            if self._api_key == 'no key':
                url = "https://maps.google.com/maps/api/geocode/json?latlng=" + entity_latlong
            else:
                url = "https://maps.googleapis.com/maps/api/geocode/json?latlng=" + entity_latlong + "&key=" + self._api_key
            response = get(url)
            json_input = response.text
            decoded = json.loads(json_input)
            street_number = ''
            street = 'Unnamed Road'
            alt_street = 'Unnamed Road'
            city = ''
            postal_town = ''
            formatted_address = ''
            state = ''
            county = ''
            country = ''


            if 'error_message' in decoded:
                self._state = decoded['error_message']
                _LOGGER.error("You have exceeded your daily requests or entered a incorrect key please create or check the api key.")
            else:
                for result in decoded["results"]:
                    for component in result["address_components"]:
                        if 'street_number' in component["types"]:
                            street_number = component["long_name"]
                            self._street_number = street_number
                        if 'route' in component["types"]:
                            street = component["long_name"]
                            self._street = street
                        if 'sublocality_level_1' in component["types"]:
                            alt_street = component["long_name"]
                        if 'postal_town' in component["types"]:
                            postal_town = component["long_name"]
                            self._postal_town = postal_town
                        if 'locality' in component["types"]:
                            city = component["long_name"]
                            self._city = city
                        if 'administrative_area_level_1' in component["types"]:
                            state = component["long_name"]
                            self._region = state
                        if 'administrative_area_level_2' in component["types"]:
                            county = component["long_name"]
                            self._county = county
                        if 'country' in component["types"]:
                            country = component["long_name"]
                            self._country = country
                        if 'postal_code' in component["types"]:
                            postal_code = component["long_name"]
                            self._postal_code = postal_code

                try:
                    if 'formatted_address' in decoded['results'][0]:
                        formatted_address = decoded['results'][0]['formatted_address']
                        self._formatted_address = formatted_address
                except IndexError:
                    pass

                if street == 'Unnamed Road':
                    street = alt_street
                    self._street = alt_street
                if city == '':
                    city = postal_town
                    if city == '':
                        city = county

                
                user_display = []

                if "street_number" in self._options:
                    self._append_to_user_display(user_display,street_number)
                if "street" in self._options:
                    self._append_to_user_display(user_display,street)
                if "city" in self._options:
                    self._append_to_user_display(user_display,city)
                if "county" in self._options:
                    self._append_to_user_display(user_display,county)
                if "state" in self._options:
                    self._append_to_user_display(user_display,state)
                if "postal_code" in self._options:
                    self._append_to_user_display(user_display,postal_code)
                if "country" in self._options:
                    self._append_to_user_display(user_display,country)
                if "formatted_address" in self._options:
                    self._append_to_user_display(user_display,formatted_address)

                if user_display == []:
                    self._append_to_user_display(user_display,city)
                        
                user_display = ', '.join(  x for x in user_display )
                
                self._set_state(user_display)

                self._latlong = entity_latlong

    def _reset_attributes(self):
        """Resets attributes."""
        self._street = None
        self._street_number = None
        self._city = None
        self._postal_town = None
        self._postal_code = None
        self._region = None
        self._country = None
        self._county = None
        self._formatted_address = None

    def _set_state(self, user_display):
        entity_zone = self._get_zone_from_entity()

        if self._display_zone != 'hide' and entity_zone != None and entity_zone != 'not_home':
            _LOGGER.debug("Using entity zone as state")
            self._state = entity_zone[0].upper() + entity_zone[1:]
        else:
            _LOGGER.debug("Using retrieved location as state")
            self._state = user_display

    def _get_location_from_entity(self):
        """Get the origin from the entity state or attributes."""
        entity = self._hass.states.get(self._origin_entity_id)

        if entity is None:
            _LOGGER.error("Unable to find entity %s", self._origin_entity_id)
            return None

        # Check if the entity has origin attributes
        if location.has_location(entity):
            return "%s,%s" % (entity.attributes.get(ATTR_LATITUDE), entity.attributes.get(ATTR_LONGITUDE))

        # When everything fails just return nothing
        return None

    def _get_picture_from_entity(self):
        """Get the picture from the entity."""
        entity = self._hass.states.get(self._origin_entity_id)

        if entity is None:
            _LOGGER.error("Unable to find entity %s", self._origin_entity_id)
            return None

        return entity.attributes.get(ATTR_ENTITY_PICTURE)

    def _get_zone_from_entity(self):
        """Get the zone from the entity."""
        entity = self._hass.states.get(self._origin_entity_id)

        if entity is None:
            _LOGGER.error("Unable to find entity %s", self._origin_entity_id)
            return None

        return entity.state

    @staticmethod
    def _append_to_user_display(user_display, append_check):
        """Appends attribute to state if false."""
        if append_check == "":
            pass
        else:
            user_display.append(append_check)
        
    @staticmethod
    def _get_gravatar_for_email(email: str):
        """Return an 80px Gravatar for the given email address.
        Async friendly.
        """
        import hashlib
        url = 'https://www.gravatar.com/avatar/{}.jpg?s=80&d=wavatar'
        return url.format(hashlib.md5(email.encode('utf-8').lower()).hexdigest())
