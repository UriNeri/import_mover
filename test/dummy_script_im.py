# test_script.py
# import os
# import sys
# import math as m
# import random
# import time
from logging import basicConfig


class ConfigSubclass(basicConfig):
    
    def __init__(self, name):
        import math as m
        self.name = name
        self.pi = m.pi
        self.config = basicConfig()

def function1(self):
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
        print(time.time())
    function3()

def main():
    function1()
    function2()

if __name__ == "__main__":
    main()