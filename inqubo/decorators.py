from inqubo.retry_strategies import BaseRetryStrategy
from inqubo.workflow import Step
from inqubo.typing import StepCallable


def step(name: str=None, retry_strategy: BaseRetryStrategy=None):
    def step_decorator(func: StepCallable):
        func._step = Step(func, name=name, retry_strategy=retry_strategy)
        func.then = lambda *args, **kwargs: func._step.then(*args, **kwargs)
        return func
    return step_decorator
