#!/usr/bin/env python3
"""
Anonymize DICOM directory

author : Evi Vanoost <vanooste@rcbi.rochester.edu>
license : MIT

See README.md

"""

import json
import os
from pathlib import Path
import random
import sys
from datetime import datetime, timedelta
import pydicom
from pydicom.datadict import dictionary_VR
from pydicom.errors import InvalidDicomError
from dcm_functions import hashtext, time2str, date2str, datetime2str, str2time, str2date, str2datetime, \
    regenuid
import subprocess

# Define where our incoming and outgoing data are going to live
# I am using environment variables here to be able to modify using Docker
# The peculiar name picked is because we want to also use this in conjunction with Mercure DICOM router
INCOMING_DIR = os.environ.get("MERCURE_IN_DIR", "/in")
OUTGOING_DIR = os.environ.get("MERCURE_OUT_DIR", "/out")
RECEIVER_IP = os.environ.get("RECEIVER_IP", False)

# Whether we want Mercure-specific things such as task.json to load. If not, set to False
DO_MERCURE_STUFF = int(os.environ.get("DO_MERCURE_STUFF", True))

# Find out where "we" live at runtime. This increases portability.
app_path = Path(__file__).parent.absolute()
# config should be a directory in the current app directory
config_path = os.path.join(app_path, "config")

# Check whether our incoming and outgoing paths actually exist. A common mistake if using Docker.
# Reason we're not just blindly going forward, is because we could create the directories in locations we don't want
if not Path(INCOMING_DIR).exists() or not Path(OUTGOING_DIR).exists():
    print("IN/OUT paths do not exist")
    sys.exit(1)

# Check and see whether we have a studies and stations configuration
# studies.json contains the study de-identification configuration
# stations.json contains the configuration to decode the study name from a particular scanner
# Every MRI system (Philips, GE, Siemens) and sometimes even institutions have their own 'way' of doing things
# random.txt contains a random seed that initializes the randomizer that we should keep secret
# task.json is Mercure specific.
try:
    with open(os.path.join(config_path, 'studies.json'), 'r') as json_file:
        studies: dict = json.load(json_file)

    with open(os.path.join(config_path, 'stations.json'), 'r') as json_file:
        stations: dict = json.load(json_file)

    with open(os.path.join(config_path, 'random.txt'), 'r') as file:
        RANDOM_UUID: str = file.read().replace('\n', '')

    if DO_MERCURE_STUFF:
        with open(Path(INCOMING_DIR) / "task.json", "r") as json_file:
            task = json.load(json_file)
except FileNotFoundError:
    print("No studies.json, stations.json, random.txt and/or task.json found")
    sys.exit(1)

# Mercure can override our standard configuration from Mercure
if DO_MERCURE_STUFF and task.get("process", False):
    settings = task["process"].get("settings", False)
    if settings:
        # Here we override (merge) our settings with Mercure's settings
        RANDOM_UUID = settings.get("RANDOM_UUID", RANDOM_UUID)
        studies.update(settings.get("studies", {}))
        stations.update(settings.get("stations", {}))

# Keep track of when we start
NOW = datetime.now()

# Empty series
series = {}

# Scan the incoming directory for files
for root, dir, files in os.walk(INCOMING_DIR):
    for entry in files:
        # Filter out DICOM files
        if entry.endswith((".dcm", ".ima", ".DCM", ".IMA")):
            # Get the Series UID from the file name, this is based on the DCMTK storescp naming convention
            seriesString = entry.split("#", 1)[0]
            # If this is the first image of the series, create new file list for the series
            if seriesString not in series.keys():
                series[seriesString] = []
            # Add the current file to the file list
            series[seriesString].append(os.path.join(root, entry))

# Nothing to be done
if not series:
    print("No files found to be processed")
    sys.exit(0)


# Helper function to get key types of a specific action type from the study configuration
def get_key_types(study_info, action_type):
    # This will be our output
    list_of_keys = []

    for item in study_info['AnonymizeTag'].items():
        if item[1]['action'] == action_type:
            list_of_keys.append(item[0])

    return list_of_keys


# Helper function to get the default action on a VR (AnonymizeVR in JSON)
def get_vr_action(this_vr, study_info_vr):
    # If this DICOM tags' VR is in the studies list of VRs
    if this_vr in study_info_vr:
        # If no action is specified, delete
        return study_info_vr[this_vr].get('action', 'delete')
    # The default action is to keep the value
    return 'keep'


