from mid_drive.llm_revision import worth_llm_fallback, would_have_been_fallback
from mid_drive.models import MissionConstraints, MissionPatch
from mid_drive.revision import parse_turn


def test_empty_is_unrelated() -> None:
    assert parse_turn("", None).operation == "unrelated"
    assert parse_turn("   ", None).operation == "unrelated"


def test_backchannel_is_unrelated() -> None:
    assert parse_turn("uh-huh", None).operation == "unrelated"
    assert parse_turn("okay", None).operation == "unrelated"


def test_create_coffee() -> None:
    patch = parse_turn("Find a coffee shop near my route", None)
    assert patch.operation == "create"
    assert patch.category == "coffee"
    assert patch.parking_required is None
    assert patch.avoid_tolls is None


def test_create_juice() -> None:
    patch = parse_turn("Find a juice shop near my route", None)
    assert patch.operation == "create"
    assert patch.category == "juice"
    assert patch.parking_required is None
    assert patch.brand_query is None
    assert parse_turn("I need a smoothie", None).category == "juice"
    current = MissionConstraints(category="juice")
    assert parse_turn("Wait, I need parking too.", current).operation == "add"
    assert parse_turn("The second one.", current).operation == "select"
    assert parse_turn("Actually, I need fuel.", current).operation == "replace"
    assert parse_turn("Actually, I need fuel.", current).category == "fuel"


def test_add_parking() -> None:
    current = MissionConstraints(category="coffee")
    patch = parse_turn("Wait, it needs parking", current)
    assert patch.operation == "add"
    assert patch.parking_required is True
    assert patch.category is None


def test_restated_coffee_plus_parking_is_add_only() -> None:
    current = MissionConstraints(category="coffee")
    patch = parse_turn(
        "Find me a coffee shop near my route. Wait, I need parking too.",
        current,
    )
    assert patch.operation == "add"
    assert patch.parking_required is True
    assert patch.category is None


def test_demo_stt_variants_parking_and_second() -> None:
    current = MissionConstraints(category="coffee")
    assert parse_turn("Does it have a parking lot?", current).inquire_kind == "parking"
    assert parse_turn("Does this have parking?", current).inquire_kind == "parking"
    assert parse_turn("Do they have parking?", current).inquire_kind == "parking"
    assert parse_turn("Wait I need parking to.", current).operation == "add"
    assert parse_turn("Wait I need parking to.", current).parking_required is True
    assert parse_turn("Another one. The second one.", current).operation == "select"
    assert parse_turn("Another one. The second one.", current).select_index == 2
    assert parse_turn("Compare them. The second one.", current).operation == "select"
    assert parse_turn("I want the second one.", current).operation == "select"
    assert parse_turn("the second one", current).select_index == 2
    assert parse_turn("number two", current).select_index == 2


def test_need_parking_too_is_add_not_inquire() -> None:
    current = MissionConstraints(category="coffee")
    spoken = parse_turn("Wait, I need parking too.", current)
    assert spoken.operation == "add"
    assert spoken.parking_required is True
    mixed = parse_turn("Wait, I think I also need parking. Does Chai Point have parking?", current)
    assert mixed.operation == "add"
    assert mixed.parking_required is True
    assert parse_turn("Does Chai Point have parking?", current).operation == "inquire"
    assert parse_turn("Does Chai Point have parking?", current).inquire_kind == "parking"
    assert parse_turn("Is there parking in Chai Point?", current).operation == "inquire"
    assert parse_turn("Is there parking in Chai Point?", current).inquire_kind == "parking"


def test_sign_a_coffee_is_create() -> None:
    patch = parse_turn("Sign a coffee shop near my route.", None)
    assert patch.operation == "create"
    assert patch.category == "coffee"
    assert patch.brand_query is None


def test_add_avoid_tolls() -> None:
    current = MissionConstraints(category="coffee", parking_required=True)
    patch = parse_turn("Avoid toll roads too", current)
    assert patch.operation == "add"
    assert patch.avoid_tolls is True


def test_replace_category() -> None:
    current = MissionConstraints(category="coffee", parking_required=True)
    patch = parse_turn("Actually fuel", current)
    assert patch.operation == "replace"
    assert patch.category == "fuel"
    assert parse_turn("Actually, I need fuel.", current).operation == "replace"
    assert parse_turn("Actually, I need fuel.", current).category == "fuel"
    assert parse_turn("I need fuel.", current).category == "fuel"
    assert parse_turn("Actually I need full.", current).category == "fuel"
    assert parse_turn("The second one. Actually I need fuel.", current).operation == "replace"
    assert parse_turn("The second one. Actually I need fuel.", current).category == "fuel"


