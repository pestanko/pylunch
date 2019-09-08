class PyLunchError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class PyLunchApiError(PyLunchError):
    def __init__(self, message, code=400):
        super().__init__(message)
        self.code = code

    def to_json(self):
        return dict(message=self.message, status=self.code)


class UnnableToLoadContent(PyLunchApiError):
    def __init__(self, name, code=400):
        super().__init__(f"Cannot parse the menu for: {name}")
        self.name = name

    def to_json(self):
        return dict(message=self.message, name=self.name, status=400)