#!/usr/bin/env python3
"""
Anonymize DICOM directory

author : Evi Vanoost <vanooste@rcbi.rochester.edu>
license : MIT

See README.md

"""
import datetime
import hashlib
import json
import os
import pathlib
import random
import subprocess
import sys
from shlex import split

import pydicom
from pydicom.data import get_testdata_files
from pydicom.errors import InvalidDicomError
from pydicom.uid import generate_uid
from datetime import datetime, timedelta

# Getting the current work directory (cwd)
if len(sys.argv) < 2:
    print("Must pass path to the directory to be anonymized")
    exit(1)

INCOMING_DIR = sys.argv[1]
OUTGOING_DIR = "/home/hermes/anonymizer/outgoing/"
REPORT_DIR = OUTGOING_DIR

filenames = []
# r=root, d=directories, f = files
for r, d, f in os.walk(INCOMING_DIR):
    for file in f:
        filenames.append(os.path.join(r, file))

if not filenames:
    exit()

mypath = pathlib.Path(__file__).parent.absolute()

try:
    with open(os.path.join(mypath, 'studies.json'), 'r') as json_file:
        studies = json.load(json_file)

    with open(os.path.join(mypath, 'stations.json'), 'r') as json_file:
        stations = json.load(json_file)
except FileNotFoundError:
    print("No studies.json and stations.json found")
    exit(1)

# You should change this seed for your environment
try:
    with open(os.path.join(mypath, 'random.txt'), 'r') as file:
        RANDOM_UUID = file.read().replace('\n', '')
except FileNotFoundError:
    RANDOM_UUID = "be76acfcfdb04e64ba7525dbf745fe5f"

ORIGINAL_UUID = RANDOM_UUID
NOW = datetime.now()
# We don't want to stat the same files over, so make PATH COUNTER global
PATHCOUNTER = 0
DEBUG = True

OUTGOING_DIR = os.path.join(OUTGOING_DIR, datetime.strftime(NOW, "%Y%m%d-%H%M%S-%f"))
try:
    os.mkdir(OUTGOING_DIR)
except OSError:
    print("Creation of the output directory %s failed" % OUTGOING_DIR)


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


