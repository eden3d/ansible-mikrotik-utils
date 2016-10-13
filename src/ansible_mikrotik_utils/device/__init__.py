from ansible_mikrotik_utils.commands import SaveBackup, ClearBackup

from ansible_mikrotik_utils.sections import ConfigSection


class Device(object):
    def __init__(self):
        self.__section = ConfigSection(device=self)
        self.__backups = dict()
        self.__tasks = list()
        super(Device, self).__init__()

    # Backup handling
    # -------------------------------------------------------------------------

    def add_backup(self, backup):
        assert backup.name not in self.__backups, (
            "Cannot insert backup with existing name."
        )
        self.__backups[name] = backup.name
        return SaveBackup(name=backup.name, key=backup.key)

    def remove_backup(self, name):
        assert name in self.__backups.keys(), (
            "Cannot remove non-existing backup."
        )
        del self.__backups[name]
        return ClearBackup(name=name)

    # Task scheduler handling
    # -------------------------------------------------------------------------

    def add_scheduled_task(self, task):
        assert task.name in self.__backups.keys(), (
            "Cannot insert scheduled task with existing name."
        )
        self.__tasks[task.name] = task

    def remove_scheduled_task(self, name):
        assert name in self.__backups.keys(), (
            "Cannot remove non-existing scheduled task."
        )
        del self.__tasks[task.name]

    # Configuration input methods
    # -------------------------------------------------------------------------

    def load_text(self, text):
        return self.__section.load_text(text)

    def merge_text(self, text):
        return self.__section.load_text(text)

    def compare_text(self, text):
        other = ConfigSection.from_text(text, device=self)
        return self.__section.difference(other)

    def apply_script(self, script):
        self.__section.apply(script)

    # Public properties
    # -------------------------------------------------------------------------

    @property
    def root(self):
        return self.__section

    @property
    def sections(self):
        return {
            section.path: section for section in self.root.traverse()

        }



