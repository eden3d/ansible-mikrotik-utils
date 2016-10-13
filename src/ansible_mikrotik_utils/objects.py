from collections import OrderedDict
from itertools import chain

from ansible_mikrotik_utils.mixins import CopiableMixin
from ansible_mikrotik_utils.common import format_values


class ConfigItem(CopiableMixin):

    def __init__(self, values, *args, **kwargs):
        self.__values = values
        super(ConfigItem, self).__init__(*args, **kwargs)

    def __str__(self):
        return ' - {}'.format(format_values(self.values))

    def __repr__(self):
        return '<ConfigItem: {}>'.format(
            ' '.join(format_values(self.values))
        )

    def __eq__(self, other):
        return (
            other is not None and
            self.__values == other.values
        )

    def __ne__(self, other):
        return not self == other

    @property
    def copy_kwargs(self):
        kwargs = super(ConfigItem, self).copy_kwargs
        kwargs['values'] = self.values.copy()
        return kwargs

    @property
    def values(self):
        return self.__values


class ConfigSetting(ConfigItem):

    def __init__(self, identifier, *args, **kwargs):
        self.__identifier = identifier
        super(ConfigSetting, self).__init__(*args, **kwargs)

    def __str__(self):
        return '- {}: {}'.format(self.identifier, format_values(self.values))

    def __repr__(self):
        return '<ConfigSetting: {} {}>'.format(
            self.identifier, ' '.join(format_values(self.values))
        )

    def __eq__(self, other):
        return (
            super(ConfigSetting, self).__eq__(other) and
            other is not None and
            self.__identifier == other.identifier
        )

    @property
    def copy_args(self):
        args = super(ConfigSetting, self).copy_args
        args.append(self.identifier)
        return args

    @property
    def identifier(self):
        return self.__identifier


class ConfigBackup(CopiableMixin):

    def __init__(self, name, key, *args, **kwargs):
        self.__name = name
        self.__key = key
        super(ConfigBackup, self).__init__(*args, **kwargs)

    def __str__(self):
        return '@ backup: {}'.format(self.name)

    def __repr__(self):
        return '<ConfigBackup: {}>'.format(self.name)

    def __eq__(self, other):
        return self.__name == other.name

    @property
    def name(self):
        return self.__name

    @property
    def key(self):
        return self.__key

    @property
    def copy_kwargs(self):
        kwargs = super(ConfigBackup, self).copy_kwargs
        kwargs['name'] = self.name
        kwargs['key'] = self.key
        return kwargs


class ConfigTask(CopiableMixin):
    def __init__(self, name, source, *args, **kwargs):
        self.__name = name
        self.__source = source
        try:
            self.__interval = kwargs.pop('interval')
        except KeyError:
            self.__interval = None
        try:
            self.__start_time = kwargs.pop('start_time')
        except KeyError:
            self.__start_time = None
        if self.__interval is None and self.__start_time is None:
            raise TypeError("Scheduled task need an interval or start time.")
        super(ConfigTask, self).__init__(*args, **kwargs)

    def __str__(self):
        return '@ scheduled task: {}'.format(self.name)

    def __repr__(self):
        return '<ConfigTask: {}>'.format(self.name)

    def __eq__(self, other):
        return self.__name == other.name

    @property
    def copy_args(self):
        args = super(ConfigTask, self).copy_args
        args.append(self.name)
        args.append(self.source)
        return args

    @property
    def copy_kwargs(self):
        kwargs = super(ConfigTask, self).copy_args
        kwargs['interval'] = self.name
        kwargs['start_time'] = self.key
        return kwargs

    @property
    def name(self):
        return self.__name

    @property
    def source(self):
        return self.__source

    @property
    def interval(self):
        return self.__interval

    @property
    def start_time(self):
        return self.__start_time

