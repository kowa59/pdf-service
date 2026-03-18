import os
import json
import tempfile
import urllib.request
from flask import Flask, request, jsonify, send_file
import fitz  # PyMuPDF

app = Flask(__name__)

# I-130 PDF URL from Vercel Blob
I130_PDF_URL = os.environ.get(
    'I130_PDF_URL',
    'https://axqfryjovgwq4smc.public.blob.vercel-storage.com/uscis-forms/i-130.pdf'
)

# Secret key to protect the endpoint
API_SECRET = os.environ.get('PDF_SERVICE_SECRET', 'changeme')

# Map questionnaire answer IDs to PDF field names
FIELD_MAPPING = {
    # Part 1 - Relationship
    'p1_relationship': {
        'type': 'radio',
        'options': {
            'Spouse': 'Pt1Line1_Spouse',
            'Child': 'Pt1Line1_Child',
            'Parent': 'Pt1Line1_Parent',
            'Siblings': 'Pt1Line1_Siblings',
        }
    },
    # Part 2 - Petitioner
    'p2_alien_number': 'Pt2Line1_AlienNumber',
    'p2_last_name': 'Pt2Line4a_FamilyName',
    'p2_first_name': 'Pt2Line4b_GivenName',
    'p2_middle_name': 'Pt2Line4c_MiddleName',
    'p2_other_last_name': 'Pt2Line5a_FamilyName',
    'p2_other_first_name': 'Pt2Line5b_GivenName',
    'p2_city_of_birth': 'Pt2Line6_CityTownOfBirth',
    'p2_country_of_birth': 'Pt2Line7_CountryofBirth',
    'p2_date_of_birth': 'Pt2Line8_DateofBirth',
    'p2_ssn': 'Pt2Line11_SSN',
    'p2_mailing_street': 'Pt2Line10_StreetNumberName',
    'p2_mailing_city': 'Pt2Line10_CityOrTown',
    'p2_mailing_state': 'Pt2Line10_State',
    'p2_mailing_zip': 'Pt2Line10_ZipCode',
    'p2_mailing_province': 'Pt2Line10_Province',
    'p2_mailing_postal_code': 'Pt2Line10_PostalCode',
    'p2_mailing_country': 'Pt2Line10_Country',
    'p2_num_marriages': 'Pt2Line16_NumberofMarriages',
    'p2_date_of_marriage': 'Pt2Line18_DateOfMarriage',
    'p2_marriage_city': 'Pt2Line19a_CityTown',
    'p2_marriage_state': 'Pt2Line19b_State',
    'p2_marriage_country': 'Pt2Line19d_Country',
    'p2_employer1_name': 'Pt2Line42_EmployerName',
    'p2_employer1_city': 'Pt2Line43_CityOrTown',
    'p2_employer1_occupation': 'Pt2Line44_Occupation',
    # Part 3 - Biographic
    'p3_weight': 'Pt3Line4_Pound1',
    # Part 4 - Beneficiary
    'p4_alien_number': 'Pt4Line1_AlienNumber',
    'p4_last_name': 'Pt4Line4a_FamilyName',
    'p4_first_name': 'Pt4Line4b_GivenName',
    'p4_middle_name': 'Pt4Line4c_MiddleName',
    'p4_city_of_birth': 'Pt4Line7_CityTownOfBirth',
    'p4_country_of_birth': 'Pt4Line8_CountryOfBirth',
    'p4_date_of_birth': 'Pt4Line9_DateOfBirth',
    'p4_street': 'Pt4Line11_StreetNumberName',
    'p4_city': 'Pt4Line11_CityOrTown',
    'p4_country': 'Pt4Line11_Country',
    'p4_daytime_phone': 'Pt4Line14_DaytimePhoneNumber',
    'p4_email': 'Pt4Line16_EmailAddress',
    'p4_i94_number': 'Pt4Line47_I94Number',
    'p4_passport_number': 'Pt4Line49_PassportTravelDocNumber',
    'p4_passport_country': 'Pt4Line50_CountryIssuingPassport',
    'p4_passport_expiration': 'Pt4Line51_ExpirationDate',
}

def format_date(value):
    """Format date to MM/DD/YYYY"""
    if not value:
        return ''
    try:
        from datetime import datetime
        # Handle ISO format
        if 'T' in str(value):
            dt = datetime.fromisoformat(str(value).replace('Z', ''))
        else:
            # Try common formats
            for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y']:
                try:
                    dt = datetime.strptime(str(value), fmt)
                    break
                except:
                    continue
            else:
                return str(value)
        return dt.strftime('%m/%d/%Y')
    except:
        return str(value)

def fill_pdf(answers):
    """Fill I-130 PDF with answers using PyMuPDF"""
    # Download PDF
    tmp_input = tempfile.NamedTemporaryFile(
        suffix='.pdf', delete=False
    )
    urllib.request.urlretrieve(I130_PDF_URL, tmp_input.name)

    # Open with PyMuPDF
    doc = fitz.open(tmp_input.name)

    fields_filled = 0

    for answer_id, answer_value in answers.items():
        if not answer_value or answer_id not in FIELD_MAPPING:
            continue

        mapping = FIELD_MAPPING[answer_id]

        # Search all pages for the field
        for page in doc:
            for field in page.widgets():
                field_name = field.field_name or ''

                if isinstance(mapping, dict):
                    # Radio button group
                    if mapping['type'] == 'radio':
                        target = mapping['options'].get(
                            str(answer_value), ''
                        )
                        if target and target in field_name:
                            field.field_value = True
                            field.update()
                            fields_filled += 1
                elif isinstance(mapping, str):
                    # Text field - match by field name
                    if mapping in field_name:
                        # Format dates
                        if 'date' in answer_id.lower() or 'Date' in mapping:
                            value = format_date(answer_value)
                        else:
                            value = str(answer_value)

                        field.field_value = value
                        field.update()
                        fields_filled += 1

    print(f"Filled {fields_filled} fields")

    # Save to temp file
    tmp_output = tempfile.NamedTemporaryFile(
        suffix='.pdf', delete=False
    )
    doc.save(tmp_output.name)
    doc.close()

    # Cleanup input
    os.unlink(tmp_input.name)

    return tmp_output.name

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'service': 'pdf-filler'})

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

        # Fill the PDF
        output_path = fill_pdf(answers)

        # Return the PDF
        filename = f"I-130-{client_name.replace(' ', '-')}.pdf"

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
            except:
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
