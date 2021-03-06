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

#pylint: disable-msg=C0301
'''JythonMX, helpers to expose JMX data from Jython applications

:author: Nicolas Trangez
:requires: Jython_ 2.5
:version: 0.0.1

:license: `GNU Lesser General Public License version 2.1`_
:copyright: |copy| 2009 Nicolas Trangez

.. _Jython: http://www.jython.org
.. _GNU Lesser General Public License version 2.1: http://www.gnu.org/licenses/lgpl-2.1.txt
.. |copy| unicode:: 0xA9 .. copyright sign
'''
#pylint: enable-msg=C0301

__author__ = 'Nicolas Trangez <eikke eikke com>'
__version__ = 0, 0, 1
__license__ = 'GNU Lesser General Public License version 2.1'
__docformat__ = 'restructuredtext en'

__all__ = 'returns', 'args', 'TypedProperty', 'MBeanAdapter', 'Array', 'signal',

import sys
import types
import logging
import inspect
import operator
import threading
import functools
import itertools

#pylint: disable-msg=F0401
import java.lang
from java.lang.management import ManagementFactory
from javax.management import DynamicMBean, ObjectName, \
                             MBeanInfo, MBeanAttributeInfo, \
                             MBeanOperationInfo, MBeanParameterInfo, \
                             AttributeList, Attribute, \
                             AttributeNotFoundException, MBeanException, \
                             ReflectionException, \
                             Notification, NotificationBroadcasterSupport, \
                             MBeanNotificationInfo
import jarray
#pylint: enable-msg=F0401

#pylint: disable-msg=W0142,C0103,R0903,W0141,R0201,W0622
# W0142: Usage of *args, **kwargs
# C0103: Non-PEP8 casing
# R0903: Too few public methods
# W0141: Usage of builtin 'filter'
# R0201: Method could be a function
# W0622: Redefining builtin __doc__

def tag_decorator(attrname, modifier=None):
    '''A function to create a decorator which sets an attribute on the
    decorated function

    This function returns a decorator which takes a set of arguments, and sets
    these arguments as an attribute on the decorated function, optionally
    passing the arguments through a modification function first.

    If no modifier is given, the arguments will not be modified.

    Example:

    >>> tag_id = tag_decorator('__tag__', lambda i: 'tag_%d' % i)

    >>> @tag_id(10)
    ... def f(self):
    ...     pass

    >>> print f.__tag__
    tag_10

    :param attrname: name of the attribute to store the arguments
    :type attrname: `str`
    :param modifier: modification function to modify the arguments
    :type modifier: `callable`

    :return: a function decorator
    :rtype: `callable`
    '''
    def decorator(*args_):
        '''
        Set decorator arguments as an attribute on the decorated function

        :return: decorator function
        :rtype: `callable`
        '''
        def tagger(fun):
            '''
            Set decorator arguments as an attribute on the given function

            :param fun: function to decorate
            :type fun: `callable`

            :return: decorated function
            :rtype: `callable`
            '''
            modified_args = args_ if not modifier else modifier(*args_)
            setattr(fun, attrname, modified_args)

            return fun

        return tagger

    return decorator


returns = tag_decorator('__returns__', lambda *a: a[0])
returns.__doc__ = '''
Define the return type of a method
'''.strip()

def test_returns():
    '''Test `returns` behaviour'''
    @returns(java.lang.String)
    def f(): #pylint: disable-msg=C0111
        pass

    assert f.__returns__ == java.lang.String #pylint: disable-msg=E1101


args = tag_decorator('__args__', lambda *a: tuple(a))
args.__doc__ = '''
Define the argument types of a method

The argument types should be given in the argument order. The type definitions
can be just a type, or a tuple of a type and a description of the argument.
'''.strip()

def test_args():
    '''Test `args` behaviour'''
    #pylint: disable-msg=C0111
    @args(
        (java.lang.String, 'Name'),
        java.lang.Integer,
    )
    def f(name, age): #pylint: disable-msg=W0613
        pass

    #pylint: disable-msg=E1101
    assert f.__args__ == ((java.lang.String, 'Name'), java.lang.Integer)


# An attribute setter generator, similar to operator.attrgetter
#pylint: disable-msg=E0601
attrsetter = lambda attr: lambda self, value: setattr(self, attr, value)
#pylint: enable-msg=E0601

