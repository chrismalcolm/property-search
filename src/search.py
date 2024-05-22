from bs4 import BeautifulSoup
from enum import Enum
import json
import re
import requests
from typing import List, Set
from src.cache import Cache
from src.location import Location
from src.logger import Logger


# Enum for specifying different types of property available for search.
# Student Halls is RENT only
class PropertyType(Enum):
    FLAT = "flat"
    DETACHED = "detached"
    SEMI_DETACHED = "semi-detached"
    TERRACE = "terraced"
    BUNGALOW = "bungalow"
    PARK_HOME = "park-home"
    LAND = "land"
    STUDENT_HALLS = "private-halls"

# Set of all property types
AllPropertyTypes = {
    PropertyType.FLAT, 
    PropertyType.DETACHED, 
    PropertyType.SEMI_DETACHED, 
    PropertyType.TERRACE, 
    PropertyType.BUNGALOW, 
    PropertyType.PARK_HOME, 
    PropertyType.LAND, 
    PropertyType.STUDENT_HALLS
}

# Enum for must-have features in the property search criteria.
class MustHave(Enum):
    AUCTION = "auction"
    GARDEN = "garden"
    PARKING = "parking"
    NEW_HOME = "newHome"
    RETIREMENT = "retirement"
    SHARED_OWNERSHIP = "sharedOwnership"

# Enum for excluding certain features in the property search criteria.
class DontShow(Enum):
    NEW_HOME = "newHome"
    RETIREMENT = "retirement"
    SHARED_OWNERSHIP = "sharedOwnership"

# Enum for specifying different types of property available for search.
# FurnishType is RENT only.
class FurnishType(Enum):
    FURNISHED = "furnished"
    PART_FURNISHED = "partFurnished"
    UNFURNISHED = "unfurnished"

# Set of all furnish types
AllFurnishTypes = {
    FurnishType.FURNISHED,
    FurnishType.PART_FURNISHED,
    FurnishType.UNFURNISHED
}

# Enum for specifying different types of property available for search.
class PurchaseCategory(Enum):
    BUY = "buy"
    RENT = "rent"

class IntRange:
    """
        This class represents an integer range.

        Min or max can also be None to represent no limit.
    """

    def __init__(self, min: int|None, max: int|None):
        if min is not None and min < 0:
            raise ValueError("Minimum value cannot be negative.")
        if max is not None and max < 0:
            raise ValueError("Maximum value cannot be negative.")
        if min is not None and max is not None and min > max:
            raise ValueError("Minimum value cannot be greater than the maximum value.")
        self.min = min
        self.max = max

    def __repr__(self) -> str:
        return f'IntRange(min={self.min}, max={self.max})'

class URL:
    """
        This class represents a URL for a Rightmove search query.
    """

    def __init__(self, url: str, purchase_category: PurchaseCategory):
        self.url = url
        self.purchase_category = purchase_category

    def value(self, index: int|None = None, properties_per_page: int|None = None) -> str:
        if index is not None and properties_per_page is not None:
            return f"{self.url}&index={index}&numberOfPropertiesPerPage={properties_per_page}"
        if properties_per_page is not None and (index == 0 or index is None):
            return f"{self.url}&numberOfPropertiesPerPage={properties_per_page}"
        return self.url

class GeoLocation:
    """
        This class represents a geographical location with latitude and longitude coordinates.
    """

    def __init__(self, latitude: float, longitude: float):
        self.latitude = latitude
        self.longitude = longitude

    def __repr__(self) -> str:
        return f'GeoLocation(latitude={self.latitude}, longitude={self.longitude})'

class Property:
    """
        This class represents a property listing.
    """

    def __init__(
            self,
            identifier: str,
            display_address: str,
            price: int,
            geo_location: GeoLocation,
            purchase_category: PurchaseCategory,
            image_url: str,
        ):
        self.identifier = identifier
        self.display_address = display_address
        self.price = price
        self.geo_location = geo_location
        self.purchase_category = purchase_category
        self.image_url = image_url

    def __repr__(self) -> str:
        return f'Property(identifier={self.identifier}, display_address="{self.display_address}"), ' + \
        f'price={self.price}, location={self.geo_location}, purchase_category={self.purchase_category})'
    
    def href(self) -> str:
        if self.purchase_category == PurchaseCategory.BUY:
            return f"https://www.rightmove.co.uk/properties/{self.identifier}#/?channel=RES_BUY"
        return f"https://www.rightmove.co.uk/properties/{self.identifier}#/?channel=RES_LET"
    
    def set_roi(self, roi: float) -> None:
        self.roi = roi

