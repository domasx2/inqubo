#!/usr/bin/env python

from distutils.core import setup

setup(name='Inqubo',
      version='0.1.0',
      description='Workflow Engine',
      author='Domas Lapinskas',
      author_email='Domas Lapinskas',
      packages=['inqubo'],
      install_requires=['aio-pika==0.12.1'],
     )