def test_attrsetter():
    '''Test `attrsetter`'''
    class C(object): #pylint: disable-msg=C0111
        def __init__(self, i): #pylint: disable-msg=C0111
            self._i = i

        i = property(fget=operator.attrgetter('_i'), fset=attrsetter('_i'))

    c = C(123)
    assert c.i == 123
    c.i = 456
    assert c.i == 456
    assert c._i == 456 #pylint: disable-msg=W0212


# A helper to calculate the fully-qualified name of a class
classname = lambda cls: '%s.%s' % (cls.__module__, cls.__name__)

def test_classname():
    '''Test `classname`'''
    assert classname(java.lang.String) == 'java.lang.String'


# A helper to flatten a docstring in one line
format_docstring = lambda doc: ' '.join(itertools.imap(lambda s: s.strip(),
                                                   doc.splitlines())).strip()

def test_format_docstring():
    '''Test docstring to single line conversion'''
    docstring = '''
    Abc
    def
    '''
    assert format_docstring(docstring) == 'Abc def'


class TypedProperty(property):
    '''
    A descriptor, similar to the builtin `property`, which also takes a type
    definition
    '''
    def __init__(self, type_, *args_, **kwargs):
        '''Initialize a `TypedProperty`

        All ``*args_`` and ``**kwargs`` are passed as-is to the builtin
        `property` constructor.

        :param type\_: type of the property value
        :type type\_: `type`
        '''
        property.__init__(self, *args_, **kwargs)
        self._type = type_

        # Make sure the local __doc__ attribute is set correctly
        # 'property' seems to do this, but somehow instances of TypedProperty
        # still end up with the class docstring as __doc__ attribute value
        # unless we set it explicitly.
        if len(args_) == 4:
            self.__doc__ = args_[3]
        else:
            self.__doc__ = kwargs.get('doc', '')

    type = property(operator.attrgetter('_type'),
                    doc='Type of the property value')

def test_typed_property():
    '''Test `TypedProperty`'''
    getter = operator.attrgetter('_')
    setter = attrsetter('_')

    class C(object): #pylint: disable-msg=C0111
        i = TypedProperty(java.lang.String, fget=getter, fset=setter)

    assert C.i.type == java.lang.String
    assert C.i.fget is getter
    assert C.i.fset is setter


class Array(object):
    '''Representation of a Java array'''
    __slots__ = '_type',

    def __init__(self, type_):
        '''Initialize a new array representation

        :param type\_: type contained in the array
        :type type\_: `type`
        '''
        self._type = type_

    def __call__(self, values):
        '''Coerce the given values into a Java array

        This acts just like the constructor of a normal Java type definition.

        :param values: values to coerce
        :type values: ``iterable``

        :return: Java array containing all values
        :rtype: ``jarray.array``
        '''
        return jarray.array(tuple(self._type(value) for value in values),
                            self._type)

    #pylint: disable-msg=W0212
    __module__ = property(fget=lambda s: s._type.__module__,
                          doc='Type definition module name')
    __name__ = property(fget=lambda s: '%s[]' % s._type.__name__,
                        doc='Array type name')

def test_array():
    '''Test array type wrapper'''
    type_ = Array(java.lang.String)
    assert type_.__module__ == java.lang.String.__module__
    assert type_.__name__ == '%s[]' % java.lang.String.__name__
    # TODO Test array coercion


