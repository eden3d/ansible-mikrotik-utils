import paramiko
import sys
import socket

from re import compile as compile_regex

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.basic import env_fallback, get_exception
from ansible.module_utils.shell import Shell, ShellError

from ansible_mikrotik_utils.config import MikrotikConfig

from paramiko import AuthenticationException, SSHException, util
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
    pruned_sections = '/system scheduler',
    ssh_username_suffix = '+ct'

    def __init__(self, *args, **kwargs):
        kwargs['argument_spec'].update(NET_COMMON_ARGS)
        kwargs['argument_spec'].update(BACKUP_ARGS)
        kwargs['argument_spec'].update(RESTORE_ARGS)

        super(MikrotikModule, self).__init__(*args, **kwargs)

        self.__ssh = None
        self.__config = None
        self.__connected = False
        self.__protected = False
        self.__failed = False
        self.__disconnecting = False
        self.__history = list()
        self.___backup_name = None
        self.___backup_key = None

    # Public properties
    # -------------------------------------------------------------------------

    @property
    def connected(self):
        return self.__connected

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
    def __backup_save_command(self):
        return SaveBackup(self.__backup_name, self.__backup_key)

    @property
    def __backup_load_command(self):
        return LoadBackup(self.__backup_name, self.__backup_key)

    @property
    def __backup_cleanup_command(self):
        return RemoveBackup(self.__backup_name)

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
        if not self.__connected:
            self.__ssh = ssh = paramiko.SSHClient()
            ssh.load_system_host_keys()
            look_for_keys = self.__ssh_password is None
            try:
                ssh.connect(
                        hostname=self.__ssh_host,
                        port=self.__ssh_port,
                        username=self.__ssh_username,
                        password=self.__ssh_password,
                        key_filename=self.__ssh_keyfile,
                        timeout=self.__ssh_timeout,
                        allow_agent=True, look_for_keys=False
                    )
                stdin, stdout, stderr = ssh.exec_command('test', timeout=self.__ssh_timeout)
                if "bad command name test (line 1 column 1)\n" not in stdout.readlines():
                    self.__fail("Connection test failed. (result:{})".format(stdout.readlines()))
            except socket.gaierror:
                self.__fail("Unable to resolve hostname. (host:{})".format(self.__ssh_host))
            except AuthenticationException:
                self.__fail("Unable to authenticate (user:{})".format(self.__ssh_user))
            except (SSHException, IOError) as ex:
                self.__fail("Unable to connect ({})".format(str(ex)))
            else:
                self.__connected = True
                self.__backedup = False

    def __disconnect(self):
        if self.__connected:
            self.__unprotect()
            self.__ssh.close()
            self.__ssh = None

    def __log_command(self, command):
        text = command.make_command_history_text()
        if text:
            self.__history.append("command: {}".format(text))

    def __log_response(self, command, response, error=False):
        text = command.make_response_history_text(response, error=error)
        if text:
            self.__history.append("{}: {}".format(
                'response' if not error else 'error', text
            ))

    def __fail_command(self, command, error):
        self.__log_response(command, error, error=True)
        if command.log_error_message:
            self.__fail(
                "Error detected in standard error.",
                command=command.history_text, error=error
            )
        else:
            self.__fail(
                "Error detected in standard error.",
                command=command.history_text
            )

    def __send(self, command):
        if not isinstance(command, ScriptCommand):
            command = RawCommand.parse(command)
        self.__connect()
        self.__log_command(command)
        stdin, stdout, stderr = self.__ssh.exec_command(command)
        stderr_read = stderr.read()
        if error:
            self.__fail_command(command, error)
        stdout_read = stdout.read()
        for pattern in CLI_ERRORS_RE:
            if pattern.match(stdout_read):
                self.__fail_command(command, response)
        self.__log_response(response)
        return response

    # Device protection handling
    # -------------------------------------------------------------------------

    def __protect(self):
        if self.__protection_required and not self.__protected:
            self.__backup()
            for name, args in self.__restore_tasks:
                self.__send('/system scheduler add name={} {}'.format(name, args))
            self.__protected = True

    def __unprotect(self):
        if self.__protection_required and not self.__protected:
            for name, args in self.__restore_tasks:
                self.__send('/system scheduler remove {}'.format(name, args))
            self.__protected = False
            self.__cleanup()

    # Backup handling
    # -------------------------------------------------------------------------

    def __backup(self):
        if self.__backup_required and not self.__backedup:
            self.__cleanup()
            self.__send(self.__backup_save_command)
            self.__backedup = True

    def __cleanup(self):
        if self.__backup_required and self.__backedup:
            self.__unprotect()
            self.__send(self.__backup_cleanup_command)
            self.__backedup = False

    # Restore
    # -------------------------------------------------------------------------

    def __restore(self):
        self.__send((self.__backup_load_command,))

    # Foobar
    # -------------------------------------------------------------------------

    def __fail(self, message, **kwargs):
        released, disconnected = False, False
        if not self.__failed:
            self.__failed = True
            self.__unprotect()
            self.__cleanup()
            released = True
        else:
            if not self.__disconnecting:
                self.__disconnecting = True
                self.__disconnect()
                disconnected = True
        self.fail_json(
            msg=message,
            released=released,
            disconnected=disconnected,
            **kwargs
        )

    # Configuration export by device
    # -------------------------------------------------------------------------

    def __export(self):
        self.__unprotect()
        text = self.__send(Export())
        return MikrotikConfig.parse(text, prune=self.pruned_sections)

    # Public methods (used by implemented CM modules)
    # -------------------------------------------------------------------------

    def execute(self, commands, before=None, after=None, no_log=False):
        commands, result = list(commands), None

        if commands and not self.check_mode:
            pre = self.config.copy()
            if before:
                for command in before:
                    self.__send(command)
            response = '\n'.join(map(self.__send, commands))
            if after:
                for command in after:
                    self.__send(command)
            self.__clear()
            post = self.config.copy()
            changes = pre.difference(post)
        else:
            response, changes = None, []

        return response, changes

    def configure(self, target, **kwargs):
        if not isinstance(target, MikrotikConfig):
            target = MikrotikConfig.parse(target)
        response = None

        original = self.config
        copy = original.copy()
        script = copy.merge(target)

        if script and not self.check_mode:
            response, changes = self.execute(script.commands, **kwargs)
            missing = original.apply(changes).difference(copy)
            if missing:
                self.__fail(
                    "Failed to reach target configuration",
                    history=self.history,
                    changes=list(changes.commands),
                    missing=list(missing.commands)
                )

        return response, changes

    def disconnect(self):
        self.__disconnect()

    # Context manager implementation
    # -------------------------------------------------------------------------

    def __enter__(self):
        self.__protect()
        self.__backup()

    def __exit__(self, exc_type, exc_value, exc_tb):
        if exc_value is not None and False:
            self.__fail("Unknown {} error : {}".format(exc_type.__name__, str(exc_type)))
        self.__disconnect()
