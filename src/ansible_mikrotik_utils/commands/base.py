from functools import partial
from inspect import isabstract
from abc import ABCMeta, abstractproperty, abstractmethod
from re import compile as compile_regex, MULTILINE, VERBOSE, DOTALL

from ansible_mikrotik_utils.common import format_censored, classproperty
from ansible_mikrotik_utils.common import abstractclassproperty
from ansible_mikrotik_utils.common import PATH_RE, COMMAND_RE, OPTIONS_RE, optional_re
from ansible_mikrotik_utils.mixins import SubclassStoreMixin

from .mixins import BaseCommandMixin, StaticCommandMixin

__all__ = [
    'CommandMeta',
    'BaseCommand',
    'BaseScriptCommand',
    'BaseConfigCommand',
]


class CommandMeta(SubclassStoreMixin, ABCMeta):
    static_path = False
    static_command = False
    static_options = False

    config_command = False
    script_command = False

    def get_type_sort_keys(cls, **kwargs):
        yield cls.static_path
        yield cls.static_command
        yield cls.static_options
        for key in super(CommandMeta, cls).get_type_sort_keys(**kwargs):
            yield key

    def get_type_filter_key(cls, **kwargs):
        try:
            only_script = kwargs.pop('only_script')
        except KeyError:
            only_script = False
        try:
            only_config = kwargs.pop('only_config')
        except KeyError:
            only_config = False
        if not super(CommandMeta, cls).get_type_filter_key(**kwargs):
            return False
        if only_script and not cls.sript_command:
            return False
        if only_config and not cls.config_command:
            return False
        return True


class BaseCommand(BaseCommandMixin):
    __metaclass__ = CommandMeta

    multiline = False
    hide = False

    no_log = False
    no_log_command = False
    no_log_options = False
    no_log_response = False
    no_log_error = False
    no_history = False

    default_path = '/'

    command_pattern = COMMAND_RE
    options_pattern = optional_re(OPTIONS_RE)

    # Matching/parsing
    # -------------------------------------------------------------------------

    @classproperty
    def pattern(cls):
        options = VERBOSE,
        if cls.multiline:
            options += MULTILINE, DOTALL
        return compile_regex("^(?P<text>{}\s*{})$".format(
            cls.command_pattern, cls.options_pattern
        ), *options)

    @classmethod
    def match(cls, text):
        return cls.pattern.match(text)

    @classmethod
    def parse_match(cls, match):
        return dict()

    @classmethod
    def parse(cls, match, **kwargs):
        matched = match.groupdict()
        parsed = dict(cls.parse_match(matched))
        parsed.update({key: value for key, value in kwargs.items() if value is not None})
        return cls(**parsed)

    # Initializer
    # -------------------------------------------------------------------------

    def __init__(self, path):
        super(BaseCommand, self).__init__(path)

    # Special methods
    # -------------------------------------------------------------------------

    def __str__(self):
        return self.text

    def __eq__(self, other):
        return self.full_command == other.full_command

    # History handling methods
    # -------------------------------------------------------------------------

    def make_command_history_text(self):
        if not self.no_history:
            if self.no_log or self.no_log_command:
                return format_censored(self.full_command)
            else:
                if self.no_log_options:
                    return ' '.join((
                        self.path,
                        self.command,
                        format(format_censored(self.options))
                    ))
                else:
                    return self.full_command

    def make_response_history_text(self, response, error=False):
        if not self.no_history:
            no_log = self.no_log_error if error else self.no_log_response
            if self.no_log or no_log:
                return format_censored(response)
            else:
                return response

    # Public properties
    # -------------------------------------------------------------------------

    @property
    def full_command(self):
        return ' '.join(filter(None, (self.command, self.options)))

    @property
    def text(self):
        return ' '.join(filter(None, (self.path, self.full_command)))

    # Implementation-dependent methods & properties
    # -------------------------------------------------------------------------

    @abstractproperty
    def command(self):
        pass

    @abstractproperty
    def options(self):
        pass

    @abstractproperty
    def options(self):
        pass


class BaseScriptCommand(BaseCommand):
    pass


class BaseConfigCommand(StaticCommandMixin, BaseCommand):
    @abstractclassproperty
    def entity_type(cls):
        pass

    @abstractmethod
    def apply(self, section):
        pass

