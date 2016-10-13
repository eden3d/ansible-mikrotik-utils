from collections import OrderedDict
from inspect import isabstract
from string import printable
from shlex import shlex
from enum import Enum
from abc import abstractproperty, abstractmethod


# Utilities
# -----------------------------------------------------------------------------

class AbstractMethodMixin(object):
    __isabstractmethod__ = True

    def __init__(self, func):
        func.__isabstractmethod__ = True
        super(AbstractMethodMixin, self).__init__(func)


class classproperty(object):
    def __init__(self, getter):
        self.getter = getter
        super(classproperty, self).__init__()

    def __get__(self, instance, owner):
        return self.getter(owner)


class abstractclassmethod(classmethod):

    __isabstractmethod__ = True

    def __init__(self, func):
        func.__isabstractmethod__ = True
        super(abstractclassmethod, self).__init__(func)


class abstractclassproperty(classmethod):

    __isabstractmethod__ = True

    def __init__(self, func):
        func = classproperty(func)
        func.__isabstractmethod__ = True
        super(abstractclassproperty, self).__init__(func)


def lookup_implementation(base, target, *args, **kwargs):
    # try base class first
    if not isabstract(base):
        return base
    # specific implementations are first, need to try generic first
    for klass in reversed(base.lookup_subclasses(*args, **kwargs)):
        if issubclass(klass, target):
            return klass
    # try target class
    if not isabstract(target):
        return target
    # oops
    raise TypeError("No implementation found.")


def join(*args):
    return ' '.join(map(str, args))


# Ordering handdling
# -----------------------------------------------------------------------------

class OrderMode(Enum):
    UNORDERED = 0
    ORDERED = 1
    ORDERED_APPEND = 2

    @property
    def ordered(self):
        return self in (self.ORDERED, self.ORDERED_APPEND)

    @property
    def ordered_insertion(self):
        return self == self.ORDERED

UNORDERED, ORDERED = OrderMode.UNORDERED, OrderMode.ORDERED
ORDERED_APPEND = OrderMode.ORDERED_APPEND


# Raw text parsing & formatting
# -----------------------------------------------------------------------------

def split_lines(text):
    line_lexer = shlex(text, posix=True)
    line_lexer.quotes = '"'
    line_lexer.whitespace = '\n;'
    line_lexer.wordchars = set(printable) - set(
        line_lexer.quotes + line_lexer.whitespace + line_lexer.escape
    )
    return list(line_lexer)

def parse_path(text):
    if text.startswith('/'):
        return text.lstrip('/'), True
    else:
        return text, False

def format_path(words):
    return '/{}'.format(' '.join(words))


def parse_value(word):
    parts = word.split('=')
    return parts[0], '='.join(parts[1:]).strip()

def parse_values(words):
    return OrderedDict(map(parse_value, words))

def format_value(value):
    return '='.join(value)

def format_values(values):
    return list(map(format_value, values.items()))

def format_add_destination(destination):
    if destination is not None:
        return 'place-before={}'.format(destination)
    else:
        return ''

def format_censored(text):
    lines = split_lines(text)
    if len(lines) > 1:
        return '<{} censord lines>'.format(len(lines))
    else:
        return '<{} censord characters>'.format(len(lines[0]))

# Patterns
# -----------------------------------------------------------------------------
TEXT_RE = "(?P<text>.*)"
NAME_RE = "(?P<name>[\w\-]+)"
NAMES_RE = "(?P<names>(\s?{})*)".format(NAME_RE)
VALUES_RE = "(?P<values>(([\w\-0-9]+)=(.*)\s?)+)"
INDEX_RE = "(?P<index>\d+)"
COMMAND_RE = "(?P<command>{}+)".format(NAME_RE)
OPTIONS_RE = "(?P<options>.+)"
DESTINATION_RE = "(?P<destination>\d+)"
NUMERIC_ID_RE = "(?P<numeric_identifier>[0-9]+)"
STRING_ID_RE = "(?P<string_identifier>[\w\-0-9_]+)"
FILE_ID_RE = "(?P<filename>[\w\-0-9_\.\@\=\+]+)"
DYNAMIC_CRITERIA_RE = "(?P<dynamic_criteria>([\w\-0-9]+)=(.*))"
ABSOLUTE_PATH_RE = "(?P<absolute>\/)"
PATH_RE = "(?P<path>{}?{})".format(ABSOLUTE_PATH_RE, NAMES_RE)
DYNAMIC_ID_RE = "(?P<dynamic_identifier>\[\s?find\s+({}\s?)+\s?\])".format(DYNAMIC_CRITERIA_RE)
IDENTIFIER_RE = "(?P<identifier>{}|{}|{})".format(NUMERIC_ID_RE, STRING_ID_RE, DYNAMIC_ID_RE)


optional_re = '({})?'.format
