import os
import tempfile
import urllib.request
from flask import Flask, request, jsonify, send_file
import fitz  # PyMuPDF

app = Flask(__name__)

# Secret key to protect the endpoint
API_SECRET = os.environ.get('PDF_SERVICE_SECRET', 'aponte-law-pdf-2026')

# =============================================================================
# PDF URLs for all supported USCIS forms
# =============================================================================
PDF_URLS = {
    'I-130': os.environ.get(
        'I130_PDF_URL',
        'https://axqfryjovgwq4smc.public.blob.vercel-storage.com/uscis-forms/i-130.pdf'
    ),
    'I-485': os.environ.get(
        'I485_PDF_URL',
        'https://www.uscis.gov/sites/default/files/document/forms/i-485.pdf'
    ),
    'I-765': os.environ.get(
        'I765_PDF_URL',
        'https://www.uscis.gov/sites/default/files/document/forms/i-765.pdf'
    ),
    'I-131': os.environ.get(
        'I131_PDF_URL',
        'https://www.uscis.gov/sites/default/files/document/forms/i-131.pdf'
    ),
    'N-400': os.environ.get(
        'N400_PDF_URL',
        'https://www.uscis.gov/sites/default/files/document/forms/n-400.pdf'
    ),
    'I-589': os.environ.get(
        'I589_PDF_URL',
        'https://www.uscis.gov/sites/default/files/document/forms/i-589.pdf'
    ),
    'I-751': os.environ.get(
        'I751_PDF_URL',
        'https://www.uscis.gov/sites/default/files/document/forms/i-751.pdf'
    ),
    'I-539': os.environ.get(
        'I539_PDF_URL',
        'https://www.uscis.gov/sites/default/files/document/forms/i-539.pdf'
    ),
    'I-864': os.environ.get(
        'I864_PDF_URL',
        'https://www.uscis.gov/sites/default/files/document/forms/i-864.pdf'
    ),
    'G-28': os.environ.get(
        'G28_PDF_URL',
        'https://www.uscis.gov/sites/default/files/document/forms/g-28.pdf'
    ),
}

# Legacy references for backwards compatibility
I130_PDF_URL = PDF_URLS['I-130']
G28_PDF_URL = PDF_URLS['G-28']

# G-28 Field Mapping - Exact field names extracted from official PDF
G28_FIELD_MAPPING = {
    # Part 1 - USCIS Account Number
    'uscisOnlineAccountNumber': 'Pt1Line1_USCISOnlineAcctNumber[0]',

    # Part 1 - Name
    'familyName': 'Pt1Line2a_FamilyName[0]',
    'givenName': 'Pt1Line2b_GivenName[0]',
    'middleName': 'Pt1Line2c_MiddleName[0]',

    # Part 1 - Address
    'streetNumberName': 'Line3a_StreetNumber[0]',
    'aptSteFlr': 'Line3b_AptSteFlrNumber[0]',
    'cityOrTown': 'Line3c_CityOrTown[0]',
    'state': 'Line3d_State[0]',
    'zipCode': 'Line3e_ZipCode[0]',
    'province': 'Line3f_Province[0]',
    'postalCode': 'Line3g_PostalCode[0]',
    'country': 'Line3h_Country[0]',

    # Part 1 - Contact
    'daytimeTelephone': 'Line4_DaytimeTelephoneNumber[0]',
    'mobileTelephone': 'Line7_MobileTelephoneNumber[0]',
    'emailAddress': 'Line6_EMail[0]',
    'faxNumber': 'Pt1ItemNumber7_FaxNumber[0]',

    # Part 2 - Eligibility
    'licensingAuthority': 'Pt2Line1a_LicensingAuthority[0]',
    'barNumber': 'Pt2Line1b_BarNumber[0]',
    'lawFirmName': 'Pt2Line1d_NameofFirmOrOrganization[0]',

    # Part 3 - Appearance
    'specificMatter': 'Line1b_ListFormNumber[0]',
    'iceMatter': 'Line2b_ListMatter[0]',
    'cbpMatter': 'Line3b_ListSpecificMatter[0]',
}

# Separate checkbox mappings for G-28
G28_CHECKBOX_MAPPING = {
    # Unit type checkboxes (Apt/Ste/Flr)
    'aptSteFlrType': {
        'Apt': 'Line3b_Unit[0]',
        'Ste': 'Line3b_Unit[1]',
        'Flr': 'Line3b_Unit[2]',
    },

    # Part 2 - Attorney or accredited rep
    'isAttorney': {
        True: 'CheckBox1[0]',   # I am an attorney
        False: 'CheckBox2[0]',  # I am an accredited rep
    },

    # Part 2 - Subject to orders
    'notSubjectToOrders': {
        True: 'Checkbox1dAmNot[0]',   # am NOT subject
        False: 'Checkbox1dAm[0]',     # am subject
    },

    # Part 3 - Appearance before
    'appearsBeforeUSCIS': {
        True: 'Line1a_USCIS[0]',
    },
    'appearsBeforeICE': {
        True: 'Line2a_ICE[0]',
    },
    'appearsBeforeCBP': {
        True: 'Line3a_CBP[0]',
    },

    # Part 4 - Consent
    'sendNoticesToAttorney': {
        True: 'Pt4Line2a_CheckBox2a[0]',
    },
    'sendDocumentsToAttorney': {
        True: 'Pt4Line2b_CheckBox2b[0]',
    },
}