processed = []
for filename in filenames:
    # Make sure we have a valid DICOM
    try:
        dataset = pydicom.filereader.dcmread(filename)
    except InvalidDicomError:
        print("Error: " + filename +
              " is missing DICOM File Meta Information header or the 'DICM' prefix is missing from the header.")
        continue

    # Find Station Name, each Station has different methods of encoding Study Names
    try:
        StationName = dataset.data_element('StationName').value
        StationInfo = stations.get(StationName, stations.get("default"))
    except KeyError:
        print("Error: " + filename + " is missing StationName")
        continue

    # Find Study Name, each Study may have separate de-identification methods
    try:
        StudyName = dataset.data_element(StationInfo['TagForStudy']).value
        if StationInfo['Split']:
            x = StudyName.split(StationInfo['Split'])
            StudyName = x[StationInfo.get('SplitIndex', 0)]
        StudyInfo = studies.get(StudyName, studies.get("Supplement142"))
    except KeyError:
        print("Error: " + filename + " is missing " + StationInfo['TagForStudy'])
        continue

    if DEBUG:
        print("Processing: " + filename)
        print("Study: " + StudyName)

    SAVED_TAGS = {}
    if StudyInfo['RemovePrivateTags']:
        if StudyInfo['SavePrivateTags']:
            for tag in StudyInfo['SavePrivateTags']:
                SAVED_TAGS[tag] = dataset[tag]

        if DEBUG:
            print("Removing Private Tags")
        dataset.remove_private_tags()
        for tag in StudyInfo['SavePrivateTags']:
            dataset[tag] = SAVED_TAGS[tag]

    TagDefs = StudyInfo['AnonymizeTag']
    VRDefs = StudyInfo['AnonymizeVR']
    RANDOM_UUID = StudyInfo.get('RandomSeed', ORIGINAL_UUID)
    for de in dataset.iterall():
        try:
            tag = pydicom.datadict.get_entry(de.tag)[4]
        except KeyError:
            if DEBUG:
                print("Invalid DICOM Tag")
            continue

        if tag in TagDefs or de.VR in VRDefs:
            if tag in TagDefs:
                action = TagDefs[tag].get('action', 'delete')
            else:
                action = VRDefs[de.VR].get('action', 'delete')
            if DEBUG:
                print("   " + tag + " -> " + action)

            if action == "delete":
                try:
                    delattr(dataset, tag)
                except AttributeError:
                    if DEBUG:
                        print("Parent Deleted: " + tag)
            elif action == "clear":
                de.value = None
            elif action == "hash":
                salt = TagDefs[tag].get('salt', RANDOM_UUID)
                de.value = hashtext(dataset.data_element(tag).value, salt)
            elif action == "value":
                value = TagDefs[tag].get('value', None)
                if value == "TMnow":
                    de.value = time2str(NOW)
                elif value == "DAnow":
                    de.value = date2str(NOW)
                elif value == "DTnow":
                    de.value = datetime2str(NOW)
                else:
                    de.value = value
            elif action == "offset":
                amount = TagDefs[tag].get('delta', None)
                if not amount:
                    seed = TagDefs[tag].get('seed', RANDOM_UUID)
                    random.seed(seed + de.value)
                    # 100 year variation should be sufficient
                    amount = random.randint(-1576800000, 1576800000)
                if de.VR == "TM":
                    time = str2time(de.value)
                    # List = h, m, s, ms
                    time = time + timedelta(seconds=amount)
                    de.value = time2str(time)
                elif de.VR == "DA":
                    time = str2date(de.value)
                    # List = h, m, s, ms
                    time = time + timedelta(seconds=amount)
                    de.value = date2str(time)
                elif de.VR == "DT":
                    time = str2datetime(de.value)
                    # List = h, m, s, ms
                    time = time + timedelta(seconds=amount)
                    de.value = datetime2str(time)
                else:
                    print("Offsetting a " + de.VR + " Type Not Implemented")
            elif action == "regen":
                seed = TagDefs[tag].get('seed', RANDOM_UUID)
                random.seed(seed + de.value)
                # 100 year variation should be sufficient
                amount = random.randint(-1576800000, 1576800000)
                time = NOW + timedelta(seconds=amount)
                if de.VR == "TM":
                    de.value = time2str(time)
                elif de.VR == "DA":
                    de.value = date2str(time)
                elif de.VR == "DT":
                    de.value = datetime2str(time)
                else:
                    de.value = regenuid(de.value, seed)
            elif action == "keep":
                pass
            else:
                print("Tag Action Not Implemented")

    # We need to regen some File MetaData that is identifiable
    dataset.file_meta.MediaStorageSOPInstanceUID = regenuid(dataset.file_meta.MediaStorageSOPInstanceUID, RANDOM_UUID)

    newfilename = os.path.join(OUTGOING_DIR, dataset.file_meta.MediaStorageSOPInstanceUID + '.dcm')
    dataset.save_as(newfilename)
    processed.append(newfilename)
    os.remove(filename)

# Call DCMSend to send the DICOM to our storage
target_ip = "127.0.0.1"
target_port = 104
target_aet_source = "ANONYMIZER"
target_aet_target = "STORESCP"

dcmsend_status_file = os.path.join(REPORT_DIR, "report-" + datetime.strftime(NOW, "%Y%m%d-%H%M%S-%f"))
command = f"""dcmsend {target_ip} {target_port} +sd {OUTGOING_DIR} +r -aet {target_aet_source} -aec {target_aet_target} -nuc +sp '*.dcm' -to 60 +crf {dcmsend_status_file}"""
process = subprocess.run(split(command))

if process.returncode:
    exit(process.returncode)

for file_path in processed:
    try:
        os.unlink(file_path)
    except Exception as e:
        print('Failed to delete %s. Reason: %s' % (file_path, e))
        exit(1)
