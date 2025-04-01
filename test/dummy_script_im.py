# test_script.py
# import os
# import sys
# import math as m
# import random
# import time
from logging import basicConfig
from dataclasses import *
# from functools import wraps

def timing_decorator(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        import time
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        print(f"{func.__name__} took {end - start} seconds")
        return result
    return wrapper

@dataclass
class ConfigSubclass(basicConfig):
    def __init__(self, name):
        import math as m
        self.name = name
        self.pi = m.pi
        self.config = basicConfig()

@timing_decorator
def function1():
    """
    This function prints the value of pi from the math module.
    """
    import math as m
    print(m.pi)

def function2():
    """
    This function prints a random integer between 1 and 10.
    """
    import random
    print(random.randint(1, 10))

    def function3():
        """
        This function prints the current time.
        """
        import time
        import time
        print(time.time())
    function3()

def main():
    function1()
    function2()

if __name__ == "__main__":
    main()