# Complete I-130 field mapping from questionnaire IDs to PDF field names
# Based on exact field extraction from the official USCIS I-130 PDF form
FIELD_MAPPING = {
    # ============================================================
    # PART 1 - RELATIONSHIP
    # ============================================================
    'p1_relationship': {
        'type': 'radio',
        'options': {
            'Spouse': 'Pt1Line1_Spouse',
            'Child': 'Pt1Line1_Child',
            'Parent': 'Pt1Line1_Parent',
            'Siblings': 'Pt1Line1_Siblings',
        }
    },
    'p1_child_type': {
        'type': 'radio',
        'options': {
            'InWedlock': 'Pt1Line2_InWedlock',
            'OutOfWedlock': 'Pt1Line2_OutOfWedlock',
            'AdoptedChild': 'Pt1Line2_AdoptedChild',
            'Stepchild': 'Pt1Line2_Stepchild',
        }
    },
    'p1_sibling_adopted': {
        'type': 'radio',
        'options': {
            'Yes': 'Pt1Line3_Yes',
            'No': 'Pt1Line3_No',
        }
    },
    'p1_status_through_adoption': {
        'type': 'radio',
        'options': {
            'Yes': 'Pt1Line4_Yes',
            'No': 'Pt1Line4_No',
        }
    },

    # ============================================================
    # PART 2 - PETITIONER INFORMATION
    # ============================================================
    'p2_alien_number': 'Pt2Line1_AlienNumber',
    'p2_uscis_account': 'Pt2Line2_USCISOnlineActNumber',
    'p2_ssn': 'Pt2Line11_SSN',
    'p2_last_name': 'Pt2Line4a_FamilyName',
    'p2_first_name': 'Pt2Line4b_GivenName',
    'p2_middle_name': 'Pt2Line4c_MiddleName',
    'p2_other_last_name': 'Pt2Line5a_FamilyName',
    'p2_other_first_name': 'Pt2Line5b_GivenName',
    'p2_other_middle_name': 'Pt2Line5c_MiddleName',
    'p2_city_of_birth': 'Pt2Line6_CityTownOfBirth',
    'p2_country_of_birth': 'Pt2Line7_CountryofBirth',
    'p2_date_of_birth': 'Pt2Line8_DateofBirth',
    'p2_sex': {
        'type': 'radio',
        'options': {
            'Male': 'Pt2Line9_Male',
            'Female': 'Pt2Line9_Female',
        }
    },

    # Mailing Address
    'p2_mailing_care_of': 'Pt2Line10_InCareofName',
    'p2_mailing_street': 'Pt2Line10_StreetNumberName',
    'p2_mailing_unit_type': {
        'type': 'radio',
        'options': {
            'Apt': 'Pt2Line10_Unit[0]',
            'Ste': 'Pt2Line10_Unit[1]',
            'Flr': 'Pt2Line10_Unit[2]',
        }
    },
    'p2_mailing_unit_number': 'Pt2Line10_AptSteFlrNumber',
    'p2_mailing_city': 'Pt2Line10_CityOrTown',
    'p2_mailing_state': 'Pt2Line10_State',
    'p2_mailing_zip': 'Pt2Line10_ZipCode',
    'p2_mailing_province': 'Pt2Line10_Province',
    'p2_mailing_postal_code': 'Pt2Line10_PostalCode',
    'p2_mailing_country': 'Pt2Line10_Country',
    'p2_same_address': {
        'type': 'radio',
        'options': {
            'Yes': 'Pt2Line11_Yes',
            'No': 'Pt2Line11_No',
        }
    },

    # Physical Address
    'p2_physical_street': 'Pt2Line12_StreetNumberName',
    'p2_physical_unit_type': {
        'type': 'radio',
        'options': {
            'Apt': 'Pt2Line12_Unit[0]',
            'Ste': 'Pt2Line12_Unit[1]',
            'Flr': 'Pt2Line12_Unit[2]',
        }
    },
    'p2_physical_unit_number': 'Pt2Line12_AptSteFlrNumber',
    'p2_physical_city': 'Pt2Line12_CityOrTown',
    'p2_physical_state': 'Pt2Line12_State',
    'p2_physical_zip': 'Pt2Line12_ZipCode',
    'p2_physical_province': 'Pt2Line12_Province',
    'p2_physical_postal_code': 'Pt2Line12_PostalCode',
    'p2_physical_country': 'Pt2Line12_Country',
    'p2_physical_date_from': 'Pt2Line13a_DateFrom',

    # Previous Address
    'p2_prev_street': 'Pt2Line14_StreetNumberName',
    'p2_prev_unit_type': {
        'type': 'radio',
        'options': {
            'Apt': 'Pt2Line14_Unit[0]',
            'Ste': 'Pt2Line14_Unit[1]',
            'Flr': 'Pt2Line14_Unit[2]',
        }
    },
    'p2_prev_unit_number': 'Pt2Line14_AptSteFlrNumber',
    'p2_prev_city': 'Pt2Line14_CityOrTown',
    'p2_prev_state': 'Pt2Line14_State',
    'p2_prev_zip': 'Pt2Line14_ZipCode',
    'p2_prev_province': 'Pt2Line14_Province',
    'p2_prev_postal_code': 'Pt2Line14_PostalCode',
    'p2_prev_country': 'Pt2Line14_Country',
    'p2_prev_date_from': 'Pt2Line15a_DateFrom',
    'p2_prev_date_to': 'Pt2Line15b_DateTo',

    # Marital History
    'p2_num_marriages': 'Pt2Line16_NumberofMarriages',
    'p2_marital_status': {
        'type': 'radio',
        'options': {
            'Single': 'Pt2Line17_Single',
            'Married': 'Pt2Line17_Married',
            'Divorced': 'Pt2Line17_Divorced',
            'Widowed': 'Pt2Line17_Widowed',
            'Separated': 'Pt2Line17_Separated',
            'Annulled': 'Pt2Line17_Annulled',
        }
    },
    'p2_date_of_marriage': 'Pt2Line18_DateOfMarriage',
    'p2_marriage_city': 'Pt2Line19a_CityTown',
    'p2_marriage_state': 'Pt2Line19b_State',
    'p2_marriage_province': 'Pt2Line19c_Province',
    'p2_marriage_country': 'Pt2Line19d_Country',

    # Spouse Information
    'p2_spouse1_last_name': 'PtLine20a_FamilyName',
    'p2_spouse1_first_name': 'Pt2Line20b_GivenName',
    'p2_spouse1_middle_name': 'Pt2Line20c_MiddleName',
    'p2_spouse1_marriage_ended': 'Pt2Line21_DateMarriageEnded',
    'p2_spouse2_last_name': 'Pt2Line22a_FamilyName',
    'p2_spouse2_first_name': 'Pt2Line22b_GivenName',
    'p2_spouse2_middle_name': 'Pt2Line22c_MiddleName',
    'p2_spouse2_marriage_ended': 'Pt2Line23_DateMarriageEnded',

    # Parent 1 Information
    'p2_parent1_last_name': 'Pt2Line24_FamilyName',
    'p2_parent1_first_name': 'Pt2Line24_GivenName',
    'p2_parent1_middle_name': 'Pt2Line24_MiddleName',
    'p2_parent1_dob': 'Pt2Line25_DateofBirth',
    'p2_parent1_sex': {
        'type': 'radio',
        'options': {
            'Male': 'Pt2Line26_Male',
            'Female': 'Pt2Line26_Female',
        }
    },
    'p2_parent1_country_birth': 'Pt2Line27_CountryofBirth',
    'p2_parent1_city_residence': 'Pt2Line28_CityTownOrVillageOfResidence',
    'p2_parent1_country_residence': 'Pt2Line29_CountryOfResidence',

    # Parent 2 Information
    'p2_parent2_last_name': 'Pt2Line30a_FamilyName',
    'p2_parent2_first_name': 'Pt2Line30b_GivenName',
    'p2_parent2_middle_name': 'Pt2Line30c_MiddleName',
    'p2_parent2_dob': 'Pt2Line31_DateofBirth',
    'p2_parent2_sex': {
        'type': 'radio',
        'options': {
            'Male': 'Pt2Line32_Male',
            'Female': 'Pt2Line32_Female',
        }
    },
    'p2_parent2_country_birth': 'Pt2Line33_CountryofBirth',
    'p2_parent2_city_residence': 'Pt2Line34_CityTownOrVillageOfResidence',
    'p2_parent2_country_residence': 'Pt2Line35_CountryOfResidence',

    # Citizenship Status
    'p2_citizenship_status': {
        'type': 'radio',
        'options': {
            'USCitizen': 'Pt2Line36_USCitizen',
            'LPR': 'Pt2Line36_LPR',
        }
    },
    'p2_citizenship_acquired': {
        'type': 'radio',
        'options': {
            'Birth': 'Pt2Line23a_checkbox',
            'Naturalization': 'Pt2Line23b_checkbox',
            'Parents': 'Pt2Line23c_checkbox',
        }
    },
    'p2_has_certificate': {
        'type': 'radio',
        'options': {
            'Yes': 'Pt2Line36_Yes',
            'No': 'Pt2Line36_No',
        }
    },
    'p2_certificate_number': 'Pt2Line37a_CertificateNumber',
    'p2_certificate_place': 'Pt2Line37b_PlaceOfIssuance',
    'p2_certificate_date': 'Pt2Line37c_DateOfIssuance',

    # LPR Information
    'p2_lpr_class': 'Pt2Line40a_ClassOfAdmission',
    'p2_lpr_date': 'Pt2Line40b_DateOfAdmission',
    'p2_lpr_city': 'Pt2Line40d_CityOrTown',
    'p2_lpr_state': 'Pt2Line40e_State',
    'p2_lpr_through_marriage': {
        'type': 'radio',
        'options': {
            'Yes': 'Pt2Line41_Yes',
            'No': 'Pt2Line41_No',
        }
    },

    # Employment
    'p2_employer1_name': 'Pt2Line40_EmployerOrCompName',
    'p2_employer1_street': 'Pt2Line41_StreetNumberName',
    'p2_employer1_city': 'Pt2Line41_CityOrTown',
    'p2_employer1_state': 'Pt2Line41_State',
    'p2_employer1_zip': 'Pt2Line41_ZipCode',
    'p2_employer1_occupation': 'Pt2Line42_Occupation',
    'p2_employer1_date_from': 'Pt2Line43a_DateFrom',

    # ============================================================
    # PART 3 - BIOGRAPHIC INFORMATION
    # ============================================================
    'p3_ethnicity': {
        'type': 'radio',
        'options': {
            'NotHispanic': 'Pt3Line1_Ethnicity[0]',
            'Hispanic': 'Pt3Line1_Ethnicity[1]',
        }
    },
    'p3_race': {
        'type': 'checkbox',
        'options': {
            'White': 'Pt3Line2_Race_White',
            'Asian': 'Pt3Line2_Race_Asian',
            'Black': 'Pt3Line2_Race_Black',
            'AmericanIndian': 'Pt3Line2_Race_AmericanIndianAlaskaNative',
            'NativeHawaiian': 'Pt3Line2_Race_NativeHawaiianOtherPacificIslander',
        }
    },
    'p3_height_feet': 'Pt3Line3_HeightFeet',
    'p3_height_inches': 'Pt3Line3_HeightInches',
    'p3_weight': {
        'type': 'weight',
        'fields': ['Pt3Line4_Pound1', 'Pt3Line4_Pound2', 'Pt3Line4_Pound3']
    },
    'p3_eye_color': {
        'type': 'radio',
        'options': {
            '0': 'Pt3Line5_EyeColor[0]',  # Blue
            '1': 'Pt3Line5_EyeColor[1]',  # Brown
            '2': 'Pt3Line5_EyeColor[2]',  # Hazel
            '3': 'Pt3Line5_EyeColor[3]',  # Pink
            '4': 'Pt3Line5_EyeColor[4]',  # Maroon
            '5': 'Pt3Line5_EyeColor[5]',  # Green
            '6': 'Pt3Line5_EyeColor[6]',  # Gray
            '7': 'Pt3Line5_EyeColor[7]',  # Black
            '8': 'Pt3Line5_EyeColor[8]',  # Unknown/Other
        }
    },
    'p3_hair_color': {
        'type': 'radio',
        'options': {
            '0': 'Pt3Line6_HairColor[0]',  # Bald
            '1': 'Pt3Line6_HairColor[1]',  # Black
            '2': 'Pt3Line6_HairColor[2]',  # Blond
            '3': 'Pt3Line6_HairColor[3]',  # Brown
            '4': 'Pt3Line6_HairColor[4]',  # Gray
            '5': 'Pt3Line6_HairColor[5]',  # Red
            '6': 'Pt3Line6_HairColor[6]',  # Sandy
            '7': 'Pt3Line6_HairColor[7]',  # White
            '8': 'Pt3Line6_HairColor[8]',  # Unknown/Other
        }
    },

    # ============================================================
    # PART 4 - BENEFICIARY INFORMATION
    # ============================================================
    'p4_alien_number': 'Pt4Line1_AlienNumber',
    'p4_uscis_account': 'Pt4Line2_USCISOnlineActNumber',
    'p4_ssn': 'Pt4Line3_SSN',
    'p4_last_name': 'Pt4Line4a_FamilyName',
    'p4_first_name': 'Pt4Line4b_GivenName',
    'p4_middle_name': 'Pt4Line4c_MiddleName',
    'p4_other_last_name': 'P4Line5a_FamilyName',
    'p4_other_first_name': 'Pt4Line5b_GivenName',
    'p4_other_middle_name': 'Pt4Line5c_MiddleName',
    'p4_city_of_birth': 'Pt4Line7_CityTownOfBirth',
    'p4_country_of_birth': 'Pt4Line8_CountryOfBirth',
    'p4_date_of_birth': 'Pt4Line9_DateOfBirth',
    'p4_sex': {
        'type': 'radio',
        'options': {
            'Male': 'Pt4Line9_Male',
            'Female': 'Pt4Line9_Female',
        }
    },
    'p4_prior_petition': {
        'type': 'radio',
        'options': {
            'Yes': 'Pt4Line10_Yes',
            'No': 'Pt4Line10_No',
            'Unknown': 'Pt4Line10_Unknown',
        }
    },

    # Beneficiary Address
    'p4_street': 'Pt4Line11_StreetNumberName',
    'p4_unit_type': {
        'type': 'radio',
        'options': {
            'Apt': 'Pt4Line11_Unit[0]',
            'Ste': 'Pt4Line11_Unit[1]',
            'Flr': 'Pt4Line11_Unit[2]',
        }
    },
    'p4_unit_number': 'Pt4Line11_AptSteFlrNumber',
    'p4_city': 'Pt4Line11_CityOrTown',
    'p4_state': 'Pt4Line11_State',
    'p4_zip': 'Pt4Line11_ZipCode',
    'p4_province': 'Pt4Line11_Province',
    'p4_postal_code': 'Pt4Line11_PostalCode',
    'p4_country': 'Pt4Line11_Country',

    # US Intended Address
    'p4_us_street': 'Pt4Line12a_StreetNumberName',
    'p4_us_unit_type': {
        'type': 'radio',
        'options': {
            'Apt': 'Pt4Line12b_Unit[0]',
            'Ste': 'Pt4Line12b_Unit[1]',
            'Flr': 'Pt4Line12b_Unit[2]',
        }
    },
    'p4_us_unit_number': 'Pt4Line12b_AptSteFlrNumber',
    'p4_us_city': 'Pt4Line12c_CityOrTown',
    'p4_us_state': 'Pt4Line12d_State',
    'p4_us_zip': 'Pt4Line12e_ZipCode',

    # Foreign Address
    'p4_foreign_street': 'Pt4Line13_StreetNumberName',
    'p4_foreign_unit_type': {
        'type': 'radio',
        'options': {
            'Apt': 'Pt4Line13_Unit[0]',
            'Ste': 'Pt4Line13_Unit[1]',
            'Flr': 'Pt4Line13_Unit[2]',
        }
    },
    'p4_foreign_unit_number': 'Pt4Line13_AptSteFlrNumber',
    'p4_foreign_city': 'Pt4Line13_CityOrTown',
    'p4_foreign_province': 'Pt4Line13_Province',
    'p4_foreign_postal_code': 'Pt4Line13_PostalCode',
    'p4_foreign_country': 'Pt4Line13_Country',

    # Contact
    'p4_daytime_phone': 'Pt4Line14_DaytimePhoneNumber',
    'p4_mobile_phone': 'Pt4Line15_MobilePhoneNumber',
    'p4_email': 'Pt4Line16_EmailAddress',

    # Marital History
    'p4_num_marriages': 'Pt4Line17_NumberofMarriages',
    'p4_marital_status': {
        'type': 'radio',
        'options': {
            'Widowed': 'Pt4Line18_MaritalStatus[0]',
            'Annulled': 'Pt4Line18_MaritalStatus[1]',
            'Separated': 'Pt4Line18_MaritalStatus[2]',
            'Single': 'Pt4Line18_MaritalStatus[3]',
            'Married': 'Pt4Line18_MaritalStatus[4]',
            'Divorced': 'Pt4Line18_MaritalStatus[5]',
        }
    },
    'p4_date_of_marriage': 'Pt4Line19_DateOfMarriage',
    'p4_marriage_city': 'Pt4Line20a_CityTown',
    'p4_marriage_state': 'Pt4Line20b_State',
    'p4_marriage_province': 'Pt4Line20c_Province',
    'p4_marriage_country': 'Pt4Line20d_Country',

    # Spouse Info
    'p4_spouse1_last_name': 'Pt4Line16a_FamilyName',
    'p4_spouse1_first_name': 'Pt4Line16b_GivenName',
    'p4_spouse1_middle_name': 'Pt4Line16c_MiddleName',
    'p4_spouse1_marriage_ended': 'Pt4Line17_DateMarriageEnded',
    'p4_spouse2_last_name': 'Pt4Line18a_FamilyName',
    'p4_spouse2_first_name': 'Pt4Line18b_GivenName',
    'p4_spouse2_middle_name': 'Pt4Line18c_MiddleName',

    # Family Members (Person 1-5)
    'p4_family1_last_name': 'Pt4Line30a_FamilyName',
    'p4_family1_first_name': 'Pt4Line30b_GivenName',
    'p4_family1_middle_name': 'Pt4Line30c_MiddleName',
    'p4_family1_relationship': 'Pt4Line31_Relationship',
    'p4_family1_dob': 'Pt4Line32_DateOfBirth',
    'p4_family1_country_birth': 'Pt4Line49_CountryOfBirth',

    'p4_family2_last_name': 'Pt4Line34a_FamilyName',
    'p4_family2_first_name': 'Pt4Line34b_GivenName',
    'p4_family2_middle_name': 'Pt4Line34c_MiddleName',
    'p4_family2_relationship': 'Pt4Line35_Relationship',
    'p4_family2_dob': 'Pt4Line36_DateOfBirth',
    'p4_family2_country_birth': 'Pt4Line37_CountryOfBirth',

    'p4_family3_last_name': 'Pt4Line38a_FamilyName',
    'p4_family3_first_name': 'Pt4Line38b_GivenName',
    'p4_family3_middle_name': 'Pt4Line38c_MiddleName',
    'p4_family3_relationship': 'Pt4Line39_Relationship',
    'p4_family3_dob': 'Pt4Line40_DateOfBirth',
    'p4_family3_country_birth': 'Pt4Line41_CountryOfBirth',

    'p4_family4_last_name': 'Pt4Line42a_FamilyName',
    'p4_family4_first_name': 'Pt4Line42b_GivenName',
    'p4_family4_middle_name': 'Pt4Line42c_MiddleName',
    'p4_family4_relationship': 'Pt4Line43_Relationship',
    'p4_family4_dob': 'Pt4Line44_DateOfBirth',
    'p4_family4_country_birth': 'Pt4Line45_CountryOfBirth',

    'p4_family5_last_name': 'Pt4Line46a_FamilyName',
    'p4_family5_first_name': 'Pt4Line46b_GivenName',
    'p4_family5_middle_name': 'Pt4Line46c_MiddleName',
    'p4_family5_relationship': 'Pt4Line47_Relationship',
    'p4_family5_dob': 'Pt4Line48_DateOfBirth',

    # Entry Information
    'p4_ever_in_us': {
        'type': 'radio',
        'options': {
            'Yes': 'Pt4Line20_Yes',
            'No': 'Pt4Line20_No',
        }
    },
    'p4_class_of_admission': 'Pt4Line21a_ClassOfAdmission',
    'p4_i94_number': 'Pt4Line21b_ArrivalDeparture',
    'p4_date_of_arrival': 'Pt4Line21c_DateOfArrival',
    'p4_stay_expiration': 'Pt4Line21d_DateExpired',
    'p4_passport_number': 'Pt4Line22_PassportNumber',
    'p4_travel_doc_number': 'Pt4Line23_TravelDocNumber',
    'p4_passport_country': 'Pt4Line24_CountryOfIssuance',
    'p4_passport_expiration': 'Pt4Line25_ExpDate',

    # Employment
    'p4_employer_name': 'Pt4Line26_NameOfCompany',
    'p4_employer_street': 'Pt4Line26_StreetNumberName',
    'p4_employer_unit_type': {
        'type': 'radio',
        'options': {
            'Apt': 'Pt4Line26_Unit[0]',
            'Ste': 'Pt4Line26_Unit[1]',
            'Flr': 'Pt4Line26_Unit[2]',
        }
    },
    'p4_employer_unit_number': 'Pt4Line26_AptSteFlrNumber',
    'p4_employer_city': 'Pt4Line26_CityOrTown',
    'p4_employer_state': 'Pt4Line26_State',
    'p4_employer_zip': 'Pt4Line26_ZipCode',
    'p4_employer_province': 'Pt4Line26_Province',
    'p4_employer_postal_code': 'Pt4Line26_PostalCode',
    'p4_employer_country': 'Pt4Line26_Country',
    'p4_employment_date': 'Pt4Line27_DateEmploymentBegan',

    # Immigration Proceedings
    'p4_in_proceedings': {
        'type': 'radio',
        'options': {
            'Yes': 'Pt4Line28_Yes',
            'No': 'Pt4Line28_No',
        }
    },
    'p4_proceedings_type': {
        'type': 'radio',
        'options': {
            'Removal': 'Pt4Line54_Removal',
            'Exclusion': 'Pt4Line54_Exclusion',
            'Rescission': 'Pt4Line54_Rescission',
            'Judicial': 'Pt4Line54_JudicialProceedings',
        }
    },
    'p4_proceedings_city': 'Pt4Line55a_CityOrTown',
    'p4_proceedings_state': 'Pt4Line55b_State',
    'p4_proceedings_date': 'Pt4Line56_Date',

    # Native language info
    'p4_native_last_name': 'Pt4Line55a_FamilyName',
    'p4_native_first_name': 'Pt4Line55b_GivenName',
    'p4_native_middle_name': 'Pt4Line55c_MiddleName',
    'p4_native_street': 'Pt4Line56_StreetNumberName',
    'p4_native_unit_type': {
        'type': 'radio',
        'options': {
            'Apt': 'Pt4Line56_Unit[0]',
            'Ste': 'Pt4Line56_Unit[1]',
            'Flr': 'Pt4Line56_Unit[2]',
        }
    },
    'p4_native_unit_number': 'Pt4Line56_AptSteFlrNumber',
    'p4_native_city': 'Pt4Line56_CityOrTown',
    'p4_native_province': 'Pt4Line56_Province',
    'p4_native_postal_code': 'Pt4Line56_PostalCode',
    'p4_native_country': 'Pt4Line56_Country',

    # Last address lived together
    'p4_together_street': 'Pt4Line57_StreetNumberName',
    'p4_together_unit_type': {
        'type': 'radio',
        'options': {
            'Apt': 'Pt4Line57_Unit[0]',
            'Ste': 'Pt4Line57_Unit[1]',
            'Flr': 'Pt4Line57_Unit[2]',
        }
    },
    'p4_together_unit_number': 'Pt4Line57_AptSteFlrNumber',
    'p4_together_city': 'Pt4Line57_CityOrTown',
    'p4_together_state': 'Pt4Line57_State',
    'p4_together_zip': 'Pt4Line57_ZipCode',
    'p4_together_province': 'Pt4Line57_Province',
    'p4_together_postal_code': 'Pt4Line57_PostalCode',
    'p4_together_country': 'Pt4Line57_Country',
    'p4_together_date_from': 'Pt4Line58a_DateFrom',
    'p4_together_date_to': 'Pt4Line58b_DateTo',

    # USCIS Office / Consulate
    'p4_uscis_city': 'Pt4Line60a_CityOrTown',
    'p4_uscis_state': 'Pt4Line60b_State',
    'p4_consulate_city': 'Pt4Line61a_CityOrTown',
    'p4_consulate_province': 'Pt4Line61b_Province',
    'p4_consulate_country': 'Pt4Line61c_Country',

    # ============================================================
    # PART 5 - OTHER INFORMATION
    # ============================================================
    'p5_prior_petition': {
        'type': 'radio',
        'options': {
            'Yes': 'Part4Line1_Yes',
            'No': 'Part4Line1_No',
        }
    },
    'p5_prior_name': 'Pt5Line2a_FamilyName',
    'p5_prior_first_name': 'Pt5Line2b_GivenName',
    'p5_prior_middle_name': 'Pt5Line2c_MiddleName',
    'p5_prior_city': 'Pt5Line3a_CityOrTown',
    'p5_prior_state': 'Pt5Line3b_State',
    'p5_prior_date': 'Pt5Line4_DateFiled',
    'p5_prior_result': 'Pt5Line5_Result',

    # Other Relatives Being Filed For
    'p5_relative1_last_name': 'Pt4Line6a_FamilyName',
    'p5_relative1_first_name': 'Pt4Line6b_GivenName',
    'p5_relative1_middle_name': 'Pt4Line6c_MiddleName',
    'p5_relative1_relationship': 'Pt4Line7_Relationship',
    'p5_relative2_last_name': 'Pt4Line8a_FamilyName',
    'p5_relative2_first_name': 'Pt4Line8b_GivenName',
    'p5_relative2_middle_name': 'Pt4Line8c_MiddleName',
    'p5_relative2_relationship': 'Pt4Line9_Relationship',

    # ============================================================
    # PART 6 - PETITIONER CONTACT
    # ============================================================
    'p6_daytime_phone': 'Pt6Line3_DaytimePhoneNumber',
    'p6_mobile_phone': 'Pt6Line4_MobileNumber',
    'p6_email': 'Pt6Line5_Email',

    # Attorney Info (if applicable)
    'attorney_checkbox': 'CheckBox1',
    'attorney_volag': 'VolagNumber',
    'attorney_bar_number': 'AttorneyStateBarNumber',
    'attorney_uscis_account': 'USCISOnlineAcctNumber',

    # ============================================================
    # G-28 ATTORNEY AUTO-FILL FIELDS
    # ============================================================
    # Attorney section at top of form
    '__g28_attached': {
        'type': 'checkbox',
        'field': 'CheckBox1'
    },
    '__bar_number': 'AttorneyStateBarNumber',
    '__uscis_account': 'USCISOnlineAcctNumber',
    '__volag_number': 'VolagNumber',

    # Part 8 - Preparer Information
    '__preparer_family_name': 'Pt8Line1a_PreparerFamilyName',
    '__preparer_given_name': 'Pt8Line1b_PreparerGivenName',
    '__preparer_business': 'Pt8Line2_BusinessName',
    '__preparer_street': 'Pt8Line3_StreetNumberName',
    '__preparer_apt_type': {
        'type': 'radio',
        'options': {
            'Apt': 'Pt8Line3_Unit[0]',
            'Ste': 'Pt8Line3_Unit[1]',
            'Flr': 'Pt8Line3_Unit[2]',
        }
    },
    '__preparer_apt': 'Pt8Line3_AptSteFlrNumber',
    '__preparer_city': 'Pt8Line3_CityOrTown',
    '__preparer_state': 'Pt8Line3_State',
    '__preparer_zip': 'Pt8Line3_ZipCode',
    '__preparer_phone': 'Pt8Line4_DaytimePhoneNumber',
    '__preparer_mobile': 'Pt8Line5_PreparerFaxNumber',  # Actually mobile in the PDF
    '__preparer_email': 'Pt8Line6_Email',
}

