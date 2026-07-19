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

# HD.C21BASIC: 2021 Carnegie Basic Classification, included directly in the
# HD survey (IPEDS partners with ACE/the Carnegie Foundation for this).
# Per the dictionary's own description, classifications are a time-specific
# snapshot based on 2019-20 data, republished into each year's HD file — the
# vintage is "2021 update", not necessarily the HD release year. -2 means
# "not applicable, not in Carnegie universe" and is treated as no
# classification (None) rather than a labeled value.
# https://carnegieclassifications.acenet.edu/classification_descriptions/basic.php
CARNEGIE_BASIC_LABELS = {
    1: "Associate's Colleges: High Transfer-High Traditional",
    2: "Associate's Colleges: High Transfer-Mixed Traditional/Nontraditional",
    3: "Associate's Colleges: High Transfer-High Nontraditional",
    4: "Associate's Colleges: Mixed Transfer/Career & Technical-High Traditional",
    5: "Associate's Colleges: Mixed Transfer/Career & Technical-Mixed Traditional/Nontraditional",
    6: "Associate's Colleges: Mixed Transfer/Career & Technical-High Nontraditional",
    7: "Associate's Colleges: High Career & Technical-High Traditional",
    8: "Associate's Colleges: High Career & Technical-Mixed Traditional/Nontraditional",
    9: "Associate's Colleges: High Career & Technical-High Nontraditional",
    10: "Special Focus Two-Year: Health Professions",
    11: "Special Focus Two-Year: Technical Professions",
    12: "Special Focus Two-Year: Arts & Design",
    13: "Special Focus Two-Year: Other Fields",
    14: "Baccalaureate/Associate's Colleges: Associate's Dominant",
    15: "Doctoral Universities: Highest Research Activity",
    16: "Doctoral Universities: Higher Research Activity",
    17: "Doctoral/Professional Universities",
    18: "Master's Colleges & Universities: Larger Programs",
    19: "Master's Colleges & Universities: Medium Programs",
    20: "Master's Colleges & Universities: Small Programs",
    21: "Baccalaureate Colleges: Arts & Sciences Focus",
    22: "Baccalaureate Colleges: Diverse Fields",
    23: "Baccalaureate/Associate's Colleges: Mixed Baccalaureate/Associate's",
    24: "Special Focus Four-Year: Faith-Related Institutions",
    25: "Special Focus Four-Year: Medical Schools & Centers",
    26: "Special Focus Four-Year: Other Health Professions Schools",
    27: "Special Focus Four-Year: Research Institutions",
    28: "Special Focus Four-Year: Engineering and Other Technology-Related Schools",
    29: "Special Focus Four-Year: Business & Management Schools",
    30: "Special Focus Four-Year: Arts, Music & Design Schools",
    31: "Special Focus Four-Year: Law Schools",
    32: "Special Focus Four-Year: Other Special Focus Institutions",
    33: "Tribal Colleges",
}

# HD.C21SZSET: 2021 Carnegie Size & Setting Classification. Same vintage
# caveat and "not applicable" sentinel (-2) as C21BASIC above. This is the
# source for the institution-level "Campus setting" field (FULL_HANDOFF.md §5).
CAMPUS_SETTING_LABELS = {
    1: "Two-year, very small",
    2: "Two-year, small",
    3: "Two-year, medium",
    4: "Two-year, large",
    5: "Two-year, very large",
    6: "Four-year, very small, primarily nonresidential",
    7: "Four-year, very small, primarily residential",
    8: "Four-year, very small, highly residential",
    9: "Four-year, small, primarily nonresidential",
    10: "Four-year, small, primarily residential",
    11: "Four-year, small, highly residential",
    12: "Four-year, medium, primarily nonresidential",
    13: "Four-year, medium, primarily residential",
    14: "Four-year, medium, highly residential",
    15: "Four-year, large, primarily nonresidential",
    16: "Four-year, large, primarily residential",
    17: "Four-year, large, highly residential",
    18: "Exclusively graduate/professional",
}

MASTERS_GRANTING_BASIS = (
    "IPEDS HD: CYACTIVE=1 AND DEGGRANT=1 AND GROFFER=1 AND HLOFFER>=7 "
    "(highest offering is master's degree or above). This is an "
    "offering-capability heuristic, not a verified count of active "
    "master's programs — see FULL_HANDOFF.md §4."
)
