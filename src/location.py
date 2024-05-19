import json
import requests
from urllib.parse import quote
from typing import List

from src.cache import Cache
from src.logger import Logger


class Location:
    """
        A class to hold location data.
    """

    def __init__(self, display_name: str, identifier: str, normalised_name: str):
        self.display_name = display_name
        self.identifier = identifier
        self.normalised_name = normalised_name

    def __repr__(self) -> str:
        return f'Location(display_name="{self.display_name}", identifier="{self.identifier}", normalised_name="{self.normalised_name}")'

class LocationEngine:
    """
        A class to handle location-related functionality.
    """

    def __init__(self, cache: Cache, logger: Logger) -> None:
        self._cache = cache
        self._logger = logger

    def find_locations(self, location_input: str):
        """
            This function finds locations based on the input string.
        """
        self._logger.info(f"Finding locations for: {location_input}")

        # Construct the cache key
        key = f"location:{location_input.lower()}"
        
        # Attempt to load the data from the cache
        self._logger.info(f"Attempting to load locations from cache: \"{key}\"")
        try:
            payload = self._cache.get(key)
            if payload is not None:
                self._logger.info(f"Loaded payload for locations from cache: \"{key}\"")
                return self._convert_payload_to_locations(payload)
            self._logger.info(f"No location data found in cache: \"{key}\"")
        except Exception as e:
            # Failed to load the data from the cache
            self._logger.warning(f"Failed to load locations from cache: \"{key}\". Error: {e}")
        
        # Fetch the data from the Rightmove API
        self._logger.info(f"Fetching locations from Rightmove API")
        locations = self._fetch_locations(location_input)
        try:
            # Save the data to the cache
            self._logger.info(f"Saving locations to cache: \"{key}\"")
            payload = self._convert_locations_to_payload(locations)
            self._cache.set(key, json.dumps(payload), 30 * 60)
        except Exception as e:
            # Failed to save the data to the cache
            self._logger.warning(f"Failed to save locations to cache: \"{key}\". Error: {e}")

        return locations

    def _convert_payload_to_locations(self, payload: str) -> List[Location]:
        output = json.loads(payload)
        if not isinstance(output, list):
            raise ValueError("Expected a list of location objects")
        locations = []
        for obj in output:
            if not isinstance(obj, dict):
                raise ValueError("Location object to be a dictionary")
            if "display_name" not in obj:
                raise ValueError("location object is missing display_name key")
            if "identifier" not in obj:
                raise ValueError("location object is missing identifier key")
            if "normalised_name" not in obj:
                raise ValueError("location object is missing normalised_name key")
            locations.append(Location(
                display_name=obj["display_name"],
                identifier=obj["identifier"],
                normalised_name=obj["normalised_name"],
            ))
        return locations
    
    def _convert_locations_to_payload(self, locations: List[Location]) -> str:
        output = []
        for location in locations:
            output.append({
                "display_name": location.display_name,
                "identifier": location.identifier,
                "normalised_name": location.normalised_name,
            })
        return json.dumps(output)
    
    def _construct_url(self, location_input: str) -> str:
        """
            This function constructs the URL for the location query.
            The URL must be of the format: https://www.rightmove.co.uk/typeAhead/uknostreet/AB/CD/DE/FG
            where AB, CD, DE, FG are pairs of characters from the location input.
        """
        
        # Capitalize the string
        capitalized_string = location_input.upper()
        
        # Split the string into pairs
        pairs = []
        for i in range(0, len(capitalized_string), 2):
            if i + 1 < len(capitalized_string):
                pairs.append(capitalized_string[i:i+2])
            else:
                pairs.append(capitalized_string[i])

        # URL encode the pairs
        encoded_pairs = [quote(pair) for pair in pairs]
        
        # Create the full URL
        return f"https://www.rightmove.co.uk/typeAhead/uknostreet/{'/'.join(encoded_pairs)}"
    
    def _fetch_locations(self, location_input) -> List[Location]:
        """
            This function fetches the location data from the Rightmove API.
        """

        # Construct the URL
        url = self._construct_url(location_input)

        # Perform the GET request
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }

        # Send the request
        self._logger.info(f"Sending GET request to: {url}")
        response = requests.get(url, headers=headers)
        self._logger.info(f"Received response: {response.status_code}")
        
        # Raises an HTTPError for bad responses
        response.raise_for_status()

        # Parse the JSON data
        data = response.json()

        # Extract the typeAheadLocations and convert them into Location objects
        locations = [
            Location(
                display_name=item['displayName'],
                identifier=item['locationIdentifier'],
                normalised_name=item['normalisedSearchTerm']
            )
            for item in data['typeAheadLocations']
        ]

        return locations