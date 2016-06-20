from ansible_mikrotik_utils import MikrotikConfig, MikrotikScript

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
move 2 2
move 1 6
move 2 4
"""


def test_compare():
    base, target = map(MikrotikConfig.parse, (CONFIG_BASE, CONFIG_TARGET))
    actual_changes = str(base.difference(target))
    expected_changes = '\n'.join(map(str.strip, CONFIG_CHANGES.strip().split('\n')))
    assert actual_changes == expected_changes

def test_apply():
    base, target = map(MikrotikConfig.parse, (CONFIG_BASE, CONFIG_TARGET))
    changes = MikrotikScript.parse(CONFIG_CHANGES)
    base.apply(changes)
    assert not base.difference(target)
