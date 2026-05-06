from app.core.config import settings
from app.entities.nlp.intent_parser import parse_intent, parse_intent_using_llm
from app.entities.nlp.intent_schema import PropertyIntent


def parse_user_intent(query: str) -> PropertyIntent:
    if settings.llm.use_llm:
        return parse_intent_using_llm(query)
    return parse_intent(query)
