#!/usr/bin/env python3
"""
Anonymize DICOM directory

author : Evi Vanoost <vanooste@rcbi.rochester.edu>
license : MIT

See README.md

"""

import json
import os
import pathlib
import random
import subprocess
import sys
from datetime import datetime, timedelta
from shlex import split

import pydicom
from pydicom.errors import InvalidDicomError

from dcm_functions import hashtext, time2str, date2str, datetime2str, str2time, str2date, str2datetime, \
    regenuid

if len(sys.argv) < 2:
    print("Must pass path to the directory to be anonymized")
    exit(1)

INCOMING_DIR = sys.argv[1]
OUTGOING_DIR = "/out"
REPORT_DIR = "/reports"

app_path = pathlib.Path(__file__).parent.absolute()
config_path = os.path.join(app_path, "config")

try:
    with open(os.path.join(config_path, 'studies.json'), 'r') as json_file:
        studies = json.load(json_file)

    with open(os.path.join(config_path, 'stations.json'), 'r') as json_file:
        stations = json.load(json_file)
except FileNotFoundError:
    print("No studies.json and stations.json found")
    exit(1)

# You should change this seed for your environment
try:
    with open(os.path.join(config_path, 'random.txt'), 'r') as file:
        RANDOM_UUID = file.read().replace('\n', '')
except FileNotFoundError:
    RANDOM_UUID = "be76acfcfdb04e64ba7525dbf745fe5f"

ORIGINAL_UUID = RANDOM_UUID
NOW = datetime.now()
# We don't want to stat the same files over, so make PATH COUNTER global
PATHCOUNTER = 0

filenames = []
# r=root, d=directories, f = files
for r, d, f in os.walk(INCOMING_DIR):
    for file in f:
        filenames.append(os.path.join(r, file))

if not filenames:
    print("No files found to be processed")
    exit(0)

OUTGOING_DIR = os.path.join(OUTGOING_DIR, datetime.strftime(NOW, "%Y%m%d-%H%M%S-%f"))
try:
    os.mkdir(OUTGOING_DIR)
except OSError:
    print("Creation of the output directory %s failed" % OUTGOING_DIR)
    exit(1)

processed = []
StudyName = "unknown"

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
        StationName = str(dataset.data_element('StationName').value).upper()
        StationInfo = stations.get(StationName, stations.get("default"))
    except KeyError:
        print("Error: " + filename + " is missing StationName")
        continue

    # Find Study Name, each Study may have separate de-identification methods
    try:
        StudyName = str(dataset.data_element(StationInfo['TagForStudy']).value).upper()
        if StationInfo['StudySplit']:
            x = StudyName.split(StationInfo['StudySplit'])
            StudyName = x[StationInfo.get('StudySplitIndex', 0)]
        StudyInfo = studies.get(StudyName, studies.get("Supplement142"))
    except KeyError:
        print("Error: " + filename + " is missing " + StationInfo['TagForStudy'])
        continue

    print("Processing: " + filename)
    print("Study: " + StudyName)

    SAVED_TAGS = {}
    # If the Remove Private Tags flag is set
    if StudyInfo['RemovePrivateTags']:
        print("Removing Private Tags")
        # Preserve certain tags
        if StudyInfo['SavePrivateTags']:
            for tag in StudyInfo['SavePrivateTags']:
                print(f"Preserving Private Tag: {tag}")
                SAVED_TAGS[tag] = dataset[tag]

        dataset.remove_private_tags()

        # Restore private tags
        for tag in StudyInfo['SavePrivateTags']:
            dataset[tag] = SAVED_TAGS[tag]

    TagDefs = StudyInfo['AnonymizeTag']
    VRDefs = StudyInfo['AnonymizeVR']
    RANDOM_UUID = StudyInfo.get('RandomSeed', ORIGINAL_UUID)

    def get_vr_action(vr):
        if vr in VRDefs:
            return VRDefs[vr].get('action', 'delete')
        # The default action is to keep the value
        return 'keep'

    def get_tag_action(tag):
        if tag in TagDefs:
            return TagDefs[tag].get('action', 'delete')
        # The default action is to keep the value
        return 'keep'

    for de in dataset.iterall():
        try:
            tag = pydicom.datadict.get_entry(de.tag)[4]
        except KeyError:
            print("Invalid DICOM Tag")
            continue

        # We can take action on the entire VR
        action = get_vr_action(de.VR)
        # The tag action overrides VR
        action = get_tag_action(tag)

        if action == "keep":
            continue

        print(f"{tag} -> {action}")
        if action == "delete":
            try:
                delattr(dataset, tag)
            except AttributeError:
                print("Parent Already Deleted: " + tag)
            continue

        if action == "clear":
            de.value = None
            continue

        if action == "hash":
            salt = TagDefs[tag].get('salt', RANDOM_UUID)
            de.value = hashtext(dataset.data_element(tag).value, salt)
            continue

        if action == "value":
            value = TagDefs[tag].get('value', None)
            if value == "TMnow":
                de.value = time2str(NOW)
            elif value == "DAnow":
                de.value = date2str(NOW)
            elif value == "DTnow":
                de.value = datetime2str(NOW)
            else:
                de.value = value
            continue

        if action == "offset":
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
                continue

            if de.VR == "DA":
                time = str2date(de.value)
                # List = h, m, s, ms
                time = time + timedelta(seconds=amount)
                de.value = date2str(time)
                continue

            if de.VR == "DT":
                time = str2datetime(de.value)
                # List = h, m, s, ms
                time = time + timedelta(seconds=amount)
                de.value = datetime2str(time)
                continue

            print("Offsetting a " + de.VR + " Type Not Implemented")
            continue

        if action == "regen":
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
            continue

        print(f"Tag Action Not Implemented: {action}")

    # We need to always regen some File MetaData that is identifiable
    dataset.file_meta.MediaStorageSOPInstanceUID = regenuid(dataset.file_meta.MediaStorageSOPInstanceUID, RANDOM_UUID)

    newfilename = os.path.join(OUTGOING_DIR, dataset.file_meta.MediaStorageSOPInstanceUID + '.dcm')
    dataset.save_as(newfilename)
    processed.append(newfilename)
    # Delete the original file (dangerous)
    # os.remove(filename)

# Call DCMSend to send the DICOM to our storage
target_host = os.environ.get("RECEIVER_IP", "dcmsorter 104")
target_aet_source = os.environ.get("AETITLE", "ANONYMIZER")
target_aet_target = os.environ.get("RECEIVER_AET", "STORESCP")

dcmsend_status_file = os.path.join(REPORT_DIR, f"report-{StudyName}" + datetime.strftime(NOW, "%Y%m%d-%H%M%S-%f"))
command = f"dcmsend {target_host} +sd {OUTGOING_DIR} +r -aet {target_aet_source} -aec {target_aet_target}" \
          f" -nuc +sp '*.dcm' -to 60 +crf {dcmsend_status_file}"
process = subprocess.run(split(command))

if process.returncode:
    print(f"Error occurred calling dcmsend: {process.returncode}")
    exit(process.returncode)

for file_path in processed:
    try:
        os.unlink(file_path)
    except Exception as e:
        print('Failed to delete %s. Reason: %s' % (file_path, e))
        exit(1)
