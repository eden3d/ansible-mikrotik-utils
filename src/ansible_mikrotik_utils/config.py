from collections import OrderedDict
from functools import wraps, partial
from itertools import chain
from string import printable
from shlex import split, shlex
from enum import Enum
from abc import ABCMeta, abstractproperty, abstractmethod
from re import compile as compile_regex, MULTILINE, DOTALL, VERBOSE

# Patterns
# -----------------------------------------------------------------------------

PATH_RE = "((?P<path>\/(([\w\-]+\s)+))\s)"
VALUES_RE = "(?P<values>([\w\-0-9]+)=(.*)\s?)"
INDEX_RE = "(?P<index>\d+)"
DESTINATION_RE = "(?P<destination>\d+)"
NUMERIC_ID_RE = "(?P<numeric_identifier>[0-9]+)"
STRING_ID_RE = "(?P<string_identifier>[\w\-0-9_]+)"
DYNAMIC_CRITERIA_RE = "(?P<dynamic_criteria>([\w\-0-9]+)=(.*)\s?)"
DYNAMIC_ID_RE = """(?P<dynamic_identifier>\[\s?find\s+{}+\])""".format(DYNAMIC_CRITERIA_RE)
IDENTIFIER_RE = "(?P<identifier>{}|{}|{})".format(NUMERIC_ID_RE, STRING_ID_RE, DYNAMIC_ID_RE)

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
    compile_regex('^/ip firewall filter$'): OrderMode.ORDER_APPEND,
    compile_regex('^/test$'): OrderMode.ORDER_APPEND
}

def get_order_mode(text):
    for pattern, value in ORDERED_SECTIONS_RE.items():
        if pattern and pattern.match(text):
            return value
    else:
        return OrderMode.UNORDERED


# Input : Text import cleaning method
# -----------------------------------------------------------------------------
#
# In order to parse an exported configuration, we must ensure that items are
# properly separated by line returns. It's normally the case, except for the
# fact that '/export' wraps long lines. The line returns resulting of the
# wrapping are manually stripped using a regular expression.
#
# This is because currently, the section stores its contents as a list of
# "lines", which requires the above fix to work properly.
#
# This is not optimal, and it does not allow keeping escaped newlines as
# parameter value. In order to fix this, it would be required to :
#  - treat items/settings/parameters differently
#    (store them in their own list)
#    + represent items as dictionaries stored in a list
#    + represent parameters as dictionaries stored in a dictionary
#    + represent settings as a dictionary
#  - make the "lines" property directly generated from items/settings/parameters
#  - find a multiline way to parse key-value pairs
#

EXPORT_SUBS = [
    # remove escaped line returns
    (compile_regex(r'\\\s*\n\s{4}', MULTILINE), str()),
]

def clean_export(text):
    for pattern, new in EXPORT_SUBS:
        text = pattern.sub(new, text)
        return text

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


def split_lines(text):
    line_lexer = shlex(text)
    line_lexer.quotes = '"'
    line_lexer.whitespace = '\t\r\n'
    line_lexer.wordchars = set(printable) - set(
        line_lexer.escape + line_lexer.quotes + line_lexer.whitespace
    )
    return list(line_lexer)


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

def format_setting(identifier, values):
    return 'set {}'.format(
        ' '.join(filter(
            None,
            [identifier ] +
            format_values(values)
        ))
    )

def format_item(values):
    return 'add {}'.format(' '.join(format_values(values)))

# Command classes
# -----------------------------------------------------------------------------

class ConfigItem(object):

    def __init__(self, values=None):
        self.__values = OrderedDict()
        if values is not None:
            self.__values.update(values)

    def __str__(self):
        return format_item(self.values)

    def __repr__(self):
        return '<ConfigItem: {}>'.format(
            ' '.join(format_values(self.values))
        )

    def __eq__(self, other):
        return self.__values == other.__values

    @property
    def values(self):
        return self.__values


