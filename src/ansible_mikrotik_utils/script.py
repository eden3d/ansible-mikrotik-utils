from collections import OrderedDict
from functools import wraps, partial
from shlex import split
from enum import Enum
from re import compile as compile_regex


# Script actions & order enumerations
# -----------------------------------------------------------------------------
#
# Currently, this script section containers interprets and handles the
# following Mikrotik shell commands :
# - `add`: insert an item (arguments: values)
# - `remove`: remove an item (arguments: index)
# - `move`: move an item (arguments: old & new position)
# - `set`: set the value of section/item settings
#
# These 4 commands are sufficient to describe **configuration changes**,
# however they can not be interpreted as a **device configuration**, because of
# the `remove` and `move` command, that cannot be handled by the configuration
# merging classes.
#
# Commands are listed in an enumeration, and its instances can be used to
# match/filter a set of lines in order to get only the lines that match the
# command. Instances also provide a function decorator that asserts that the
# return value matches the expected command.
#

class ScriptAction(Enum):
    ADD = 'add'
    REMOVE = 'remove'
    MOVE = 'move'
    SET = 'set'

    def match(self, line):
        return line.startswith(self.value)

    def filter_and_enumerate(self, lines):
        return [(index, line) for index, line in enumerate(lines) if self.match(line)]

    def checks(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            assert self.match(result)
            return result
        return wrapper

    @staticmethod
    def matches(line, actions):
        if not isinstance(actions, (list, tuple)):
            actions = (actions,)
        return any(action.match(line) for action in actions)

ADD, REMOVE = ScriptAction.ADD, ScriptAction.REMOVE
MOVE, SET = ScriptAction.MOVE, ScriptAction.SET


# Ordered sections definition
# -----------------------------------------------------------------------------
#
# Some configurations sections are ordered, some are not. I have not yet been
# to determine whether all configuration sections support using `place-before=`
# in the `add` command, so there are 3 modes defined : unordered, ordered and
# ordered-but-append.
#
# The following code handles determining the default ordering mode based on the
# section path.

class OrderMode(Enum):
    UNORDERED = 0
    ORDER = 1
    ORDER_APPEND = 2

    @property
    def ordered(self):
        return self in (self.ORDER, self.ORDER_APPEND)

    @property
    def ordered_insertion(self):
        return self == self.ORDER

UNORDERED, ORDER = OrderMode.UNORDERED, OrderMode.ORDER
ORDER_APPEND = OrderMode.ORDER_APPEND

ORDERED_SECTIONS_RE = {
    compile_regex('^/ip firewall filter$'): OrderMode.ORDER
}

def get_order_mode(text):
    for pattern, value in ORDERED_SECTIONS_RE.items():
        if pattern and pattern.match(text):
            return value
    else:
        return OrderMode.UNORDERED

# Order refreshing handling
# -----------------------------------------------------------------------------
#
# Objects don't have a real "position" in Mikrotik. The numeric IDs we can see
# in the configuration, in the export, and in the result of a `print` command
# are ephemeral, and generated on-the-fly by the print command. This code
# expects that, for a device in the same configuration state, the generated IDs
# will always be the same.
#
# When the configuration changes, IDs are not automatically recomputed, and
# after a move, deletion or insertion, they will be out of date. Because of
# this, configuration scripts must prepend `print;` to any command that
# requires the ordering to be up to date and that is preceded by a command that
# invalidates the current ordering.
#
# These methods are used to determine whether a line requires an up to date
# ordering, and whether it should invalidate the current ordering.


EXPORT_REFRESH_SPECIAL_COMMENT = "# <<<refresh-numeric-ids>>>"


def places_before(line):
    words = split(line)
    return (
        ADD.match(words[0]) and
        any(word.startswith('place-before=') for word in words[1:])
    )


def invalidates_order(line):
    return (
        places_before(line) or
        ScriptAction.matches(line, (MOVE, REMOVE))
    )

def requires_order(line):
    return (
        invalidates_order(line) or
        ScriptAction.SET.match(line)
    )

# Text parsing
# -----------------------------------------------------------------------------
#
# Mikrotik represents item/section configuration values as key-value pairs,
# separated using `=`. This code handles parsing `SET` and `ADD` commands, and
# needs to determine the setting target (section or specific item) for `SET`
# commands, and then parse the text key-value pairs into dictionaries that can
# be matched and updated.
#
# Regular expressions are only used to determine whether a `SET` command refers
# to the current section, or to a specific object.
#
# This code will properly handle `[ find ... ]` dynamic attributes, albeit
# without matching them to their actual value (which is unknown at execution
# time).

SETTINGS_ID_RE = (
    compile_regex(
        r"set\s+(\["
        r"\s?find\s+([\w\-0-9]+)=(.*)\s?"
        r"\]|([\w\-0-9]+)|([0-9]+))\s+"
    )
)

def parse_value(word):
    parts = word.split('=')
    return parts[0], '='.join(parts[1:]).strip()

def parse_values(words):
    return dict(map(parse_value, words))

def parse_settings(text):
    match = SETTINGS_ID_RE.match(text)
    if match:
        groups = match.groups()
        identifier = (groups[0] or groups[3]).strip()
        text = text[match.end():]
    else:
        identifier = None
        text = text.lstrip(SET.value).lstrip()
    return identifier, parse_values(split(text))

def parse_addition(text):
    text = text.lstrip(ADD.value).lstrip()
    return parse_values(split(text))

# Section script class
# -----------------------------------------------------------------------------
#
# Configuration section script class : represents a list of commands that will
# be executed on a remote device. `ScriptSection` instances are usually generated
# by merging `ConfigSection` objects.
#
# This object is basically a line container that provides :
#  - Content validation (allowed commands, `move` prohibited in non-ordered
#    sections, etc)
#  - `load`/`copy` methods to import contents from an external object and clone
#    the current instance
#  - useful __repr__ and __str__ implementations
#  - filtering lines by the command they use
#  - looking up items based on their values
#  - exporting contents in a format that can be properly executed by the device

class ScriptSection(object):

    # Initializer and import/export methods
    # -------------------------------------------------------------------------

    def __init__(self, path, order_mode=None):
        self.__path = path
        if order_mode is not None:
            self.__order_mode = order_mode
        else:
            self.__order_mode = get_order_mode(path)
        self.__lines = list()
        super(ScriptSection, self).__init__()

    def validate(self, line):
        allowed_actions = (ADD, REMOVE, SET)
        if self.ordered:
            allowed_actions += (MOVE, )
        if ADD.match(line) and places_before(line):
            if not self.ordered:
                raise ValueError(
                    "Cannot use place-before= in non-ordered section."
                )
            if not self.ordered_insertion:
                raise ValueError(
                    "Cannot use place-before= when ordered insertion "
                    "is disabled."
                )
        for action in allowed_actions:
            if action.match(line):
                break
        else:
            raise ValueError("Unkown line action: {}".format(line))

    def load(self, lines):
        assert not isinstance(lines, str), "must be an iterable of strings"
        for line in lines:
            self.validate(line)
            self.__lines.append(line)

    def copy(self):
        new = type(self)(self.path)
        new.load(self.__lines)
        return new

    def export(self, pretty=False):
        invalidate = True
        refresh = False
        for line in self.lines:
            if invalidate and requires_order(line):
                refresh = True
            if not pretty and refresh:
                yield ' '.join((self.path, 'print ;', EXPORT_REFRESH_SPECIAL_COMMENT))
            if not pretty:
                yield ' '.join((self.path, line))
            else:
                yield line
            refresh = False
            if not invalidate and invalidates_order(line):
                invalidate = True

    def __nonzero__(self):
        return not self.empty

    def __bool__(self):
        return not self.empty

    def _repr_parts(self):
        if self.additions:
            yield '+{}'.format(len(self.additions))
        if self.removals:
            yield '-{}'.format(len(self.removals))
        if self.moves:
            yield '~{}'.format(len(self.moves))
        if self.settings:
            yield '{} settings ({} keys)'.format(
                len(self.settings),
                sum(len(settings) for identifier, settings in
                    map(self.parse_settings, setting_lines))
            )

    def __repr__(self):
        parts = list(self._repr_parts())
        text = '({})'.format(', '.join(parts)) if parts else str()
        return '<{}: "{}" {}>'.format(type(self).__name__, self.__path, text)

    def __str__(self):
        return '\n'.join(self.export(True))

    # Public contents properties
    # -------------------------------------------------------------------------

    @property
    def order_mode(self):
        return self.__order_mode

    @property
    def ordered(self):
        return self.order_mode.ordered

    @property
    def ordered_insertion(self):
        return self.order_mode.ordered_insertion

    @property
    def path(self):
        return self.__path

    @property
    def lines(self):
        return self.__lines

    @property
    def empty(self):
        return not self.__lines

    @property
    def additions(self):
        return list(ScriptAction.ADD.filter_and_enumerate(self.lines))

    @property
    def removals(self):
        return list(ScriptAction.REMOVE.filter_and_enumerate(self.lines))

    @property
    def moves(self):
        return list(ScriptAction.MOVE.filter_and_enumerate(self.lines))

    @property
    def settings(self):
        return list(ScriptAction.SET.filter_and_enumerate(self.lines))

    # Public lookup methods
    # -------------------------------------------------------------------------

    def lookup_settings(self, target_identifier):
        for index, line in self.settings:
            identifier, settings = parse_settings(line)
            if identifier == target_identifier:
                return index, settings
        else:
            raise KeyError

    def lookup_addition(self, target_values):
        for index, line in self.additions:
            values = parse_addition(line)
            if values == target_values:
                return index
        else:
            raise KeyError


# Mikrotik script section container class
# -----------------------------------------------------------------------------
#
# This object is a container for section script objects, and can be used to
# represent changes that are going to be applied to a device, grouped by the
# section they refer to. It provides features such as :
# - Validation (instance-type-check for loaded sections)
# - `load`/`copy` methods to import contents from an external object and clone
#   the current instance
# - useful __repr__ and __str__ implementations
# - exporting contents in a format that can be properly executed by the device


class MikrotikScript(object):
    
    # Base object definition, and copy handler
    # -------------------------------------------------------------------------

    prettify = False

    def __init__(self, version=None):
        """Create an empty Mikrotik script (ordered container for ScriptSection
        instances).

        ..note :: Use :func:`load` to add new sections.

        """
        self.__sections = OrderedDict()
        self.__version = version

    def __validate(self, section):
        assert isinstance(section, ScriptSection)

    def load(self, sections):
        for path, section in OrderedDict(sections).items():
            self.__validate(section)
            self.__sections[path] = section.copy()

    def copy(self):
        new = type(self)(version=self.__version)
        new.load(self.__sections)
        return new

    def export(self, pretty=False, blank=None, header=False):
        if blank is None:
            blank = pretty
        if header:
            yield "# Generated by: {} {} for {} {}".format(
                "ansible-mikrotik-utils",
                "0.1",
                "ROS",
                self.version
            )
        for path, section in self.sections.items():
            if section:
                if pretty:
                    yield path
                if blank:
                    yield str()
                for line in section.export(pretty=pretty):
                    yield line
                if blank:
                    yield str()

    def show(self):
        return self.export(pretty=True, blank=False, header=False)

    # Public properties
    # -------------------------------------------------------------------------

    @property
    def version(self):
        return self.__version

    @version.setter
    def version(self, value):
        assert self.version is None, "version is already set"
        self.__version = value

    @property
    def sections(self):
        return self.__sections

    @property
    def empty(self):
        return not any(self.__sections.values())

    # Special methods
    # -------------------------------------------------------------------------

    def __nonzero__(self):
        return not self.empty

    def __bool__(self):
        return not self.empty

    def _repr_parts(self):
        yield '{} sections'.format(len(self.sections))

    def __repr__(self):
        parts = list(self._repr_parts())
        text = '({})'.format(', '.join(parts)) if parts else str()
        return '<{}: {}>'.format(type(self).__name__, text)

    def __str__(self):
        return '\n'.join(self.export(pretty=True, header=True))
