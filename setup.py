#!/usr/bin/env jython

# JythonMX, helpers to expose JMX data from Jython applications
#
# Copyright (C) 2009 Nicolas Trangez  <eikke eikke com>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation, version 2.1
# of the License.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA  02110-1301  USA

from distutils.core import setup

import jythonmx

setup(name='JythonMX',
      version='.'.join(map(str, jythonmx.__version__)),
      description='A library to expose plain Python classes as JMX MBeans',

      author='Nicolas Trangez',
      author_email='eikke eikke com',
      license='LGPL-2.1',

      url='http://github.com/NicolasT/JythonMX',

      py_modules=['jythonmx', ],
)