# =============================================================================
# I-485 FIELD MAPPING - Application to Register Permanent Residence
# =============================================================================
I485_FIELD_MAPPING = {
    'p1_alien_number': 'AlienNumber[0]',
    'p1_uscis_account': 'Pt1Line1a_OnlineAcctNumber[0]',
    'p1_last_name': 'Pt1Line1_FamilyName[0]',
    'p1_first_name': 'Pt1Line2_GivenName[0]',
    'p1_middle_name': 'Pt1Line3_MiddleName[0]',
    'p1_date_of_birth': 'Pt1Line3_DOB[0]',
    'p1_country_of_birth': 'Pt1Line5_CountryOfBirth[0]',
    'p1_country_of_citizenship': 'Pt1Line6_CountryofCitizenship[0]',
    'p1_ssn': 'Pt1Line7_SSN[0]',
    'p1_date_of_arrival': 'Pt1Line8_DateOfLastArrival[0]',
    'p1_i94_number': 'Pt1Line9_I94Number[0]',
    'p1_current_status': 'Pt1Line12_CurrentImmigrationStatus[0]',
    'p1_status_expires': 'Pt1Line13_StatusExpires[0]',
    'p1_passport_number': 'Pt1Line10a_PassportNumber[0]',
    'p1_travel_doc_number': 'Pt1Line10b_TravelDocNumber[0]',
    'p1_passport_country': 'Pt1Line11_CountryOfIssuance[0]',
    'p1_passport_expiration': 'Pt1Line11a_ExpDate[0]',
    # Mailing Address
    'p2_mailing_care_of': 'Pt2Line1_InCareofName[0]',
    'p2_mailing_street': 'Pt2Line1_StreetNumberName[0]',
    'p2_mailing_apt': 'Pt2Line1_AptSteFlrNumber[0]',
    'p2_mailing_city': 'Pt2Line1_CityOrTown[0]',
    'p2_mailing_state': 'Pt2Line1_State[0]',
    'p2_mailing_zip': 'Pt2Line1_ZipCode[0]',
    # Physical Address
    'p2_physical_street': 'Pt2Line2a_StreetNumberName[0]',
    'p2_physical_apt': 'Pt2Line2b_AptSteFlrNumber[0]',
    'p2_physical_city': 'Pt2Line2c_CityOrTown[0]',
    'p2_physical_state': 'Pt2Line2d_State[0]',
    'p2_physical_zip': 'Pt2Line2e_ZipCode[0]',
    'p2_physical_date_from': 'Pt2Line2f_DateFrom[0]',
    # Contact
    'p3_daytime_phone': 'Pt3Line1_DaytimePhone[0]',
    'p3_mobile_phone': 'Pt3Line2_MobilePhone[0]',
    'p3_email': 'Pt3Line3_Email[0]',
}