class NotificationTrigger(object):
    '''An MBean notification/signal slot'''
    __slots__ = '_name', '_sendNotification', '_nextId', '_source',

    def __init__(self, name):
        self._name = name

        self._sendNotification = None
        self._nextId = None
        self._source = None

    def __call__(self, message=None, userData=None):
        '''Emit notification

        Note: both arguments will be coerced into ``java.lang.String``.

        :param message: notification message
        :type message: `unicode`
        :param userData: notification ``userData``
        :type userData: `unicode`
        '''
        # If not all of these are set, we aren't registered yet. No-op.
        if not all((self._sendNotification, self._nextId, self._source, )):
            return

        if not message:
            notification = Notification(self.name, self._source, self._nextId())
        else:
            notification = Notification(self.name, self._source, self._nextId(),
                                        java.lang.String(message))

        if userData:
            notification.setUserData(java.lang.String(userData))

        self._sendNotification(notification)

    name = property(operator.attrgetter('_name'), doc='Notification type name')

    def _setSendNotification(self, value):
        '''Set the callable to use to emit notifications'''
        if self._sendNotification:
            raise RuntimeError('Can\'t set sendNotification twice')

        self._sendNotification = value

    sendNotification = property(fset=_setSendNotification,
                                doc='Setter for function to call when ' \
                                    'sending notifications')

    def _setNextId(self, value):
        '''
        Set the callable to use to retrieve the next notification sequence
        number
        '''
        if self._nextId:
            raise RuntimeError('Can\'t set nextId twice')

        self._nextId = value

    nextId = property(fset=_setNextId, doc='Setter for the nextId function')

    def _setSource(self, value):
        '''Set the source of all notifications'''
        if self._source:
            raise RuntimeError('Can\'t set source twice')

        self._source = value

    source = property(fset=_setSource, doc='Setter for the notification source')

signal = NotificationTrigger


# TODO This is not correct, the returned function is locked by a global lock
# (for all instances), not instance-specific
def synchronised(fun):
    '''Decorator to add a lock around a function

    Think ``synchronised`` in Java.

    :param fun: function to decorate
    :type fun: `callable`

    :return: decorated function
    :rtype: `callable`
    '''
    lock = threading.Lock()

    @functools.wraps(fun)
    def _wrapped(*args_, **kwargs): #pylint: disable-msg=C0111
        lock.acquire()
        try:
            return fun(*args_, **kwargs)
        finally:
            lock.release()

    return _wrapped

def test_synchronised():
    '''Test `synchronised`'''
    import time

    @synchronised
    def f(): #pylint: disable-msg=C0111
        time.sleep(1)

    t1 = threading.Thread(target=f)
    t2 = threading.Thread(target=f)

    start = time.time()
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    end = time.time()

    assert 1.9 < (end - start) < 2.5


#pylint: disable-msg=E0601
list_attributes = lambda obj: itertools.imap(
                                  lambda name: (name, getattr(obj, name)),
                                  itertools.ifilter(
                                      lambda name: not name.startswith('_'),
                                      dir(obj)))
#pylint: enable-msg=E0601
list_attributes.__doc__ = '''
List all public, non-internal attributes of an object

This function yields all ``(name, attribute)`` pairs for all attributes on the
given object whose name doesn't start with an underscore.

:param obj: object to inspect
:type obj: `object`

:return: ``(name, attribute)`` pairs of all public attributes on the object
:rtype: ``iterable<tuple<str, object>>``
'''.strip()

def test_list_attributes():
    '''Test `list_attributes`'''
    class C(object): #pylint: disable-msg=C0111
        def __init__(self):
            pass

        def hello(self): #pylint: disable-msg=C0111
            pass

        def _bye(self): #pylint: disable-msg=C0111
            pass

        i = property()
        _j = property()

    assert set(list_attributes(C)) == set((('hello', C.hello), ('i', C.i)))


#TODO Use class logger
def logged(fun):
    '''A decorator to log all exceptions raised in a method

    The Java JMX subsystems swallows all exceptions raised in MBean methods,
    which makes debugging rather hard. This decorator can be wrapped around a
    method, after which any exception raised while executing the method will be
    logged using logging.exception, and re-raised.

    :param fun: function to decorate
    :type fun: `callable`

    :return: decorated function
    :rtype: `callable`
    '''
    @functools.wraps(fun)
    def _wrapped(*args_, **kwargs): #pylint: disable-msg=C0111
        try:
            return fun(*args_, **kwargs)
        except:
            logging.exception('Error executing %s', fun.__name__)
            raise

    return _wrapped

def test_logged():
    '''Make sure `logged` passes through the exception'''
    raised_exc = Exception('Hello world')

    @logged
    def f(): #pylint: disable-msg=C0111
        raise raised_exc

    try:
        f()
    except Exception, exc: #pylint: disable-msg=W0703
        assert exc is raised_exc
    else:
        assert False, 'Exception not raised'


