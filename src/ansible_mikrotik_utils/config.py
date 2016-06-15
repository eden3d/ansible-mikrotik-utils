from re import compile as compile_regex, MULTILINE
from shlex import split

from ansible_mikrotik_utils.script import ADD, SET, ScriptAction, ScriptSection, MikrotikScript
from ansible_mikrotik_utils.script import parse_addition, parse_settings, invalidates_order


# Input : Text import cleaning method
# -----------------------------------------------------------------------------
#
# In order to parse an exported configuration, we must ensure that items are
# properly separated by line returns. It's normally the case, except for the
# fact that '/export' wraps long lines. The line returns resulting of the
# wrapping are manually stripped using a regular expression.
#
# This is because currently, the section stores its contents as a list of
# "lines", which requires the above fix to work properly.
#
# This is not optimal, and it does not allow keeping escaped newlines as
# parameter value. In order to fix this, it would be required to :
#  - treat items/settings/parameters differently
#    (store them in their own list)
#    + represent items as dictionaries stored in a list
#    + represent parameters as dictionaries stored in a dictionary
#    + represent settings as a dictionary
#  - make the "lines" property directly generated from items/settings/parameters
#  - find a multiline way to parse key-value pairs
#

EXPORT_SUBS = [
    # remove escaped line returns
    (compile_regex(r'\\\s*\n\s{4}', MULTILINE), str()),
]

def clean_export(text):
    for pattern, new in EXPORT_SUBS:
        text = pattern.sub(new, text)
        return text

# Output : Text formatting
# -----------------------------------------------------------------------------
#
# These functions are used to format parsed entities back into the script syntax.
#
# Those of them that return an operation that can move an item
# (:func:`format_addition` and :func:`format_move`) require the length of the
# current item list, as a different syntax is used to move to the last
# position.

def format_values(values):
    return ' '.join(sorted('='.join(parts) for parts in values.items()))

@ScriptAction.ADD.checks
def format_addition(values, count=0, index=None):
    assert isinstance(values, dict)
    text = format_values(values)
    if index is not None and (index + 1) < count:
        return 'add {} place-before={}'.format(text, index)
    else:
        return 'add {}'.format(text)

@ScriptAction.REMOVE.checks
def format_removal(index):
    return 'remove {}'.format(index)

@ScriptAction.MOVE.checks
def format_move(index, count, new_index):
    if new_index >= count:
        new_index = ''
    return 'move {} {}'.format(index, new_index)

@ScriptAction.SET.checks
def format_settings(identifier, values):
    text = format_values(values)
    if identifier is None:
        return 'set {}'.format(text)
    else:
        return 'set {} {}'.format(identifier, text)

# Configuration section class
# -----------------------------------------------------------------------------
#
# Configuration section class: represents a list of commands that were exported
# by a remote device. `ConfigSection` objects are usually merged together to
# produce a `ScriptSection` representing the changes.
#
# This object extends :class:`ScriptSection`, to restrict the allowed commands
# to `add` and `set`, also disallowing the use of `place-before=`.
#
# It provides methods that allow itself to merge with another instance and
# return the resulting changes in a new :class:`ScriptSection` instance.


