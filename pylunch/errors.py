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


class UnableToLoadContent(PyLunchApiError):
    def __init__(self, name: str, code=400, url: str = None):
        super().__init__(f"""Cannot parse the menu for: {name}\n
        You can try to take a look at here: {url}""", code=code)
        self.name = name

    def to_json(self):
        return dict(message=self.message, name=self.name, status=400)