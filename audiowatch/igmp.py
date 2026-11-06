"""
IGMP parsing (required) and building (for testing):

"""


# Protocol value
IGMP_PROTOCOL = 2

# Message types
TYPE_QUERY = 0x11
TYPE_V1_REPORT = 0x12
TYPE_V2_REPORT = 0x16
TYPE_V2_LEAVE = 0x17
TYPE_V3_REPORT = 0x22

ALL_ROUTERS = "224.0.0.2"       # IGMPv2 leaves go here
V3_REPORT_GROUP = "224.0.0.22"  # IGMPv3 reports go here