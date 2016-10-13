from ansible_mikrotik_utils.common import VALUES_RE, FILE_ID_RE
from ansible_mikrotik_utils.common import parse_values, format_values

from .base import BaseConfigCommand
from .mixins import StaticPathMixin
from .config import AddCommand, RemoveCommand


class BaseSchedulerCommand(StaticPathMixin, BaseConfigCommand):
    path = '/system scheduler'


class AddScheduledTask(AddCommand, BaseSchedulerCommand):

    def apply(self, section):
        section.device.add_task(
            name=self.name, source=self.source,
            start_time=self.start_time, interval=self.interval
        )
        return super(AddScheduledTask, self).apply(section)

    @property
    def name(self):
        return self.__values['name']

    @property
    def source(self):
        return self.__values['source']

    @property
    def start_time(self):
        return self.__values.get('start-time')

    @property
    def interval(self):
        return self.__values.get('interval')


class RemoveScheduledTask(RemoveCommand, BaseSchedulerCommand):

    def apply(self, section):
        section.device.remove_task(
            section.items[self.index].name
        )
        return super(RemoveScheduledTask, self).apply(section)
