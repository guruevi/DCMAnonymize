from datetime import datetime
import hashlib
from pydicom.uid import generate_uid


def hashtext(text, saltstr):
    return hashlib.sha256(saltstr.encode() + text.encode()).hexdigest()


def regenuid(element, saltstr):
    return generate_uid(entropy_srcs=[element, saltstr])


def str2time(ts):
    ts = str(ts)
    length = len(ts)
    if 7 < length < 14:
        # Typical DICOM format allows for HHMMSS.FFFFFF to HHMMSS.F
        tf = '%H%M%S.%f'
    elif 4 < length < 7:
        # Between 5 and 6 digits (although %h is not valid, converting from int may cause artifacts)
        # DICOM format without the fractional seconds
        tf = '%H%M%S'
    elif 2 < length < 5:
        # Between 3 and 4 digits
        # DICOM standard seems to indicate in the DT VR that less precision (null components) are allowed
        tf = '%H%M'
    elif 0 < length < 3:
        # 1 and 2 digits are allowed
        tf = '%H'
    else:
        # Invalid format
        return None

    return datetime.strptime(ts, tf)


def time2str(obj):
    """
    :type obj Date
    """
    return obj.strftime("%H%M%S.%f")


def str2date(ds):
    ds = str(ds).strip()
    length = len(ds)
    if length == 8:
        # Typical DICOM format is YYYYMMDD - 8 bytes fixed
        tf = '%Y%m%d'
    else:
        # Invalid format
        return None

    return datetime.strptime(ds, tf)


def date2str(obj):
    """
    :type obj: Date
    """
    return obj.strftime("%Y%m%d")


def str2datetime(dts):
    dts = str(dts).strip()
    length = len(dts)
    # This is the DICOM format
    # YYYYMMDDHHMMSS.FFFFFF&ZZXX where everything beyond YYYY is optional, however the &ZZXX may be specified regardless
    # test for +/-
    if '+' in dts or '-' in dts:
        if length == 9:
            tf = "%Y%z"
        if length == 11:
            tf = "%Y%m%z"
        if length == 13:
            tf = "%Y%m%d%z"
        if length == 15:
            tf = "%Y%m%d%H%z"
        if length == 17:
            tf = "%Y%m%d%H%M%z"
        if length == 19:
            tf = "%Y%m%d%H%M%S%z"
        if 20 < length < 27:
            tf = "%Y%m%d%H%M%S.%f%z"
    else:
        if length == 4:
            tf = "%Y"
        if length == 6:
            tf = "%Y%m"
        if length == 8:
            tf = "%Y%m%d"
        if length == 10:
            tf = "%Y%m%d%H"
        if length == 12:
            tf = "%Y%m%d%H%M"
        if length == 14:
            tf = "%Y%m%d%H%M%S"
        if 15 < length < 22:
            tf = "%Y%m%d%H%M%S.%f"

    return datetime.strptime(dts, tf)


def datetime2str(obj):
    return obj.strftime("%Y%m%d%H%M%S.%f%z")
