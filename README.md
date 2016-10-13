ansible-mikrotik-utils
======================

This library provides a way to represent Mikrotik devices configuration and
determine the changes required to get the device to another configuration. This
makes it possible to properly manage Mikrotik devices from configuration
management tools, such as Ansible.

Current status
--------------

 - This is still a WIP, as indicated by the version number.
 - Two example modules are provided in `mkr`: mkr_config, and mkr_command
 - mkr_config provides a good example of the features of this library

 - the library uses a Python object structure to store the configuration, 
   and is able to merge and compare them.

More notes:

 - Mikrotik does not use a configuration file
 - The only way to completely configure a device (API has too much limitations) is by a sequence of commands passed to the interpreter
 - This is how export/import works

 - This means that the only way to represent a device's configuration is the sequence of commands that executed on it since the default configuration.
 - So, in order to make idempotent changes, we need to parse the existing sequence of commands, compare it to a target configuration, and determine the required commands to apply the change.
 - In order to do this, we need to parse some parts of the Mikrotik shell syntax (add/remove/move/set) and simulate its execution.

Install
-------

`pip install ansible-mikrotik-utils`

Documentation
-------------

TODO

License
-------

See `LICENSE.txt`.

Unit tests
----------

There is currently only a single unit test located in `src/test`.


