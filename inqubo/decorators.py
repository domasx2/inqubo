from inqubo.workflow import Step
from inqubo.typing import StepCallable


def step(name: str=None):
    def step_decorator(func: StepCallable):
        func._step = Step(func, name=name)
        func.then = lambda *args, **kwargs: func._step.then(*args, **kwargs)
        return func
    return step_decorator
