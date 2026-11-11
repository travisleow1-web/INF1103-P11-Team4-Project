class ValidationResult:
    def __init__(self, shipment, errors):
        self.__shipment = shipment
        self.__errors = errors

    def is_valid(self):
        return len(self.__errors) == 0

    @property
    def shipment(self):
        return self.__shipment

    @property
    def errors(self):
        return list(self.__errors)
