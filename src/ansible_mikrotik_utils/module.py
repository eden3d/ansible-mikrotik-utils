import paramiko
import sys

from re import compile as compile_regex

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.basic import env_fallback, get_exception
from ansible.module_utils.shell import Shell, ShellError

from ansible_mikrotik_utils.script import EXPORT_REFRESH_SPECIAL_COMMENT
from ansible_mikrotik_utils.config import MikrotikConfig

from paramiko import SSHException, util
from getpass import getuser

if __debug__:
    paramiko.util.log_to_file('/dev/stderr')

# Constants
# =============================================================================

CLI_PROMPTS_RE = [
    compile_regex(r"\[([\w\-]+)@([\.\w\-]+)\]\s(\/(\w+\s?)*)?\>"),
]

CLI_ERRORS_RE = [
    compile_regex(r"failure: (.*)"),
    compile_regex(r"bad command name ([\w\-]+) \(line \d+ column \d+\)"),
    compile_regex(r"syntax error \(line \d+ column \d+\)"),
    compile_regex(r"expected end of command \(line \d+ column \d+\)"),
    compile_regex(r"expected command name \(line \d+ column \d+\)"),

]

NET_COMMON_ARGS = dict(
    host=dict(required=True),
    port=dict(default=22, type='int'),
    username=dict(fallback=(env_fallback, ['ANSIBLE_NET_USERNAME'])),
    password=dict(no_log=True, fallback=(env_fallback, ['ANSIBLE_NET_PASSWORD'])),
    ssh_keyfile=dict(fallback=(env_fallback, ['ANSIBLE_NET_SSH_KEYFILE']), type='path'),
    authorize=dict(default=False, fallback=(env_fallback, ['ANSIBLE_NET_AUTHORIZE']), type='bool'),
    auth_pass=dict(no_log=True, fallback=(env_fallback, ['ANSIBLE_NET_AUTH_PASS'])),
    provider=dict(),
    timeout=dict(default=10, type='int')
)

BACKUP_ARGS = dict(
    backup_name=dict(fallback=(env_fallback, ['MIKROTIK_BACKUP_NAME'])),
    backup_key=dict(no_log=True, fallback=(env_fallback, ['MIKROTIK_BACKUP_KEY'])),
)

RESTORE_ARGS = dict(
    restore_on_error=dict(default=False, fallback=(env_fallback, ['MIKROTIK_RESTORE_ON_ERROR']), type='bool'),
    restore_on_reboot=dict(default=False, fallback=(env_fallback, ['MIKROTIK_RESTORE_ON_REBOOT']), type='bool'),
    restore_on_timeout=dict(default=0, fallback=(env_fallback, ['MIKROTIK_RESTORE_ON_TIMEOUT']), type='int'),
)

# Utilities
# =============================================================================

def make_random_text(length=12):
    return ''.join(
        SystemRandom().choice(
            string.ascii_uppercase + string.digits
        ) for _ in range(length)
    )

def make_random_name():
    return make_random_text(length=6)

def make_random_password():
    return make_random_text(length=16)


# Ansible module implementation
# =============================================================================

