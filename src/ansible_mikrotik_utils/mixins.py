from functools import partial
from itertools import chain
from weakref import ref, WeakSet
from inspect import isabstract
from abc import ABCMeta

from ansible_mikrotik_utils.common import NAME_RE, PATH_RE, UNORDERED
from ansible_mikrotik_utils.common import abstractclassproperty


class SubclassStoreMixin(type):
    __subclasses = None

    def get_type_filter_key(cls, **kwargs):
        return True

    def get_type_sort_keys(cls, **kwargs):
        yield - len(cls.mro())

    @property
    def _subclasses(cls):
        if cls.__subclasses is not None:
            for klass in cls.__subclasses:
                if issubclass(klass, cls):
                    yield klass

    def lookup_subclasses(cls, **kwargs):
        _filter = partial(filter, lambda x: bool(x.get_type_filter_key()))
        _sorted = partial(sorted, key=lambda x: tuple(x.get_type_sort_keys()), reverse=True)
        return list(_sorted(_filter(cls._subclasses)))

    def __init__(cls, name, bases, attrs):
        super(SubclassStoreMixin, cls).__init__(name, bases, attrs)
        if cls.__subclasses is None:
            cls.__subclasses = WeakSet()
        if not isabstract(cls):
            cls.__subclasses.add(cls)


class BaseMixin(object):
    __metaclass__ = ABCMeta

    @property
    def copy_kwargs(self):
        return {}

    @property
    def copy_args(self):
        return []


class OrderedMixin(BaseMixin):

    ordering_mode = UNORDERED

    # -------------------------------------------------------------------------

    @property
    def ordered(cls):
        return cls.ordering_mode.ordered

    @property
    def ordered_insertion(cls):
        return cls.ordering_mode.ordered_insertion


class CopiableMixin(BaseMixin):
    def copy(self, *args, **kwargs):
        combined_args = list(chain(args, self.copy_args))
        combined_kwargs = dict(self.copy_kwargs)
        combined_kwargs.update(kwargs)
        return type(self)(*combined_args, **combined_kwargs)


class BasePathMixin(BaseMixin):
    path_pattern = PATH_RE
    name_pattern = NAME_RE

    static_path = False
    __path = None

    def __init__(self, *args, **kwargs):
        args = list(args)
        try:
            path = args.pop(0)
        except IndexError:
            try:
                path = kwargs.pop('path')
            except KeyError:
                path = None
        if path is not None:
            if self.path is None:
                self.__path = path
            elif path != self.path:
                raise ValueError(
                    "The {} class already defines path as {}, cannot override to {}."
                    "".format(type(self).__name__, self.path, path)
                )
        elif self.path is None:
            raise ValueError("No path given")
        super(BasePathMixin, self).__init__(*args, **kwargs)

    @property
    def path(self):
        return self.__path

    @property
    def copy_kwargs(self):
        kwargs = super(BasePathMixin, self).copy_kwargs
        kwargs['path'] = self.path
        return kwargs


class StaticPathMixin(BasePathMixin):

    static_path = True

    @abstractclassproperty
    def path(cls):
        pass

    @abstractclassproperty
    def path_pattern(cls):
        return make_path_re(cls.path)




