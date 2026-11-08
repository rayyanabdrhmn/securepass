from django import forms
from .models import Visitor


class VisitorForm(forms.ModelForm):
    class Meta:
        model = Visitor
        fields = ["name", "vehicle_plate", "phone", "gender", "ic_number"]
        labels = {
            "vehicle_plate": "Vehicle plate number",
            "phone": "Phone number",
            "ic_number": "IC number",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
        self.fields["gender"].widget.attrs["class"] = "form-select"

    def clean_vehicle_plate(self):
        plate = self.cleaned_data["vehicle_plate"]
        return plate.replace(" ", "").upper()

    def clean_ic_number(self):
        ic = self.cleaned_data["ic_number"].replace("-", "").replace(" ", "")
        if not (ic.isdigit() and len(ic) == 12):
            raise forms.ValidationError("Enter a valid 12-digit IC number, e.g. 960110101234.")
        return ic