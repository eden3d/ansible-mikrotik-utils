#!/usr/bin/env python

# Main module handler
# =============================================================================

def main():
    argument_spec = dict(
        config=dict(required=True),
        before=dict(type='list'),
        after=dict(type='list'),
    )
    module = MikrotikModule(
        argument_spec=argument_spec,
        supports_check_mode=True # oh yeah
    )
    config = module.params['config']
    before = module.params['before']
    after = module.params['after']

    result = dict(changed=False)

    response, changes = module.configure(config, before, after)
    updates = changes.export(pretty=True, header=False, blank=False)

    result['backup_name'] = str(module.backup_name)
    result['history'] = list(module.history)

    result['response'] = str(response)
    result['changed'] = bool(changes)
    result['updates'] = list(updates)

    module.exit_json(**result)

# Imports
# =============================================================================

from ansible.module_utils.basic import *  # NOQA
from ansible_mikrotik_utils import MikrotikModule


if __name__ == '__main__':
    main()
