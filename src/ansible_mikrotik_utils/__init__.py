from ansible_mikrotik_utils.config import MikrotikConfig

__all__ = ['compare', 'MikrotikConfig']


def compare(base, target):
    if isinstance(base, str):
        base = MikrotikConfig.parse(base)
    if isinstance(target, str):
        target = MikrotikConfig.parse(target)
    return base.difference(target)



