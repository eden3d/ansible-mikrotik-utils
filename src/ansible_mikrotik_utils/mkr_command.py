#!/usr/bin/env python

# Main module handler
# =============================================================================

def main():
    argument_spec = dict(
        commands=dict(type='list', required=True),
        before=dict(type='list'),
        after=dict(type='list'),
    )
    module = MikrotikModule(
        argument_spec=argument_spec,
        supports_check_mode=True
    )
    commands = module.params['commands']
    before = module.params['before']
    after = module.params['after']

    with module:
        result = dict(changed=False)

        response, changes = module.execute(commands, before, after)

        if module.backup_name:
            result['backup_name'] = str(module.backup_name)
        result['history'] = list(module.history)

        result['response'] = str(response)
        result['changed'] = bool(changes)

        module.exit_json(**result)

# Imports
# =============================================================================

from ansible.module_utils.basic import *  # NOQA
from ansible_mikrotik_utils import MikrotikModule


if __name__ == '__main__':
    main()
