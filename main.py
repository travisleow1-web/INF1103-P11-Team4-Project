import ai_manager
import io_manager


def main():
    """Collect shipments, then fetch and show the weather at each one's ends."""
    shipments = io_manager.input_method()
    for shipment in shipments.to_dict("records"):
        weather = ai_manager.get_shipment_weather(shipment)
        io_manager.show_weather(shipment, weather)


if __name__ == "__main__":
    main()
