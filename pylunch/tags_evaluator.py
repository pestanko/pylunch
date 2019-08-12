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
            eval_res = tag in tags
            result[tag] = eval_res
        return result

    def evaluate(self, test_tags) -> bool:
        expression = self.expression
        if not expression:
            return True
        tags = self.build_dict(*(test_tags or []))
        log.debug(f"[TAGS] Eval: \"{expression}\": {tags}")
        result = False
        try:
            result = eval(expression, {'__builtins__': None}, tags)
        except Exception as ex:
            log.debug(f"[EVAL] Expr Error - \"{expression}\": {ex}")
            return False
        return result
