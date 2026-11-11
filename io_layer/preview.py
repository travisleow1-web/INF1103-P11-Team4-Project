class Preview:
    def __init__(self, results):
        self.__results = results        # list of (row_number, ValidationResult)

    def total(self):
        return len(self.__results)

    def valid_shipments(self):
        return [r.shipment for n, r in self.__results if r.is_valid()]

    def problems(self):
        return [(n, r.errors) for n, r in self.__results if not r.is_valid()]

    def has_problems(self):
        return any(not r.is_valid() for n, r in self.__results)