class SearchParameters:
    """
        This class represents the search parameters for a property search.
    """

    def __init__(
            self, 
            location: Location,
            radius: float, 
            price: IntRange, 
            bedrooms: IntRange, 
            max_days_since_added: int|None,
            property_types: Set[PropertyType],
            must_have: Set[MustHave],
            dont_show: Set[DontShow],
            furnish_types: Set[FurnishType],
            purchase_category: PurchaseCategory,
        ):
        if radius < 0:
            raise ValueError("Radius cannot be negative.")
        if max_days_since_added is not None and max_days_since_added < 0:
            raise ValueError("Maximum days since added cannot be negative.")
        self.location_name = location.display_name
        self.location_id = location.identifier
        self.radius = radius
        self.min_price = price.min if price.min is not None else ""
        self.max_price = price.max if price.max is not None else ""
        self.min_bedrooms = bedrooms.min if bedrooms.min is not None else ""
        self.max_bedrooms = bedrooms.max if bedrooms.max is not None else ""
        self.max_days_since_added = max_days_since_added if max_days_since_added is not None else ""
        self.property_types = sorted(list(property_types), key=lambda x: x.value)
        self.must_have = sorted(list(must_have), key=lambda x: x.value)
        self.dont_show = sorted(list(dont_show), key=lambda x: x.value)
        self.furnish_types = sorted(list(furnish_types), key=lambda x: x.value)
        self.purchase_category = purchase_category

    def to_buy(self) -> 'SearchParameters':
        self.purchase_category = PurchaseCategory.BUY
        return self

    def to_rent(self) -> 'SearchParameters':
        self.purchase_category = PurchaseCategory.RENT
        return self

    def to_url(self) -> URL:
        if self.purchase_category == PurchaseCategory.BUY:
            return self._url_property_for_sale()
        elif self.purchase_category == PurchaseCategory.RENT:
            return self._url_property_to_rent()
        else:
            raise ValueError("Invalid purchase category.")

    def _url_property_for_sale(self) -> URL:
        url = "https://www.rightmove.co.uk/property-for-sale/find.html?"
        url += f"locationIdentifier={self.location_id}&"
        url += f"radius={self.radius}&"
        url += f"minPrice={self.min_price}&"
        url += f"maxPrice={self.max_price}&"
        url += f"minBedrooms={self.min_bedrooms}&"
        url += f"maxBedrooms={self.max_bedrooms}&"
        url += f"maxDaysSinceAdded={self.max_days_since_added}&"
        url += f"propertyTypes={','.join(property_type.value for property_type in self.property_types)}&"
        url += f"mustHave={','.join(must_have.value for must_have in self.must_have)}&"
        url += f"dontShow={','.join(dont_show.value for dont_show in self.dont_show)}&"
        url += "includeSSTC=false"
        return URL(url, PurchaseCategory.BUY)
    
    def _url_property_to_rent(self) -> URL:
        url = "https://www.rightmove.co.uk/property-to-rent/find.html?"
        url += f"locationIdentifier={self.location_id}&"
        url += f"radius={self.radius}&"
        url += f"minBedrooms={self.min_bedrooms}&"
        url += f"maxBedrooms={self.max_bedrooms}&"
        url += f"maxDaysSinceAdded={self.max_days_since_added}&"
        url += f"propertyTypes={','.join(property_type.value for property_type in self.property_types)}&"
        url += f"mustHave={','.join(must_have.value for must_have in self.must_have)}&"
        url += f"dontShow={','.join(dont_show.value for dont_show in self.dont_show)}&"
        url += f"furnishTypes={','.join(furnish_type.value for furnish_type in self.furnish_types)}&"
        url += "includeLetAgreed=true"
        return URL(url, PurchaseCategory.RENT)

