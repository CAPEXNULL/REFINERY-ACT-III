"""Optional AMD explanation overlay for the existing IndustryService.

The qualified IndustryService and its persisted diagnostic record stay unchanged.
The AMD explanation is returned separately as a transient presentation field.
"""

from amd.industry_service import IndustryService
from amd.amd_explainer import explain_diagnosis


class AMDIndustryService(IndustryService):
    def run(self, args, progress=None):
        accepted = super().run(args, progress=progress)
        # Copy rather than mutate the accepted diagnosis result already archived.
        displayed = dict(accepted)
        # The explainer itself only sends an allowlisted label and confidence.
        displayed["amd_explanation"] = explain_diagnosis(accepted["diagnosis"])
        return displayed
