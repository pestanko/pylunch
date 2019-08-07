import logging

log = logging.getLogger(__name__)


class TagsEvaluator:
    def __init__(self, expression: str, registered_tags=None):
        self.expression = expression
        self.registered_tags = registered_tags or []

    def register_tags(self, *tags):
        self.registered_tags.extend(tags)

    def build_dict(self, *tags):
        result = {}
        for tag in self.registered_tags:
            result[tag] = tag in tags
        return result

    def evaluate(self, *test_tags) -> bool:
        expression = self.expression
        if not expression:
            return True
        tags = self.build_dict(*test_tags)
        log.trace(f"[TAGS] Eval: \"{expression}\": {tags}")
        try:
            return eval(expression, {'__builtins__': None}, tags)
        except Exception as ex:
            log.warning(f"There is some error: {ex}")
            return False
