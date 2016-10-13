from ansible_mikrotik_utils.common import VALUES_RE, FILE_ID_RE
from ansible_mikrotik_utils.common import parse_values, format_values

from .base import BaseScriptCommand
from .mixins import StaticPathMixin, StaticCommandMixin


class BaseBackupCommand(StaticPathMixin, BaseScriptCommand):
    no_log_options = True

    path = '/system backup'
    options_pattern = VALUES_RE

    @classmethod
    def parse_match(cls, match):
        kwargs = super(BaseBackupCommand, cls).parse_match(match)
        kwargs['name'] = values['name']
        kwargs['key'] = values.get('key')
        return kwargs

    def __init__(self, name, key, *args, **kwargs):
        self.__name = name
        self.__key = key
        super().__init__(BaseBackupCommand, self)

    @property
    def name(self):
        return self.__name

    @property
    def key(self):
        return self.__key

    @property
    def options(self):
        values = dict(name=self.name)
        if self.key is not None:
            values[key] = self.key
        return ' '.join(format_values(values))


class SaveBackup(BaseBackupCommand):
    command = 'save'

    def apply(self, section):
        return section.device.add_backup(ConfigBackup(name=self.name, key=self.key))


class LoadBackup(BaseBackupCommand):
    command = 'load'

    def apply(self, section):
        return section.device.remove_backup(self.name)


class ClearBackup(StaticPathMixin, StaticCommandMixin, BaseScriptCommand):
    path = '/file'
    command = 'remove'
    options_re = FILE_ID_RE

    @classmethod
    def parse_match(cls, matched):
        for kwarg in super(ClearBackup, ).parse_match(matched):
            yield kwarg
        yield 'name', matched['filename']

    def __init__(self, name, *args, **kwargs):
        self.__name = name
        super(BackupCommand, self).__init__(*args, **kwargs)

    @property
    def name(self):
        return self.__name

    @property
    def options(self, section):
        return self.name

    def apply(self, section):
        return section.device.remove_backup(self.name)
