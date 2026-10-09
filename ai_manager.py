"""ai_manager: the AI side of the pipeline, no domain logic.

It builds prompts, defines the response the AI must return, validates that
response and hands the result on. All network calls live in api_client.py.
"""

import json


def build_prompt(shipment, weather):
    """Build the user prompt from a shipment and its weather data.

    shipment is a dict or DataFrame row. weather is the dict returned by
    api_client.fetch_shipment_weather. Both are written out as JSON.
    """
    return (
        "SHIPMENT:\n" + json.dumps(dict(shipment), indent=2, default=str)
        + "\n\nEXTERNAL DATA:\n" + json.dumps(weather, indent=2, default=str)
    )
