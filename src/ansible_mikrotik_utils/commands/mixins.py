from re import escape

from ansible_mikrotik_utils.common import classproperty, abstractclassmethod, abstractclassproperty
from ansible_mikrotik_utils.common import PATH_RE
from ansible_mikrotik_utils.mixins import BasePathMixin
from ansible_mikrotik_utils.mixins import StaticPathMixin as BaseStaticPathMixin
from ansible_mikrotik_utils.objects import ConfigItem, ConfigSetting


class BaseCommandMixin(BasePathMixin):

    static_command = False
    static_options = False

    @classproperty
    def greedy(cls):
        return not cls.static_path and not cls.static_command
    


class StaticPathMixin(BaseStaticPathMixin, BaseCommandMixin):
    pass


class StaticCommandMixin(BaseCommandMixin):

    static_command = True

    @abstractclassproperty
    def command(cls):
        pass

    @classproperty
    def command_pattern(cls):
        return '(?P<command>{})'.format(escape(cls.command))


class StaticOptionsMixin(BaseCommandMixin):

    static_options = True

    @abstractclassproperty
    def options(cls):
        pass

    @classproperty
    def options_pattern(cls):
        return '(?P<options>{})'.format(escape(cls.options))


class NoCommandMixin(StaticCommandMixin):
    command = ''


class NoOptionsMixin(StaticOptionsMixin):
    options = ''


class KeyValuePairsMixin(BaseCommandMixin):

    def __init__(self, values, *args, **kwargs):
        self.__values = values.copy()
        super(KeyValuePairsMixin, self).__init__(*args, **kwargs)

    @property
    def values(self):
        return self.__values


class ExistingItemMixin(BaseCommandMixin):

    require_numeric_ids = True

    def __init__(self, index, *args, **kwargs):
        self.__index = index
        super(ExistingItemMixin, self).__init__(*args, **kwargs)

    @property
    def index(self):
        return self.__index


class PositionedItemMixin(BaseCommandMixin):

    require_numeric_ids = True

    def __init__(self, *args, **kwargs):
        try:
            self.__destination = kwargs.pop('destination')
        except KeyError:
            self.__destination = None
        super(PositionedItemMixin, self).__init__(*args, **kwargs)

    @property
    def destination(self):
        return self.__destination


class DynamicIdentifierMixin(BaseCommandMixin):

    def __init__(self, identifier, *args, **kwargs):
        self.__identifier = identifier
        super(DynamicIdentifierMixin, self).__init__(*args, **kwargs)

    @property
    def identifier(self):
        return self.__identifier

    @property
    def require_numeric_ids(self):
        return isinstance(self.__identifier, int)


class InsertionMixin(PositionedItemMixin, KeyValuePairsMixin):
    entity_type = ConfigItem


class DeletionMixin(ExistingItemMixin):
    entity_type = ConfigItem


class MoveMixin(ExistingItemMixin, PositionedItemMixin):
    entity_type = ConfigItem


class SettingMixin(DynamicIdentifierMixin, KeyValuePairsMixin):
    entity_type = ConfigSetting