def test_allow_tolls_again() -> None:
    current = MissionConstraints(category="coffee", avoid_tolls=True)
    patch = parse_turn("Allow tolls again", current)
    assert patch.operation == "add"
    assert patch.avoid_tolls is False


def test_cancel_standalone_only() -> None:
    current = MissionConstraints(category="coffee")
    assert parse_turn("stop", current).operation == "cancel"
    assert parse_turn("forget it", current).operation == "cancel"
    assert parse_turn("stop avoiding tolls", current).operation == "add"
    assert parse_turn("stop avoiding tolls", current).avoid_tolls is False


def test_ambiguous_find_without_category() -> None:
    patch = parse_turn("Find something near me", None)
    assert patch.operation == "ambiguous"


def test_detour_minutes() -> None:
    patch = parse_turn("Find coffee within 10 minutes", None)
    assert patch.operation == "create"
    assert patch.maximum_detour_minutes == 10


def test_gas_is_fuel() -> None:
    patch = parse_turn("I need gas", None)
    assert patch.operation == "create"
    assert patch.category == "fuel"


def test_two_categories_are_ambiguous() -> None:
    patch = parse_turn("Find coffee or fuel", None)
    assert patch.operation == "ambiguous"


def test_confirm_and_next() -> None:
    current = MissionConstraints(category="coffee")
    assert parse_turn("Keep this one", current).operation == "confirm"
    assert parse_turn("Not that, another one", current).operation == "next"
    assert parse_turn("Keep this one", None).operation != "confirm"


def test_closer_sets_detour() -> None:
    current = MissionConstraints(category="coffee")
    patch = parse_turn("That's too far, closer", current)
    assert patch.operation == "add"
    assert patch.maximum_detour_minutes == 5


def test_near_my_route_is_not_a_landmark() -> None:
    patch = parse_turn("Find a coffee shop near my route", None)
    assert patch.operation == "create"
    assert patch.landmark_query is None
    assert parse_turn("Find coffee on the way", None).landmark_query is None


def test_landmark_from_speech() -> None:
    patch = parse_turn("Find coffee near Cyber Hub", None)
    assert patch.operation == "create"
    assert patch.landmark_query == "Cyber Hub"


def test_destination_and_origin() -> None:
    current = MissionConstraints(category="coffee")
    dest = parse_turn("Change destination to India Gate", current)
    assert dest.operation == "add"
    assert dest.destination_query == "India Gate"
    origin = parse_turn("Start from IFFCO Chowk", current)
    assert origin.origin_query == "IFFCO Chowk"
    assert parse_turn("Take me to a pharmacy", current).operation == "replace"
    assert parse_turn("Take me to a pharmacy", current).destination_query is None
    assert parse_turn("Take me to a pharmacy", current).category == "pharmacy"


def test_petrol_pump_and_medical_store() -> None:
    petrol = parse_turn("Need a petrol pump", None)
    assert petrol.category == "fuel"
    assert petrol.brand_query is None
    medical = parse_turn("Find a medical store", None)
    assert medical.category == "pharmacy"
    assert medical.brand_query is None
    chai = parse_turn("Find chai", None)
    assert chai.category == "coffee"
    assert chai.brand_query is None


def test_parking_off_and_mixed_inquire_do_not_invent_brand() -> None:
    current = MissionConstraints(category="coffee", parking_required=True)
    dropped = parse_turn("Don't need parking", current)
    assert dropped.operation == "add"
    assert dropped.parking_required is False
    assert dropped.brand_query is None
    mixed = parse_turn("I need parking — does Chai Point have parking?", current)
    assert mixed.operation == "add"
    assert mixed.parking_required is True
    assert mixed.brand_query is None


def test_weather_does_not_trigger_llm() -> None:
    patch = MissionPatch(operation="unrelated")
    assert worth_llm_fallback("how's the weather on the ring road", patch) is False
    assert worth_llm_fallback("can you look for something with parking maybe", patch) is False
    assert would_have_been_fallback("how's the weather on the ring road", patch) is False
    assert would_have_been_fallback("can you look for something with parking maybe", patch) is True
