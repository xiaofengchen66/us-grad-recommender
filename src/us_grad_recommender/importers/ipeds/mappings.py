"""Code -> label lookups for IPEDS HD (institutional characteristics) and
EF (fall enrollment) survey components.

Every value below was read off the official IPEDS data dictionaries
(HD2023_dict.xlsx / ef2023a.xlsx, "Frequencies" sheet, downloaded directly
from https://nces.ed.gov/ipeds/datacenter/data/) rather than reconstructed
from memory, per the mandatory rule to never invent institutional facts.
These variable definitions are part of the IPEDS survey design and are
stable across recent years; verify against the current year's dictionary
before pointing the importer at a new release, since NCES has changed
codes across years in the past (e.g. HLOFFER historically used different
values before the current scale).
"""

from __future__ import annotations

from us_grad_recommender.models.university import Sector

# HD.CONTROL: institutional control.
CONTROL_TO_SECTOR = {
    1: Sector.PUBLIC,
    2: Sector.PRIVATE_NONPROFIT,
    3: Sector.PRIVATE_FOR_PROFIT,
}

# HD.HLOFFER: highest level of offering.
HLOFFER_LABELS = {
    1: "Award of less than one academic year",
    2: "At least 1, but less than 2 academic years",
    3: "Associate's degree",
    4: "At least 2, but less than 4 academic years",
    5: "Bachelor's degree",
    6: "Postbaccalaureate certificate",
    7: "Master's degree",
    8: "Post-master's certificate",
    9: "Doctor's degree",
}

# An institution's highest offering must be at least a master's degree (HLOFFER
# code 7) for masters_granting to be set. See hd_importer.compute_masters_granting.
MASTERS_OR_ABOVE_HLOFFER_CODES = {7, 8, 9}

# HD.GROFFER: 1 = graduate degree or certificate offering.
GROFFER_OFFERS_GRADUATE = 1

# HD.DEGGRANT: 1 = degree-granting.
DEGGRANT_IS_DEGREE_GRANTING = 1

# HD.CYACTIVE: 1 = active in the current IPEDS universe.
CYACTIVE_IS_ACTIVE = 1

# EF<year>A.EFALEVEL: the "all students" level-of-student rows we need.
EFALEVEL_ALL_STUDENTS_TOTAL = 1
EFALEVEL_ALL_STUDENTS_GRADUATE = 12

MASTERS_GRANTING_BASIS = (
    "IPEDS HD: CYACTIVE=1 AND DEGGRANT=1 AND GROFFER=1 AND HLOFFER>=7 "
    "(highest offering is master's degree or above). This is an "
    "offering-capability heuristic, not a verified count of active "
    "master's programs — see FULL_HANDOFF.md §4."
)
