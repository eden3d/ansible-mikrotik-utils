from ansible_mikrotik_utils.commands import BaseSchedulerCommand

from .mixins import StaticPathMixin
from . import BaseSection


class SchedulerSection(StaticPathMixin, BaseSection):
    path = '/system scheduler'
    base_command_class = BaseSchedulerCommand

