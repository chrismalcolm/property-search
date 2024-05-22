from flask import Flask, render_template, request, jsonify
from rest_framework import status
from typing import List
from src.cache import Cache
from src.logger import Logger
from src.location import LocationEngine, Location
from src.search import SearchEngine, SearchParameters, IntRange, AllPropertyTypes, AllFurnishTypes, DontShow, PurchaseCategory
from src.valuation import ValuationEngine, Valuation, ValuationParameters


class App:
    """
        The main application class.
    """

    def __init__(self, cache: Cache, logger: Logger):
        self._server = Flask("Property Valuation App")
        self._location_engine = LocationEngine(cache, logger)
        self._search_engine = SearchEngine(cache, logger)
        self._valuation_engine = ValuationEngine(cache, logger)
        self._logger = logger

    def run(self, debug: bool = False):
        self._server.run(debug=debug)

    def set_routes(self):

        @self._server.route('/')
        def location_search():
            return render_template('location_search.html')
        
        @self._server.route('/properties')
        def property_search():
            identifier = request.args.get('identifier', 'REGION^87490')
            display_name = request.args.get('display_name', 'London')
            return render_template('property_search.html', identifier=identifier, display_name=display_name)
        
        @self._server.route('/locations', methods=['GET'])
        def get_locations():
            location_input = request.args.get('query', None)
            if location_input is None or location_input == '':
                return jsonify([])
            suggestions = self.get_location_suggestions(location_input) 
            return jsonify(suggestions)

        @self._server.route('/properties_data', methods=['POST'])
        def get_properties():

            # Validate the request
            try:
                min_price = validate('min_price', int)
                max_price = validate('max_price', int)
                min_bedrooms = validate('min_bedrooms', int)
                max_bedrooms = validate('max_bedrooms', int)
                min_deposit = validate('min_deposit', int)
                max_deposit = validate('max_deposit', int)
                mortgage_length = validate('mortgage_length', int)
                mortgage_interest_rate = validate('mortgage_interest_rate', float)
                investment_increase = validate('investment_increase', int)
                investment_deduction = validate('investment_deduction', int)
                rent_increase = validate('rent_increase', int)
                rent_deduction = validate('rent_deduction', int)
                identifier = validate('identifier', str)
                display_name = validate('display_name', str)
            except Exception as e:
                return str(e), status.HTTP_400_BAD_REQUEST

            # Get the property valuations
            location = Location(display_name=display_name, identifier=identifier, normalised_name="")

            search_params = SearchParameters(
                location=location,
                radius=0.25,
                price=IntRange(min=min_price, max=max_price),
                bedrooms=IntRange(min=min_bedrooms, max=max_bedrooms),
                max_days_since_added=None,
                property_types=AllPropertyTypes,
                must_have=set(),
                dont_show=set([DontShow.SHARED_OWNERSHIP]),
                furnish_types=AllFurnishTypes,
                purchase_category=PurchaseCategory.BUY,
            )

            valuation_params = ValuationParameters(
                min_deposit=min_deposit,
                max_deposit=max_deposit,
                mortgage_length=mortgage_length,
                mortgage_interest_rate=mortgage_interest_rate,
                investment_increase=investment_increase,
                investment_deduction=investment_deduction,
                rent_increase=rent_increase,
                rent_deduction=rent_deduction,
            )

            valuations = self.get_property_valuations(search_params, valuation_params)
            valuations.sort(key=lambda v: v.return_on_investment, reverse=True)
            
            # Return the property data
            properties = [
                {
                    "rank": i + 1,
                    "address": valuation.property.display_address,
                    "price": f"£{int(valuation.property.price):,}",
                    "estimated_rent": f"£{int(valuation.estimated_rental_income):,}",
                    "roi": f"{valuation.return_on_investment:.2f}%",
                    "longitude": valuation.property.geo_location.longitude,
                    "latitude": valuation.property.geo_location.latitude,
                    "image": valuation.property.image_url,
                    "href": valuation.property.href(),
                }
                for i, valuation in enumerate(valuations[:100])
            ]

            return jsonify(properties)

    def get_location_suggestions(self, location_input: str) -> List[dict]:
        """
            This function gets location suggestions.
        """
        self._logger.info(f"Getting location suggestions for: {location_input}")
        try:
            locations = self._location_engine.find_locations(location_input)
        except Exception as e:
            self._logger.error(f"Failed to get location suggestions. Error: {e}")
            return []
        self._logger.info(f"Got {len(locations)} location suggestions")
        suggestions = [
            { "display_name": location.display_name, "identifier": location.identifier }
            for location in locations
        ]
        return suggestions

    def get_property_valuations(self, params: SearchParameters, valuation_params: ValuationParameters) -> List[Valuation]:
        """
            This function gets property valuations.
        """
        self._logger.info(f"Getting property valuations for search {params.location_name} with radius {params.radius} km")
        propery_finder = self._search_engine.find_properties
        try:
            valuations = self._valuation_engine.rank_properties(params, valuation_params, propery_finder)
        except Exception as e:
            self._logger.error(f"Failed to get property valuations. Error: {e}")
            return []
        self._logger.info(f"Got {len(valuations)} property valuations")
        return valuations

def validate(field: str, type: type):
    try:
        return type(request.json.get(field))
    except ValueError:
        raise Exception(f"Invalid {field} unable to convert to {type}")
    
if __name__ == '__main__':
    cache = Cache()
    logger = Logger()
    app = App(cache, logger)
    app.set_routes()
    app.run(debug=True)