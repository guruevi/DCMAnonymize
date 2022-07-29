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

INCOMING_DIR = os.environ.get("MERCURE_IN_DIR", "/in")
OUTGOING_DIR = os.environ.get("MERCURE_OUT_DIR", "/out")

app_path = Path(__file__).parent.absolute()
config_path = os.path.join(app_path, "config")

if not Path(INCOMING_DIR).exists() or not Path(OUTGOING_DIR).exists():
    print("IN/OUT paths do not exist")
    sys.exit(1)

try:
    with open(os.path.join(config_path, 'studies.json'), 'r') as json_file:
        studies: dict = json.load(json_file)

    with open(os.path.join(config_path, 'stations.json'), 'r') as json_file:
        stations: dict = json.load(json_file)

    with open(os.path.join(config_path, 'random.txt'), 'r') as file:
        RANDOM_UUID: str = file.read().replace('\n', '')

    with open(Path(INCOMING_DIR) / "task.json", "r") as json_file:
        task = json.load(json_file)
except FileNotFoundError:
    print("No studies.json, stations.json, random.txt and/or task.json found")
    sys.exit(1)

if task.get("process", False):
    settings = task["process"].get("settings", False)
    if settings:
        RANDOM_UUID = settings.get("RANDOM_UUID", RANDOM_UUID)
        studies.update(settings.get("studies", {}))
        stations.update(settings.get("stations", {}))

ORIGINAL_UUID = RANDOM_UUID
NOW = datetime.now()

series = {}
for entry in os.scandir(INCOMING_DIR):
    if entry.name.endswith(".dcm") and not entry.is_dir():
        # Get the Series UID from the file name
        seriesString = entry.name.split("#", 1)[0]
        # If this is the first image of the series, create new file list for the series
        if seriesString not in series.keys():
            series[seriesString] = []
        # Add the current file to the file list
        series[seriesString].append(entry.name)

if not series:
    print("No files found to be processed")
    sys.exit(0)


def get_key_types(studyinfo, action_type='value'):
    listOfKeys = list()
    listOfItems = studyinfo['AnonymizeTag'].items()
    for item in listOfItems:
        if item[1]['action'] == action_type:
            listOfKeys.append(item[0])

    return listOfKeys


def get_vr_action(vr):
    if vr in VRDefaults:
        return VRDefaults[vr].get('action', 'delete')
    # The default action is to keep the value
    return 'keep'


def get_tag_action(tag):
    if tag in TagDefaults:
        return TagDefaults[tag].get('action', 'delete')
    # The default action is to keep the value
    return 'keep'

