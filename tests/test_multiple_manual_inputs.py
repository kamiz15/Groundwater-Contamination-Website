"""The input form under the graph on a multiple page has to actually drive it.

The workbench form kept the original CAST field names (tv, g, Ca, Cd, W, ...)
while panel_site_comparison runs on canonical symbols (alpha_Tv, gamma, C_A,
C_D, S_w, ...). Nothing fails loudly when those drift apart - the field just
stops doing anything - so it is pinned here.
"""

import pytest

from analytical_routes import ANALYTICAL_INPUT_SPECS
from empirical_routes import EMPIRICAL_INPUT_SPECS
from panel_site_comparison import FORM_ALIASES, MODEL_SPECS, manual_fallback

FORM_SPECS = {**ANALYTICAL_INPUT_SPECS, **EMPIRICAL_INPUT_SPECS}
MODELS = sorted(MODEL_SPECS)


def _form_names(model):
    spec = FORM_SPECS.get(f"panel_{model}_multiple")
    assert spec, f"no workbench input form is defined for {model}"
    return [field[0] for field in spec]


@pytest.mark.parametrize("model", MODELS)
def test_every_form_field_reaches_a_model_parameter(model):
    aliases = FORM_ALIASES.get(model, {})
    reachable = set(MODEL_SPECS[model]["defaults"]) | set(aliases.values())

    orphans = [name for name in _form_names(model) if name not in reachable]
    assert not orphans, f"{model}: form fields that change nothing: {orphans}"


@pytest.mark.parametrize("model", MODELS)
def test_every_model_parameter_is_editable_in_the_form(model):
    aliases = FORM_ALIASES.get(model, {})
    form = set(_form_names(model))

    missing = [key for key in MODEL_SPECS[model]["defaults"]
               if key not in form and aliases.get(key) not in form]
    assert not missing, f"{model}: parameters with no input field: {missing}"


@pytest.mark.parametrize("model", MODELS)
def test_aliases_only_rename_real_parameters(model):
    unknown = [k for k in FORM_ALIASES.get(model, {}) if k not in MODEL_SPECS[model]["defaults"]]
    assert not unknown, f"{model}: aliases for parameters the model does not take: {unknown}"


def test_form_values_are_read_under_the_forms_own_names(monkeypatch):
    """?tv=0.002 from the birla form must land on alpha_Tv."""
    import panel_site_comparison as psc

    posted = {"tv": 0.002, "Ca": 9.0, "M": 3.0}
    monkeypatch.setattr(psc, "query_float", lambda name, default: posted.get(name, default))

    fallback = manual_fallback("birla")

    assert fallback["alpha_Tv"] == 0.002      # renamed field
    assert fallback["C_A"] == 9.0             # renamed field
    assert fallback["M"] == 3.0               # name shared by both sides
    assert fallback["C_D"] == MODEL_SPECS["birla"]["defaults"]["C_D"]   # untouched


def test_canonical_name_wins_over_the_form_alias(monkeypatch):
    """A URL written with the canonical symbol keeps working."""
    import panel_site_comparison as psc

    posted = {"tv": 0.002, "alpha_Tv": 0.007}
    monkeypatch.setattr(psc, "query_float", lambda name, default: posted.get(name, default))

    assert manual_fallback("birla")["alpha_Tv"] == 0.007
