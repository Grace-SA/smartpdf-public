"""Pure, opt-in proof of the current PPT/LibreOffice canvas quantization.

Not a visual acceptance rule. No coordinate transform or tolerance is applied to
pixels, glyphs or ROIs. Callers must parse original PDF numbers without floats.
Output serialization is narrowly the observed runtime's 12-place half-up, not
a claim that all LibreOffice versions use that format.
LO: presentationfragmenthandler.cxx sldSz -> drawingmltypes.cxx GetSize2D /
GetCoordinate -> include/o3tl/unit_conversion.hxx MulDiv (positive half-up).
"""
import math
from decimal import Decimal, InvalidOperation, localcontext, Context
from fractions import Fraction

DPIS=(144,216,288,432)
HALF_SERIAL_UNIT=Decimal('0.0000000000005')
SERIAL_UNIT=Decimal('0.000000000001')

class Refused(ValueError):
    pass

def _decimal(value):
    if type(value) not in (str,int,Decimal):raise Refused('raw_decimal_required')
    try:result=Decimal(value)
    except (InvalidOperation,ValueError):raise Refused('invalid_decimal') from None
    if not result.is_finite() or result.copy_abs()>Decimal('1000000'):
        raise Refused('invalid_decimal')
    return result

def _metadata(value):
    try:
        media=tuple(_decimal(v) for v in value['media_box'])
        crop=tuple(_decimal(v) for v in value['crop_box'])
        unit=_decimal(value.get('user_unit',1))
        rotation=_decimal(value.get('rotation',0))
    except (KeyError,TypeError):raise Refused('invalid_metadata') from None
    if len(media)!=4 or len(crop)!=4:raise Refused('invalid_boxes')
    if media!=crop or media[:2]!=(Decimal(0),Decimal(0)):
        raise Refused('unsupported_origin_or_crop')
    if media[2]<=0 or media[3]<=0 or unit!=1 or rotation!=0:
        raise Refused('unsupported_page')
    return media[2:]

def _grid(size,dpi):
    return tuple(math.ceil(Fraction(v)*dpi/72) for v in size)

def _quantized_points(emu):
    with localcontext(Context(prec=80)):
        return Decimal((emu+180)//360)*360/12700

def prove(emu_size,source_size,source_metadata,previous_metadata,candidate_metadata,source_boxes):
    """Prove one zero-origin canvas model, or raise Refused.

    source_size is the actual PDFium size used by the producer's Pt(float)
    conversion. Raw metadata coordinates are decimal strings/Decimal/integers.
    This proof does not assert that a renderer or any changed text is correct.
    """
    if len(emu_size)!=2 or any(type(v) is not int or not 0<v<=2147483647 for v in emu_size):
        raise Refused('invalid_emu')
    if len(source_size)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in source_size):
        raise Refused('invalid_source_size')
    if tuple(emu_size)!=tuple(int(v*12700) for v in source_size):
        raise Refused('source_emu_contract')
    source=_metadata(source_metadata);previous=_metadata(previous_metadata);candidate=_metadata(candidate_metadata)
    if previous!=candidate:raise Refused('output_dimensions_differ')
    # Require the raw source to agree with PDFium's float32 representation.
    # This is representation validation, not an additional dimension tolerance.
    import struct
    f32=lambda v: struct.unpack('f',struct.pack('f',float(v)))[0]
    if any(f32(raw)!=float(observed) for raw,observed in zip(source,source_size)):
        raise Refused('source_parser_disagreement')
    expected=tuple(_quantized_points(v) for v in emu_size)
    exact=tuple(Fraction(((v+180)//360)*360,12700) for v in emu_size)
    # Integer half-up at 12 places, with exact rational comparisons. Decimal
    # context (including caller precision/traps) cannot hide a boundary.
    scale=10**12
    serialized=tuple(Fraction((2*v.numerator*scale+v.denominator)//(2*v.denominator),scale) for v in exact)
    if any(Fraction(v)!=s or abs(Fraction(v)-e)>Fraction(1,2*scale) for v,e,s in zip(candidate,exact,serialized)):
        raise Refused('output_quantization_mismatch')
    observed=tuple(Decimal.from_float(float(v)) for v in source_size)
    grids={}
    for dpi in DPIS:
        grid=_grid(source,dpi)
        if any(_grid(size,dpi)!=grid for size in (observed,previous,candidate)):
            raise Refused('pixel_grid_mismatch')
        grids[str(dpi)]=list(grid)
    if not 0<len(source_boxes)<=64:raise Refused('invalid_roi_count')
    for box in source_boxes:
        if len(box)!=4 or any(type(v) not in (int,float,Decimal) or isinstance(v,bool) for v in box):
            raise Refused('invalid_source_box')
        values=tuple(Decimal.from_float(v) if type(v) is float else Decimal(v) for v in box)
        if not all(v.is_finite() for v in values):raise Refused('invalid_source_box')
        l,b,r,t=values
        if any(not (0<=l<r<=w and 0<=b<t<=h) for w,h in (source,observed,candidate)):
            raise Refused('source_box_outside_page')
    return {'model':'ppt-emu-to-observed-lo-mm100-12dp-half-up-v1','emu_size':list(emu_size),
            'source_size':[str(v) for v in source], 'expected_output_size':[str(v) for v in expected],
            'serialized_output_size':[str(v) for v in candidate], 'pixel_grids':grids,
            'visual_acceptance':False}