class MikrotikModule(AnsibleModule):

    # Class attributes and initializer
    # -------------------------------------------------------------------------
    config_class = MikrotikConfig
    catched_exceptions = SSHException, ShellError, IOError
    backup_extension = '.backup'
    stripped_sections = '/system scheduler',
    ssh_username_suffix = '+ct'

    def __init__(self, *args, **kwargs):
        kwargs['argument_spec'].update(NET_COMMON_ARGS)
        kwargs['argument_spec'].update(BACKUP_ARGS)
        kwargs['argument_spec'].update(RESTORE_ARGS)
        super(MikrotikModule, self).__init__(*args, **kwargs)
        self.__shell = None
        self.__config = None
        self.__protected = False
        self.__history = list()
        self.___backup_name = None
        self.___backup_key = None

    # Public properties
    # -------------------------------------------------------------------------

    @property
    def connected(self):
        return self.__shell is not None

    @property
    def protected(self):
        return self.__protected

    @property
    def history(self):
        return self.__history

    @property
    def backedup(self):
        return self.__backedup

    @property
    def config(self):
        if self.__config is None:
            self.__config = self.__export()
        return self.__config

    @property
    def backup_name(self):
        return self.___backup_name

    # Internal properties
    # -------------------------------------------------------------------------

    # SSH parameters

    @property
    def __ssh_host(self):
        return self.params['host']

    @property
    def __ssh_port(self):
        return self.params['port']

    @property
    def __ssh_username(self):
        username = self.params['username'] or getuser()
        if not username.endswith(self.ssh_username_suffix):
            username = ''.join((username, self.ssh_username_suffix))
        return username

    @property
    def __ssh_password(self):
        return self.params['password']

    @property
    def __ssh_timeout(self):
        return self.params['timeout']

    @property
    def __ssh_keyfile(self):
        return self.params['ssh_keyfile']

    # Backup

    @property
    def __protection_required(self):
        return any in (
            self.params['restore_on_error'],
            self.params['restore_on_reboot'],
            self.params['restore_on_timeout'],
        )

    @property
    def __backup_required(self):
        return self.__protection_required or self.params['backup_name']

    @property
    def __backup_name(self):
        if self.__backup_required and self.___backup_name is None:
            try:
                self.___backup_name = self.params['backup_name']
            except KeyError:
                self.___backup_name = make_random_name()
        return self.___backup_name

    @property
    def __backup_key(self):
        if self.__backup_required and self.___backup_key is None:
            try:
                self.___backup_key = self.params['backup_key']
            except KeyError:
                self.___backup_key = make_random_password()
        return self.___backup_key

    @property
    def __backup_path(self):
        if not self.__backup_name.endswith(self.backup_extension):
            return ''.join((self.__backup_name, self.backup_extension))
        else:
            return self.__backup_name

    @property
    def __backup_args(self):
        return 'name={} password={}'.format(self.__backup_name, self.__backup_key)

    @property
    def __backup_save_command(self):
        return '/system backup save {}'.format(self.__backup_args)

    @property
    def __backup_load_command(self):
        return '/system backup load {}'.format(self.__backup_args)

    @property
    def __backup_cleanup_command(self):
        return '/file remove {}'.format(self.__backup_path)

    # Restore

    @property
    def __restore_tasks(self):
        if self.__restore_on_reboot:
            yield (
                'restore_on_reboot',
                'startup-time=reboot source="{}"'
                ''.format(self.__backup_load_command)
            )
        if self.__restore_on_timeout:
            yield (
                'restore_on_reboot',
                'interval={} source="{}"'
                ''.format(
                    timedelta(self.restore_on_timeout),
                    self.__backup_load_command
                )
            )


    # Module parameters handling
    # -------------------------------------------------------------------------

    def _load_params(self):
        super(MikrotikModule, self)._load_params()
        provider = self.params.get('provider') or dict()
        for key, value in provider.items():
            if key in NET_COMMON_ARGS:
                if self.params.get(key) is None and value is not None:
                    self.params[key] = value

    # Connection handling
    # -------------------------------------------------------------------------

    def __connect(self):
        if self.__shell is None:
            self.__shell = shell = Shell(
                kickstart=True,
                prompts_re=CLI_PROMPTS_RE,
                errors_re=CLI_ERRORS_RE,
            )
            try:

                shell.open(
                    host=self.__ssh_host,
                    port=self.__ssh_port,
                    username=self.__ssh_username,
                    password=self.__ssh_password,
                    key_filename=self.__ssh_keyfile,
                    timeout=self.__ssh_timeout,
                    allow_agent=True, look_for_keys=False
                )
            except self.catched_exceptions as ex:
                message = "Failed to connect to {}@{}:{} : {}".format(
                    self.__ssh_username, self.__ssh_host, self.__ssh_port,
                    get_exception().message or ' '.join((type(ex).__name__, str(ex)))
                )
                self.fail_json(msg=message)
                assert False
            else:
                self.__backedup = False

    def __disconnect(self):
        if self.__shell is not None:
            self.__cleanup()
            self.__shell.close()
            self.__shell = None

    def __send(self, commands, **kwargs):
        self.__connect()

        no_log = kwargs.pop('no_log') if 'no_log' in kwargs else False
        no_log_command = kwargs.pop('no_log_command') if 'no_log_command' in kwargs else False
        no_log_response = kwargs.pop('no_log_response') if 'no_log_response' in kwargs else False
        responses = list()

        for command in commands:
            if EXPORT_REFRESH_SPECIAL_COMMENT not in command:
                if no_log_command:
                    self.__history.append("command: <censured...>")
                else:
                    self.__history.append("command: {}".format(command))
            try:
                response = self.__shell.send(command, **kwargs)
            except self.catched_exceptions:
                self.__history.append("error: {}: {}".format(type(ex).__name__, str(ex)))
                raise
            else:
                response_raw = response[0]
                response_text = response_raw.replace('\n', '').strip().lstrip(command).strip()
                if EXPORT_REFRESH_SPECIAL_COMMENT not in command:
                    if no_log_response:
                        self.__history.append(
                            "response: <{} characters, {} lines censured...>"
                            "".format(len(response_raw), len(response_raw.split('\n')))
                        )
                    else:
                        self.__history.append("response: {}".format(response_text))
                    responses.append(response_raw)

        return responses

    # Device protection handling
    # -------------------------------------------------------------------------

    def __protect(self):
        if self.__protection_required and not self.__protected:
            for name, args in self.__restore_tasks:
                self.__send(('/system scheduler add name={} {}'.format(name, args),))
            self.__backup()
            self.__protected = True

    def __unprotect(self):
        if self.__protection_required and not self.__protected:
            for name, args in self.__restore_tasks:
                self.__send(('/system scheduler remove {}'.format(name, args),))
            self.__cleanup()
            self.__protected = False

    # Backup handling
    # -------------------------------------------------------------------------

    def __backup(self):
        if self.__backup_required and not self.__backedup:
            self.__cleanup()
            self.__send((self.__backup_save_command,))
            self.__backedup = True

    def __cleanup(self):
        if self.__backup_required and self.__backedup:
            self.__unprotect()
            self.__send((self.__backup_cleanup_command,))
            self.__backedup = False

    # Restore
    # -------------------------------------------------------------------------

    def __restore(self):
        self.__send((self.__backup_load_command,))

    # Configuration export by device
    # -------------------------------------------------------------------------

    def __make_config(self, text):
        return self.config_class(text)

    def __strip_sections(self, config):

        for section in self.stripped_sections:
            try:
                del config.sections[section]
            except KeyError:
                pass
        return config

    def __export(self):
        self.__unprotect()
        text =  self.__send(('/export',), no_log_response=True)[0]
        return MikrotikConfig.parse(text)

    # Public methods (used by implemented CM modules)
    # -------------------------------------------------------------------------

    def execute(self, commands, no_log=False):
        commands = list(commands)
        if commands:
            self.__backup()
            self.__protect()
            try:
                if not self.check_mode:
                    return self.__send(commands, no_log=no_log)
            except self.catched_exceptions:
                self.__restore()
                raise
            else:
                self.__unprotect()
            finally:
                self.__config = None

    def configure(self, target, before=None, after=None):
        if not isinstance(target, MikrotikConfig):
            target = MikrotikConfig.parse(target)
        response = None

        old_config = self.config
        new_config = self.config.copy()
        changes = new_config.merge(target)

        if changes and not self.check_mode:
            if before:
                self.__send(list(before.export()))
            response = self.execute(changes.export())
            if after:
                self.__send(list(after.export()))
            assert self.config is not old_config
            missing_config = self.config.difference(new_config)
            if missing_config:
                self.fail_json(
                    msg="Failed to reach target configuration",
                    history=self.history,
                    changes=list(changes.show()),
                    missing=list(missing_config.show())
                )
        return response, changes

    def disconnect(self):
        self.__disconnect()

    # Context manager implementation
    # -------------------------------------------------------------------------

    def __enter__(self):
        self.__connect()

    def __exit__(self, *exc_details):
        self.__disconnect()
