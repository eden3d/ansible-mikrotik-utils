from ansible_mikrotik_utils.commands import BaseCommand


from .base import BaseSection

class ScriptSection(BaseSection):
    base_section_class = None
    base_command_class = BaseCommand