# =============================================================================
# I-765 FIELD MAPPING - Employment Authorization
# =============================================================================
I765_FIELD_MAPPING = {
    'p1_last_name': 'Line1a_FamilyName[0]',
    'p1_first_name': 'Line1b_GivenName[0]',
    'p1_middle_name': 'Line1c_MiddleName[0]',
    'p1_other_last_name': 'Line2a_FamilyName[0]',
    'p1_other_first_name': 'Line2b_GivenName[0]',
    'p1_other_middle_name': 'Line2c_MiddleName[0]',
    'p1_alien_number': 'Line7_AlienNumber[0]',
    'p1_uscis_account': 'Line8_USCISOnlineAcctNumber[0]',
    'p1_date_of_birth': 'Line4_DateOfBirth[0]',
    'p1_country_of_birth': 'Line5_CountryofBirth[0]',
    'p1_ssn': 'Line6_SSN[0]',
    'p1_i94_number': 'Line9_I94ArrivalDepartureRecordNumber[0]',
    'p1_passport_number': 'Line10_PassportNumber[0]',
    'p1_travel_doc_number': 'Line11_TravelDocumentNumber[0]',
    'p1_passport_country': 'Line12_CountryofIssuance[0]',
    'p1_passport_expiration': 'Line13_ExpDate[0]',
    'p1_date_of_arrival': 'Line14_DateofLastEntryIntoUS[0]',
    'p1_place_of_arrival': 'Line15_PlaceofLastEntryIntoUS[0]',
    'p1_current_status': 'Line16_CurrentImmStatus[0]',
    # Mailing Address
    'p2_mailing_care_of': 'Pt2Line1_InCareofName[0]',
    'p2_mailing_street': 'Pt2Line2_StreetNumberName[0]',
    'p2_mailing_apt': 'Pt2Line4_AptSteFlrNumber[0]',
    'p2_mailing_city': 'Pt2Line5_CityOrTown[0]',
    'p2_mailing_state': 'Pt2Line6_State[0]',
    'p2_mailing_zip': 'Pt2Line7_ZipCode[0]',
}

