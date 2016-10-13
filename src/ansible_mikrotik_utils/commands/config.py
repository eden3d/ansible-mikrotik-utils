from itertools import chain
from shlex import split

from ansible_mikrotik_utils.common import VALUES_RE, INDEX_RE
from ansible_mikrotik_utils.common import DESTINATION_RE, IDENTIFIER_RE
from ansible_mikrotik_utils.common import parse_values, format_values, format_add_destination

from .base import BaseConfigCommand
from .mixins import InsertionMixin, DeletionMixin, MoveMixin, SettingMixin

__all__ = [
    'AddCommand',
    'RemoveCommand',
    'MoveCommand',
    'SetCommand'
]



class AddCommand(InsertionMixin, BaseConfigCommand):

    command = 'add'
    options_pattern = VALUES_RE

    @classmethod
    def parse_match(cls, matched):
        values = parse_values(split(matched['values']))
        try:
            destination = values.pop('place-before')
        except KeyError:
            destination = None
        kwargs = super(AddCommand, cls).parse_match(matched)
        kwargs['values'] = values
        kwargs['destination'] = destination
        return kwargs

    @property
    def require_numeric_ids(self):
        return self.destination is not None

    @property
    def options(self):
        return ' '.join(filter(None, chain(
            format_values(self.values),
            [format_add_destination(self.destination)]
        )))

    def apply(self, section):
        super(AddCommand, self).apply(section)
        section.insert_item(self.entity_type(self.values), destination=self.destination)

class RemoveCommand(DeletionMixin, BaseConfigCommand):
    command = 'remove'
    options_pattern = INDEX_RE

    @classmethod
    def parse_match(cls, matched):
        kwargs = super(RemoveCommand, cls).parse_match(matched)
        kwargs['index'] = int(matched['index'])
        return kwargs

    @property
    def options(self):
        return str(self.index)

    def apply(self, section):
        super(RemoveCommand, self).apply(section)
        return section.delete_item(section.items[self.index])

class MoveCommand(MoveMixin, BaseConfigCommand):
    command = 'move'
    options_pattern = '{}(\s{})?'.format(INDEX_RE, DESTINATION_RE)

    @classmethod
    def parse_match(cls, matched):
        kwargs = super(MoveCommand, cls).parse_match(matched)
        kwargs['index'] = int(matched['index'])
        kwargs['destination'] = int(matched['destination']) - 1
        return kwargs

    @property
    def options(self):
        if self.destination is not None:
            return ' '.join(map(str, (self.index, self.destination + 1)))
        else:
            return str(self.index)

    def apply(self, section):
        super(MoveCommand, self).apply(section)
        section.move_item(section.items[self.index], destination=self.destination)

class SetCommand(SettingMixin, BaseConfigCommand):
    command = 'set'
    options_pattern = '{}(\s{})'.format(IDENTIFIER_RE, VALUES_RE)

    @classmethod
    def parse_match(cls, matched):
        kwargs = super(SetCommand, cls).parse_match(matched)
        if matched['numeric_identifier']:
            kwargs['identifier'] = int(matched['numeric_identifier'])
        else:
            kwargs['identifier'] = matched['identifier']
        kwargs['values'] = parse_values(split(matched['values']))
        return kwargs

    @property
    def options(self):
        return ' '.join(filter(None, chain(
            [self.identifier],
            format_values(self.values)
        )))

    def apply(self, section):
        super(SetCommand, self).apply(section)
        section.set_settings(self.entity_type(self.identifier, self.values))