# Helper function to get the action on a specific tag (AnonymizeTag in JSON)
def get_tag_action(this_tag, study_info_tag):
    # If this DICOM tag is listed in the AnonymizeTag
    if this_tag in study_info_tag:
        return study_info_tag[this_tag].get('action', 'delete')
    # The default action is to keep the value
    return 'keep'


def anonymize_dicom_file(this_dataset, global_random_uuid, study_info):
    # Keep track of any private tags to save
    saved_private_tags = {}

    # If the Remove Private Tags flag is set
    if study_info.get('RemovePrivateTags', True):
        print("Removing Private Tags")
        # Preserve certain tags
        for tag in study_info.get('SavePrivateTags', []):
            print(f"Preserving Private Tag: {tag}")
            try:
                saved_private_tags[tag] = this_dataset[tag]
            except KeyError:
                print(f"Private Tag does not exist: {tag}")

        this_dataset.remove_private_tags()

        # Restore private tags
        for tag in saved_private_tags:
            this_dataset[tag] = saved_private_tags[tag]

    # See if our Study overrides our default random seed
    study_random_uuid = study_info.get('RandomSeed', global_random_uuid)

    # Action = value
    # Values should always be set
    tags_to_set = get_key_types(study_info, 'value')
    for tag in tags_to_set:
        value = study_info['AnonymizeTag'][tag].get('value', None)
        if value == "TMnow":
            value = time2str(NOW)
        elif value == "DAnow":
            value = date2str(NOW)
        elif value == "DTnow":
            value = datetime2str(NOW)

        # This apparently overwrites existing tags
        this_dataset.add_new(tag, dictionary_VR(tag), value)

    # pydicom dataset is a dict which contains DataElement instances
    for this_data_element in this_dataset.iterall():
        # Check whether this data_element is a valid DICOM tag (is in pydicom data dictionary)
        try:
            tag = pydicom.datadict.get_entry(this_data_element.tag)[4]
        except KeyError:
            print(f"{this_data_element.tag} -> keep (Invalid Tag)")
            continue

        # Get the action for the entire VR
        action = get_vr_action(this_data_element.VR, study_info['AnonymizeVR'])
        tag_action = get_tag_action(tag, study_info['AnonymizeTag'])
        # The tag action overrides VR
        if tag_action:
            action = tag_action

        print(f"{tag} -> {action}")

        # Define each action
        # We need to keep the current tag as-is
        if action == "keep":
            # Do nothing
            continue

        # Delete the current tag
        if action == "delete":
            try:
                delattr(this_dataset, tag)
            except AttributeError:
                # It is possible that nested tags may be deleted
                print(f"{tag} no longer exists - parent deleted?")
            continue

        # Clear (keeps the tag, but sets the tag value to nothing)
        if action == "clear":
            try:
                this_data_element.value = None
            except KeyError:
                print(f"{tag} no longer exists - parent deleted?")
            continue

        # Hash the value of the tag
        if action == "hash":
            salt = study_info['AnonymizeTag'][tag].get('salt', study_random_uuid)
            try:
                this_data_element.value = hashtext(this_dataset.data_element(tag).value, salt)
            except KeyError:
                print(f"{tag} no longer exists - parent deleted?")
            continue

        # Offset the integer value within the tag by a set amount
        if action == "offset":
            amount = study_info['AnonymizeTag'][tag].get('delta', None)
            if not amount:
                seed = study_info['AnonymizeTag'][tag].get('seed', study_random_uuid)
                # Do not use the value for offsetting as we want everything to be offset by the same value
                random.seed(seed)
                # 100 year variation should be sufficient
                amount = random.randint(-1576800000, 1576800000)

            # AS: TODO (Age String nnnD, nnnW, nnnM, nnnY)
            # DS: TODO (Decimal String "0"-"9", "+", "-", "E", "e", ".")
            # FL: TODO (Floating Point Single)
            # FD: TODO (Floating Point Double)
            # IS: TODO (Integer String)
            # SL: TODO (Signed Long)
            # SS: TODO (Signed Short)
            # UL: TODO (Unsigned Long)
            # US: TODO (Unsigned Short)

            if this_data_element.VR == "TM":
                time = str2time(this_data_element.value)
                # List = h, m, s, ms
                time = time + timedelta(seconds=amount)
                this_data_element.value = time2str(time)
                continue

            if this_data_element.VR == "DA":
                time = str2date(this_data_element.value)
                # List = h, m, s, ms
                time = time + timedelta(seconds=amount)
                this_data_element.value = date2str(time)
                continue

            if this_data_element.VR == "DT":
                time = str2datetime(this_data_element.value)
                # List = h, m, s, ms
                time = time + timedelta(seconds=amount)
                this_data_element.value = datetime2str(time)
                continue

            print(f"{tag} -> Changed from {action} to keep (Error)")
            print(f"ERROR: Offsetting a {this_data_element.VR} Not Implemented")
            continue

        if action == "regen":
            seed = study_info['AnonymizeTag'][tag].get('seed', study_random_uuid)
            # Use the value as the seed as we are simply regenerating, not offsetting
            random.seed(seed + this_data_element.value)
            # 100 year variation should be sufficient
            amount = random.randint(-1576800000, 1576800000)
            time = NOW + timedelta(seconds=amount)
            if this_data_element.VR == "TM":
                this_data_element.value = time2str(time)
            elif this_data_element.VR == "DA":
                this_data_element.value = date2str(time)
            elif this_data_element.VR == "DT":
                this_data_element.value = datetime2str(time)
            else:
                this_data_element.value = regenuid(this_data_element.value, seed)
            continue

        print(f"{tag} -> Changed from {action} to keep (Error)")
        print(f"ERROR: Action Not Implemented: {action}")

    # We need to always regen some File MetaData that is identifiable
    this_dataset.file_meta.MediaStorageSOPInstanceUID = regenuid(this_dataset.file_meta.MediaStorageSOPInstanceUID,
                                                                 study_random_uuid)
    # By convention, DICOM files provided by
    # mercure have the format [series_UID]#[file_UID].dcm
    series_instance_uid = str(this_dataset.data_element("SeriesInstanceUID").value)
    file_uid = this_dataset.file_meta.MediaStorageSOPInstanceUID
    new_filename = os.path.join(OUTGOING_DIR, f"{series_instance_uid}#{file_uid}.dcm")
    this_dataset.save_as(new_filename)