# =============================================================================
# I-131 FIELD MAPPING - Travel Document
# =============================================================================
I131_FIELD_MAPPING = {
    'p2_last_name': 'Part2_Line1_FamilyName[0]',
    'p2_first_name': 'Part2_Line2_GivenName[0]',
    'p2_middle_name': 'Part2_Line3_MiddleName[0]',
    'p1_alien_number': 'P1_Line4[0]',
    'p1_uscis_account': 'P1_Line5A[0]',
    'p1_date_of_birth': 'P2_Line5_DateOfBirth[0]',
    'p1_country_of_birth': 'P2_Line6_CountryOfBirth[0]',
    'p1_country_of_citizenship': 'P2_Line7_CountryOfCitizenship[0]',
    'p1_ssn': 'P2_Line3_SSN[0]',
    'p1_class_of_admission': 'P2_Line8_ClassOfAdmission[0]',
    # Mailing Address
    'p2_mailing_care_of': 'P2_Line9_InCareofName[0]',
    'p2_mailing_street': 'P2_Line10_StreetNumberName[0]',
    'p2_mailing_apt': 'P2_Line10_AptSteFlrNumber[0]',
    'p2_mailing_city': 'P2_Line10_CityOrTown[0]',
    'p2_mailing_state': 'P2_Line10_State[0]',
    'p2_mailing_zip': 'P2_Line10_ZipCode[0]',
    # Contact
    'p2_daytime_phone': 'P2_Line11_DaytimePhone[0]',
    'p2_email': 'P2_Line12_Email[0]',
}