class ConfigSetting(ConfigItem):

    def __init__(self, identifier, *args, **kwargs):
        self.__identifier = identifier
        super(ConfigSetting, self).__init__(*args, **kwargs)

    def __str__(self):
        return format_setting(self.identifier, self.values)

    def __repr__(self):
        return '<ConfigSetting: {} {}>'.format(
            ' '.join(filter(None, chain(
                [self.identifier] + format_values(self.values)
            )))
        )

    def __eq__(self, other):
        return (
            self.__identifier == other.__identifier
            and super(ConfigSetting, self).__eq__(other)
        )

    @property
    def identifier(self):
        return self.__identifier


class ScriptCommand(object):
    __metaclass__ = ABCMeta

    multiline = False
    hide = False
    path = '/'

    pattern = "^(?P<text>{}?.*)$".format(PATH_RE)

    @classmethod
    def match(cls, text):
        options = VERBOSE,
        if cls.multiline:
            options += MULTILINE, DOTALL
        pattern = compile_regex(cls.pattern, *options)
        return pattern.match(text)

    @classmethod
    def parse(cls, match):
        groupdict = match.groupdict()
        path = groupdict['path'] or '/'
        return cls(path=path)

    @abstractproperty
    def text(self):
        pass

    def __str__(self):
        return self.text


class RawCommand(ScriptCommand):

    pattern = "^(?P<text>{}?(?<command>.*))".format(PATH_RE)

    @classmethod
    def parse(cls, match):
        groupdict = match.groupdict()
        path = groupdict['path'] or '/'
        command = groupdict['command']
        return cls(path=path, command=command)


    def __init__(self, command, **kwargs):
        self.__text = text
        super(RawCommand, self).__init__(**kwargs)

    @property
    def text(self):
        return self.__text

class ConfigCommand(ScriptCommand):

    def __init__(self, path, *args, **kwargs):
        self.__path = path
        super(ConfigCommand, self).__init__(*args, **kwargs)

    @property
    def path(self):
        return self.__path

    @abstractmethod
    def apply(self, section):
        pass

    @abstractproperty
    def command(self):
        pass

    @abstractproperty
    def options(self):
        pass

    @property
    def text(self):
        return ' '.join(filter(None, (self.path, self.full_command)))

    @property
    def full_command(self):
        return ' '.join(filter(None, (self.command, self.options)))


class KeyValuePairsCommand(ConfigCommand):

    def __init__(self, values, *args, **kwargs):
        self.__values = OrderedDict(values)
        super(KeyValuePairsCommand, self).__init__(*args, **kwargs)

    @property
    def values(self):
        return self.__values


class ItemCommand(ConfigCommand):
    pass


class ExistingItemCommand(ItemCommand):

    require_numeric_ids = True

    def __init__(self, index, *args, **kwargs):
        self.__index = index
        super(ExistingItemCommand, self).__init__(*args, **kwargs)

    @property
    def index(self):
        return self.__index


class PositionedItemCommand(ItemCommand):

    require_numeric_ids = True

    def __init__(self, *args, **kwargs):
        try:
            self.__destination = kwargs.pop('destination')
        except KeyError:
            self.__destination = None
        super(PositionedItemCommand, self).__init__(*args, **kwargs)

    @property
    def destination(self):
        return self.__destination

class DynamicIdentifierCommand(ConfigCommand):

    def __init__(self, identifier, *args, **kwargs):
        self.__identifier = identifier
        super(DynamicIdentifierCommand, self).__init__(*args, **kwargs)

    @property
    def identifier(self):
        return self.__identifier

    @property
    def require_numeric_ids(self):
        return isinstance(self.__identifier, int)


class AddCommand(KeyValuePairsCommand, PositionedItemCommand):

    command = 'add'
    pattern = """^(?P<text>{}?(?P<command>{})\s+{})$""".format(
        PATH_RE, command, VALUES_RE
    )

    def apply(self, section):
        section.insert_item(ConfigItem(self.values), destination=self.destination)

    @classmethod
    def parse(cls, match):
        groupdict = match.groupdict()
        path = groupdict['path'] or '/'
        values = parse_values(split(groupdict['values']))
        try:
            destination = int(values.pop('place-before'))
        except KeyError:
            destination = None
        return cls(path=path, values=values, destination=destination)

    @property
    def require_numeric_ids(self):
        return self.destination is not None

    @property
    def options(self):
        return ' '.join(filter(None, chain(
            format_values(self.values),
            [format_add_destination(self.destination)]
        )))

