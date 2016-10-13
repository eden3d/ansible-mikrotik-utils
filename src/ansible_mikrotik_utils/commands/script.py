from .mixins import StaticCommandMixin, StaticOptionsMixin
from .mixins import NoCommandMixin, NoOptionsMixin
from .base import BaseScriptCommand

__all__ = [
    'RawCommand',
    'Export',
    'Enumerate',
    'ChangeSection',
]

class RawCommand(BaseScriptCommand):
    @classmethod
    def parse_match(cls, matched):
        for kwarg in super(RawCommand, cls).parse_match(matched):
            yield kwarg
        yield 'command', matched['command']
        yield 'options', matched['options']

    def __init__(self, command, options, **kwargs):
        self.__command = command
        self.__options = options
        super(RawCommand, self).__init__(**kwargs)

    @property
    def command(self):
        return self.__command

    @property
    def options(self):
        return self.__options


class Export(StaticCommandMixin, BaseScriptCommand):
    no_log_response = True
    command = 'export'


class Enumerate(NoOptionsMixin, StaticCommandMixin, BaseScriptCommand):
    hide = True
    command = 'print'