# =============================================================================
# N-400 FIELD MAPPING - Naturalization
# =============================================================================
N400_FIELD_MAPPING = {
    'p2_last_name': 'P2_Line1_FamilyName[0]',
    'p2_first_name': 'P2_Line2_GivenName[0]',
    'p2_middle_name': 'P2_Line3_MiddleName[0]',
    'p1_alien_number': 'Line1_AlienNumber[0]',
    'p1_uscis_account': 'Line2_USCISOnlineActNumber[0]',
    'p2_date_of_birth': 'P2_Line8_DateOfBirth[0]',
    'p2_date_became_lpr': 'P2_Line9_DateYouBecameLPR[0]',
    'p2_country_of_birth': 'P2_Line10_CountryOfBirth[0]',
    'p2_country_of_citizenship': 'P2_Line11_CountryOfNationality[0]',
    'p2_ssn': 'P2_Line14_SSN[0]',
    # Mailing Address
    'p4_mailing_care_of': 'P4Line1_InCareofName[0]',
    'p4_mailing_street': 'P4Line2_StreetNumberName[0]',
    'p4_mailing_apt': 'P4Line4_AptSteFlrNumber[0]',
    'p4_mailing_city': 'P4Line5_CityOrTown[0]',
    'p4_mailing_state': 'P4Line6_State[0]',
    'p4_mailing_zip': 'P4Line7_ZipCode[0]',
    # Contact
    'p4_daytime_phone': 'P4Line10_DaytimePhoneNumber[0]',
    'p4_work_phone': 'P4Line11_WorkPhoneNumber[0]',
    'p4_email': 'P4Line12_EmailAddress[0]',
}

# =============================================================================
# I-589 FIELD MAPPING - Asylum
# =============================================================================
I589_FIELD_MAPPING = {
    'pa1_alien_number': 'PtAILine1_ANumber[0]',
    'pa1_last_name': 'PtAILine4_LastName[0]',
    'pa1_first_name': 'PtAILine5_FirstName[0]',
    'pa1_middle_name': 'PtAILine6_MiddleName[0]',
    'pa1_date_of_birth': 'DateTimeField1[0]',
    'pa1_sex': {
        'type': 'radio',
        'options': {
            'Male': 'PartALine9Sex[0]',
            'Female': 'PartALine9Sex[1]',
        }
    },
    'pa1_marital_status': {
        'type': 'radio',
        'options': {
            'Single': 'Marital[0]',
            'Married': 'Marital[1]',
            'Divorced': 'Marital[2]',
            'Widowed': 'Marital[3]',
        }
    },
    # Address
    'pa1_street': 'PtAILine8_StreetNumandName[0]',
    'pa1_apt': 'PtAILine8_AptNumber[0]',
    'pa1_state': 'PtAILine8_State[0]',
    'pa1_zip': 'PtAILine8_Zipcode[0]',
    'pa1_area_code': 'PtAILine8_AreaCode[0]',
    'pa1_phone': 'PtAILine8_TelephoneNumber[0]',
    # Mailing Address
    'pa1_mailing_street': 'PtAILine9_StreetNumandName[0]',
    'pa1_mailing_apt': 'PtAILine9_AptNumber[0]',
    'pa1_mailing_city': 'PtAILine9_City[0]',
    'pa1_mailing_state': 'PtAILine9_State[0]',
    'pa1_mailing_zip': 'PtAILine9_ZipCode[0]',
}

# =============================================================================
# I-751 FIELD MAPPING - Remove Conditions
# =============================================================================
I751_FIELD_MAPPING = {
    'p1_last_name': 'Pt1Line1a_FamilyName[0]',
    'p1_first_name': 'Pt1Line1b_GivenName[0]',
    'p1_middle_name': 'Pt1Line1c_MiddleName[0]',
    'p1_maiden_last_name': 'P1_Line2a_FamilyName[0]',
    'p1_maiden_first_name': 'P1_Line2b_GivenName[0]',
    'p1_other_last_name': 'P1_Line3a_FamilyName[0]',
    'p1_other_first_name': 'P1_Line3b_GivenName[0]',
    'p1_date_of_birth': 'P1_Line4_DateOfBirth[0]',
    'p1_country_of_birth': 'P1_Line5_CountryOfBirth[0]',
    'p1_country_of_citizenship': 'P1_Line6_CountryOfCitizenship[0]',
    'p1_alien_number': 'P1_Line7_AlienNumber[0]',
    'p1_ssn': 'P1_Line8_SSN[0]',
    'p1_uscis_account': 'P1_Line9_AcctIdentifier[0]',
    'p1_marital_status': {
        'type': 'radio',
        'options': {
            'Married': 'Part1_Line10_MaritalStatus[0]',
            'Divorced': 'Part1_Line10_MaritalStatus[1]',
            'Widowed': 'Part1_Line10_MaritalStatus[2]',
            'Annulled': 'Part1_Line10_MaritalStatus[3]',
        }
    },
    'p1_date_of_marriage': 'P1_Line11_DateOfMarriage[0]',
    'p1_place_of_marriage': 'P1_Line12_PlaceOfMarriage[0]',
    'p1_date_marriage_ended': 'P1_Line13_DateMarriageEnded[0]',
    'p1_cr_expires': 'P1_Line14_CRExpiresOn[0]',
    # Mailing Address
    'p1_mailing_care_of': 'Pt1Line17_InCareofName[0]',
    'p1_mailing_street': 'Pt1Line17_StreetNumberName[0]',
    'p1_mailing_apt': 'Pt1Line17_AptSteFlrNumber[0]',
    'p1_mailing_city': 'Pt1Line17_CityOrTown[0]',
    'p1_mailing_zip': 'Pt1Line17_ZipCode[0]',
}

