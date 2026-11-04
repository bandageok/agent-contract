"""Shared factories for the test suite."""

from agent_contract.model import Step, Trace


def make_tool(name, result=None, **args):
    return Step(kind="tool", name=name, args=args, result=result)


def make_trace(idx, input_text, output="", steps=None, tid=None):
    return Trace(
        id=tid or "t-%03d" % idx,
        input=input_text,
        output=output,
        steps=steps if steps is not None else [],
    )