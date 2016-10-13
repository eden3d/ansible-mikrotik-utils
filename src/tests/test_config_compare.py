from pytest import fixture

from ansible_mikrotik_utils.device import Device
from ansible_mikrotik_utils.sections import ConfigSection, ScriptSection

# Assets
# =============================================================================

CONFIG_BASE = """
/ip address
add address=192.168.88.1/24
add address=10.0.0.1 network=10.0.0.2

/ip firewall filter
add chain=test comment="1"
add chain=test comment="2"
add chain=test comment="3"
add chain=test comment="A"
add chain=test comment="B"
add chain=test comment="C"
add chain=test comment="D"
add chain=test comment="E"
add chain=test comment="4"
add chain=test comment="5"
add chain=test comment="6"

/interface bridge
set 0 wat=foo

"""

CONFIG_TARGET = """
/ip address
add address=192.168.88.1/24
add address=10.0.0.1 network=10.0.0.2

/ip firewall filter
add chain=test comment="foo"
add chain=test comment="C"
add chain=test comment="D"
add chain=test comment="A"
add chain=test comment="E"
add chain=test comment="B"
add chain=test comment="bar"

/interface bridge
set 0 wat=foo

"""

CONFIG_CHANGES = """
/ip firewall filter

remove 0
remove 0
remove 0
remove 5
remove 5
remove 5
add chain=test comment=foo place-before=0
add chain=test comment=bar
move 1 4
move 1 6
move 2 4
"""


# Fixtures
# =============================================================================

@fixture
def device():
    return Device()

@fixture
def config_base(device):
    return ConfigSection.from_text(CONFIG_BASE, device=device)

@fixture
def config_target(device):
    return ConfigSection.from_text(CONFIG_TARGET, device=device)

@fixture
def config_changes(device):
    return ScriptSection.from_text(CONFIG_CHANGES, device=device)

# Tests
# =============================================================================

def test_compare(config_base, config_target, config_changes):
    assert list(map(str, config_base.difference(config_target))) == list(map(str, config_changes))