# =============================================================================
# I-539 FIELD MAPPING - Extend/Change Status
# =============================================================================
I539_FIELD_MAPPING = {
    'p1_last_name': 'P1Line1a_FamilyName[0]',
    'p1_first_name': 'P1_Line1b_GivenName[0]',
    'p1_middle_name': 'P1_Line1c_MiddleName[0]',
    'p1_alien_number': 'Pt1Line2_AlienNumber[0]',
    'p1_uscis_account': 'Pt1Line2_USCISOnlineAcctNumber[0]',
    'p1_country_of_birth': 'P1_Line6_CountryOfBirth[0]',
    'p1_country_of_citizenship': 'P1_Line7_CountryOfCitizenship[0]',
    'p1_date_of_birth': 'P1_Line8_DateOfBirth[0]',
    'p1_ssn': 'P1_Line9_SSN[0]',
    'p1_date_of_arrival': 'SupA_Line1i_DateOfArrival[0]',
    'p1_i94_number': 'SupA_Line1j_ArrivalDeparture[0]',
    'p1_passport_number': 'SupA_Line1k_Passport[0]',
    'p1_travel_doc_number': 'SupA_Line1l_TravelDoc[0]',
    'p1_passport_country': 'SupA_Line1m_CountryOfIssuance[0]',
    'p1_passport_expiration': 'SupA_Line1n_ExpDate[0]',
    'p1_status_expiration': 'SupA_Line1p_DateExpires[0]',
    # Mailing Address
    'p2_mailing_care_of': 'Part2_Item11_InCareOfName[0]',
    'p2_mailing_street': 'Part2_Item11_StreetName[0]',
    'p2_mailing_apt': 'Part1_Item4_Number[0]',
    'p2_mailing_city': 'Part2_Item11_City[0]',
    'p2_mailing_zip': 'Part2_Item11_ZipCode[0]',
    # Physical Address
    'p1_physical_street': 'Part1_Item6_StreetName[0]',
    'p1_physical_apt': 'Part1_Item6_Number[0]',
    'p1_physical_city': 'Part1_Item6_City[0]',
    'p1_physical_zip': 'Part1_Item6_ZipCode[0]',
    # Application Details
    'p2_requested_date': 'Pt2Line2b_EffectiveDate[0]',
    'p3_receipt_number': 'P3_Line5_ReceiptNumber[0]',
}

# =============================================================================
# I-864 FIELD MAPPING - Affidavit of Support
# =============================================================================
I864_FIELD_MAPPING = {
    # Part 4 - Sponsor Information
    'p4_last_name': 'P4_Line1a_FamilyName[0]',
    'p4_first_name': 'P4_Line1b_GivenName[0]',
    'p4_middle_name': 'P4_Line1c_MiddleName[0]',
    'p4_date_of_birth': 'P4_Line6_DateOfBirth[0]',
    'p4_city_of_birth': 'P4_Line7_CityofBirth[0]',
    'p4_country_of_domicile': 'P4_Line5_CountryOfDomicile[0]',
    'p4_ssn': 'P4_Line10_SocialSecurityNumber[0]',
    'p4_alien_number': 'P4_Line12_AlienNumber[0]',
    'p4_uscis_account': 'P4_Line13_AcctIdentifier[0]',
    # Sponsor Mailing Address
    'p4_mailing_care_of': 'P4_Line2a_InCareOf[0]',
    'p4_mailing_street': 'P4_Line2b_StreetNumberName[0]',
    'p4_mailing_apt': 'P4_Line2d_AptSteFlrNumber[0]',
    'p4_mailing_city': 'P4_Line2e_CityOrTown[0]',
    'p4_mailing_zip': 'P4_Line2g_ZipCode[0]',
    'p4_mailing_province': 'P4_Line2h_Province[0]',
    'p4_mailing_postal_code': 'P4_Line2i_PostalCode[0]',
    'p4_mailing_country': 'P4_Line2j_Country[0]',
    # Physical Address
    'p4_physical_street': 'P4_Line4a_StreetNumberName[0]',
    'p4_physical_apt': 'P4_Line4c_AptSteFlrNumber[0]',
    'p4_physical_city': 'P4_Line4d_CityOrTown[0]',
    'p4_physical_zip': 'P4_Line4f_ZipCode[0]',
    # Part 2 - Immigrant Information
    'p2_last_name': 'P2_Line1a_FamilyName[0]',
    'p2_first_name': 'P2_Line1b_GivenName[0]',
    'p2_middle_name': 'P2_Line1c_MiddleName[0]',
    'p2_relationship': 'P1_Line1b_Relationship[0]',
}

# =============================================================================
# FORM FIELD MAPPINGS REGISTRY
# =============================================================================
FORM_FIELD_MAPPINGS = {
    'I-130': FIELD_MAPPING,  # Uses the existing comprehensive mapping
    'I-485': I485_FIELD_MAPPING,
    'I-765': I765_FIELD_MAPPING,
    'I-131': I131_FIELD_MAPPING,
    'N-400': N400_FIELD_MAPPING,
    'I-589': I589_FIELD_MAPPING,
    'I-751': I751_FIELD_MAPPING,
    'I-539': I539_FIELD_MAPPING,
    'I-864': I864_FIELD_MAPPING,
}


def format_date(value):
    """Format date to MM/DD/YYYY"""
    if not value:
        return ''
    try:
        from datetime import datetime
        # Handle ISO format
        if 'T' in str(value):
            dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        else:
            # Try common formats
            for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y']:
                try:
                    dt = datetime.strptime(str(value), fmt)
                    break
                except ValueError:
                    continue
            else:
                return str(value)
        return dt.strftime('%m/%d/%Y')
    except Exception:
        return str(value)


