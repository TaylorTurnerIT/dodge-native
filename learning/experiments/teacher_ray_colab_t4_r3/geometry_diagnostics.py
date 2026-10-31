"""Report only admitted player scalars and collection phase on bad geometry."""


def geometry_failure(error):
    rows = getattr(error, "player_geometry_rows", None)
    if rows is None:
        return None
    return [dict(row, phase=getattr(error, "phase", "unspecified")) for row in rows]
