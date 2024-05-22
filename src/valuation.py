import json
import math
import numpy as np
from scipy.interpolate import griddata
from typing import Callable, List, Set
from src.cache import Cache
from src.logger import Logger
from src.search import SearchParameters, Property, GeoLocation, PurchaseCategory


class ValuationParameters:
    """
        A class to hold valuation parameters.
    """

    def __init__(
            self, 
            min_deposit: int,
            max_deposit: int,
            mortgage_length: int,
            mortgage_interest_rate: float,
            investment_increase: int,
            investment_deduction: int,
            rent_increase: int,
            rent_deduction: int
        ) -> None:
        self.min_deposit = min_deposit
        self.max_deposit = max_deposit
        self.mortgage_length = mortgage_length
        self.mortgage_interest_rate = mortgage_interest_rate
        self.investment_increase = investment_increase
        self.investment_deduction = investment_deduction
        self.rent_increase = rent_increase
        self.rent_deduction = rent_deduction

    def __repr__(self) -> str:
        return (
            'ValuationParameters(' +
            f'min_deposit={self.min_deposit}, ' +
            f'max_deposit={self.max_deposit}, ' +
            f'mortgage_length={self.mortgage_length}, ' +
            f'mortgage_interest_rate={self.mortgage_interest_rate}, ' +
            f'investment_increase={self.investment_increase}, ' +
            f'investment_deduction={self.investment_deduction}, ' +
            f'rent_increase={self.rent_increase}, ' +
            f'rent_deduction={self.rent_deduction}' +
            ')'
        )

class Valuation:
    """
        A class to hold valuation data.
    """

    def __init__(self, property: Property, estimated_rental_income: float, return_on_investment: float) -> None:
        self.property = property
        self.estimated_rental_income = estimated_rental_income
        self.return_on_investment = return_on_investment

    def __repr__(self) -> str:
        return (
            'Valuation(' +
            f'property={self.property}, ' +
            f'estimated_rental_income={self.estimated_rental_income}, ' +
            f'return_on_investment={self.return_on_investment}' +
            ')'
        )