class SearchEngine:
    """
        This class represents a search engine for finding properties.
    """

    def __init__(self, cache: Cache, logger: Logger):
        self._cache = cache
        self._logger = logger

    def find_properties(self, params: SearchParameters) -> List[Property]:
        """
            This function searches for properties based on the search parameters.
            It first attempts to load the data from the cache. If the data is not found,
            it fetches the data from the Rightmove API and saves it to the cache.
        """
        self._logger.info(f"Searching for properties to {params.purchase_category.value} in {params.location_name} with radius {params.radius} km")

        # Construct the cache key
        url = params.to_url()
        key = f"properties:{url.value()}"
        
        # Attempt to load the data from the cache
        self._logger.info(f"Attempting to load properties from cache: \"{key}\"")
        try:
            payload = self._cache.get(key)
            if payload is not None:
                self._logger.info(f"Loaded payload for properties from cache: \"{key}\"")
                return self._convert_payload_to_properties(payload)
            self._logger.info(f"No property data found in cache: \"{key}\"")
        except Exception as e:
            # Failed to load the data from the cache
            self._logger.warning(f"Failed to load properties from cache: \"{key}\". Error: {e}")
        
        # Fetch the data from the Rightmove API
        self._logger.info(f"Fetching properties from Rightmove API")
        properties = self._fetch_properties(url)
        try:
            # Save the data to the cache
            self._logger.info(f"Saving properties to cache: \"{key}\"")
            payload = self._convert_properties_to_payload(properties)
            self._cache.set(key, json.dumps(payload), 30 * 60)
        except Exception as e:
            # Failed to save the data to the cache
            self._logger.warning(f"Failed to save properties to cache: \"{key}\". Error: {e}")

        buy_or_rent = "buy" if url.purchase_category == PurchaseCategory.BUY else "rent"
        self._logger.info(f"Found {len(properties)} properties to {buy_or_rent} in {params.location_name} with radius {params.radius} km")
        return properties
    
    def _fetch_properties(self, url: URL) -> list[Property]:

        # Variable to store properties
        properties = list()

        property_count = self._fetch_number_of_properties(url.value())

        property_count = min(property_count, 1000)

        # Fetch properties from each URL
        max_properties_per_page = 499
        for index in range(0, property_count, max_properties_per_page):
            properties.extend(self._fetch_property(url.value(index, max_properties_per_page), url.purchase_category))

        return properties
    
    def _fetch_number_of_properties(self, url: str) -> int:
        
        # Perform the GET request
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }

        # Send a GET request to the URLs
        self._logger.info(f"Sending GET request to {url}")
        response = requests.get(url, headers=headers)
        self._logger.info(f"Received response with status code {response.status_code}")

        # Raises an HTTPError for bad responses
        response.raise_for_status()

        # Parse the HTML content of the page
        soup = BeautifulSoup(response.content, 'html.parser')

        # Extract the number of properties
        property_count = 0
        result_count_spans = soup.find_all('span', class_='searchHeader-resultCount')
        if len(result_count_spans) == 0:
            raise ValueError("unable to find property result count")
        try:
            property_count = int(result_count_spans[0].text.replace(",", ""))
        except ValueError as e:
            raise ValueError(f'unable to parse property result count: {e}')
        if property_count < 0:
            raise ValueError("property result count is negative")

        return property_count

    def _fetch_property(self, url_str: str, purchase_category: PurchaseCategory) -> list[Property]:

        # Dictionary to store property prices and image urls
        property_prices = dict()
        property_image_urls = dict()

        # Perform the GET request
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }

        # Send a GET request to the URLs
        self._logger.info(f"Sending GET request to {url_str}")
        response = requests.get(url_str, headers=headers)
        self._logger.info(f"Received response with status code {response.status_code}")

        # Raises an HTTPError for bad responses
        response.raise_for_status()

        # Parse the HTML content of the page
        soup = BeautifulSoup(response.content, 'html.parser')

        # Extract property cards
        property_cards = soup.find_all('div', class_='propertyCard-wrapper')

        # Variations in the HTML structure for buy and rent pages
        buy = purchase_category == PurchaseCategory.BUY
        price_text_element = 'div' if buy else 'span'
        price_text_regex = r"£([\d,]+)\s*" if buy else r"£([\d,]+)\s*pcm"

        # Extract property data from each card
        for card in property_cards:
            try:
                property_href = card.find('a', class_='propertyCard-priceLink')['href']
                price_text = card.find(price_text_element, class_='propertyCard-priceValue').text.strip()
                image_url = card.find('img')["src"] if buy else ""
            except Exception:
                # Ignore property cards with missing data
                continue

            # Extract the property ID from the href
            match = re.search(r"/properties/(\d+)", property_href)
            if match:
                property_id = match.group(1)
            else:
                # Ignore properties without an ID
                continue

            # Extract the price from the text
            match = re.search(price_text_regex, price_text)
            if match:
                number_str = match.group(1)
                # Remove commas and convert to float
                price = float(number_str.replace(",", ""))
            else:
                # Ignore properties without a price
                continue

            property_prices[property_id] = price
            property_image_urls[property_id] = image_url

        # Iterate through script tags to get property geo location and display address
        # Property geo location and display address is present in the property metadata
        # which is a JSON object stored in the window.jsonModel variable
        properties = list()
        script_tags = soup.find_all('script')
        for script_tag in script_tags:
            # Check if the script contains window.jsonModel
            if 'window.jsonModel = ' not in script_tag.text:
                continue

            # Extract the JSON object from the window.jsonModel variable
            json_data = re.search(r'window.jsonModel = (.*)', script_tag.text).group(1)
            json_object = json.loads(json_data)
            property_metadata = json_object["properties"]

            # Extract property metadata and create Property objects
            for metadata in property_metadata :
                property_id = str(metadata["id"])
                if property_id not in property_prices:
                    continue
                properties.append(Property(
                    identifier=property_id,
                    display_address=metadata["displayAddress"],
                    price=property_prices[property_id],
                    geo_location=GeoLocation(
                        latitude=metadata["location"]["latitude"],
                        longitude=metadata["location"]["longitude"]
                    ),
                    purchase_category=purchase_category,
                    image_url=property_image_urls.get(property_id, "")
                ))
            break
        else:
            raise ValueError("unable to get property metadata")

        return properties
        
    @staticmethod
    def _convert_payload_to_properties(payload: str) -> List[Property]:
        output = json.loads(payload)
        if not isinstance(output, list):
            raise ValueError("Expected a list of property objects")
        properties = []
        for obj in output:
            if not isinstance(obj, dict):
                raise ValueError("Property object to be a dictionary")
            if "identifier" not in obj:
                raise ValueError("property object is missing identifier key")
            if "display_address" not in obj:
                raise ValueError("property object is missing display_address key")
            if "price" not in obj:
                raise ValueError("property object is missing price key")
            if "geo_location" not in obj:
                raise ValueError("property object is missing geo_location key")
            if "latitude" not in obj["geo_location"]:
                raise ValueError("geo_location object is missing latitude key")
            if "longitude" not in obj["geo_location"]:
                raise ValueError("geo_location object is missing longitude key")
            if "purchase_category" not in obj:
                raise ValueError("property object is missing purchase_category key")
            if "image_url" not in obj:
                raise ValueError("property object is missing image_url key")
            properties.append(Property(
                identifier=obj["identifier"],
                display_address=obj["display_address"],
                price=obj["price"],
                geo_location=GeoLocation(
                    latitude=obj["geo_location"]["latitude"], 
                    longitude=obj["geo_location"]["longitude"]
                ),
                purchase_category=PurchaseCategory(
                    obj["purchase_category"]
                ),
                image_url=obj["image_url"]
            ))
        return properties

    @staticmethod
    def _convert_properties_to_payload(properties: List[Property]) -> str:
        output = []
        for property in properties:
            output.append({
                "identifier": property.identifier,
                "display_address": property.display_address,
                "price": property.price,
                "geo_location": {
                    "latitude": property.geo_location.latitude,
                    "longitude": property.geo_location.longitude,
                },
                "purchase_category": property.purchase_category.value,
                "image_url": property.image_url,
            })
        return json.dumps(output)