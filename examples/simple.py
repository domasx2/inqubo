import pprint
from inqubo.workflow import  Workflow
from inqubo.decorators import step

pp = pprint.PrettyPrinter(indent=4)

@step()
def step1():
    pass

@step()
def step2():
    pass

@step()
def step3():
    pass

@step()
def step4():
    pass

flow = Workflow('simple')

flow.start(step1)\
    .then(step2)\
    .then(step3, step4)

print(pp.pprint(flow.serialize()))