for oldseriesuid in series:
    for filename in series[oldseriesuid]:
        # Make sure we have a valid DICOM
        try:
            dataset = pydicom.filereader.dcmread(f"{INCOMING_DIR}/{filename}")
        except InvalidDicomError:
            print("Error: " + filename +
                  " is missing DICOM File Meta Information header or the 'DICM' prefix is missing from the header.")
            continue

        # Find Station Name, each Station has different methods of encoding Study Names
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

        SAVED_TAGS = {}
        REMOVE_PRIVATE_TAGS = StudyInfo.get('RemovePrivateTags', True)
        SAVE_PRIVATE_TAGS = StudyInfo.get('SavePrivateTags', [])
        # If the Remove Private Tags flag is set
        if REMOVE_PRIVATE_TAGS:
            print("Removing Private Tags")
            # Preserve certain tags
            for tag in SAVE_PRIVATE_TAGS:
                print(f"Preserving Private Tag: {tag}")
                try:
                    SAVED_TAGS[tag] = dataset[tag]
                except KeyError:
                    print(f"Private Tag does not exist: {tag}")

            dataset.remove_private_tags()

            # Restore private tags
            for tag in SAVED_TAGS:
                dataset[tag] = SAVED_TAGS[tag]

        TagDefaults = StudyInfo['AnonymizeTag']
        VRDefaults = StudyInfo['AnonymizeVR']
        RANDOM_UUID = StudyInfo.get('RandomSeed', ORIGINAL_UUID)

        # Values should always be set
        tags_to_set = get_key_types(StudyInfo, 'value')
        for tag in tags_to_set:
            value = TagDefaults[tag].get('value', None)
            if value == "TMnow":
                value = time2str(NOW)
            elif value == "DAnow":
                value = date2str(NOW)
            elif value == "DTnow":
                value = datetime2str(NOW)

            # This apparently overwrites existing tags
            dataset.add_new(tag, dictionary_VR(tag), value)

        for data_entry in dataset.iterall():
            try:
                tag = pydicom.datadict.get_entry(data_entry.tag)[4]
            except KeyError:
                print(f"{data_entry.tag} -> keep (Invalid Tag)")
                continue

            # We can take action on the entire VR
            action = get_vr_action(data_entry.VR)
            # The tag action overrides VR
            action = get_tag_action(tag)
            print(f"{tag} -> {action}")

            if action == "keep":
                # Do nothing
                continue

            if action == "delete":
                try:
                    delattr(dataset, tag)
                except AttributeError:
                    print(f"{tag} no longer exists - parent deleted?")
                continue

            if action == "clear":
                data_entry.value = None
                continue

            if action == "hash":
                salt = TagDefaults[tag].get('salt', RANDOM_UUID)
                try:
                    data_entry.value = hashtext(dataset.data_element(tag).value, salt)
                except KeyError:
                    print(f"{tag} no longer exists - parent deleted?")
                continue

            if action == "offset":
                amount = TagDefaults[tag].get('delta', None)
                if not amount:
                    seed = TagDefaults[tag].get('seed', RANDOM_UUID)
                    # Do not use the value for offsetting as we want everything to be offset by the same value
                    random.seed(seed)
                    # 100 year variation should be sufficient
                    amount = random.randint(-1576800000, 1576800000)

                if data_entry.VR == "TM":
                    time = str2time(data_entry.value)
                    # List = h, m, s, ms
                    time = time + timedelta(seconds=amount)
                    data_entry.value = time2str(time)
                    continue

                if data_entry.VR == "DA":
                    time = str2date(data_entry.value)
                    # List = h, m, s, ms
                    time = time + timedelta(seconds=amount)
                    data_entry.value = date2str(time)
                    continue

                if data_entry.VR == "DT":
                    time = str2datetime(data_entry.value)
                    # List = h, m, s, ms
                    time = time + timedelta(seconds=amount)
                    data_entry.value = datetime2str(time)
                    continue

                print(f"{tag} -> Changed from {action} to keep (Error)")
                print(f"ERROR: Offsetting a {data_entry.VR} Not Implemented")
                continue

            if action == "regen":
                seed = TagDefaults[tag].get('seed', RANDOM_UUID)
                # Use the value as the seed as we are simply regenerating, not offsetting
                random.seed(seed + data_entry.value)
                # 100 year variation should be sufficient
                amount = random.randint(-1576800000, 1576800000)
                time = NOW + timedelta(seconds=amount)
                if data_entry.VR == "TM":
                    data_entry.value = time2str(time)
                elif data_entry.VR == "DA":
                    data_entry.value = date2str(time)
                elif data_entry.VR == "DT":
                    data_entry.value = datetime2str(time)
                else:
                    data_entry.value = regenuid(data_entry.value, seed)
                continue

            print(f"{tag} -> Changed from {action} to keep (Error)")
            print(f"ERROR: Action Not Implemented: {action}")

        # We need to always regen some File MetaData that is identifiable
        dataset.file_meta.MediaStorageSOPInstanceUID = regenuid(dataset.file_meta.MediaStorageSOPInstanceUID,
                                                                RANDOM_UUID)

        # By convention, DICOM files provided by
        # mercure have the format [series_UID]#[file_UID].dcm
        SeriesInstanceUID = str(dataset.data_element("SeriesInstanceUID").value)
        FileUID = dataset.file_meta.MediaStorageSOPInstanceUID
        newfilename = os.path.join(OUTGOING_DIR, f"{SeriesInstanceUID}#{FileUID}.dcm")
        dataset.save_as(newfilename)