class MBeanAdapter(NotificationBroadcasterSupport, DynamicMBean, object):
    '''An adapter for plain Python classes to act as MBeans in JMX'''

    __slots__ = '_bean', '_registered', '_name', '_currentId', '_beaninfo', \
                '_notificationinfo', '_logger',

    # Default property value type
    DEFAULT_PROPERTY_TYPE = java.lang.String
    # Default method return type
    DEFAULT_FUNCTION_RETURN_TYPE = java.lang.Void

    def __init__(self, bean):
        '''Initialize a new `MBeanAdapter`

        :param bean: instance to expose on JMX
        :type bean: `object`
        '''
        NotificationBroadcasterSupport.__init__(self)

        self._bean = bean

        self._registered = False
        self._name = None
        self._beaninfo = None
        self._notificationinfo = None

        self._logger = logging.getLogger('mbeanadapter')

        self._currentId = 0

    # Public API
    @synchronised
    def register(self, name):
        '''Register the bean in JMX using the given `name`

        :param name: name to register the bean as
        :type name: `str`
        '''
        if self._registered:
            raise RuntimeError('Adapter already registered')

        self._logger = logging.getLogger('mbeanadapter.%s' % name)

        self._logger.debug('Registering adapter')

        server = ManagementFactory.getPlatformMBeanServer()
        self._name = ObjectName(name)
        server.registerMBean(self, self._name)

        self._registered = True

    @synchronised
    def unregister(self):
        '''Unregister the bean from JMX'''
        if not self._registered:
            raise RuntimeError('Adapter not registered')

        assert self._name

        self._logger.debug('Unregistering adapter')

        server = ManagementFactory.getPlatformMBeanServer()
        server.unregisterMBean(self._name)

        self._name = None
        self._registered = False

    # Private stuff
    @property
    @synchronised
    @logged
    def beaninfo(self): #pylint: disable-msg=R0912
        '''Calculate the ``MBeanInfo`` of the bean

        :return: ``MBeanInfo`` object describing the MBean
        :rtype: ``MBeanInfo``
        '''
        # Short path
        if self._beaninfo:
            return self._beaninfo

        self._logger.debug('Inspecting MBean')

        def attributes():
            '''Calculate and list all attributes exposed on the MBean'''
            cls = self._bean.__class__

            # List all properties found on the bean type
            for name, attr in filter(lambda (_, a): isinstance(a, property),
                                     list_attributes(cls)):
                # Calculate property value type
                type_ = attr.type if isinstance(attr, TypedProperty) \
                                  else self.DEFAULT_PROPERTY_TYPE

                yield MBeanAttributeInfo(name, classname(type_),
                                         format_docstring(attr.__doc__ or ''),
                                         callable(attr.fget),
                                         callable(attr.fset), False)

        def operations():
            '''Calculate and list all methods exposed on the MBean'''
            cls = self._bean.__class__

            # List all callable attributes found on the bean type
            for name, attr in filter(lambda (_, a): callable(a),
                                     list_attributes(cls)):
                # If it's a NotificationTrigger, skip
                if isinstance(attr, NotificationTrigger):
                    continue

                # Make sure it's a method
                if not isinstance(attr, types.MethodType):
                    raise TypeError('MBean methods can\'t be staticmethods')

                # Make sure it's not a classmethod
                if attr.im_self:
                    raise TypeError('MBean methods can\'t have classmethods')

                # Make sure it has no *args, **kwargs or argument defaults
                spec = inspect.getargspec(attr)
                if spec[1:] != (None, None, None):
                    raise TypeError('MBean methods can\'t have *args, ' \
                                    '**kwargs or defaults')

                # Make sure an @args decorator is used, if the method takes any
                # arguments (next to self)
                names = spec[0]
                if len(names[1:]) > 0 and not hasattr(attr, '__args__'):
                    raise TypeError('No @args definition on method %s' % name)

                # Calculate the method return type (string)
                return_type = classname(getattr(attr, '__returns__',
                                            self.DEFAULT_FUNCTION_RETURN_TYPE))

                def args_():
                    '''List all method parameters taken by the method'''
                    # Check whether this is a zero-argument method
                    if not hasattr(attr, '__args__'):
                        assert len(names[1:]) == 0
                        return

                    arg_types = attr.__args__

                    # Validate number of argument type definitions
                    if len(names[1:]) != len(arg_types):
                        raise ValueError(
                            'Invalid number of argument definitions')

                    # Loop through all arguments and their type definition
                    for name, type_ in zip(names[1:], arg_types):
                        # Figure out type and docstring, if given
                        if isinstance(type_, type):
                            type_, doc = type_, None
                        else:
                            type_, doc = type_

                        # Yield the parameter info for the current parameter
                        yield MBeanParameterInfo(name, classname(type_), doc)

                # Yield method info for the current method
                # All methods are ACTIONs for now.
                yield MBeanOperationInfo(attr.__name__,
                                         format_docstring(attr.__doc__ or ''),
                                         tuple(args_()), return_type,
                                         MBeanOperationInfo.ACTION)

        # Calculate and store MBeanInfo
        self._beaninfo = MBeanInfo(classname(self._bean.__class__),
                                   format_docstring(
                                       self._bean.__class__.__doc__ or ''),
                                   tuple(attributes()), None,
                                   tuple(operations()), self.notificationinfo)

        return self._beaninfo

    @property
    @logged
    @synchronised
    def notificationinfo(self):
        '''Calculate the ``MBeanNotificationInfo`` of the bean

        :return: ``MBeanNotificationInfo`` array describing the notifications
                 emitted by the MBean
        :rtype: ``tuple<MBeanNotificationInfo>``
        '''
        # Short path
        if self._notificationinfo:
            return self._notificationinfo

        def notifications():
            '''Calculate and list all notifications exposed on the MBean'''
            cls = self._bean.__class__

            # List all callable attributes found on the bean type
            for _, attr in filter(
                    lambda (_, a): isinstance(a, NotificationTrigger),
                    list_attributes(cls)):
                attr.sendNotification = self.sendNotification
                attr.nextId = self._nextId
                attr.source = self._bean.__class__.__name__

                yield attr.name

        self._logger.debug('Calculating notifications info')

        notificationinfo = MBeanNotificationInfo(tuple(notifications()),
                                   classname(Notification),
                                   'Notifications emitted through JythonMX')

        self._notificationinfo = (notificationinfo, )
        return self._notificationinfo

    @synchronised
    def _nextId(self):
        '''
        Calculate and return a sequence number for notifications sent by the
        MBean

        :return: sequence ID
        :rtype: ``number``
        '''
        self._currentId += 1
        return self._currentId

    # DynamicMBean implementation
    @logged
    def getMBeanInfo(self):
        '''Retrieve ``MBeanInfo`` for the bean

        :return: ``MBeanInfo`` of the bean
        :rtype: ``MBeanInfo``
        '''
        self._logger.debug('MBean info requested')

        return self.beaninfo

    @logged
    def getAttribute(self, name):
        '''Get an attribute value from the bean

        :param name: attribute to retrieve
        :type name: `str`

        :return: attribute value
        :rtype: `object`
        '''
        self._logger.debug('Attribute requested: %s', name)

        if not hasattr(self._bean, name):
            self._logger.exception('Attribute not found')
            raise AttributeNotFoundException('No such attribute: %s' % name)

        # Calculate attribute type
        type_ = self.DEFAULT_PROPERTY_TYPE
        if hasattr(self._bean.__class__, name):
            # Override the default if the property is a TypedProperty
            property_ = getattr(self._bean.__class__, name)
            if isinstance(property_, TypedProperty):
                type_ = property_.type

        # Retrieve attribute value
        value = getattr(self._bean, name)

        # Coerce before returning
        return type_(value)

    @logged
    def getAttributes(self, names):
        '''Get multiple attributes at once

        :param names: attributes to retrieve
        :type names: ``iterable<Attribute>``

        :return: requested attribute values, if available
        :rtype: ``AttributeList``
        '''
        self._logger.debug('Attributes requested: %s', names)

        attributes = AttributeList()

        for name in names:
            try:
                value = self.getAttribute(name)
            except AttributeNotFoundException:
                # We can discard unknown attributes
                pass
            else:
                attributes.add(Attribute(name, value))

        return attributes

    @logged
    def setAttribute(self, attribute):
        '''Set the value of an attribute

        :param attribute: attribute to set
        :type attribute: ``Attribute``
        '''
        self._logger.debug('Attribute set: %s = %s', attribute.name,
                           attribute.value)
        setattr(self._bean, attribute.name, attribute.value)

    @logged
    def setAttributes(self, attributes):
        '''Set multiple attributes at once

        :param attributes: attributes to set
        :type attributes: ``iterable<Attribute>``
        '''
        map(self.setAttribute, attributes)

    @logged
    def invoke(self, name, args_, sig):
        '''Invoke a method on the bean

        :param name: method to invoke
        :type name: `str`
        :param args\_: arguments to pass to the method
        :type args\_: ``iterable<object>``
        :param sig: method signature
        :type sig: ``iterable<java.lang.String>``

        :return: method call result
        :rtype: `object`
        '''
        self._logger.debug('Invoke: %s(%s), sig=%s', name, args_, sig)

        if not hasattr(self._bean, name):
            raise ReflectionException(java.lang.NoSuchMethodException(name))

        fun = None
        try:
            fun = getattr(self._bean, name, None)
        except Exception, exc:
            self._logger.exception('Error retrieving method on bean')
            raise MBeanException(exc)

        if not callable(fun):
            raise ReflectionException(java.lang.NoSuchMethodException(name))

        return_type = getattr(fun, '__returns__',
                              self.DEFAULT_FUNCTION_RETURN_TYPE)
        try:
            value = fun(*args_)
            # Coerce before returning
            if return_type is java.lang.Void:
                return
            else:
                return return_type(value)
        except Exception, exc:
            self._logger.exception('Error executing or coercing return value')
            raise MBeanException(exc)

    # NotificationBroadcasterSupport
    @logged
    def getNotificationInfo(self):
        '''Retrieve info of all notifications emitted by the MBean

        :return: MBean notification info
        :rtype: ``tuple<MBeanNotificationInfo>``
        '''
        self._logger.debug('Notification info requested')

        return self.notificationinfo

    @logged
    def sendNotification(self, notification):
        '''Emit a notification to all listeners

        :param notification: Notification to emit
        :type notification: ``Notification``
        '''
        self._logger.debug('Emit notification: %s', notification)

        return NotificationBroadcasterSupport.sendNotification(self,
                                                               notification)