class RemoveCommand(ExistingItemCommand):

    command = 'remove'
    pattern = """^(?P<text>{}?(?P<command>{})\s+{})$""".format(
        PATH_RE, command, INDEX_RE
    )

    def apply(self, section):
        section.delete_item(section.items[self.index])

    @classmethod
    def parse(cls, match):
        groupdict = match.groupdict()
        path = groupdict['path'] or '/'
        index = int(groupdict['index'])
        return cls(path=path, index=index)

    @property
    def options(self):
        return str(self.index)

class MoveCommand(ExistingItemCommand, PositionedItemCommand):

    command = 'move'
    pattern = """^(?P<text>{}?(?P<command>{})\s+{}(\s+{}))$""".format(
        PATH_RE, command, INDEX_RE, DESTINATION_RE
    )

    def apply(self, section):
        section.move_item(section.items[self.index], destination=self.destination)

    @classmethod
    def parse(cls, match):
        groupdict = match.groupdict()
        path = groupdict['path'] or '/'
        index = int(groupdict['index'])
        destination = int(groupdict['destination']) - 1
        return cls(path=path, index=index, destination=destination)

    @property
    def options(self):
        if self.destination is not None:
            return ' '.join(map(str, (self.index, self.destination + 1)))
        else:
            return str(self.index)

class SetCommand(DynamicIdentifierCommand, KeyValuePairsCommand):

    command = 'set'
    pattern = "^(?P<text>{}?(?P<command>{})\s+{}\s+{})$".format(PATH_RE, command, IDENTIFIER_RE, VALUES_RE)

    def apply(self, section):
        section.set_settings(ConfigSetting(self.identifier, self.values))

    @classmethod
    def parse(cls, match):
        groupdict = match.groupdict()
        path = groupdict['path'] or '/'
        if groupdict['numeric_identifier']:
            identifier = int(groupdict['numeric_identifier'])
        else:
            identifier = groupdict['identifier']
        values = parse_values(split(groupdict['values']))
        return cls(path=path, identifier=identifier, values=values)

    @property
    def options(self):
        return ' '.join(filter(None, chain(
            [self.identifier],
            format_values(self.values)
        )))


class Enumerate(ScriptCommand):

    hide = True
    pattern = '^(?P<text>{}?(?P<command>print)\;)$'.format(PATH_RE)
    command = 'print ;'

# Parsing error class
# -------------------------------------------------------------------------

class ParseError(ValueError):
    pass


# Configuration section class
# -----------------------------------------------------------------------------
#
# Configuration section class: represents a list of commands that were exported
# by a remote device. `ConfigSection` objects are usually merged together to
# produce a `ScriptSection` representing the changes.
#
# This object extends :class:`ScriptSection`, to restrict the allowed commands
# to `add` and `set`, also disallowing the use of `place-before=`.
#
# It provides methods that allow itself to merge with another instance and
# return the resulting changes in a new :class:`ScriptSection` instance.


class MikrotikScript(object):

    # Initializer
    # -------------------------------------------------------------------------

    def __init__(self, sections=None):
        self.__sections = OrderedDict()
        if sections is not None:
            self.__sections.update(sections)

    def __str__(self):
        def _make_lines():
            for path, commands in self.__sections.items():
                yield path
                yield str()
                for command in commands:
                    yield command.full_command
        return '\n'.join(_make_lines())

    # Copy/load methods
    # -------------------------------------------------------------------------

    def copy(self):
        return type(self)(sections=self.__sections)

    def load(self, command):
        path = command.path
        try:
            commands = self.__sections[path]
        except KeyError:
            commands = self.__sections[path] = list()
        commands.append(command)

    @property
    def commands(self):
        return list(chain(*self.__sections.values()))