# Loop through the series, we name it old_series_uid because we need to deidentify uid
for old_series_uid in series:
    # Loop through each file in the filename
    for filename in series[old_series_uid]:
        # Make sure the file we have is a valid DICOM. pydicom bubbles up an exception
        try:
            dataset = pydicom.filereader.dcmread(filename)
        except InvalidDicomError:
            print("Error: " + filename +
                  " is missing DICOM File Meta Information header or the 'DICM' prefix is missing from the header.")
            continue

        # Find StationName in the DICOM file
        # Each Station may have different methods of encoding Study Names
        try:
            StationName = str(dataset.data_element('StationName').value).upper()
            StationInfo = stations.get(StationName, stations.get("default"))
        except KeyError:
            print("Error: " + filename + " is missing StationName - Already anonymized?")
            continue

        # Find Study Name, each Study may have separate de-identification methods
        try:
            StudyName = str(dataset.data_element(StationInfo['TagForStudy']).value).upper()
            if StationInfo.get('StudySplit', False):
                StudyNameList = StudyName.split(StationInfo['StudySplit'])
                StudyName = StudyNameList[StationInfo.get('StudySplitIndex', 0)]
            StudyInfo = studies.get(StudyName, studies.get("Supplement142"))
        except KeyError:
            print("Error: " + filename + " is missing " + StationInfo['TagForStudy'])
            continue

        # Filter out Phoenix ZIP Reports - Siemens PDF with all sorts of data
        try:
            SeriesDescription = str(dataset.data_element("SeriesDescription").value).upper()
            if SeriesDescription == "PHOENIXZIPREPORT":
                print("Series is a Phoenix ZIP Report and cannot be anonymized")
                continue
        except KeyError:
            print("No SeriesDescription")

        print("Processing: " + filename)
        print("Study: " + StudyName)

        anonymize_dicom_file(dataset, RANDOM_UUID, StudyInfo)

# If we have a destination, send the files
if RECEIVER_IP:
    # Call dcmsend to send the series to the destination
    command = f"dcmsend -v -aet ANONYMIZER {RECEIVER_IP} --scan-directories --recurse {OUTGOING_DIR}"
    # Execute the command and print the error and output
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    output, error = process.communicate()
    print(output.decode())
    print(error.decode())

