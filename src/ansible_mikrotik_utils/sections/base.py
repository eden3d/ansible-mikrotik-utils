from collections import OrderedDict
from itertools import chain
from weakref import ref
from shlex import split
from abc import ABCMeta
from re import compile as compile_regex

from ansible_mikrotik_utils.exceptions import ParseError
from ansible_mikrotik_utils.mixins import SubclassStoreMixin
from ansible_mikrotik_utils.common import PATH_RE, classproperty, lookup_implementation
from ansible_mikrotik_utils.common import abstractclassproperty
from ansible_mikrotik_utils.common import format_path, split_lines, join
from ansible_mikrotik_utils.commands import BaseCommand

from .mixins import BaseSectionMixin


class SectionMeta(SubclassStoreMixin, ABCMeta):
    def get_type_sort_keys(cls, **kwargs):
        for key in super(SectionMeta, cls).get_type_sort_keys(**kwargs):
            yield key
        yield - len(cls.command_classes)

    def get_type_filter_key(cls, **kwargs):
        if not super(SectionMeta, cls).get_type_filter_key(**kwargs):
            return False
        return True


class BaseSection(BaseSectionMixin):
    __metaclass__ = SectionMeta

    # Implementation-defined types
    # -------------------------------------------------------------------------

    @abstractclassproperty
    def base_command_class(cls):
        pass

    @abstractclassproperty
    def base_section_class(cls):
        pass


    # Parsing
    # -------------------------------------------------------------------------

    @classmethod
    def parse_command(cls, text, *args, **kwargs):
        for cmd_cls in cls.command_classes:
            if not cmd_cls.greedy:
                match = cmd_cls.match(text)
                if match:
                    return cmd_cls.parse(match, *args, **kwargs)
        else:
            raise ParseError("Unknown command")

    @classmethod
    def from_text(cls, text, *args, **kwargs):
        new = cls(*args, **kwargs)
        new.load_text(text)
        return new

    # Specialization handling
    # -------------------------------------------------------------------------

    @classproperty
    def __path_pattern(cls):
        return compile_regex('^{}$'.format(cls.path_pattern))

    @classproperty
    def __name_pattern(cls):
        return compile_regex('^{}$'.format(cls.name_pattern))

    @classproperty
    def __base_section_class(cls):
        if cls.base_section_class is None:
            return cls
        else:
            return cls.base_section_class

    @classmethod
    def match_path(cls, text):
        return cls.__path_pattern.match(text)

    @classmethod
    def match_name(cls, text):
        return cls.__name_pattern.match(text)

    @classmethod
    def lookup_section_class(cls, path):
        for klass in reversed(cls.__base_section_class.lookup_subclasses()):
            if klass.match_path(path):
                return klass
        else:
            return cls

    # Command classes
    # -------------------------------------------------------------------------

    @classmethod
    def lookup_command_class(cls, target_klass, *args, **kwargs):
        return lookup_implementation(cls.base_command_class, target_klass, *args, **kwargs)

    @classproperty
    def command_class(cls):
        return cls.lookup_command_class(cls.base_command_class)

    @classproperty
    def command_classes(cls):
        return cls.base_command_class.lookup_subclasses()

    # Initializer
    # -------------------------------------------------------------------------

    def __init__(self, parent=None, name=None, commands=None,
                 children=None, device=None, path=None):
        if parent is not None:
            self.__parent_ref = ref(parent)
        else:
            self.__parent_ref = ref(self)

        if name is not None:
            self.__name = name
        elif self.static_path:
            self.__name = split(self.path)[0]
        else:
            self.__name = ''

        if self.path and not self.match_path(self.path):
            raise ValueError("Non-matching section path: {}".format(self.path))

        if device is not None:
            self.__device_ref = ref(device)
        elif parent is not None:
            self.__device_ref = None
        else:
            raise ValueError("Root section must be given a device.")

        if commands is not None:
            self.__commands = list(commands)
        else:
            self.__commands = list()

        if children is not None:
            self.__children = OrderedDict(
                (name, child.copy(parent=self))
                for name, child in children.items()
            )
        else:
            self.__children = OrderedDict()

        super(BaseSection, self).__init__(path=path)

    # Special methods
    # -------------------------------------------------------------------------

    def __str__(self):
        return '\n'.join(map(str, self.all_commands))

    def __nonzero__(self):
        return len(self.__commands)

    def __bool__(self):
        return self.__nonzero__()

    def __getitem__(self, name):
        try:
            child = self.__children[name]
        except KeyError as ex:
            if self.match_name(name):
                path = format_path(self.ascendant_names + [name])
                child = self.__children[name] = self.lookup_section_class(path)(self, name)
            else:
                raise
        return child

    def __iter__(self):
        return iter(self.all_commands)

    def __contains__(self, name):
        return name in self.__children

    # Copy protocol
    # -------------------------------------------------------------------------

    @property
    def copy_kwargs(self):
        kwargs = super(BaseSection, self).copy_kwargs
        kwargs['name'] = self.__name
        kwargs['commands'] = self.__commands
        if self.parent is self:
            kwargs['device'] = self.device
        kwargs['children'] = self.__children
        return kwargs

    # Input text
    # -------------------------------------------------------------------------

    def load_lines(self, lines):
        current = self

        for line in lines:
            if line.startswith('/'):
                current = self
                line = line.lstrip('/')
            words = list(split(line))
            while words:
                word = words.pop(0)
                try:
                    current = current.children[word]
                except KeyError:
                    pass
                else:
                    continue
                try:
                    command = current.parse_command(join(word, *words), path=current.path)
                except ParseError:
                    pass
                else:
                    current.load_command(command)
                    break
                try:
                    current = current[word]
                except KeyError:
                    pass
                else:
                    continue
                raise ParseError("Could not parse line: {} (in {})".format(repr(line), current.path))

    def load_text(self, text):
        return self.load_lines(map(str.strip, filter(None, split_lines(text))))

    def load_command(self, command):
        self.commands.append(command)

    # Tree traversal
    # -------------------------------------------------------------------------

    def traverse(self):
        yield self
        for child in self.__children.values():
            for grandchild in child.traverse():
                yield grandchild

    # Public properties
    # -------------------------------------------------------------------------

    @property
    def name(self):
        return self.__name

    @property
    def commands(self):
        return self.__commands

    @property
    def all_commands(self):
        return list(chain(*(section.commands for section in self.traverse())))

    @property
    def children(self):
        return self.__children

    @property
    def parent(self):
        return self.__parent_ref()

    @property
    def device(self):
        if self.__device_ref is not None:
            return self.__device_ref()
        else:
            return self.parent.device

    # Public methods
    # -------------------------------------------------------------------------

    @property
    def ascendants(self):
        if self.parent is not None:
            if self.parent is not self:
                for ascendant in self.parent.ascendants:
                    yield ascendant
            yield self.parent

    @property
    def ascendant_names(self):
        return list(ascendant.name for ascendant in self.ascendants if ascendant.name)

    @property
    def path(self):
        return format_path(self.ascendant_names + [self.name])