class ScriptSection(object):

    # Initializer
    # -------------------------------------------------------------------------

    def __init__(self, path):
        self.__path = path
        self.__commands = list()
        super(ScriptSection, self).__init__()

    def __str__(self):
        return '\n\n'.join((
            self.path,
            '\n'.join(command.full_command for command in self.__commands)
        ))


    def __nonzero__(self):
        return len(self.__commands)

    def __bool__(self):
        return self.__nonzero__()


    def load(self, command):
        self.__commands.append(command)

    def copy(self):
        new = type(self)(self.__path)
        for command in self.__commands:
            new.load(command)
        return new

    # Public properties
    # -------------------------------------------------------------------------

    @property
    def path(self):
        return self.__path

    @property
    def commands(self):
        return self.__commands


class ConfigSection(object):

    # Initializer
    # -------------------------------------------------------------------------

    def __init__(self, path, order_mode=None):
        self.__path = path
        if order_mode is not None:
            self.__order_mode = order_mode
        else:
            self.__order_mode = get_order_mode(path)
        self.__items = list()
        self.__settings = OrderedDict()
        super(ConfigSection, self).__init__()

    def __str__(self):
        return '\n'.join(map(str, chain(self.__items, self.__settings.values())))

    def __nonzero__(self):
        return len(self.__items) or len(self.__settings)

    def __bool__(self):
        return self.__nonzero__()

    def load(self, command):
        command.apply(self)

    def copy(self):
        new = type(self)(self.__path, order_mode=self.__order_mode)
        for item in self.__items:
            new.__insert_item(item)
        for settings in self.__settings:
            new.__set_settings(settings)
        return new

    def apply(self, script):
        for command in script.commands:
            self.load(command)

    # Ordering properties
    # -------------------------------------------------------------------------

    @property
    def ordered(self):
        return self.__order_mode in (ORDER, ORDER_APPEND)

    @property
    def ordered_insertion(self):
        return self.__order_mode == ORDER_APPEND

    # Raw change methods
    # -------------------------------------------------------------------------

    def __insert_item(self, item, destination=None):
        if destination is not None:
            self.__items.insert(destination, item)
        else:
            self.__items.append(item)

    def __delete_item(self, item):
        index = self.__items.index(item)
        self.__items.pop(index)
        return index

    def __move_item(self, item, destination=None):
        index = self.__delete_item(item)
        if destination is not None and index > destination:
            destination += 1
        self.__insert_item(item, destination)
        return index

    def __set_settings(self, settings):
        identifier = settings.identifier
        try:
            ours = self.settings[identifier]
        except KeyError:
            ours = self.settings[identifier] = ConfigSetting(identifier)
        different_values = {
            key: value
            for key, value in settings.values.items()
            if ours.values.get(key) != value
        }
        ours.values.update(different_values)
        return different_values


    # Change methods
    # -------------------------------------------------------------------------

    def insert_item(self, item, destination=None):
        if destination is not None:
            assert self.ordered and self.ordered_insertion, (
                "Cannot use place-before if ordered insertion is disabled."
            )
            assert destination <= len(self.__items), (
                "Cannot insert at out of range destination: {} ({})"
                "".format(destination, len(self.__items))
            )
            if destination + 1 >= len(self.__items):
                destination = None
        assert item not in self.__items, (
            "Cannot insert duplicate item."
        )
        self.__insert_item(item, destination)
        return AddCommand(path=self.__path, values=item.values, destination=destination)

    def delete_item(self, item):
        assert item in self.__items, (
            "Cannot delete non-existing item."
        )
        index = self.__delete_item(item)
        return RemoveCommand(path=self.__path, index=index)

    def move_item(self, item, destination=None):
        if destination is not None:
            assert self.ordered, (
                "Cannot use move item if non-ordered section."
            )
            assert destination <= len(self.__items), (
                "Cannot move to out of range destination: {}"
                "".format(destination)
            )
            if destination + 1 >= len(self.__items):
                destination = None
        assert item in self.__items, (
            "Cannot move non-existing item."
        )
        index = self.__move_item(item, destination)
        return MoveCommand(path=self.__path, index=index, destination=destination)

    def set_settings(self, settings):
        values = self.__set_settings(settings)
        if values:
            return SetCommand(path=self.__path, identifier=settings.identifier, values=values)

    # Settings merging methods
    # -------------------------------------------------------------------------

    def __update_settings(self, target):
        for settings in target.__settings.values():
            change = self.set_settings(settings)
            if change:
                yield change

    def __delete_removed(self, target):
        index = 0
        while index < len(self.__items):
            item = self.__items[index]
            if item not in target.__items:
                change = self.delete_item(item)
                if change:
                    yield change
            else:
                # not present, jump to next line
                index += 1

    def __insert_added(self, target):
        for index, item in enumerate(target.__items):
            if item not in self.items:
                yield self.insert_item(item, destination=index)

    def __update_positions(self, target):
        index = 0
        while index < len(self.__items):
            item = self.__items[index]
            target_index = target.__items.index(item)
            if index != target_index:
                change = yield self.move_item(item, target_index)
                if change:
                    yield change
                if target_index < index:
                    index += 1
                index += 1
                index = min(target_index, index)
            else:
                # matching index, jump to next line
                index += 1

    # Root merging method
    # -------------------------------------------------------------------------

    def __merge(self, target):
        assert isinstance(target, type(self)), (
            "Can not compare ConfigSections of different type"
        )
        for change in self.__update_settings(target):
            yield change
        for change in self.__delete_removed(target):
            yield change
        for change in self.__insert_added(target):
            yield change
        if self.ordered:
            for change in self.__update_positions(target):
                yield change

    def merge(self, target):
        new = ScriptSection(self.__path)
        for command in self.__merge(target):
            new.load(command)
        return new

    # Diff methods
    # -------------------------------------------------------------------------

    def difference(self, target):
        return self.copy().merge(target)

    # Public properties
    # -----------------------------------------------------------------------------

    @property
    def path(self):
        return self.__path

    @property
    def items(self):
        return self.__items

    @property
    def settings(self):
        return self.__settings


