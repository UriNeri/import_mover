# test_script.py
import os
import sys
import math as m
import random
import time
from logging import basicConfig
from dataclasses import dataclass


@dataclass
class ConfigSubclass(basicConfig):
    
    def __init__(self, name):
        self.name = name
        self.pi = m.pi
        self.config = basicConfig()

def function1(self):
    """
    This function prints the value of pi from the math module.
"""
    print(m.pi) 

def function2():
    """
    This function prints a random integer between 1 and 10.
    """
    print(random.randint(1, 10))

    def function3():
        """
        This function prints the current time.
        """
        print(time.time())
    function3()

def main():
    function1()
    function2()

if __name__ == "__main__":
    main()