"""Admitted player bounds from native fixed-point updates, not a float tolerance.

update_freeze yields 0.4<=freeze_rate<=1. update_size adds floor(0.5*rate)
when size<4, without clamping until the next raw frame. Thus size raw is in
[2*65536, 4*65536-1+32768]. Center clamp is independent of size.
"""

import math

ONE_RAW = 65536
MIN_PLAYER_SIZE = 2.0
MAX_PLAYER_SIZE_RAW = 4*ONE_RAW-1+ONE_RAW//2
MAX_PLAYER_SIZE = MAX_PLAYER_SIZE_RAW/ONE_RAW


def scalar_for_receipt(value):
    value=float(value)
    return value if math.isfinite(value) else ('nan' if math.isnan(value) else '+inf' if value>0 else '-inf')


class AdmittedPlayerGeometryError(ValueError):
    def __init__(self,rows):
        super().__init__('Player center/size outside source-proven admitted physics range')
        self.player_geometry_rows=rows
        self.phase='unspecified'


def player_row(row,x,y,size):
    return dict(row=int(row),player_x=scalar_for_receipt(x),player_y=scalar_for_receipt(y),
                player_size=scalar_for_receipt(size))


def validate_player(row,x,y,size):
    if not (all(math.isfinite(v) for v in (x,y,size)) and 2<=x<=125 and 2<=y<=125
            and MIN_PLAYER_SIZE<=size<=MAX_PLAYER_SIZE):
        raise AdmittedPlayerGeometryError([player_row(row,x,y,size)])