class DemoMBean(object):
    '''A demonstration MBean'''
    def __init__(self, strValue, intValue, boolValue):
        self._strValue = strValue
        self._intValue = intValue
        self._boolValue = boolValue

    # Properties represent attributes on the MBean. They are readable if fget
    # is implemented, writable if fset is implemented, and have the given doc
    # string as description.

    # Standard Python properties are considered to be of type 'java.lang.String'
    strValue = property(fget=operator.attrgetter('_strValue'),
                        fset=attrsetter('_strValue'), doc='A string value')
    # TypedProperties allow one to define the Java type of an attribute, given
    # as the first argument to the constructor
    intValue = TypedProperty(java.lang.Integer,
                             fget=operator.attrgetter('_intValue'),
                             doc='A read-only integer value')
    boolValue = TypedProperty(java.lang.Boolean,
                              fget=operator.attrgetter('_boolValue'),
                              fset=attrsetter('_boolValue'))

    @returns(java.lang.String)
    @args((java.lang.String, 'User name'))
    def hello(self, name):
        '''A method saying hello'''
        return 'Hello, %s' % name

    # By default, methods are considered to return nothing, and take no
    # arguments
    def demo(self):
        '''A demo function which only prints to console'''
        print 'Demo called'

    @returns(java.lang.Boolean)
    @args(
        (java.lang.Integer, 'Dividend'),
        java.lang.Integer,
    )
    def divides(self, a, b):
        '''Check whether b is a whole divisor of a'''
        if b == 0:
            return False

        return (a % b == 0)

    modules = TypedProperty(Array(java.lang.String),
                            fget=lambda _: sorted(sys.modules.iterkeys()),
                            doc='List of all loaded modules')

    # Notifications
    test = signal('test')
    test2 = signal('test2')

    def notifyTest(self):
        '''A function which emits both test notifications'''
        self.test('Test succeeded')
        # User data must be a string, e.g. machine-readable information
        self.test2('Test really succeeded', 'With user data')


def main():
    '''Expose the demo MBean and wait for termination'''
    bean = DemoMBean(u'demo', 123, True)
    adapter = MBeanAdapter(bean)
    adapter.register('JythonMX:name=demo')
    print
    raw_input('Press return to quit\n')
    print
    adapter.unregister()

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    main()
else:
    # No need to expose these
    del main
    del DemoMBean
