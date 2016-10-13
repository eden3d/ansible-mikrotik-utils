from ansible_mikrotik_utils.common import abstractclassproperty
from ansible_mikrotik_utils.mixins import OrderedMixin, CopiableMixin
from ansible_mikrotik_utils.mixins import BasePathMixin
from ansible_mikrotik_utils.mixins import StaticPathMixin as BaseStaticPathMixin


class BaseSectionMixin(OrderedMixin, CopiableMixin, BasePathMixin):
    pass


class StaticPathMixin(BaseStaticPathMixin, BaseSectionMixin):
    pass