# Mikrotik configuration container class
# -----------------------------------------------------------------------------
#
# This object is a container for section config objects, and can be used to
# represent the configuration of a Mikrotik device, grouped by sections.
#
# It extends :class:`MikrotikScript` to allow parsing of an exported
# configuration, and allows merging itself with another instance, returning the
# changes wrapped in a :class:`MikrotikScript` that can then be executed on the
# remote device.

class MikrotikScript(object):

    allowed_commands = AddCommand, RemoveCommand, MoveCommand, SetCommand
    section_class = ScriptSection

    # Initializer
    # -------------------------------------------------------------------------

    def __init__(self):
        self.__sections = OrderedDict()

    def __str__(self):
        return '\n'.join(map(str, filter(None, self.__sections.values())))

    def __nonzero__(self):
        return any(self.__sections.values())

    def get_section(self, path):
        try:
            section = self.__sections[path]
        except KeyError:
            section = self.__sections[path] = self.section_class(path)
        return section

    def load(self, text, path=None):
        for cls in self.allowed_commands:
            match = cls.match(text)
            if match:
                command = cls.parse(match)
                break
        else:
            raise ParseError("Unknown command")
        section = self.get_section(path or command.path)
        section.load(command)

    def copy(self):
        new = type(self)()
        new.__sections.update(self.__sections)
        return new

    # Text import methods
    # -------------------------------------------------------------------------

    @classmethod
    def parse(cls, text):
        new, section = cls(), None
        for line in map(str.strip, split_lines(text)):
            if line.startswith('/'):
                path = line
            elif line:
                new.load(line, path)
        return new

    # Public properties
    # -------------------------------------------------------------------------

    @property
    def sections(self):
        return self.__sections


class MikrotikConfig(MikrotikScript):

    allowed_commands = AddCommand, SetCommand
    section_class = ConfigSection

    # Merging methods
    # -------------------------------------------------------------------------

    def __merge(self, target):
        for path, target_section in target.sections.items():
            try:
                section = self.sections[path]
            except KeyError:
                section = self.sections[path] = ConfigSection(path)
            yield path, section.merge(target_section)

    def merge(self, target):
        new = MikrotikScript()
        for path, script in self.__merge(target):
            new.sections[path] = script
        return new

    def difference(self, target):
        return self.copy().merge(target)

    def apply(self, script):
        for path, section_script in script.sections.items():
            section = self.get_section(path)
            section.apply(section_script)
