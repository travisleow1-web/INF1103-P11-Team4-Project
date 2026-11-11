from .shipment_source import ShipmentSource


class FormSource(ShipmentSource):
    def __init__(self, fields):
        self.__fields = fields

    def read(self):
        return [dict(self.__fields)]