class ConfigSection(ScriptSection):

    # Base section overrides and parameter properties
    # -------------------------------------------------------------------------
    def validate(self, line):
        super(ConfigSection, self).validate(line)
        if invalidates_order(line):
            raise ValueError("move/remove/place-before not supported in config")

    # Settings merging methods
    # -------------------------------------------------------------------------

    def __update_changed_settings(self, target):
        for line_index, line in target.settings:
            # apply setting changes
            identifier, settings = parse_settings(line)
            try:
                index, current = self.lookup_settings(identifier)
            except KeyError:
                index, current = None, {}
            difference = {
                key: value
                for key, value in settings.items()
                if current.get(key, None) != value
            }
            if difference:
                current.update(difference)
                formatted_settings = format_settings(identifier, current)
                formatted_differences = format_settings(identifier, difference)
                if index is not None:
                    self.lines.pop(index)
                self.lines.append(formatted_settings)
                yield formatted_differences

    def __insert_added_items(self, target):
        for item_index, (line_index, line) in enumerate(target.additions):
            values = parse_addition(line)
            try:
                self.lookup_addition(values)
            except KeyError:
                pass
            else:
                continue
            if self.ordered and target.ordered:
                if self.ordered_insertion:
                    self.lines.insert(item_index, line)
                    yield format_addition(
                        values,
                        count=len(self.additions),
                        index=item_index
                    )
                else:
                    self.lines.append(line)
                    yield format_addition(values)

            else:
                yield format_addition(values)

    def __delete_removed_items(self, target):
        # we cannot iterate on self.additions on self.line, as we will be
        # modifying it during this loop
        line_index, item_index = 0, 0
        while line_index < len(self.lines):
            line = self.lines[line_index]
            if not ADD.match(line):
                line_index +=1
                continue
            values = parse_addition(line)
            try:
                target.lookup_addition(values)
            except KeyError:
                self.lines.pop(line_index)
                yield format_removal(item_index)
            else:
                line_index += 1
                item_index += 1

    def __apply_position_changes(self, target):
        # we cannot iterate on self.additions on self.line, as we will be
        # modifying it during this loop
        line_index, item_index = 0, 0
        while line_index < len(self.lines):
            line = self.lines[line_index]
            offset = line_index - item_index
            if not ADD.match(line):
                line_index +=1
                continue
            values = parse_addition(line)
            try:
                matched_index = target.lookup_addition(values)
            except KeyError:
                pass
            else:
                if (target.ordered and
                    matched_index != item_index):
                    new_index = matched_index + 1
                    yield format_move(item_index, len(self.additions), new_index)
                    self.lines.insert(new_index, line)
                    if matched_index < item_index:
                        # we inserted before the current line, so we must raise
                        # the line index
                        line_index += 1
                        item_index += 1
                    self.lines.pop(line_index)
                    line_index = min(matched_index, item_index + offset + 1)
                    item_index = min(matched_index, item_index + 1)
                    continue
            line_index += 1
            item_index += 1

    # Root merging method
    # -------------------------------------------------------------------------

    def __merge(self, target):
        assert isinstance(target, type(self)), (
            "Can not compare ConfigSections of different type"
        )
        for change in self.__update_changed_settings(target):
            yield change
        for change in self.__delete_removed_items(target):
            yield change
        for change in self.__insert_added_items(target):
            yield change
        for change in self.__apply_position_changes(target):
            yield change

    def merge(self, target):
        script = ScriptSection(
            self.path,
            order_mode=self.order_mode,
        )
        script.load(self.__merge(target))
        return script

    # Diff methods
    # -------------------------------------------------------------------------

    def difference(self, target):
        return self.copy().merge(target)


# Mikrotik configuration container class
# -----------------------------------------------------------------------------
#
# This object is a container for section config objects, and can be used to
# represent the configuration of a Mikrotik device, grouped by sections.
#
# It extends :class:`MikrotikScript` to allow parsing of an exported
# configuration, and allows merging itself with another instance, returning the
# changes wrapped in a :class:`MikrotikScript` that can then be executed on the
# remote device.

class MikrotikConfig(MikrotikScript):

    # Text import methods
    # -------------------------------------------------------------------------
    #
    @classmethod
    def parse(cls, text):
        new = cls()
        cleaned = clean_export(text)
        splitted = map(str.strip, cleaned.split('\n'))
        section = None
        for line in filter(None, splitted):
            if line.startswith('/'):
                if line in new.sections:
                    section = new.sections[line]
                else:
                    section = new.sections[line] = ConfigSection(line)
            elif line.startswith('#'):
                if 'RouterOS' in line:
                    new.version = split(line)[-1]
            else:
                if section is None:
                    section = new.sections['/']
                section.load((line,))
        return new

    # Merging methods
    # -------------------------------------------------------------------------

    def __merge(self, target):
        for name, target_section in target.sections.items():
            if name in self.sections:
                section = self.sections[name]
            else:
                section = self.sections[name] = ConfigSection(name)
            script = section.merge(target_section)
            if script:
                yield name, script

    def merge(self, target):
        new = MikrotikScript()
        new.load(self.__merge(target))
        return new

    def difference(self, target):
        return self.copy().merge(target)