def fill_pdf(answers, form_type='I-130'):
    """Fill PDF with answers using PyMuPDF - supports all form types"""
    # Get PDF URL for the form type
    pdf_url = PDF_URLS.get(form_type)
    if not pdf_url:
        raise ValueError(f"Unknown form type: {form_type}")

    # Get field mapping for the form type
    field_mapping = FORM_FIELD_MAPPINGS.get(form_type, {})
    if not field_mapping:
        raise ValueError(f"No field mapping for form type: {form_type}")

    print(f"Filling {form_type} PDF with {len(field_mapping)} mapped fields")

    # Download PDF
    tmp_input = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    urllib.request.urlretrieve(pdf_url, tmp_input.name)

    # Open with PyMuPDF
    doc = fitz.open(tmp_input.name)

    fields_filled = 0

    for page in doc:
        for field in page.widgets():
            field_name = field.field_name or ''

            for answer_id, answer_value in answers.items():
                if not answer_value or answer_id not in field_mapping:
                    continue

                mapping = field_mapping[answer_id]

                try:
                    if isinstance(mapping, dict):
                        if mapping['type'] == 'radio':
                            target = mapping['options'].get(
                                str(answer_value), ''
                            )
                            if target and target in field_name:
                                field.field_value = True
                                field.update()
                                fields_filled += 1
                        elif mapping['type'] == 'checkbox':
                            selected = answer_value if isinstance(answer_value, list) else [answer_value]
                            for sel in selected:
                                target = mapping['options'].get(str(sel), '')
                                if target and target in field_name:
                                    field.field_value = True
                                    field.update()
                                    fields_filled += 1
                        elif mapping['type'] == 'weight':
                            weight_str = str(answer_value).zfill(3)
                            weight_fields = mapping['fields']
                            for i, digit in enumerate(weight_str[-3:]):
                                if i < len(weight_fields):
                                    target = weight_fields[i]
                                    if target in field_name:
                                        field.field_value = digit
                                        field.update()
                                        fields_filled += 1
                    elif isinstance(mapping, str):
                        if mapping in field_name:
                            field_type = field.field_type

                            # Format dates
                            if 'date' in answer_id.lower() or \
                               'Date' in mapping or 'dob' in answer_id.lower():
                                value = format_date(answer_value)
                            else:
                                value = str(answer_value)

                            # Handle dropdown fields carefully
                            if field_type == 2:  # dropdown/listbox
                                # Only set if value is in choices
                                choices = field.choice_values or []
                                choice_strings = [
                                    str(c) if not isinstance(c, str)
                                    else c
                                    for c in choices
                                ]
                                if value in choice_strings:
                                    field.field_value = value
                                    field.update()
                                    fields_filled += 1
                                else:
                                    print(f'Skipping dropdown {field_name}: '
                                          f'"{value}" not in {choice_strings[:5]}')
                            else:
                                # Text field or checkbox
                                field.field_value = value
                                field.update()
                                fields_filled += 1
                except Exception as e:
                    print(f'Warning: Could not fill {field_name}: {e}')
                    continue

    print(f"Filled {fields_filled} fields")

    # ============================================================
    # G-28 ATTORNEY AUTO-FILL: Check G-28 checkbox and attorney box
    # ============================================================

    # Check G-28 attached checkbox if attorney data is provided
    if answers.get('__g28_attached') or answers.get('__bar_number'):
        for page in doc:
            for field in page.widgets():
                field_name = field.field_name or ''
                # G-28 checkbox at top of form (CheckBox1)
                if 'CheckBox1' in field_name and 'Pt8' not in field_name:
                    try:
                        field.field_value = True
                        field.update()
                        print(f"Checked G-28 box: {field_name}")
                    except Exception as e:
                        print(f"Could not check G-28 box: {e}")

    # Check "I am an attorney" checkbox in Part 8 if attorney
    if answers.get('__is_attorney', False):
        for page in doc:
            for field in page.widgets():
                field_name = field.field_name or ''
                # Part 8 attorney checkbox - "extends beyond preparation"
                if 'Pt8Line7b_Checkbox[0]' in field_name:
                    try:
                        field.field_value = True
                        field.update()
                        print(f"Checked attorney checkbox: {field_name}")
                    except Exception as e:
                        print(f"Could not check attorney box: {e}")
                # Also select Part 8 Line 7 Option B (attorney section)
                if 'Pt8Line7_Checkbox[1]' in field_name:
                    try:
                        field.field_value = True
                        field.update()
                        print(f"Checked Part 8 Line 7 attorney option: {field_name}")
                    except Exception as e:
                        print(f"Could not check attorney option: {e}")

    # Save to temp file
    tmp_output = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    doc.save(tmp_output.name)
    doc.close()

    # Cleanup input
    os.unlink(tmp_input.name)

    return tmp_output.name


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'service': 'pdf-filler',
        'supported_forms': list(FORM_FIELD_MAPPINGS.keys()),
        'fields_mapped': {form: len(mapping) for form, mapping in FORM_FIELD_MAPPINGS.items()},
        'i130_fields': len(FIELD_MAPPING)  # Legacy compatibility
    })


@app.route('/fill-pdf', methods=['POST'])
def fill_pdf_endpoint():
    # Verify secret
    auth = request.headers.get('Authorization', '')
    if auth != f'Bearer {API_SECRET}':
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        data = request.get_json()
        if not data or 'answers' not in data:
            return jsonify({'error': 'Missing answers'}), 400

        answers = data['answers']
        form_type = data.get('form_type', 'I-130')
        client_name = data.get('client_name', 'client')

        print(f"Filling {form_type} for {client_name}")
        print(f"Answers count: {len(answers)}")

        # Fill the PDF with the specified form type
        output_path = fill_pdf(answers, form_type)

        # Return the PDF with form-specific filename
        safe_name = client_name.replace(' ', '-').replace('/', '-')
        filename = f"{form_type}-{safe_name}.pdf"

        response = send_file(
            output_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )

        # Cleanup after sending
        @response.call_on_close
        def cleanup():
            try:
                os.unlink(output_path)
            except Exception:
                pass

        return response

    except Exception as e:
        print(f"Error filling PDF: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': str(e),
            'details': traceback.format_exc()
        }), 500


def fill_g28(settings):
    """Fill G-28 PDF with attorney settings using PyMuPDF"""
    # Download G-28 PDF
    g28_url = 'https://www.uscis.gov/sites/default/files/document/forms/g-28.pdf'

    tmp_input = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    urllib.request.urlretrieve(g28_url, tmp_input.name)

    doc = fitz.open(tmp_input.name)
    fields_filled = 0

    for page in doc:
        for field in page.widgets():
            field_name = field.field_name or ''

            # TEXT FIELDS
            for answer_key, pdf_field in G28_FIELD_MAPPING.items():
                if pdf_field in field_name:
                    value = settings.get(answer_key, '')
                    if value:
                        try:
                            field.field_value = str(value)
                            field.update()
                            fields_filled += 1
                            print(f"Filled text: {field_name} = {value}")
                        except Exception as e:
                            print(f"Warning text {field_name}: {e}")

            # CHECKBOX FIELDS
            for answer_key, option_map in G28_CHECKBOX_MAPPING.items():
                answer_value = settings.get(answer_key)
                if answer_value is None:
                    continue

                target_field = option_map.get(answer_value)
                if target_field and target_field in field_name:
                    try:
                        field.field_value = True
                        field.update()
                        fields_filled += 1
                        print(f"Checked: {field_name}")
                    except Exception as e:
                        print(f"Warning checkbox {field_name}: {e}")

    print(f"Total G-28 fields filled: {fields_filled}")

    tmp_output = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    doc.save(tmp_output.name)
    doc.close()
    os.unlink(tmp_input.name)

    return tmp_output.name


@app.route('/fill-g28', methods=['POST'])
def fill_g28_endpoint():
    """Fill G-28 form with attorney data from Settings"""
    auth = request.headers.get('Authorization', '')
    if auth != f'Bearer {API_SECRET}':
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        data = request.get_json()
        if not data or 'settings' not in data:
            return jsonify({'error': 'Missing settings'}), 400

        settings = data['settings']
        print(f"Filling G-28 for: {settings.get('givenName')} {settings.get('familyName')}")
        print(f"Settings keys: {list(settings.keys())}")

        output_path = fill_g28(settings)

        attorney_name = f"{settings.get('givenName', '')}-{settings.get('familyName', '')}"
        filename = f"G-28-{attorney_name}.pdf"

        response = send_file(
            output_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )

        @response.call_on_close
        def cleanup():
            try:
                os.unlink(output_path)
            except:
                pass

        return response

    except Exception as e:
        import traceback
        print(f"ERROR: {e}")
        print(traceback.format_exc())
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
