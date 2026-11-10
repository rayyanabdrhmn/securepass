import re
from datetime import date

from django import forms
from .models import Visitor

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z @'./-]*$")
PLATE_RE = re.compile(r"^(?=.*[A-Z])[A-Z0-9]{1,10}\d{1,4}[A-Z]{0,2}$")
PHONE_RE = re.compile(r"^01\d{8,9}$")


class VisitorForm(forms.ModelForm):
    class Meta:
        model = Visitor
        fields = ["name", "vehicle_plate", "phone", "gender", "ic_number"]
        labels = {
            "name": "Full name",
            "vehicle_plate": "Vehicle plate number",
            "phone": "Mobile number",
            "ic_number": "MyKad (IC) number",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
        self.fields["gender"].widget.attrs["class"] = "form-select"

        # Hints for phone keyboards (number pad for IC and phone, capitals for plate)
        hints = {
            "name": {"placeholder": "Full name as on MyKad", "autocomplete": "name"},
            "vehicle_plate": {"placeholder": "e.g. WXY 1234", "autocapitalize": "characters"},
            "phone": {"placeholder": "e.g. 012-345 6789", "inputmode": "tel", "autocomplete": "tel"},
            "ic_number": {"placeholder": "12 digits, dashes optional", "inputmode": "numeric"},
        }
        for name, attrs in hints.items():
            self.fields[name].widget.attrs.update(attrs)

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())   # removes extra spaces
        letters = sum(c.isalpha() for c in name)
        if letters < 3 or not NAME_RE.match(name):
            raise forms.ValidationError("Enter your full name using letters only.")
        return name

    def clean_vehicle_plate(self):
        plate = self.cleaned_data["vehicle_plate"].upper().replace(" ", "").replace("-", "")
        if not PLATE_RE.match(plate):
            raise forms.ValidationError("Enter a valid Malaysian plate number, e.g. WXY 1234.")
        return plate

    def clean_phone(self):
        phone = re.sub(r"[\s\-+()]", "", self.cleaned_data["phone"])
        if phone.startswith("60"):
            phone = phone[1:]   # 60123456789 becomes 0123456789
        if not PHONE_RE.match(phone):
            raise forms.ValidationError("Enter a valid Malaysian mobile number, e.g. 012-345 6789.")
        return phone

    def clean_ic_number(self):
        ic = re.sub(r"[\s-]", "", self.cleaned_data["ic_number"])
        if not (ic.isdigit() and len(ic) == 12):
            raise forms.ValidationError("Enter your 12-digit MyKad number.")

        # The first 6 digits are the birth date (YYMMDD)
        yy, mm, dd = int(ic[0:2]), int(ic[2:4]), int(ic[4:6])
        real_date = False
        for century in (1900, 2000):
            try:
                date(century + yy, mm, dd)
                real_date = True
                break
            except ValueError:
                pass
        if not real_date or ic[6:8] == "00":
            raise forms.ValidationError("This MyKad number doesn't look valid. Please check it.")
        return ic