from collections import OrderedDict
from itertools import chain
from weakref import ref

from ansible_mikrotik_utils.common import classproperty, ORDERED

from ansible_mikrotik_utils.commands import BaseConfigCommand
from ansible_mikrotik_utils.commands import AddCommand, RemoveCommand
from ansible_mikrotik_utils.commands import MoveCommand, SetCommand

from .base import BaseSection
from .mixins import StaticPathMixin
from .script import ScriptSection



class ConfigSection(BaseSection):

    ordering_mode = ORDERED
    base_section_class = None
    base_command_class = BaseConfigCommand
    base_insertion_command_class = AddCommand
    base_deletion_command_class = RemoveCommand
    base_move_command_class = MoveCommand
    base_set_command_class = SetCommand

    # Command classes
    # -------------------------------------------------------------------------

    @classproperty
    def insertion_command_class(cls):
        return cls.lookup_command_class(cls.base_insertion_command_class)

    @classproperty
    def deletion_command_class(cls):
        return cls.lookup_command_class(cls.base_deletion_command_class)

    @classproperty
    def move_command_class(cls):
        return cls.lookup_command_class(cls.base_move_command_class)

    @classproperty
    def set_command_class(cls):
        return cls.lookup_command_class(cls.base_set_command_class)


    # Initializer
    # -------------------------------------------------------------------------

    def __init__(self, *args, **kwargs):
        try:
            items = kwargs.pop('items')
        except KeyError:
            self.__items = list()
        else:
            self.__items = [item.copy() for item in items]
        try:
            settings = kwargs.pop('settings')
        except KeyError:
            self.__settings = OrderedDict()
        else:
            self.__settings = OrderedDict(
                (key, value.copy())
                for key, value in settings.items()
            )
        super(ConfigSection, self).__init__(*args, **kwargs)

    # Copy protocol
    # -------------------------------------------------------------------------

    @property
    def copy_kwargs(self):
        kwargs = super(ConfigSection, self).copy_kwargs
        kwargs['settings'] = OrderedDict(self.__settings)
        kwargs['items'] = list(self.__items)
        return kwargs

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
            self.settings[identifier] = settings.copy()
            difference = settings.values
        else:
            difference = {
                key: value
                for key, value in settings.values.items()
                if ours.values.get(key) != value
            }
            ours.values.update(difference)
        return difference

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
        return self.insertion_command_class(
            path=self.path,
            values=item.values,
            destination=destination
        )

    def delete_item(self, item):
        assert item in self.__items, (
            "Cannot delete non-existing item."
        )
        index = self.__delete_item(item)
        return self.deletion_command_class(
            path=self.path,
            index=index
        )

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
        return self.move_command_class(
            path=self.path,
            index=index,
            destination=destination
        )

    def set_settings(self, settings):
        values = self.__set_settings(settings)
        return self.set_command_class(
            path=self.path,
            identifier=settings.identifier,
            values=values
        )

    # Change application method
    # -------------------------------------------------------------------------

    def load_command(self, command):
        command.apply(self)
        super(ConfigSection, self).load_command(command)

    # Merging methods
    # -------------------------------------------------------------------------

    def __update_settings(self, target):
        for identifier, settings in target.__settings.items():
            if self.settings.get(identifier) != settings:
                yield self.set_settings(settings)

    def __delete_removed(self, target):
        index = 0
        while index < len(self.items):
            item = self.items[index]
            if item not in target.items:
                yield self.delete_item(item)
            else:
                index += 1

    def __insert_added(self, target):
        for index, item in enumerate(target.items):
            if item not in self.items:
                if self.ordered_insertion:
                    yield self.insert_item(item, index)
                else:
                    yield self.insert_item(item)

    def __update_positions(self, target):
        index = 0
        while index < len(self.items):
            item = self.items[index]
            destination = target.items.index(item)
            if index != destination:
                yield self.move_item(item, destination)
                if destination < (index - 1):
                    index += 1
            else:
                index += 1

    # Diff methods
    # -------------------------------------------------------------------------

    def __merge(self, target):
        for change in self.__update_settings(target):
            yield change
        for change in self.__delete_removed(target):
            yield change
        for change in self.__insert_added(target):
            yield change
        if self.ordered:
            for change in self.__update_positions(target):
                yield change

    def merge(self, section, parent=None):
        if parent is not None:
            script = ScriptSection(name=self.name, parent=parent)
        else:
            script = ScriptSection(name=self.name, device=self.device)
        for change in self.__merge(section):
            script.load_command(change)
        for name, child in section.children.items():
            script.children[name] = self[name].merge(child, parent=script)
        return script

    def difference(self, section):
        return self.copy().merge(section)

    def apply(self, script):
        for command in script.commands:
            command.apply(self)
        for name, child in section.children:
            self[name].apply(child)

    # Public properties
    # -------------------------------------------------------------------------

    @property
    def items(self):
        return self.__items

    @property
    def settings(self):
        return self.__settings
