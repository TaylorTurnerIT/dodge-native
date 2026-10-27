"""Unchanged frozen death_fields definition; no runtime imports."""
from expanded_eval import DEATH_CAUSES as ALL_CAUSES
DEATH_CAUSES=ALL_CAUSES[:-1]
DEATH_CAUSE_UNAVAILABLE="unavailable"
from contracts import need as require

def death_fields(info: dict, terminated: bool, truncated: bool) -> dict:
    """Diagnostic death fields for one finished episode; never a model input.

    `death_cause` is the first lethal contact in legacy source order on the
    fatal frame. `death_observed_lethal_contacts` counts every lethal contact the
    legacy loop processed that frame (first included); extras are observations,
    not alternate proven causes. Live and cap-truncated episodes carry None.
    """
    if "death_cause" not in info:
        return {"death_cause": DEATH_CAUSE_UNAVAILABLE if terminated else None,
                "fatal_gameplay_frame": None, "death_observed_lethal_contacts": None}
    cause, frame, contacts = (info["death_cause"], info["fatal_gameplay_frame"],
                              info["death_observed_lethal_contacts"])
    if terminated:
        require(cause in DEATH_CAUSES and type(frame) is int
                and frame == info["gameplay_frames"]
                and isinstance(contacts, dict) and set(contacts) == set(DEATH_CAUSES)
                and all(type(v) is int and v >= 0 for v in contacts.values())
                and (cause == "unknown" or contacts[cause] >= 1),
                "Development death telemetry differs from terminated episode")
    else:
        require(truncated and cause is None and frame is None and contacts is None,
                "Development death telemetry present on a non-terminated episode")
    return {"death_cause": cause, "fatal_gameplay_frame": frame,
            "death_observed_lethal_contacts": contacts}