class ValuationEngine:
    """
        A class to handle valuation-related functionality.
    """

    def __init__(self, cache: Cache, logger: Logger) -> None:
        self._cache = cache
        self._logger = logger

    def rank_properties(self, params: SearchParameters, valuation_params: ValuationParameters, find_properties: Callable[[SearchParameters], List[Property]]) -> List[Valuation]:
        """
            This function ranks the properties based on highest return on investment.
        """
        self._logger.info(f"Ranking properties for search {params.location_name} with radius {params.radius} km")

        # Construct the cache key
        url = params.to_buy().to_url()
        key = f"valuation:{url.value()}-{valuation_params}"

        # Attempt to load the data from the cache
        self._logger.info(f"Attempting to load valuations from cache: \"{key}\"")
        try:
            payload = self._cache.get(key)
            if payload is not None:
                self._logger.info(f"Loaded payload for valuations from cache: \"{key}\"")
                return self._convert_payload_to_valuations(payload)
            self._logger.info(f"No valuation data found in cache: \"{key}\"")
        except Exception as e:
            # Failed to load the data from the cache
            self._logger.warning(f"Failed to load valuations from cache: \"{key}\". Error: {e}")
        
        # Create valuation data
        self._logger.info(f"Creating valuations")
        rent_properties = find_properties(params.to_rent())
        buy_properties = find_properties(params.to_buy())
        valuations = self._get_valuation(rent_properties, buy_properties, valuation_params)
        try:
            # Save the data to the cache
            self._logger.info(f"Saving valuations to cache: \"{key}\"")
            payload = self._convert_valuations_to_payload(valuations)
            self._cache.set(key, json.dumps(payload), 30 * 60)
        except Exception as e:
            # Failed to save the data to the cache
            self._logger.warning(f"Failed to save valuations to cache: \"{key}\". Error: {e}")

        return valuations

    def _get_valuation(self, rent_properties: List[Property], buy_properties: List[Property], valuation_params: ValuationParameters) -> List[Valuation]:
        if len(rent_properties) == 0 or len(buy_properties) == 0:
            return []
        
        rent_prices = [property.price for property in rent_properties]
        filtered_rent_prices = remove_outliers(rent_prices)
        rent_properties = [property for property in rent_properties if property.price in filtered_rent_prices]
        rent_prices = [property.price for property in rent_properties]
        
        self.points = [
            (property.geo_location.longitude, property.geo_location.latitude)
            for property in rent_properties
        ]
        min_lon, max_lon = min(property.geo_location.longitude for property in rent_properties), max(property.geo_location.longitude for property in rent_properties)
        min_lat, max_lat = min(property.geo_location.latitude for property in rent_properties), max(property.geo_location.latitude for property in rent_properties)
        self.points.extend([(min_lon, min_lat), (max_lon, min_lat), (min_lon, max_lat), (max_lon, max_lat)])
        self.values = [property.price for property in rent_properties]
        self.average_price = sum(self.values) / len(self.values)
        self.values.extend([self.average_price, self.average_price, self.average_price, self.average_price])

        valuations = []
        for property in buy_properties:
            try:
                valuations.append(Valuation(
                    property=property,
                    estimated_rental_income=self.get_height(property.geo_location.longitude, property.geo_location.latitude),
                    return_on_investment=self.get_score(property, valuation_params),
                ))
            except ValueError as e:
                self._logger.warning(f"Failed to get score for property: {property.display_address}. Error: {e}")

        return sorted(valuations, key=lambda valuation: -valuation.return_on_investment)

    def get_height(self, x, y):
        try:
            value = griddata(self.points, self.values, (x, y), method='linear')
        except ValueError:
            value = self.average_price
        if str(value) == 'nan':
            return float(self.average_price)
        return float(value)

    def get_score(self, property: Property, valuation_params: ValuationParameters) -> float:
        rent_price = self.get_height(property.geo_location.longitude, property.geo_location.latitude)
        property_price = property.price
        deposit = valuation_params.max_deposit
        mortgage_percentage = valuation_params.mortgage_interest_rate
        mortgage_length = valuation_params.mortgage_length
        net_investment_increase = valuation_params.investment_increase - valuation_params.investment_deduction
        net_rent_increase = valuation_params.rent_increase - valuation_params.rent_deduction
        r = mortgage_percentage / (12 * 100)
        n = mortgage_length * 12
        p = max(property_price - deposit, 0)

        if r == 0:
            raise ValueError("Mortgage percentage cannot be zero")

        monthly_mortgage = p * r * math.pow(1+r, n)/(math.pow(1+r, n) - 1)
        net_annual_income = (rent_price + net_rent_increase - monthly_mortgage) * 12
        cost = deposit + net_investment_increase

        if cost == 0:
            raise ValueError("Cost cannot be zero")

        return_on_investment = round(float(100 * net_annual_income / cost), 2)
        return return_on_investment
    
    @staticmethod
    def _convert_payload_to_valuations(payload: str) -> List[Valuation]:
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
            if "estimated_rental_income" not in obj:
                raise ValueError("property object is missing estimated_rental_income key")
            if "return_on_investment" not in obj:
                raise ValueError("property object is missing return_on_investment key")
            if "image_url" not in obj:
                raise ValueError("property object is missing image_url key")
            properties.append(Valuation(
                property=Property(
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
                ),
                estimated_rental_income=obj["estimated_rental_income"],
                return_on_investment=obj["return_on_investment"],
            ))
        return properties

    @staticmethod
    def _convert_valuations_to_payload(valuations: List[Valuation]) -> str:
        output = []
        for valuation in valuations:
            output.append({
                "identifier": valuation.property.identifier,
                "display_address": valuation.property.display_address,
                "price": valuation.property.price,
                "geo_location": {
                    "latitude": valuation.property.geo_location.latitude,
                    "longitude": valuation.property.geo_location.longitude,
                },
                "purchase_category": valuation.property.purchase_category.value,
                "estimated_rental_income": valuation.estimated_rental_income,
                "return_on_investment": valuation.return_on_investment,
                "image_url": valuation.property.image_url,
            })
        return json.dumps(output)
    
def getHeight(properties: Set[Property], width: int, height: int):
    if len(properties) == 0:
        raise ValueError("No properties to plot.")
    prices = [property.price for property in properties]
    lons = [property.geo_location.longitude for property in properties]
    lats = [property.geo_location.latitude for property in properties]

    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)
    avg_price = sum(prices) / len(prices)
    avg_price = 0

    lon_diff = max_lon - min_lon
    lat_diff = max_lat - min_lat

    points = list()
    values = list()
    for property in properties:
        points.append((
            (property.geo_location.longitude - min_lon) / lon_diff * width, 
            (property.geo_location.latitude - min_lat) / lat_diff * height, 
        ))
        values.append(property.price)
    
    points.extend([(0, 0), (width, 0), (0, height), (width, height)])
    values.extend([avg_price, avg_price, avg_price, avg_price])

    def f(x, y):
        return griddata(points, values, (x, y), method='cubic')

    return f

def remove_outliers(data, threshold=1.5):
    """
    Remove outliers from data using the IQR method.
    """
    data = np.array(data)
    q1 = np.percentile(data, 25)
    q3 = np.percentile(data, 75)
    iqr = q3 - q1
    lower_bound = q1 - (iqr * threshold)
    upper_bound = q3 + (iqr * threshold)
    return [x for x in data if lower_bound <= x <= upper_bound]