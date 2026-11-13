import os

from langchain_core.messages import HumanMessage, SystemMessage

STRATEGY = os.getenv("MEMORY")          # "window" or "summary"
KEEP_TURNS = int(os.getenv("KEEP_TURNS"))   # how many earlier turns (question + answer) the model sees


def window(history: list, keep_turns: int = KEEP_TURNS) -> list:
    """The last keep_turns turns. One turn = 2 messages. """
    return history[-2 * keep_turns:] if keep_turns > 0 else []


SUMMARY_PROMPT = ("Summarise this store conversation in at most 5 short bullet points. Keep every name, order "
                  "number, pincode and figure the CUSTOMER gave. Do not add anything that was not said.")


def summarise(history: list, llm, keep_turns: int = KEEP_TURNS) -> list:
    recent_limit = 2 * keep_turns
    
    if len(history) <= recent_limit:
        return history
        
    old = history[:-recent_limit]
    recent = history[-recent_limit:]
    
    if len(old) < 4 and any(isinstance(m, SystemMessage) and m.content.startswith("Summary") for m in old):
        return old + recent
    
    transcript = "\n".join(f"{type(m).__name__}: {m.content}" for m in old)
    
    summary = llm.invoke([
        SystemMessage(content=SUMMARY_PROMPT), 
        HumanMessage(content=transcript)
    ]).content
    
    return [SystemMessage(content=f"Summary of the earlier conversation:\n{summary}")] + recent


def trim(history: list, llm=None) -> list:
    """What the model sees of this session's history - the strategy chosen above."""
    if STRATEGY == "summary":
        return summarise(history, llm, KEEP_TURNS)
    return window(history, KEEP_TURNS)
