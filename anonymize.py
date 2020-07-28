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
import subprocess

import pydicom
from pydicom.data import get_testdata_files
from pydicom.errors import InvalidDicomError
from pydicom.uid import generate_uid

# Getting the current work directory (cwd)
indir = "./incoming/"
outdir = "./outgoing/"
filenames = []
# r=root, d=directories, f = files
for r, d, f in os.walk(indir):
    for file in f:
        filenames.append(os.path.join(r, file))

if not filenames:
    exit()

with open('studies.json', 'r') as json_file:
    studies = json.load(json_file)

with open('stations.json', 'r') as json_file:
    stations = json.load(json_file)

# You should change this seed for your environment
try:
    with open('random.txt', 'r') as file:
        data = file.read().replace('\n', '')
except FileNotFoundError:
    RANDOM_UUID = "be76acfcfdb04e64ba7525dbf745fe5f"

# If you want UUID's to be consistently translated, you may want to implement a lookup table
ORIGINAL_UUID = {}


def hashtext(text, salt):
    return hashlib.sha256(salt.encode() + text.encode()).hexdigest()


def regenuid(element):
    ORIGINAL_UUID[element] = ORIGINAL_UUID.get(element, generate_uid())
    return ORIGINAL_UUID[element]


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

    print("Processing: " + filename)
    print("Study: " + StudyName)

    if StudyInfo['RemovePrivateTags']:
        print("Removing Private Tags")
        dataset.remove_private_tags()

    TagDefs = StudyInfo['AnonymizeTag']
    VRDefs = StudyInfo['AnonymizeVR']
    for de in dataset.iterall():
        try:
            tag = pydicom.datadict.get_entry(de.tag)[4]
        except KeyError:
            print("Invalid DICOM Tag")
            continue

        if tag in TagDefs or de.VR in VRDefs:
            if tag in TagDefs:
                action = TagDefs[tag].get('action', 'delete')
            else:
                action = VRDefs[de.VR].get('action', 'delete')

            print("   " + tag + " -> " + action)
            if action == "delete":
                try:
                    delattr(dataset, tag)
                except AttributeError:
                    print("Parent Deleted: " + tag)
            elif action == "clear":
                de.value = None
            elif action == "hash":
                salt = TagDefs[tag].get('salt', RANDOM_UUID)
                de.value = hashtext(dataset.data_element(tag).value, salt)
            elif action == "value":
                de.value = TagDefs[tag].get('value', None)
            elif action == "offset":
                print("Offsetting a " + de.VR + " Type Not Implemented")
            elif action == "regen":
                de.value = regenuid(de.value)
            elif action == "keep":
                pass
            else:
                print("Tag Action Not Implemented")

    for de in dataset.iterall():
        print(de)

    # This is a prerequisite
    dataset.file_meta.MediaStorageSOPInstanceUID = regenuid(dataset.file_meta.MediaStorageSOPInstanceUID)

    i = 0
    while os.path.exists(os.path.join(outdir, "ANON%05d.DCM" % i)):
        i += 1
    dataset.save_as(os.path.join(outdir, "ANON%05d.DCM" % i))
    os.remove(filename)

# Call DCMSend to send the DICOM to our storage
process = subprocess.run(['/usr/bin/dcmsend',
                 '--aetitle ANONYMIZER',
                 '--call STORESCP',
                 '--scan-directories',
                 '127.0.0.1', '104',
                 outdir])

if process.returncode:
    exit(process.returncode)

for filename in os.listdir(outdir):
    file_path = os.path.join(outdir, filename)
    try:
        os.unlink(file_path)
    except Exception as e:
        print('Failed to delete %s. Reason: %s' % (file_path, e))
        exit(1)
